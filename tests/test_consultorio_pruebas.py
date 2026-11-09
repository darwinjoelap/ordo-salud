"""Consultorio de pruebas: se crea, se le agrega un médico por especialidad y carga casos ficticios sin duplicar."""
import io

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.core.tenancy import usando_tenant
from apps.pacientes.models import Paciente
from apps.plataforma.models import Tenant


class ConsultorioPruebasTest(TestCase):
    def cmd(self, *args):
        call_command('consultorio_pruebas', *args, stdout=io.StringIO())

    def test_ciclo_completo(self):
        self.cmd('--crear', '--clave', 'Clave-larga-123')
        self.cmd('--medico', 'pediatria', '--usuario', 'pediatra', '--clave', 'Clave-larga-123')
        tenant = Tenant.objects.get(slug='pruebas')
        with usando_tenant(tenant):
            demo = Paciente.objects.filter(observaciones__startswith='[DEMO]')
            n = demo.count()
            self.assertGreaterEqual(n, 12)
            self.cmd('--escenarios', 'pediatria')                 # no duplica
            self.assertEqual(demo.count(), n)
            self.cmd('--borrar')
            self.assertEqual(demo.count(), 0)

    def test_especialidad_sin_paquete_solo_agrega_medico(self):
        self.cmd('--crear', '--clave', 'Clave-larga-123')
        self.cmd('--medico', 'dermatologia', '--usuario', 'derma', '--clave', 'Clave-larga-123')
        with self.assertRaises(CommandError):
            self.cmd('--escenarios', 'dermatologia')

    def test_medicina_interna(self):
        self.cmd('--crear', '--clave', 'Clave-larga-123')
        self.cmd('--medico', 'medicina_interna', '--usuario', 'agonzalez', '--clave', 'Clave-larga-123')
        from apps.usuarios.models import Usuario
        u = Usuario.objects.get(username='agonzalez')
        self.assertEqual((u.first_name, u.last_name), ('Alí', 'González'))
        with usando_tenant(Tenant.objects.get(slug='pruebas')):
            self.assertGreaterEqual(Paciente.objects.filter(observaciones__startswith='[DEMO]').count(), 10)
