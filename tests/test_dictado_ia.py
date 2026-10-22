"""Dictado de toda la consulta con IA (ADR-045): permisos, minutos del plan, esquema, validación y llenado."""
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from apps.clinica.models import Consulta, PlantillaHistoria
from apps.configuracion.models import ConfiguracionTenant
from apps.dictado import servicios
from apps.dictado.models import SesionDictado
from apps.pacientes.models import Paciente
from apps.plataforma.models import Plan

from .base import BaseTest, crear_consultorio

ENTRADA = {'secciones': {
    'nucleo.signos_vitales': {'fc': 103, 'spo2': 97, 'pa_sistolica': 105, 'pa_diastolica': 60, 'peso_kg': 21.1,
                              'talla_cm': 121},
    'cp.ekg': {'ritmo': 'RS', 'fc': 94, 'pr': 0.12, 'qt': 0.34, 'trazo': 'HVD'},
    'cp.eco': {'tia': 'DEFECTO', 'cia_tipo': 'OS', 'qpqs': 2.5, 'situs': 'NO_EXISTE', 'fevi': '74 %',
               'pulm_z': -50},
    'nucleo.diagnosticos': {'diagnosticos': [{'codigo': 'Q21.1', 'descripcion': 'CIA ostium secundum'}]},
    'nucleo.plan': {'plan': 'Se inicia tratamiento. Se revalorará en 4 meses.'}},
    'no_ubicado': 'La mamá trae un Holter de otra institución.'}


def audio():
    return SimpleUploadedFile('dictado.webm', b'\x1aE\xdf\xa3audio-falso', content_type='audio/webm')


@override_settings(DICTADO_SINCRONO=True)
class DictadoTest(BaseTest):
    def setUp(self):
        self.tenant, self.titular = crear_consultorio('Cardio', 'cardio2', especialidad='cardiologia_pediatrica')
        self.cliente = self.entrar(self.tenant, 'titular')
        with self.en_tenant():
            self.p = Paciente.objects.create(nombres='Ana', apellidos='Ruiz', sexo='F')
            self.plantilla = PlantillaHistoria.objects.get(nombre='Consulta de cardiología pediátrica')

    def activar(self, minutos=0):
        ConfiguracionTenant.objects.filter(tenant=self.tenant).update(dictado_activo=True)
        plan = Plan.objects.create(nombre='Con dictado', incluye_dictado=True, minutos_dictado_mes=minutos)
        self.tenant.plan = plan
        self.tenant.save(update_fields=['plan'])

    def subir(self, segundos=120, **extra):
        return self.cliente.post('/dictado/', {'audio': audio(), 'segundos': segundos, 'consentimiento': '1',
                                                'paciente': self.p.pk, 'plantilla': self.plantilla.pk, **extra})

    def test_inactivo_o_sin_consentimiento_no_dicta(self):
        self.assertEqual(self.subir().status_code, 403)
        self.assertNotContains(self.cliente.get(f'/pacientes/{self.p.pk}/consultas/nueva/'), 'Dictar consulta')
        self.activar()
        self.assertContains(self.cliente.get(f'/pacientes/{self.p.pk}/consultas/nueva/'), 'Dictar consulta')
        r = self.cliente.post('/dictado/', {'audio': audio(), 'segundos': 10, 'paciente': self.p.pk,
                                            'plantilla': self.plantilla.pk})
        self.assertEqual(r.status_code, 400)

    def test_minutos_del_plan(self):
        self.activar(minutos=3)
        with mock.patch('apps.dictado.proveedores.en_prueba', return_value=True):
            self.assertEqual(self.subir(segundos=150).status_code, 200)
            self.assertEqual(self.subir(segundos=60).status_code, 403)          # 2.5 + 1 > 3

    def test_esquema_y_llenado_validado(self):
        self.activar()
        with mock.patch('apps.dictado.proveedores.transcribir', return_value=('texto dictado', 'gpt-4o-transcribe')), \
             mock.patch('apps.dictado.proveedores.ordenar', return_value=(ENTRADA, 9000, 1500, 'claude-sonnet-5-5')) \
                as ordenar:
            r = self.subir()
        self.assertEqual(r.json()['estado'], 'LISTO')
        sistema, herramienta = ordenar.call_args[0][1], ordenar.call_args[0][2]
        self.assertNotIn('Ana', sistema)                                       # sin nombre del paciente
        eco = herramienta['input_schema']['properties']['secciones']['properties']['cp.eco']['properties']
        self.assertIn('OS', eco['cia_tipo']['enum'])
        self.assertNotIn('texto_informe', eco)                                  # los calculados no se piden
        j = self.cliente.get(f"/dictado/{r.json()['id']}/").json()
        campos = {(c['prefijo'], c['clave']): c['valor'] for c in j['resultado']['campos']}
        self.assertIn(94, campos.values())
        self.assertEqual(j['resultado']['tablas'][0]['filas'][0]['codigo'], 'Q21.1')
        self.assertIn('Holter', j['no_ubicado'])
        self.assertIn('NO_EXISTE', j['no_ubicado'])                            # opción inválida → a revisar
        self.assertIn('-50', j['no_ubicado'])                                  # fuera de rango → a revisar
        with self.en_tenant():
            s = SesionDictado.objects.get()
        self.assertEqual((s.tokens_entrada, s.modelo_ia), (9000, 'claude-sonnet-5-5'))
        # al guardar la consulta, la sesión queda vinculada
        self.cliente.post(f'/pacientes/{self.p.pk}/consultas/nueva/', {
            'completa': '1', 'tipo': 'PRIMERA', 'plantilla': self.plantilla.pk, 'accion': 'guardar',
            'dictado': s.pk})
        with self.en_tenant():
            self.assertEqual(SesionDictado.objects.get().consulta, Consulta.objects.latest('id'))

    def test_error_del_proveedor_no_cuelga(self):
        self.activar()
        from apps.dictado.proveedores import ErrorProveedor
        with mock.patch('apps.dictado.proveedores.transcribir', side_effect=ErrorProveedor('sin saldo')):
            r = self.subir()
        j = self.cliente.get(f"/dictado/{r.json()['id']}/").json()
        self.assertEqual((j['estado'], j['error']), ('ERROR', 'sin saldo'))
        self.assertEqual(servicios.minutos_usados(self.tenant), 0)              # un error no consume minutos

    def test_modo_prueba_sin_claves(self):
        self.activar()
        with self.settings(OPENAI_API_KEY='', ANTHROPIC_API_KEY=''):
            r = self.subir()
        j = self.cliente.get(f"/dictado/{r.json()['id']}/").json()
        self.assertTrue(j['prueba'])
        self.assertIn('Modo de prueba', j['no_ubicado'])

    def test_procesar_fuera_del_request_sin_tenant_activo(self):
        """En producción corre en un hilo sin consultorio activo: debe encontrar la sesión igual."""
        self.activar()
        with self.en_tenant():
            s = SesionDictado.objects.create(paciente=self.p, profesional=self.titular.membresias.first().perfil,
                                             plantilla=self.plantilla, segundos=30, consentimiento=True)
            from apps.clinica.consultas import congelar_estructura
            estructura = congelar_estructura(self.plantilla)
        with self.settings(OPENAI_API_KEY='', ANTHROPIC_API_KEY=''):
            servicios.procesar(s.pk, b'audio', 'a.webm', 'audio/webm', estructura, 'cardiologia_pediatrica', 'Cardio')
        s.refresh_from_db()
        self.assertEqual(s.estado, 'LISTO')
