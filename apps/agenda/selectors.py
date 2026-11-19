from calendar import monthrange
from datetime import date

from dateutil.relativedelta import relativedelta
from django.db.models import Exists, F, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce, Greatest, TruncDate

from apps.clinica.models import Consulta, Procedimiento
from apps.core.tenancy import tenant_actual
from apps.pacientes.models import Paciente
from apps.pacientes.selectors import filtrar_propios, puede_ver_todos

from .models import Cita, RecordatorioInactividad


def solo_propia(request):
    """Perfil al que está limitada la agenda de la membresía (ADR-064)."""
    m = request.membresia
    return m.perfil_activo if m and not puede_ver_todos(m) else None


def citas_visibles(request, qs=None):
    qs = Cita.objects.all() if qs is None else qs
    propio = solo_propia(request)
    return qs.filter(profesional=propio) if propio else qs


def _ultima_asistencia(fecha, profesional=None):
    consultas = (Consulta.objects.filter(paciente_id=OuterRef('pk'), estado=Consulta.Estado.CERRADA,
                                         fecha_hora__date__lte=fecha)
                 .filter(Q(cita__isnull=True) | Q(cita__estado=Cita.Estado.ATENDIDA,
                                                   cita__paciente_id=OuterRef('pk'),
                                                   cita__tenant_id=OuterRef('tenant_id'))))
    procedimientos = (Procedimiento.objects.filter(paciente_id=OuterRef('pk'), anulado=False, fecha__lte=fecha)
                      .filter(Q(cita__isnull=True) | Q(cita__estado=Cita.Estado.ATENDIDA,
                                                        cita__paciente_id=OuterRef('pk'),
                                                        cita__tenant_id=OuterRef('tenant_id'))))
    if profesional is not None:
        consultas = consultas.filter(profesional=profesional)
        procedimientos = procedimientos.filter(profesional=profesional)
    consulta = consultas.order_by('-fecha_hora').annotate(dia=TruncDate('fecha_hora')).values('dia')[:1]
    procedimiento = procedimientos.order_by('-fecha').values('fecha')[:1]
    return Greatest(Coalesce(Subquery(consulta), Value(date.min)),
                    Coalesce(Subquery(procedimiento), Value(date.min)))


def sugerencias_inactividad(*, fecha, membresia, profesional=None):
    tenant = tenant_actual()
    if not tenant or membresia is None or membresia.tenant.pk != tenant.pk:
        return Paciente.objects.none()
    meses = tenant.configuracion.recordatorio_sin_consulta_meses
    if not meses or meses >= fecha.year * 12 + fecha.month - 12:
        return Paciente.objects.none()
    limite = fecha - relativedelta(months=meses)
    if fecha.day == monthrange(fecha.year, fecha.month)[1]:
        limite = limite.replace(day=monthrange(limite.year, limite.month)[1])

    proximas = Cita.objects.filter(paciente_id=OuterRef('pk'), fecha__gte=fecha, estado__in=Cita.ACTIVAS)
    pacientes = (Paciente.objects.filter(activo=True)
                 .annotate(ultima_asistencia=_ultima_asistencia(fecha))
                 .filter(ultima_asistencia__gt=date.min, ultima_asistencia__lte=limite)
                 .filter(~Exists(proximas)))
    if not puede_ver_todos(membresia):
        pacientes = filtrar_propios(pacientes, membresia)
        profesional = membresia.perfil_activo
    if profesional is not None:
        pacientes = pacientes.alias(ultima_propia=_ultima_asistencia(fecha, profesional)).filter(
            ultima_propia=F('ultima_asistencia'))

    decisiones = RecordatorioInactividad.objects.filter(paciente_id=OuterRef('pk'))
    resueltas = decisiones.filter(ultima_asistencia__gte=OuterRef('ultima_asistencia')).exclude(
        estado=RecordatorioInactividad.Estado.INTENTO)
    intentos = decisiones.filter(ultima_asistencia=OuterRef('ultima_asistencia'))
    # Una corrección que retrocede la última asistencia no inicia un episodio nuevo.
    return (pacientes.filter(~Exists(resueltas)).annotate(intento_registrado=Exists(intentos))
            .order_by('ultima_asistencia', 'apellidos', 'nombres'))
