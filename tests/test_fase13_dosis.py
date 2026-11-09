"""Fase 13.6: calculadora de dosis del glosario (casos de Pediae)."""
from decimal import Decimal

from django.test import SimpleTestCase

from apps.clinica.dosis import calcular
from apps.clinica.models import Medicamento


def med(**kw):
    base = {'nombre': 'Amoxicilina', 'presentacion': 'susp. 250 mg/5 mL', 'modo': 'PESO', 'unidad_kg': 'mg',
            'rangos_edad': []}
    base.update(kw)
    return Medicamento(**base)


class DosisTest(SimpleTestCase):
    def test_por_peso_con_concentracion_a_ml(self):
        m = med(dosis_kg_min=Decimal('15'), concentracion_mg=Decimal('250'), volumen_ml=Decimal('5'),
                unidad_resultado='mL', frecuencia_horas=8, duracion_dias=7,
                indicaciones='{{DOSIS}} ({{DOSIS_MG}}) {{FRECUENCIA}} {{DURACION}}')
        r = calcular(m, peso_kg=12)
        self.assertEqual(r['dosis'], '3,6 mL')                  # 15 × 12 = 180 mg → 3,6 mL
        self.assertEqual(r['dosis_mg'], '180 mg')
        self.assertEqual(r['texto'], '3,6 mL (180 mg) cada 8 horas por 7 días')

    def test_rango_y_niveles(self):
        m = med(dosis_kg_min=Decimal('10'), dosis_kg_max=Decimal('15'), concentracion_mg=Decimal('160'),
                volumen_ml=Decimal('5'), unidad_resultado='mL')
        self.assertEqual(calcular(m, peso_kg=10, nivel='minimo')['dosis_mg'], '100 mg')
        self.assertEqual(calcular(m, peso_kg=10)['dosis_mg'], '125 mg')
        self.assertEqual(calcular(m, peso_kg=10, nivel='maximo')['dosis_mg'], '150 mg')

    def test_tope_absoluto(self):
        m = med(dosis_kg_min=Decimal('15'), concentracion_mg=Decimal('500'), unidad_resultado='tableta',
                dosis_max=Decimal('500'))
        r = calcular(m, peso_kg=60)                               # 900 mg → tope 500 → 1 tableta
        self.assertEqual(r['dosis'], '1 tableta(s)')
        self.assertTrue(any('tope' in a['msg'] for a in r['alertas']))

    def test_tabletas_a_media(self):
        m = med(dosis_kg_min=Decimal('10'), concentracion_mg=Decimal('500'), unidad_resultado='tableta')
        self.assertEqual(calcular(m, peso_kg=37)['dosis'], '0,5 tableta(s)')      # 370 mg → 0,74 → ½

    def test_unidad_directa(self):
        m = med(unidad_kg='gotas', dosis_kg_min=Decimal('1'))
        self.assertEqual(calcular(m, peso_kg=8.4)['dosis'], '8 gotas')

    def test_fija_y_por_edad(self):
        self.assertEqual(calcular(med(modo='FIJA', dosis_fija='2 puffs'))['dosis'], '2 puffs')
        m = med(modo='EDAD', rangos_edad=[{'min': 6, 'max': 23, 'dosis': '½ sobre'},
                                          {'min': 24, 'max': None, 'dosis': '1 sobre'}])
        self.assertEqual(calcular(m, edad_meses=12)['dosis'], '½ sobre')
        self.assertEqual(calcular(m, edad_meses=40)['dosis'], '1 sobre')
        r = calcular(m, edad_meses=3)
        self.assertEqual(r['dosis'], '')
        self.assertTrue(r['alertas'])

    def test_alertas_y_sin_peso(self):
        m = med(dosis_kg_min=Decimal('15'), edad_min_meses=24, peso_min_kg=Decimal('10'))
        r = calcular(m, peso_kg=8, edad_meses=12)
        self.assertEqual({a['tipo'] for a in r['alertas']} & {'danger', 'warning'}, {'danger', 'warning'})
        self.assertIn('Indica el peso', calcular(m)['alertas'][0]['msg'])

    def test_sin_concentracion_queda_en_mg(self):
        r = calcular(med(dosis_kg_min=Decimal('10')), peso_kg=10)
        self.assertEqual(r['dosis'], '100 mg')


class SoloIndicacionesTest(SimpleTestCase):
    """Medicamentos de Pediae sin dosis por kg, solo con texto: el texto va al récipe y no hay alerta."""

    def test_texto_sin_dosis(self):
        m = med(nombre='Solución nasal', presentacion='', indicaciones='{{NOMBRE}} 1 atomización cada 8 horas')
        r = calcular(m, peso_kg=12)
        self.assertFalse(r['calculada'])
        self.assertTrue(r['con_indicaciones'])
        self.assertEqual(r['texto'], 'Solución nasal 1 atomización cada 8 horas')
        self.assertEqual(r['alertas'], [])

    def test_sin_dosis_ni_texto_avisa(self):
        r = calcular(med(indicaciones=''), peso_kg=12)
        self.assertFalse(r['con_indicaciones'])
        self.assertTrue(r['alertas'])
