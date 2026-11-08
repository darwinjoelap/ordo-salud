"""Fase 18a: conversiones del importador de Pediae (datos ficticios; la importación completa se ensaya con el respaldo)."""
import tempfile

from django.core.management.base import CommandError
from django.test import SimpleTestCase

from apps.especialidades.pediatria.management.commands.importar_pediae import (
    Command,
    documento,
    opcion,
    si_no,
    tension,
    texto,
)


class ConversionesTest(SimpleTestCase):
    def test_documento(self):
        self.assertEqual(documento('V-12.345.678'), ('V', '12345678'))
        self.assertEqual(documento('v-9876543'), ('V', '9876543'))
        self.assertEqual(documento('E 81234567'), ('E', '81234567'))
        self.assertEqual(documento('12345678'), ('V', '12345678'))
        self.assertEqual(documento(''), ('', ''))
        self.assertEqual(documento(None), ('', ''))

    def test_tension(self):
        self.assertEqual(tension('100/60'), ('100', '60'))
        self.assertEqual(tension(' 90 / 55 '), ('90', '55'))
        self.assertEqual(tension('normal'), (None, None))
        self.assertEqual(tension(''), (None, None))

    def test_opcion_y_si_no(self):
        self.assertEqual(opcion('estreñimiento'), 'ESTRENIMIENTO')
        self.assertEqual(opcion('control sano'), 'CONTROL_SANO')
        self.assertIsNone(opcion(''))
        self.assertEqual(si_no(True), 'si')
        self.assertEqual(si_no(False), 'no')
        self.assertIsNone(si_no(None))

    def test_texto(self):
        self.assertEqual(texto('a', None, ' ', 'b'), 'a\nb')


class NombresCsvTest(SimpleTestCase):
    def _csv(self, contenido):
        with tempfile.NamedTemporaryFile('w', suffix='.csv', delete=False, encoding='utf-8-sig') as f:
            f.write(contenido)
        return f.name

    def test_lee_nombres_y_apellidos(self):
        ruta = self._csv('id_pediae;nombre_completo;nombres;apellidos;confianza\n'
                         '7;Ana Luisa Prueba Ficticia;Ana Luisa;Prueba Ficticia;ok\n')
        self.assertEqual(Command()._leer_nombres(ruta), {7: ('Ana Luisa', 'Prueba Ficticia')})

    def test_falta_nombre_detiene(self):
        ruta = self._csv('id_pediae;nombre_completo;nombres;apellidos\n8;Ficticio;;Ficticio\n')
        with self.assertRaises(CommandError):
            Command()._leer_nombres(ruta)
