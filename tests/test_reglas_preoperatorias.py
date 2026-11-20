"""Casos de referencia para las versiones clínicas documentadas."""
from decimal import Decimal

from django.test import SimpleTestCase
from django.utils import timezone

from apps.clinica import reglas_preoperatorias as reglas
from apps.clinica.escalas_preoperatorias import POR_CODIGO, EscalaForm


def formulario(codigo, **datos):
    return EscalaForm(POR_CODIGO[codigo], {f'{codigo}-{k}': str(v) for k, v in datos.items()})


def factores_rcri():
    return {'edad': 65, 'ambito': 'si', 'tipo_cirugia': 'no', 'isquemica': 'no', 'falla_cardiaca': 'no',
            'cerebrovascular': 'no', 'insulina': 'no', 'creatinina': '2,0', 'fecha': timezone.localdate()}


class ReglasPreoperatoriasTest(SimpleTestCase):
    def test_goldman_casos_historicos_y_fronteras(self):
        datos = {'edad': 70, 'infarto': 'no', 's3_yugular': 'no', 'estenosis': 'no', 'ritmo': 'no',
                 'ectopia': 5, 'estado_general': 'no', 'tipo_cirugia': 'no', 'emergencia': 'no'}
        resultado = reglas.goldman(datos)
        self.assertEqual((resultado.total, resultado.clase), (0, 'I'))
        resultado = reglas.goldman({**datos, 'edad': 71, 'infarto': 'reciente', 's3_yugular': 'si',
                                    'emergencia': 'si'})
        self.assertEqual((resultado.total, resultado.clase), (30, 'IV'))
        self.assertEqual(reglas.goldman({**datos, 'ectopia': 6}).puntos['ectopia'], 7)
        self.assertEqual(reglas.goldman({**datos, 'infarto': 'limite'}).estado, 'regla_pendiente')
        self.assertEqual(reglas.goldman({**datos, 'edad': 40}).estado, 'no_aplica')
        for positivos, total, clase in (
            ({'edad': 71}, 5, 'I'),
            ({'estenosis': 'si', 'estado_general': 'si'}, 6, 'II'),
            ({'edad': 71, 'ectopia': 6}, 12, 'II'),
            ({'infarto': 'reciente', 'estenosis': 'si'}, 13, 'III'),
            ({'s3_yugular': 'si', 'ectopia': 6, 'ritmo': 'si'}, 25, 'III'),
            ({'s3_yugular': 'si', 'infarto': 'reciente', 'edad': 71}, 26, 'IV'),
        ):
            with self.subTest(puntos=total):
                resultado = reglas.goldman({**datos, **positivos})
                self.assertEqual((resultado.total, resultado.clase), (total, clase))

    def test_detsky_dos_casos_publicados_y_limites_pendientes(self):
        datos = {'edad': 67, 'infarto': 'remoto', 'angina_ccs': 'IV', 'inestable': 'si', 'edema': 'no',
                 'estenosis': 'no', 'ritmo': 'no', 'ectopia_o_tv_fv': 'no', 'estado_general': 'no',
                 'emergencia': 'no'}
        resultado = reglas.detsky(datos)
        self.assertEqual((resultado.total, resultado.clase), (35, 'III'))
        segundo = {**datos, 'edad': 80, 'infarto': 'no', 'angina_ccs': 'no', 'inestable': 'no',
                   'ectopia_o_tv_fv': 'si'}
        resultado = reglas.detsky(segundo)
        self.assertEqual((resultado.total, resultado.clase), (10, 'I'))
        for limite in ({'edad': 70}, {'edema': 'limite'}, {'infarto': 'limite'}):
            resultado = reglas.detsky({**segundo, **limite})
            self.assertEqual(resultado.estado, 'regla_pendiente')
            self.assertIsNone(resultado.total)
        resultado = reglas.detsky({**segundo, 'edad': 69, 'inestable': 'si', 'edema': 'remoto'})
        self.assertEqual((resultado.total, resultado.clase), (20, 'II'))

    def test_ariscat_cortes_de_puntos_hemoglobina_oximetro_y_duracion(self):
        datos = {'edad': 60, 'spo2': 94, 'modo_spo2': 'aire_supino', 'infeccion': 'no',
                 'hb': Decimal('12'), 'incision': 'superior', 'duracion': 120, 'emergencia': 'no'}
        resultado = reglas.ariscat(datos)
        self.assertEqual((resultado.total, resultado.clase), (26, 'Intermedio'))
        alto = {**datos, 'edad': 61, 'hb': Decimal('10.00'), 'emergencia': 'si'}
        resultado = reglas.ariscat(alto)
        self.assertEqual((resultado.total, resultado.clase), (45, 'Alto'))
        self.assertEqual(reglas.ariscat({**alto, 'hb': Decimal('10.01')}).puntos['hb'], 0)
        for spo2, puntos in ((90, 24), (91, 8), (95, 8), (96, 0)):
            self.assertEqual(reglas.ariscat({**datos, 'spo2': spo2}).puntos['spo2'], puntos)
        for duracion, puntos in ((120, 0), (121, 16), (180, 16), (181, 23)):
            self.assertEqual(reglas.ariscat({**datos, 'duracion': duracion}).puntos['duracion'], puntos)
        self.assertEqual(reglas.ariscat({**datos, 'edad': 50, 'spo2': 96}).clase, 'Bajo')
        self.assertEqual(reglas.ariscat({**datos, 'modo_spo2': 'otras'}).estado, 'datos_insuficientes')

    def test_rcri_creatinina_exacta_y_casos_completos(self):
        datos = factores_rcri()
        resultado = formulario('rcri', **datos).calcular()
        self.assertEqual((resultado.total, resultado.clase), (0, 'I'))
        segundo = {**datos, 'edad': 72, 'tipo_cirugia': 'si', 'cerebrovascular': 'si', 'creatinina': '2.1'}
        resultado = formulario('rcri', **segundo).calcular()
        self.assertEqual((resultado.total, resultado.clase), (3, 'IV'))
        self.assertEqual(formulario('rcri', **{**datos, 'creatinina': '2.001'}).calcular().total, 1)
        self.assertEqual(formulario('rcri', **{**datos, 'edad': '49'}).calcular().estado, 'no_aplica')

    def test_formulario_ausencia_discordancia_y_ambito(self):
        datos = factores_rcri()
        for campos, estado in (
            ({'creatinina': ''}, 'datos_insuficientes'),
            ({'creatinina': '-2'}, 'datos_insuficientes'),
            ({'isquemica': 'discordante'}, 'contradiccion'),
            ({'ambito': 'no', 'creatinina': ''}, 'no_aplica'),
            ({'ambito': ''}, 'datos_insuficientes'),
            ({'fecha': ''}, 'datos_insuficientes'),
        ):
            with self.subTest(campos=campos):
                resultado = formulario('rcri', **{**datos, **campos}).calcular()
                self.assertEqual(resultado.estado, estado)
                self.assertIsNone(resultado.total)

    def test_caprini_combinaciones_verificadas_y_pendientes(self):
        datos = dict.fromkeys(reglas.CAPRINI_UN_PUNTO + reglas.CAPRINI_CINCO_PUNTOS, 'no')
        datos.update(edad=52, imc=27, duracion=60, artroplastias=0, movilidad='sin_restriccion',
                     enfermedades_pulmonares=0, canceres=0, inmovilizacion='no', acceso_central='no',
                     episodios_venosos=0, historia_familiar='no', marcadores=0, vih='no', aplica_reproductivo='no')
        self.assertEqual(reglas.caprini(datos).total, 4)
        artroplastia = {**datos, 'edad': 68, 'imc': 24, 'artroplastias': 1, 'duracion': 150, 'episodios_venosos': 1}
        resultado = reglas.caprini(artroplastia)
        self.assertEqual(resultado.total, 10)
        self.assertEqual(resultado.puntos['duracion'], 0)
        self.assertEqual(reglas.caprini({**artroplastia, 'artroplastias': 2}).total, 15)
        self.assertEqual(reglas.caprini({**datos, 'episodios_venosos': 2}).puntos['episodios_venosos'], 6)
        self.assertEqual(reglas.caprini({**datos, 'duracion': 45}).estado, 'regla_pendiente')
        self.assertEqual(reglas.caprini({**datos, 'vih': 'si'}).estado, 'regla_pendiente')
        self.assertEqual(reglas.caprini({**datos, 'fractura': 'si', 'trauma_grave': 'si'}).estado, 'regla_pendiente')
        self.assertEqual(reglas.caprini({**datos, 'embarazo_puerperio': 'si'}).estado, 'contradiccion')

    def test_dasi_vectores_numerados_y_redondeo(self):
        afirmativas = {1, 2, 4, 5, 7, 8, 9}
        resultado = reglas.dasi([i in afirmativas for i in range(1, 13)])
        self.assertEqual((resultado.total, resultado.clase), (Decimal('34.00'), '≤34 puntos'))
        self.assertEqual(tuple(v for _, v in resultado.derivados), ('24.22', '6.92'))
        resultado = reglas.dasi([True] * 12)
        self.assertEqual((resultado.total, resultado.clase), (Decimal('58.20'), '>34 puntos'))
        self.assertEqual(tuple(v for _, v in resultado.derivados), ('34.63', '9.89'))
        self.assertEqual(reglas.dasi([False] * 12).total, 0)
        self.assertEqual(reglas.dasi([True] * 11 + [None]).estado, 'datos_insuficientes')
