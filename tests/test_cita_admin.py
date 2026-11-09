"""Fix 2026-11-09: el titular administrador (sin perfil de médico) agenda en un consultorio con UN solo médico."""
from apps.core.permisos import Rol
from apps.equipo import servicios as equipo
from apps.equipo.models import Membresia
from apps.pacientes.models import Paciente
from apps.plataforma.models import Especialidad

from .base import BaseTest, crear_consultorio


class CitaDesdeAdministradorTest(BaseTest):
    def setUp(self):
        self.tenant, self.titular = crear_consultorio('Admin', 'admin-c', profesional=False)
        actor = Membresia.objects.get(usuario=self.titular)
        esp = Especialidad.objects.get(codigo='medicina_general')
        self.medico, _ = equipo.agregar(self.tenant, actor, 'doc', 'Ana', 'Gil', Rol.MEDICO, especialidad=esp)
        self.cliente = self.entrar(self.tenant, 'titular')
        with self.en_tenant():
            self.paciente = Paciente.objects.create(nombres='Rosa', apellidos='Paz', sexo='F')

    def test_el_profesional_oculto_viene_lleno(self):
        r = self.cliente.get('/agenda/citas/nueva/')
        form = r.context['form']
        self.assertTrue(form.solo_un_profesional)
        self.assertEqual(form['profesional'].value(), self.medico.perfil.pk)
        self.assertContains(r, f'<option value="{self.medico.perfil.pk}" selected>')
