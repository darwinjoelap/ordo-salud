"""Fase 13.1: ajustes de Pediae en el núcleo (próximo control tentativo, cumpleaños, panel de horas, datos opcionales)."""
from datetime import date, time, timedelta

from django.utils import timezone

from apps.agenda import servicios as agenda
from apps.agenda.models import Cita, HorarioAtencion
from apps.clinica.models import Consulta, SeccionClinica
from apps.equipo.models import Membresia
from apps.pacientes.models import Paciente, Representante

from .base import BaseTest


class ProximoControlTest(BaseTest):
    def setUp(self):
        super().setUp()
        with self.en_tenant():
            self.paciente = Paciente.objects.create(nombres='Sofía', apellidos='Paz', sexo='F',
                                                    fecha_nacimiento=date(2022, 3, 1))
            self.s = {s.codigo: s.pk for s in SeccionClinica.objects.visibles()}
        r = self.iniciar_independiente(self.paciente, {'tipo': 'PRIMERA'})
        self.assertEqual(r.status_code, 302)
        with self.en_tenant():
            self.consulta = Consulta.objects.latest('id')

    def guardar(self, fecha, diagnostico='Rinofaringitis'):
        datos = {f's{self.s["nucleo.motivo"]}-motivo': 'Fiebre',
                 f's{self.s["nucleo.diagnosticos"]}-diagnosticos__0__descripcion': diagnostico,
                 f's{self.s["nucleo.plan"]}-proximo_control': fecha.isoformat() if fecha else ''}
        return self.cliente.post(f'/consultas/{self.consulta.pk}/editar/', datos, follow=True)

    def test_crea_cita_tentativa_sin_hora_y_la_mueve(self):
        en_15 = timezone.localdate() + timedelta(days=15)
        r = self.guardar(en_15)
        self.assertContains(r, 'cita tentativa (sin hora)')
        with self.en_tenant():
            cita = Cita.objects.get(consulta_origen=self.consulta)
            self.assertEqual((cita.estado, cita.hora_inicio, cita.fecha), ('TENTATIVA', None, en_15))
            self.assertEqual(cita.motivo, 'Control – Rinofaringitis')
        self.guardar(en_15)                                   # volver a guardar no duplica
        self.guardar(en_15 + timedelta(days=7))               # cambiar la fecha mueve la misma cita
        with self.en_tenant():
            self.assertEqual(Cita.objects.filter(paciente=self.paciente).count(), 1)
            self.assertEqual(Cita.objects.get().fecha, en_15 + timedelta(days=7))
        self.guardar(None)                                    # borrar la fecha quita la tentativa sin hora
        with self.en_tenant():
            self.assertFalse(Cita.objects.exists())

    def test_no_duplica_si_ya_hay_cita_ese_dia(self):
        en_10 = timezone.localdate() + timedelta(days=10)
        with self.en_tenant():
            perfil = Membresia.objects.get(usuario=self.titular).perfil
            Cita.objects.create(paciente=self.paciente, profesional=perfil, especialidad=perfil.especialidad,
                                fecha=en_10, hora_inicio=time(9), hora_fin=time(9, 30))
        self.guardar(en_10)
        with self.en_tenant():
            self.assertEqual(Cita.objects.count(), 1)


class CumpleanosYHorasTest(BaseTest):
    def setUp(self):
        super().setUp()
        hoy = timezone.localdate()
        with self.en_tenant():
            self.perfil = Membresia.objects.get(usuario=self.titular).perfil
            self.nino = Paciente.objects.create(nombres='Mateo', apellidos='Rondón', sexo='M',
                                                fecha_nacimiento=hoy.replace(year=hoy.year - 4))
            Representante.objects.create(paciente=self.nino, nombre='Carla Rondón', telefono='0414-1112233')
            self.adulto = Paciente.objects.create(nombres='Ana', apellidos='Gil', sexo='F', telefono='04125556677',
                                                  fecha_nacimiento=hoy.replace(year=hoy.year - 30))
            Paciente.objects.create(nombres='Otro', apellidos='Día', sexo='F', fecha_nacimiento=date(2020, 1, 1)
                                    if (hoy.month, hoy.day) != (1, 1) else date(2020, 1, 2))

    def test_cumpleanos_saluda_al_representante_del_menor(self):
        r = self.cliente.get('/agenda/')
        lista = r.context['cumpleanos']
        self.assertEqual([c['paciente'].nombres for c in lista], ['Ana', 'Mateo'])
        self.assertNotContains(r, 'https://wa.me/')
        hoy = timezone.localdate().isoformat()
        datos = {'accion': 'web', 'clave_intento': '00000000-0000-4000-8000-000000000001'}
        nino = self.cliente.post(f'/agenda/cumpleanos/{self.nino.pk}/{hoy}/contacto/', datos).json()['destino']
        self.assertIn('wa.me/584141112233', nino)
        self.assertIn('Hola%20Carla', nino)
        self.assertIn('cumple%204%20a%C3%B1os', nino)
        adulto = self.cliente.post(f'/agenda/cumpleanos/{self.adulto.pk}/{hoy}/contacto/', datos).json()['destino']
        self.assertIn('Hola%20Ana', adulto)
        self.assertContains(r, 'Felicitar')

    def test_panel_de_horas_marca_ocupadas(self):
        manana = timezone.localdate() + timedelta(days=1)
        with self.en_tenant():
            HorarioAtencion.objects.create(profesional=self.perfil, dia_semana=manana.weekday(), hora_inicio=time(8),
                                           hora_fin=time(10), duracion_turno_min=30)
            Cita.objects.create(paciente=self.adulto, profesional=self.perfil, especialidad=self.perfil.especialidad,
                                fecha=manana, hora_inicio=time(8, 30), hora_fin=time(9))
            Cita.objects.create(paciente=self.nino, profesional=self.perfil, especialidad=self.perfil.especialidad,
                                fecha=manana, estado='TENTATIVA')
        r = self.cliente.get(f'/agenda/horas/?fecha={manana.isoformat()}&profesional={self.perfil.pk}')
        turnos = r.context['turnos']
        self.assertEqual([t['hora'] for t in turnos], [time(8), time(8, 30), time(9), time(9, 30)])
        self.assertEqual([bool(t['cita']) for t in turnos], [False, True, False, False])
        self.assertEqual(len(r.context['tentativas']), 1)
        self.assertContains(r, '8:30 a.')              # formato de 12 horas
        self.assertContains(r, 'data-hora="09:00"')

    def test_sin_horario_usa_jornada_por_defecto(self):
        datos = agenda.horas_del_dia(self.perfil, timezone.localdate() + timedelta(days=2))
        self.assertTrue(datos['sin_horario'])
        self.assertEqual(datos['turnos'][0]['hora'], time(7))
        self.assertEqual(len(datos['turnos']), 22)
