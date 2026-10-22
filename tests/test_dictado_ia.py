"""Dictado de toda la consulta con IA (ADR-045): permisos, minutos del plan, esquema, validación y llenado."""
import json
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings

from apps.clinica.models import Consulta, PlantillaHistoria
from apps.configuracion.models import ConfiguracionTenant
from apps.dictado import audio as conversor
from apps.dictado import proveedores, servicios
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
        with mock.patch('apps.dictado.proveedores.en_prueba', return_value=True), \
             mock.patch('apps.dictado.audio._ffmpeg', return_value=None):
            self.assertEqual(self.subir(segundos=150).status_code, 200)
            self.assertEqual(self.subir(segundos=60).status_code, 403)          # 2.5 + 1 > 3

    def test_esquema_y_llenado_validado(self):
        self.activar()
        resultado = proveedores.Resultado('texto dictado', json.loads(json.dumps(ENTRADA)), 9000, 1500,
                                          'gemini-3.8-flash', 'gemini-3.8-flash')
        with mock.patch('apps.dictado.proveedores.procesar_audio', return_value=resultado) as procesar:
            r = self.subir()
        self.assertEqual(r.json()['estado'], 'LISTO')
        sistema, herramienta = procesar.call_args[0][3], procesar.call_args[0][4]
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
        self.assertEqual((s.tokens_entrada, s.modelo_ia), (9000, 'gemini-3.8-flash'))
        # al guardar la consulta, la sesión queda vinculada
        self.cliente.post(f'/pacientes/{self.p.pk}/consultas/nueva/', {
            'completa': '1', 'tipo': 'PRIMERA', 'plantilla': self.plantilla.pk, 'accion': 'guardar',
            'dictado': s.pk})
        with self.en_tenant():
            self.assertEqual(SesionDictado.objects.get().consulta, Consulta.objects.latest('id'))

    def test_error_del_proveedor_no_cuelga(self):
        self.activar()
        from apps.dictado.proveedores import ErrorProveedor
        with mock.patch('apps.dictado.proveedores.procesar_audio', side_effect=ErrorProveedor('sin saldo')):
            r = self.subir()
        j = self.cliente.get(f"/dictado/{r.json()['id']}/").json()
        self.assertEqual((j['estado'], j['error']), ('ERROR', 'sin saldo'))
        self.assertEqual(servicios.minutos_usados(self.tenant), 0)              # un error no consume minutos

    def test_modo_prueba_sin_claves(self):
        self.activar()
        with self.settings(GEMINI_API_KEY=''):
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
        with self.settings(GEMINI_API_KEY=''):
            servicios.procesar(s.pk, b'audio', 'a.webm', 'audio/webm', estructura, 'cardiologia_pediatrica', 'Cardio')
        s.refresh_from_db()
        self.assertEqual(s.estado, 'LISTO')


    def test_grabacion_del_telefono_se_convierte_y_mide(self):
        """«Si se va la luz»: la doctora graba con el teléfono (.m4a) y lo sube después; se cobra la duración real."""
        import os
        import subprocess
        import tempfile
        ffmpeg = conversor._ffmpeg()
        if not ffmpeg:
            self.skipTest('sin ffmpeg')
        # Carpeta temporal (no NamedTemporaryFile): en Windows un archivo abierto no lo puede escribir ffmpeg.
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = os.path.join(carpeta, 'nota.m4a')
            subprocess.run([ffmpeg, '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=75', '-c:a', 'aac',
                            ruta], capture_output=True, check=True)
            with open(ruta, 'rb') as leido:
                datos = leido.read()
        mp3, tipo, segundos = conversor.convertir(datos, 'nota de voz.m4a', 'audio/x-m4a')
        self.assertEqual((tipo, segundos), ('audio/mp3', 75))
        self.assertLess(len(mp3), len(datos))
        self.activar()
        with self.settings(GEMINI_API_KEY=''):
            r = self.cliente.post('/dictado/', {
                'audio': SimpleUploadedFile('nota de voz.m4a', datos, content_type='audio/x-m4a'), 'segundos': 0,
                'origen': 'archivo', 'consentimiento': '1', 'paciente': self.p.pk, 'plantilla': self.plantilla.pk})
        with self.en_tenant():
            s = SesionDictado.objects.get(pk=r.json()['id'])
        self.assertEqual((s.origen, s.segundos), ('ARCHIVO', 75))           # el navegador no la supo: la mide ffmpeg
        self.assertEqual(self.cliente.post('/dictado/', {
            'audio': SimpleUploadedFile('foto.jpg', b'x', content_type='image/jpeg'), 'consentimiento': '1',
            'paciente': self.p.pk, 'plantilla': self.plantilla.pk}).status_code, 400)


class GeminiTest(SimpleTestCase):
    """La llamada a Gemini se arma y se lee bien (sin salir a internet)."""

    def respuesta(self, datos, estado=200, texto=''):
        r = mock.Mock(status_code=estado, text=texto or json.dumps(datos))
        r.json.return_value = datos
        return r

    @override_settings(GEMINI_API_KEY='clave', DICTADO_MODELO_GEMINI='gemini-3.8-flash', DICTADO_PROVEEDOR='gemini')
    def test_llamada_y_lectura(self):
        herramienta = servicios.herramienta([{'seccion_id': 7, 'codigo': 'cp.ekg', 'nombre': 'EKG', 'campos': [
            {'clave': 'fc', 'tipo': 'numero', 'etiqueta': 'FC', 'unidad': 'lpm'}]}])
        salida = {'transcripcion': 'EKG frecuencia 94', 'secciones': {'cp.ekg': {'fc': 94}}, 'no_ubicado': ''}
        ok = self.respuesta({'candidates': [{'content': {'parts': [{'text': 'pensando', 'thought': True},
                                                                   {'text': json.dumps(salida)}]}}],
                             'usageMetadata': {'promptTokenCount': 4000, 'candidatesTokenCount': 300,
                                               'thoughtsTokenCount': 200,
                                               'promptTokensDetails': [{'modality': 'AUDIO', 'tokenCount': 1920}]}})
        with mock.patch('apps.dictado.proveedores.requests.post', return_value=ok) as post:
            r = proveedores.procesar_audio(b'mp3', 'audio/mp3', 'TAPSE', 'sistema', herramienta)
        cuerpo = json.loads(post.call_args.kwargs['data'])
        self.assertIn('gemini-3.8-flash:generateContent', post.call_args.args[0])
        self.assertFalse(cuerpo['store'])                                     # Google no guarda la conversación
        self.assertEqual(cuerpo['contents'][0]['parts'][0]['inline_data']['mime_type'], 'audio/mp3')
        self.assertIn('transcripcion', cuerpo['generation_config']['response_json_schema']['required'])
        self.assertEqual(r.entrada['secciones']['cp.ekg']['fc'], 94)
        self.assertEqual((r.transcripcion, r.tokens_entrada, r.tokens_salida, r.segundos_audio),
                         ('EKG frecuencia 94', 4000, 500, 60))

    @override_settings(GEMINI_API_KEY='clave', DICTADO_PROVEEDOR='gemini')
    def test_si_no_admite_json_schema_usa_el_esquema_openapi(self):
        herramienta = servicios.herramienta([])
        malo = self.respuesta({}, 400, 'Unknown name "response_json_schema": schema not supported')
        vacio = '{"transcripcion": "", "secciones": {}}'
        bueno = self.respuesta({'candidates': [{'content': {'parts': [{'text': vacio}]}}]})
        with mock.patch('apps.dictado.proveedores.requests.post', side_effect=[malo, bueno]) as post:
            proveedores.procesar_audio(b'mp3', 'audio/mp3', '', 'sistema', herramienta)
        segundo = json.loads(post.call_args.kwargs['data'])['generation_config']
        self.assertIn('response_schema', segundo)
        self.assertNotIn('additionalProperties', json.dumps(segundo))

    @override_settings(GEMINI_API_KEY='clave', DICTADO_PROVEEDOR='gemini')
    def test_audio_grande_va_por_files_api_y_se_borra(self):
        inicio = mock.Mock(status_code=200, headers={'x-goog-upload-url': 'https://subida'})
        subida = self.respuesta({'file': {'name': 'files/abc', 'uri': 'https://archivo', 'state': 'ACTIVE'}})
        texto = '{"transcripcion": "x", "secciones": {}}'
        bueno = self.respuesta({'candidates': [{'content': {'parts': [{'text': texto}]}}]})
        with mock.patch('apps.dictado.proveedores.requests.post', side_effect=[inicio, subida, bueno]) as post, \
             mock.patch('apps.dictado.proveedores.requests.delete') as borrar:
            proveedores.procesar_audio(b'0' * (proveedores.MAX_INLINE + 1), 'audio/mp3', '', 's', servicios.herramienta([]))
        cuerpo = json.loads(post.call_args.kwargs['data'])
        self.assertEqual(cuerpo['contents'][0]['parts'][0]['file_data']['file_uri'], 'https://archivo')
        self.assertIn('files/abc', borrar.call_args.args[0])                  # no queda en Google
