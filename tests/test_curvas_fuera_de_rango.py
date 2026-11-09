"""Fix 2026-11-09 (500 en la ficha): mediciones fuera del rango de la tabla OMS de un indicador."""
from django.test import SimpleTestCase

from apps.especialidades.pediatria import curvas


class CurvasFueraDeRangoTest(SimpleTestCase):
    def test_ninguna_edad_rompe_el_grafico(self):
        for ind in ('peso', 'talla', 'imc', 'pc'):
            for sexo in ('M', 'F'):
                for meses in range(0, 240):
                    with self.subTest(ind=ind, sexo=sexo, meses=meses):
                        curvas.geometria(ind, sexo, [(0.0, 3.2, None, 'Nacimiento'), (float(meses), 30.0, None, 'x')])
                        curvas.geometria(ind, sexo, [(float(meses), 30.0, None, 'x')])

    def test_fuera_de_la_tabla_no_se_dibuja(self):
        self.assertIsNone(curvas.geometria('peso', 'M', [(144.0, 38.0, None, 'x')]))     # peso/edad OMS: hasta 10 años
        self.assertIsNotNone(curvas.geometria('imc', 'M', [(144.0, 18.0, None, 'x')]))   # IMC/edad: hasta 19 años
