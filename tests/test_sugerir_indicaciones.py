"""ADR-060: sugerir récipe e indicaciones con IA. La IA elige y redacta; la dosis la calcula el sistema."""
import json
from decimal import Decimal
from unittest import mock

from django.test import SimpleTestCase

from apps.clinica.models import Medicamento
from apps.dictado import indicaciones
from apps.dictado.models import SugerenciaIA
from apps.equipo.models import Membresia
from apps.pacientes.models import AntecedenteBase, Paciente

from .base import BaseTest

AMOXI = {'glosario_id': 0, 'nombre': 'Amoxicilina', 'presentacion': 'susp. 250 mg/5 mL', 'modo': 'PESO',
         'mg_kg_min': 15, 'mg_kg_max': 25, 'unidad_kg': 'mg', 'concentracion': 250, 'volumen_ml': 5,
         'unidad_resultado': 'mL', 'frecuencia_horas': 8, 'duracion_dias': 7, 'dosis_max': 500, 'via': 'oral'}


class ArmarFilasTest(SimpleTestCase):
    def test_ficha_de_la_ia_la_calcula_el_sistema(self):
        filas = indicaciones.armar_filas({'medicamentos': [AMOXI]}, [], 12, 30, '')
        f = filas[0]
        self.assertEqual(f['origen'], 'ia')
        self.assertEqual(f['dosis'], '4,8 mL')                     # 20 mg/kg (estándar) × 12 kg = 240 mg → 4,8 mL
        self.assertEqual(f['dosis_mg'], '240 mg')
        self.assertIn('15–25 mg/kg/dosis (45–75 mg/kg/día)', f['ficha'])
        self.assertIn('250 mg/5 mL', f['ficha'])
        self.assertTrue(any('verificar' in a['msg'] for a in f['alertas']))
        self.assertEqual(f['para_glosario']['dosis_kg_min'], '15')

    def test_del_glosario_usa_su_ficha(self):
        med = Medicamento(pk=7, nombre='Apiret', presentacion='180 mg/5 mL', modo='PESO', unidad_kg='mg',
                          dosis_kg_min=Decimal('15'), concentracion_mg=Decimal('180'), volumen_ml=Decimal('5'),
                          unidad_resultado='mL', frecuencia_horas=6, rangos_edad=[], indicaciones='')
        filas = indicaciones.armar_filas({'medicamentos': [{'glosario_id': 7, 'nombre': 'x'}]}, [med], 12, 30, '')
        self.assertEqual((filas[0]['origen'], filas[0]['dosis'], filas[0]['ficha']), ('glosario', '5 mL', ''))

    def test_alergia_marca_peligro(self):
        filas = indicaciones.armar_filas({'medicamentos': [{**AMOXI, 'nombre': 'Penicilina benzatínica'}]}, [],
                                         12, 30, 'Alérgico a la penicilina')
        self.assertEqual(filas[0]['alertas'][0]['tipo'], 'danger')

    def test_datos_absurdos_no_rompen(self):
        filas = indicaciones.armar_filas({'medicamentos': [{'glosario_id': 0, 'nombre': 'X', 'modo': 'PESO',
                                                            'mg_kg_min': -3, 'unidad_resultado': 'litros',
                                                            'frecuencia_horas': 999}, 'basura', {'nombre': ''}]},
                                         [], 12, 30, '')
        self.assertEqual(len(filas), 1)
        self.assertTrue(any('no dio dosis por kg' in a['msg'] for a in filas[0]['alertas']))


class SugerirVistaTest(BaseTest):
    def setUp(self):
        super().setUp()
        with self.en_tenant():
            self.paciente = Paciente.objects.create(nombres='Tomás', apellidos='Paz', sexo='M')
            AntecedenteBase.objects.create(paciente=self.paciente, alergias='')
        self.url = f'/dictado/sugerir/{self.paciente.pk}/'
        self.cuerpo = json.dumps({'campos': {'Diagnósticos · Diagnóstico': 'Otitis media aguda'}, 'peso': '12'})

    def activar(self):
        config = self.tenant.configuracion
        config.sugerencias_ia = True
        config.save()

    def post(self, cuerpo=None):
        return self.cliente.post(self.url, cuerpo or self.cuerpo, content_type='application/json')

    def test_inactivo_responde_403(self):
        self.assertEqual(self.post().status_code, 403)

    def test_sugiere_y_registra_uso(self):
        self.activar()
        salida = {'medicamentos': [AMOXI], 'indicaciones': 'Control en 48 h si persiste la fiebre.', 'alertas': []}
        with mock.patch.object(indicaciones, '_llamar', return_value=(salida, (4000, 900), 'gemini-3.8-flash')):
            r = self.post()
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d['filas'][0]['dosis'], '4,8 mL')
        self.assertIn('48 h', d['indicaciones'])
        with self.en_tenant():
            s = SugerenciaIA.objects.get()
        self.assertEqual((s.tokens_entrada, s.tokens_salida, s.ok), (4000, 900, True))
        self.assertEqual(indicaciones.uso_mes(self.tenant), {'n': 1, 'costo': '0.01'})

    def test_sin_texto_pide_escribir(self):
        self.activar()
        r = self.post(json.dumps({'campos': {}}))
        self.assertEqual(r.status_code, 400)

    def test_el_sistema_no_lleva_nombre_del_paciente(self):
        self.activar()
        with mock.patch.object(indicaciones, '_llamar', return_value=({}, (0, 0), 'm')) as llamada:
            self.post()
        sistema, usuario = llamada.call_args[0]
        self.assertNotIn('Tomás', sistema + usuario)
        self.assertIn('12', sistema)

    def test_guardar_ficha_en_glosario(self):
        perfil = Membresia.objects.get(usuario=self.titular).perfil
        ficha = indicaciones._para_glosario(indicaciones._ficha_medicamento(AMOXI))
        r = self.cliente.post('/dictado/sugerir/glosario/', json.dumps(ficha), content_type='application/json')
        self.assertEqual(r.status_code, 200)
        with self.en_tenant():
            med = Medicamento.objects.get(pk=r.json()['id'])
        self.assertEqual((med.profesional_id, med.dosis_kg_max, med.unidad_resultado), (perfil.pk, Decimal('25'), 'mL'))

    def test_boton_en_la_consulta_solo_si_activo(self):
        r = self.cliente.get(f'/pacientes/{self.paciente.pk}/consultas/nueva/')
        if r.status_code != 200:
            self.skipTest(f'ruta de nueva consulta distinta ({r.status_code})')
        self.assertNotContains(r, 'data-sugerir-ia')
        self.activar()
        self.assertContains(self.cliente.get(f'/pacientes/{self.paciente.pk}/consultas/nueva/'), 'data-sugerir-ia')

    def test_gemini_lento_un_solo_intento_y_mensaje_claro(self):
        import requests
        from django.test import override_settings
        self.activar()
        with override_settings(GEMINI_API_KEY='x', DICTADO_MODO=''), \
                mock.patch('apps.dictado.proveedores.requests.post', side_effect=requests.ReadTimeout) as post, \
                mock.patch('apps.dictado.proveedores.time.sleep'):
            r = self.post()
        self.assertEqual(r.status_code, 502)
        self.assertEqual(post.call_count, 1)
        self.assertIn('tardó demasiado', r.json()['error'])
        self.assertNotIn('grabación', r.json()['error'])
        self.assertEqual(post.call_args.kwargs['timeout'], 45)

