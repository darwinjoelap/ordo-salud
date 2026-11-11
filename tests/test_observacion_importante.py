"""ADR-065: observación importante — en la consulta siguiente; fija, en todas hasta soltarla; solo médicos."""
from datetime import timedelta

from django.utils import timezone

from apps.clinica import observaciones
from apps.clinica.consultas import abrir_consulta
from apps.clinica.models import Consulta
from apps.core.permisos import Rol
from apps.equipo import servicios as equipo
from apps.equipo.models import Membresia
from apps.pacientes.models import Paciente
from apps.plataforma.models import Especialidad

from .base import BaseTest


class ObservacionImportanteTest(BaseTest):
    def setUp(self):
        super().setUp()
        actor = Membresia.objects.get(usuario=self.titular)
        self.perfil = actor.perfil
        esp = Especialidad.objects.get(codigo='medicina_general')
        self.m_doc, clave = equipo.agregar(self.tenant, actor, 'drdos', 'Luis', 'Mar', Rol.MEDICO, especialidad=esp)
        self.m_asis, clave_a = equipo.agregar(self.tenant, actor, 'recepcion', 'Ana', 'Gil', Rol.ASISTENTE)
        for m in (self.m_doc, self.m_asis):
            m.usuario.debe_cambiar_clave = False
            m.usuario.save()
        config = self.tenant.configuracion
        config.medicos_ven_todos_pacientes = True
        config.save()
        self.doc = self.entrar(self.tenant, 'drdos', clave)
        self.asis = self.entrar(self.tenant, 'recepcion', clave_a)
        with self.en_tenant():
            self.p = Paciente.objects.create(nombres='Rosa', apellidos='Paz', sexo='F')

    def consulta(self, dias_atras, texto='', fija=False):
        with self.en_tenant():
            c = abrir_consulta(paciente=self.p, profesional=self.perfil)
            Consulta.objects.filter(pk=c.pk).update(fecha_hora=timezone.now() - timedelta(days=dias_atras),
                                                    observacion_importante=texto, observacion_fija=fija)
            c.refresh_from_db()
            return c

    def test_se_guarda_desde_el_formulario(self):
        c = self.consulta(0)
        r = self.cliente.post(f'/consultas/{c.pk}/editar/', {'accion': 'guardar', 'observacion_importante': ' Ver hemato ',
                                                             'observacion_fija': 'on'})
        self.assertEqual(r.status_code, 302)
        c.refresh_from_db()
        self.assertEqual((c.observacion_importante, c.observacion_fija), ('Ver hemato', True))
        self.cliente.post(f'/consultas/{c.pk}/editar/', {'accion': 'guardar', 'observacion_importante': ''})
        c.refresh_from_db()
        self.assertEqual((c.observacion_importante, c.observacion_fija), ('', False))

    def test_solo_en_la_siguiente_y_fija_en_todas(self):
        self.consulta(30, 'Paciente prefiere llamada', fija=True)
        self.consulta(10, 'Revisar hematología')
        r = self.cliente.get(f'/pacientes/{self.p.pk}/consultas/nueva/')
        self.assertContains(r, 'Revisar hematología')
        self.assertContains(r, 'Paciente prefiere llamada')
        self.consulta(2)                                  # hubo otra consulta: la no fija ya no se muestra
        r = self.cliente.get(f'/pacientes/{self.p.pk}/consultas/nueva/')
        self.assertNotContains(r, 'Revisar hematología')
        self.assertContains(r, 'Paciente prefiere llamada')
        self.assertContains(self.cliente.get(f'/pacientes/{self.p.pk}/'), 'Paciente prefiere llamada')

    def test_ya_no_fijar(self):
        c = self.consulta(5, 'Fija', fija=True)
        r = self.doc.post(f'/consultas/{c.pk}/observacion/soltar/', {'volver': f'/pacientes/{self.p.pk}/'})
        self.assertRedirects(r, f'/pacientes/{self.p.pk}/', fetch_redirect_response=False)
        c.refresh_from_db()
        self.assertFalse(c.observacion_fija)

    def test_asistente_no_la_ve(self):
        self.consulta(5, 'Secreto clínico', fija=True)
        self.assertNotContains(self.asis.get(f'/pacientes/{self.p.pk}/'), 'Secreto clínico')
        with self.en_tenant():
            self.assertEqual(observaciones.para(self.m_asis, self.p), {'fijas': [], 'anterior': None})

    def test_solo_el_autor_si_la_configuracion_lo_pide(self):
        self.consulta(5, 'De la titular', fija=True)
        self.assertContains(self.doc.get(f'/pacientes/{self.p.pk}/'), 'De la titular')
        config = self.tenant.configuracion
        config.observaciones_visibles = 'AUTOR'
        config.save()
        self.assertNotContains(self.doc.get(f'/pacientes/{self.p.pk}/'), 'De la titular')
        self.assertContains(self.cliente.get(f'/pacientes/{self.p.pk}/'), 'De la titular')
