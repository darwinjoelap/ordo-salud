"""Procedimientos sin consulta (ADR-040), agenda estilo Pediae e historial en la ficha."""
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.agenda.models import Cita
from apps.clinica.models import Procedimiento
from apps.cobros.models import Cargo, Servicio
from apps.equipo.models import PerfilProfesional
from apps.especialidades.pediatria.models import Vacuna, VacunaAplicada
from apps.pacientes.models import Paciente

from .base import BaseTest, crear_consultorio


class ProcedimientosTest(BaseTest):
    def setUp(self):
        self.tenant, self.titular = crear_consultorio('Pediatra', 'pedi', especialidad='pediatria')
        self.cliente = self.entrar(self.tenant, 'titular')
        hoy = timezone.localdate()
        with self.en_tenant():
            self.p = Paciente.objects.create(nombres='Luis', apellidos='Mora', sexo='M',
                                             fecha_nacimiento=hoy - timedelta(days=400))
            self.perfil = PerfilProfesional.objects.get()
            self.vac = Servicio.objects.create(nombre='Aplicación de vacuna', precio_usd=Decimal('10'))
            self.neb = Servicio.objects.create(nombre='Nebulización', precio_usd=Decimal('8'))
            self.cita = Cita.objects.create(paciente=self.p, profesional=self.perfil,
                                            especialidad=self.perfil.especialidad, fecha=hoy, motivo='Vacunas',
                                            estado='TENTATIVA')
            self.vacuna = Vacuna.objects.visibles().filter(anual=False, edad_meses__lte=12).first()

    def url(self, **extra):
        q = '&'.join(f'{k}={v}' for k, v in extra.items())
        return f'/pacientes/{self.p.pk}/procedimientos/nuevo/' + (f'?{q}' if q else '')

    def test_desde_la_cita_con_vacuna(self):
        r = self.cliente.get(self.url(cita=self.cita.pk))
        self.assertContains(r, 'Vacunas aplicadas hoy')
        r = self.cliente.post(self.url(), {'cita': self.cita.pk, 'servicios': [self.vac.pk, self.neb.pk],
                                           'vacunas': [self.vacuna.pk], 'vacuna_lote': 'L-77'})
        self.assertEqual(r.status_code, 302)
        with self.en_tenant():
            proc = Procedimiento.objects.get()
            self.assertIn(self.vacuna.nombre, proc.descripcion)
            self.assertEqual(proc.total_usd, Decimal('18'))
            self.assertEqual(Cargo.objects.filter(procedimiento=proc).count(), 2)
            self.assertEqual(Cita.objects.get(pk=self.cita.pk).estado, 'ATENDIDA')
            self.assertEqual(VacunaAplicada.objects.get(vacuna=self.vacuna).lote, 'L-77')

    def test_varios_en_el_dia_y_anular(self):
        for _ in range(2):
            self.cliente.post(self.url(), {'servicios': [self.neb.pk]})
        self.cliente.post(self.url(), {'otro_concepto': 'Curación', 'otro_monto': '5'})
        with self.en_tenant():
            self.assertEqual(Procedimiento.objects.count(), 3)
            proc = Procedimiento.objects.filter(descripcion='Curación').get()
        self.cliente.post(f'/procedimientos/{proc.pk}/anular/', {'motivo': 'Error de carga'})
        with self.en_tenant():
            proc.refresh_from_db()
            self.assertTrue(proc.anulado)
            self.assertFalse(proc.cargos.exclude(estado='ANULADO').exists())
        # sin nada elegido: error, no crea
        r = self.cliente.post(self.url(), {})
        self.assertContains(r, 'Elige al menos un servicio')

    def test_agenda_y_ficha(self):
        self.cliente.post(self.url(), {'servicios': [self.neb.pk]})          # sin cita
        r = self.cliente.get('/agenda/')
        self.assertContains(r, 'Sin hora asignada')
        self.assertContains(r, 'Atendidos sin cita previa')
        self.assertContains(r, 'Nebulización')
        self.assertContains(r, 'Registrar procedimiento')
        self.assertEqual(r.context['resumen'], {'total': 1, 'atendidas': 0, 'pendientes': 1})
        r = self.cliente.get(f'/pacientes/{self.p.pk}/')
        self.assertContains(r, 'Historial de consultas')
        self.assertContains(r, 'Procedimiento')

    def test_solo_marcar_atendida_una_tentativa(self):
        r = self.cliente.post(f'/agenda/citas/{self.cita.pk}/estado/', {'estado': 'ATENDIDA', 'volver': '/agenda/'})
        self.assertEqual(r.status_code, 302)
        with self.en_tenant():
            self.assertEqual(Cita.objects.get(pk=self.cita.pk).estado, 'ATENDIDA')

    def test_otro_consultorio_no_ve_el_paciente(self):
        otro, _ = crear_consultorio('Otro', 'otro3', usuario='otro3')
        c = self.entrar(otro, 'otro3')
        self.assertEqual(c.get(self.url()).status_code, 404)
