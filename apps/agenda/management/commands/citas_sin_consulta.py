"""
Citas que quedaron «pendientes» aunque el paciente sí se atendió ese día (consulta creada desde la ficha del paciente
y no con «Atender» en la agenda). Solo muestra números (sin nombres de pacientes):

    python manage.py citas_sin_consulta --consultorio dra-anaisbaez            # revisar últimos 7 días
    python manage.py citas_sin_consulta --consultorio dra-anaisbaez --dias 30
    python manage.py citas_sin_consulta --consultorio dra-anaisbaez --aplicar  # marcarlas atendidas y vincularlas

Al aplicar no se crea cargo si la consulta ya tiene uno (para no cobrar dos veces).
"""
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.core.tenancy import usando_tenant
from apps.plataforma.models import Tenant


class Command(BaseCommand):
    help = 'Lista (y con --aplicar, vincula) citas pendientes cuyo paciente sí se atendió ese día.'

    def add_arguments(self, parser):
        parser.add_argument('--consultorio', help='Enlace del consultorio (por defecto, todos).')
        parser.add_argument('--dias', type=int, default=7)
        parser.add_argument('--aplicar', action='store_true')

    def handle(self, *args, consultorio=None, dias=7, aplicar=False, **opciones):
        from apps.agenda.models import Cita
        from apps.agenda.servicios import vincular_consulta
        from apps.clinica.models import Consulta
        tenants = Tenant.objects.all()
        if consultorio:
            tenants = tenants.filter(slug=consultorio)
            if not tenants.exists():
                raise CommandError(f'No existe el consultorio «{consultorio}».')
        hoy = timezone.localdate()
        total = 0
        for tenant in tenants:
            with usando_tenant(tenant):
                citas = (Cita.objects.filter(fecha__range=(hoy - timedelta(days=dias), hoy), estado__in=Cita.ACTIVAS,
                                             consulta__isnull=True).order_by('fecha', 'hora_inicio'))
                for cita in citas:
                    consulta = (Consulta.objects.filter(
                        paciente_id=cita.paciente_id, profesional_id=cita.profesional_id,
                        fecha_hora__date=cita.fecha, cita__isnull=True)
                        .exclude(estado=Consulta.Estado.ANULADA).order_by('fecha_hora').first())
                    hora = cita.hora_inicio.strftime('%H:%M') if cita.hora_inicio else 'sin hora'
                    if consulta is None:
                        self.stdout.write(f'{tenant.slug} · cita {cita.pk} · {cita.fecha:%d/%m} {hora} · '
                                          f'{cita.get_estado_display()} · sin consulta ese día (no vino o no se registró)')
                        continue
                    total += 1
                    hecho = ''
                    if aplicar:
                        with transaction.atomic():
                            vincular_consulta(cita, consulta, consulta.profesional)
                        hecho = ' → VINCULADA'
                    self.stdout.write(self.style.WARNING(
                        f'{tenant.slug} · cita {cita.pk} · {cita.fecha:%d/%m} {hora} · {cita.get_estado_display()} · '
                        f'consulta {consulta.pk} ({consulta.get_estado_display()}, '
                        f'{timezone.localtime(consulta.fecha_hora):%H:%M}){hecho}'))
        accion = 'vinculadas' if aplicar else 'por vincular (usa --aplicar)'
        self.stdout.write(self.style.SUCCESS(f'{total} cita(s) {accion}.'))
