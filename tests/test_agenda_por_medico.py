"""ADR-064: el médico que no ve todos los pacientes tampoco ve las agendas de los demás (misma opción)."""
from datetime import time, timedelta

from django.utils import timezone

from apps.agenda.models import Bloqueo, Cita
from apps.core.permisos import Rol
from apps.equipo import servicios as equipo
from apps.equipo.models import Membresia
from apps.pacientes.models import Paciente
from apps.plataforma.models import Especialidad

from .base import BaseTest


class AgendaPorMedicoTest(BaseTest):
    def setUp(self):
        super().setUp()
        esp = Especialidad.objects.get(codigo='medicina_general')
        actor = Membresia.objects.get(usuario=self.titular)
        self.titular_perfil = actor.perfil
        self.m_medico, clave = equipo.agregar(self.tenant, actor, 'drdos', 'Luis', 'Mar', Rol.MEDICO, especialidad=esp)
        self.m_medico.usuario.debe_cambiar_clave = False
        self.m_medico.usuario.save()
        self.medico = self.entrar(self.tenant, 'drdos', clave)
        hoy = timezone.localdate()
        with self.en_tenant():
            p1 = Paciente.objects.create(nombres='Rosa', apellidos='Propia', sexo='F')
            p2 = Paciente.objects.create(nombres='Juan', apellidos='Ajeno', sexo='M')
            self.mia = Cita.objects.create(paciente=p1, profesional=self.m_medico.perfil, especialidad=esp,
                                           fecha=hoy, hora_inicio=time(9), hora_fin=time(9, 30))
            self.ajena = Cita.objects.create(paciente=p2, profesional=self.titular_perfil, especialidad=esp,
                                             fecha=hoy, hora_inicio=time(10), hora_fin=time(10, 30))
            self.bloqueo_ajeno = Bloqueo.objects.create(profesional=self.titular_perfil, motivo='Congreso',
                                                        desde=timezone.now(), hasta=timezone.now() + timedelta(days=1))

    def abrir_agendas(self):
        config = self.tenant.configuracion
        config.medicos_ven_todos_pacientes = True
        config.save()

    def test_medico_ve_solo_su_agenda_aunque_pida_todos(self):
        for url in ('/agenda/', '/agenda/?p=todos', f'/agenda/?p={self.titular_perfil.pk}', '/agenda/semana/?p=todos'):
            r = self.medico.get(url)
            self.assertContains(r, 'Propia', msg_prefix=url)
            self.assertNotContains(r, 'Ajeno', msg_prefix=url)
        self.assertEqual(self.medico.get('/agenda/').context['profesionales'], [self.m_medico.perfil])

    def test_cita_ajena_da_404(self):
        self.assertEqual(self.medico.get(f'/agenda/citas/{self.mia.pk}/').status_code, 200)
        for url in (f'/agenda/citas/{self.ajena.pk}/', f'/agenda/citas/{self.ajena.pk}/editar/'):
            self.assertEqual(self.medico.get(url).status_code, 404, url)
        r = self.medico.post(f'/agenda/citas/{self.ajena.pk}/estado/', {'estado': 'CANCELADA'})
        self.assertEqual(r.status_code, 404)
        r = self.medico.post(f'/agenda/bloqueos/{self.bloqueo_ajeno.pk}/eliminar/')
        self.assertEqual(r.status_code, 404)

    def test_nueva_cita_solo_para_si(self):
        form = self.medico.get(f'/agenda/citas/nueva/?p={self.titular_perfil.pk}').context['form']
        self.assertEqual(list(form.fields['profesional'].queryset), [self.m_medico.perfil])
        self.assertEqual(form['profesional'].value(), self.m_medico.perfil.pk)

    def test_titular_ve_todo(self):
        r = self.cliente.get('/agenda/?p=todos')
        self.assertContains(r, 'Propia')
        self.assertContains(r, 'Ajeno')

    def test_con_la_opcion_activa_el_medico_ve_todas(self):
        self.abrir_agendas()
        r = self.medico.get('/agenda/?p=todos')
        self.assertContains(r, 'Ajeno')
        self.assertEqual(self.medico.get(f'/agenda/citas/{self.ajena.pk}/').status_code, 200)
