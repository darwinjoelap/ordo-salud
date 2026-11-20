"""Fase 08: agenda multi-profesional."""
from datetime import datetime, time, timedelta

from django.utils import timezone

from apps.agenda import servicios as srv
from apps.agenda.models import Bloqueo, Cita, HorarioAtencion, TipoCita
from apps.clinica.models import Consulta
from apps.core.excepciones import ErrorDeNegocio
from apps.core.permisos import Rol
from apps.equipo import servicios as equipo
from apps.equipo.models import Membresia
from apps.pacientes.models import Paciente, Representante
from apps.plataforma.models import Especialidad

from .base import BaseTest


class AgendaTest(BaseTest):
    def setUp(self):
        super().setUp()
        self.manana = timezone.localdate() + timedelta(days=1)
        with self.en_tenant():
            self.perfil = Membresia.objects.get(usuario=self.titular).perfil
            self.paciente = Paciente.objects.create(nombres='Elena', apellidos='Paz', sexo='F', telefono='04141112233')
            self.otro = Paciente.objects.create(nombres='Raúl', apellidos='Paz', sexo='M')

    def nueva(self, paciente=None, hora='09:00', **extra):
        datos = {'paciente': (paciente or self.paciente).pk, 'profesional': self.perfil.pk,
                 'fecha': self.manana.isoformat(), 'hora_inicio': hora, 'motivo': 'Control'}
        datos.update(extra)
        return self.cliente.post('/agenda/citas/nueva/', datos)

    def test_crear_cita_calcula_fin(self):
        r = self.nueva()
        self.assertEqual(r.status_code, 302)
        with self.en_tenant():
            c = Cita.objects.get()
            self.assertEqual(c.hora_fin, time(9, 30))
            self.assertEqual(c.especialidad, self.perfil.especialidad)
            self.assertEqual(c.estado, Cita.Estado.PROGRAMADA)

    def test_solapamiento_y_sobrecupo(self):
        self.nueva()
        r = self.nueva(self.otro, '09:15')
        self.assertContains(r, 'ya tiene cita a esa hora')
        r = self.nueva(self.otro, '09:15', sobrecupo='on')
        self.assertEqual(r.status_code, 302)
        with self.en_tenant():
            self.assertTrue(Cita.objects.get(paciente=self.otro).sobrecupo)

    def test_cita_cancelada_libera_el_horario(self):
        self.nueva()
        with self.en_tenant():
            srv.cambiar_estado(Cita.objects.get(), 'CANCELADA', 'Viaje')
        self.assertEqual(self.nueva(self.otro, '09:00').status_code, 302)

    def test_sin_hora_es_tentativa(self):
        self.nueva(hora='')
        with self.en_tenant():
            self.assertEqual(Cita.objects.get().estado, Cita.Estado.TENTATIVA)

    def test_bloqueo_impide_agendar(self):
        with self.en_tenant():
            inicio = timezone.make_aware(datetime.combine(self.manana, time(8, 0)))
            Bloqueo.objects.create(desde=inicio, hasta=inicio + timedelta(hours=4), motivo='Congreso')
        self.assertContains(self.nueva(), 'Congreso')

    def test_transicion_invalida(self):
        self.nueva()
        with self.en_tenant():
            c = Cita.objects.get()
            srv.cambiar_estado(c, 'CANCELADA')
            with self.assertRaises(ErrorDeNegocio):
                srv.cambiar_estado(c, 'EN_SALA')

    def test_turnos_libres_segun_horario(self):
        with self.en_tenant():
            HorarioAtencion.objects.create(profesional=self.perfil, dia_semana=self.manana.weekday(),
                                           hora_inicio=time(8, 0), hora_fin=time(10, 0), duracion_turno_min=30)
        self.nueva(hora='08:30')
        with self.en_tenant():
            libres = [h for h, _ in srv.turnos_libres(self.perfil, self.manana)]
        self.assertEqual(libres, [time(8, 0), time(9, 0), time(9, 30)])
        r = self.cliente.get(f'/agenda/?fecha={self.manana.isoformat()}')
        self.assertContains(r, '9:30 a. m.')

    def test_aviso_fuera_de_horario(self):
        with self.en_tenant():
            HorarioAtencion.objects.create(profesional=self.perfil, dia_semana=self.manana.weekday(),
                                           hora_inicio=time(8, 0), hora_fin=time(12, 0))
        r = self.nueva(hora='15:00')
        self.assertEqual(r.status_code, 302)
        self.assertIn('fuera del horario', str([m.message for m in r.wsgi_request._messages]))

    def test_atender_abre_consulta_con_plantilla_del_tipo(self):
        with self.en_tenant():
            from apps.clinica.models import PlantillaHistoria
            control = PlantillaHistoria.objects.get(nombre='Control')
            tipo = TipoCita.objects.get(nombre='Control')
            tipo.duracion_min = 20
            tipo.tipo_consulta = 'CONTROL'
            tipo.plantilla = control
            tipo.save()
        self.nueva(tipo=tipo.pk)
        with self.en_tenant():
            c = Cita.objects.get()
            self.assertEqual(c.hora_fin, time(9, 20))
        r = self.cliente.post(f'/agenda/citas/{c.pk}/atender/')
        with self.en_tenant():
            consulta = Consulta.objects.get()
            c.refresh_from_db()
        self.assertRedirects(r, f'/consultas/{consulta.pk}/editar/', fetch_redirect_response=False)
        self.assertEqual(consulta.plantilla, control)
        self.assertEqual(consulta.tipo, 'CONTROL')
        self.assertEqual(c.estado, Cita.Estado.ATENDIDA)
        self.assertEqual(c.consulta, consulta)

    def test_whatsapp_a_representante_de_menor(self):
        with self.en_tenant():
            nino = Paciente.objects.create(nombres='Tomás', apellidos='Paz', sexo='M',
                                           fecha_nacimiento=timezone.localdate() - timedelta(days=700))
            Representante.objects.create(paciente=nino, nombre='Elena Paz', telefono='0424-555 66 77')
        self.nueva(nino)
        with self.en_tenant():
            url = srv.url_whatsapp(Cita.objects.get())
        self.assertTrue(url.startswith('https://wa.me/584245556677?text=Hola%20Elena'))
        self.assertIn('Tom%C3%A1s', url)

    def test_asistente_agenda_para_otro_medico_pero_no_atiende(self):
        actor = Membresia.objects.get(usuario=self.titular)
        m, clave = equipo.agregar(self.tenant, actor, 'recepcion', 'Ana', 'Gil', Rol.ASISTENTE)
        m.usuario.debe_cambiar_clave = False
        m.usuario.save()
        c = self.entrar(self.tenant, 'recepcion', clave)
        r = c.post('/agenda/citas/nueva/', {'paciente': self.paciente.pk, 'profesional': self.perfil.pk,
                                            'fecha': self.manana.isoformat(), 'hora_inicio': '10:00'})
        self.assertEqual(r.status_code, 302)
        with self.en_tenant():
            cita = Cita.objects.get()
        self.assertEqual(c.post(f'/agenda/citas/{cita.pk}/atender/').status_code, 403)
        self.assertContains(c.get(f'/agenda/?p=todos&fecha={self.manana.isoformat()}'), 'Elena Paz')

    def test_dos_profesionales_vista_de_clinica(self):
        esp = Especialidad.objects.get(codigo='medicina_general')
        actor = Membresia.objects.get(usuario=self.titular)
        m, _ = equipo.agregar(self.tenant, actor, 'drdos', 'Luis', 'Mar', Rol.MEDICO, especialidad=esp)
        with self.en_tenant():
            Cita.objects.create(paciente=self.otro, profesional=m.perfil, especialidad=esp, fecha=self.manana,
                                hora_inicio=time(9, 0), hora_fin=time(9, 30))
        self.nueva()     # misma hora, otro profesional: no choca
        r = self.cliente.get(f'/agenda/?fecha={self.manana.isoformat()}&p=todos')
        self.assertContains(r, 'Dr. Luis Mar')
        self.assertContains(r, 'Raúl Paz')
        self.assertContains(r, 'Elena Paz')
        self.assertEqual(self.cliente.get(f'/agenda/semana/?fecha={self.manana.isoformat()}').status_code, 200)

    def test_paginas_de_configuracion(self):
        for url in ('/agenda/horarios/', '/agenda/tipos/', '/agenda/bloqueos/'):
            self.assertEqual(self.cliente.get(url).status_code, 200, url)
        r = self.cliente.post('/agenda/horarios/', {'dias': ['0', '2'], 'hora_inicio': '08:00', 'hora_fin': '12:00',
                                                    'duracion_turno_min': 20})
        self.assertEqual(r.status_code, 302)
        with self.en_tenant():
            self.assertEqual(HorarioAtencion.objects.count(), 2)
