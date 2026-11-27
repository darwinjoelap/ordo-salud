"""
Reglas de la agenda (Fase 08). Los cambios de estado de una cita pasan SOLO por aquí.
"""
import re
from datetime import date, datetime, time, timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.configuracion import whatsapp
from apps.core.excepciones import ErrorDeNegocio
from apps.core.fechas import hora12
from apps.core.tenancy import tenant_actual

from . import servicios_previstos as previstos
from .models import Bloqueo, Cita, HorarioAtencion, TipoCita

TRANSICIONES = {
    'TENTATIVA': {'PROGRAMADA', 'CONFIRMADA', 'ATENDIDA', 'CANCELADA'},
    'PROGRAMADA': {'CONFIRMADA', 'EN_SALA', 'ATENDIDA', 'CANCELADA', 'NO_ASISTIO', 'TENTATIVA'},
    'CONFIRMADA': {'EN_SALA', 'ATENDIDA', 'CANCELADA', 'NO_ASISTIO', 'PROGRAMADA'},
    'EN_SALA': {'ATENDIDA', 'CONFIRMADA', 'NO_ASISTIO'},
    'ATENDIDA': set(),
    'CANCELADA': {'PROGRAMADA'},
    'NO_ASISTIO': {'PROGRAMADA'},
}


def _dt(fecha, hora):
    return timezone.make_aware(datetime.combine(fecha, hora))


def calcular_fin(fecha, hora_inicio, duracion_min):
    if hora_inicio is None:
        return None
    fin = datetime.combine(fecha, hora_inicio) + timedelta(minutes=duracion_min or 30)
    return fin.time() if fin.date() == fecha else time(23, 59)


def solapadas(*, profesional, fecha, hora_inicio, hora_fin, excluir_pk=None):
    if hora_inicio is None:
        return Cita.objects.none()
    qs = Cita.objects.filter(profesional=profesional, fecha=fecha, estado__in=Cita.ACTIVAS,
                             hora_inicio__isnull=False, hora_inicio__lt=hora_fin, hora_fin__gt=hora_inicio)
    return qs.exclude(pk=excluir_pk) if excluir_pk else qs


def bloqueo_en(*, profesional, fecha, hora_inicio, hora_fin):
    inicio = _dt(fecha, hora_inicio or time(0, 0))
    fin = _dt(fecha, hora_fin or time(23, 59))
    return (Bloqueo.objects.filter(desde__lt=fin, hasta__gt=inicio)
            .filter(Q(profesional=profesional) | Q(profesional__isnull=True)).first())


def fuera_de_horario(*, profesional, fecha, hora_inicio, hora_fin):
    """True si el profesional tiene horario cargado para ese día y la cita cae fuera (solo aviso)."""
    if hora_inicio is None:
        return False
    horarios = HorarioAtencion.objects.filter(profesional=profesional, dia_semana=fecha.weekday(), activo=True)
    if not horarios.exists():
        return False
    return not horarios.filter(hora_inicio__lte=hora_inicio, hora_fin__gte=hora_fin).exists()


@transaction.atomic
def guardar_cita(cita, *, sobrecupo=False, servicios=None, version=None):
    """
    Crea o actualiza una cita (instancia ya llenada desde el formulario). Reglas:
    - el profesional debe estar activo; la especialidad es la suya;
    - no se pisa con otra cita activa del mismo profesional, salvo sobrecupo explícito;
    - no cae en un bloqueo; sin hora = tentativa.
    Devuelve (cita, avisos).
    """
    from apps.equipo.models import PerfilProfesional
    from apps.pacientes.models import Paciente

    tenant = tenant_actual()
    if tenant is None or cita.tenant_id not in (None, tenant.pk):
        raise ErrorDeNegocio('La cita no pertenece al consultorio activo.')
    anterior = None
    if cita.pk:
        anterior = Cita.objects.select_for_update().filter(pk=cita.pk).first()
        if anterior is None or not anterior.activa:
            raise ErrorDeNegocio('Esta cita ya no está activa o ya no existe.')
        if cita.paciente_id != anterior.paciente_id:
            raise ErrorDeNegocio('No se puede cambiar el paciente de una cita existente.')
        if (version or cita.actualizado_en) != anterior.actualizado_en:
            raise ErrorDeNegocio('La cita cambió mientras la editabas. Vuelve a abrirla antes de guardar.')
        if cita.exonerada != anterior.exonerada and previstos.plan_bloqueado(anterior):
            raise ErrorDeNegocio('La cita tiene atención o cargos registrados. Revisa la exoneración en Cobros.')
        cita.estado = anterior.estado
        cita.servicios_explicitos = anterior.servicios_explicitos
    elif not Paciente.objects.filter(pk=cita.paciente_id, activo=True).exists():
        raise ErrorDeNegocio('El paciente no está disponible en este consultorio.')
    perfil = PerfilProfesional.objects.select_for_update().get(pk=cita.profesional_id)   # serializa por profesional
    if not perfil.activo or not perfil.membresia.activa:
        raise ErrorDeNegocio('Ese profesional no está activo.')
    cita.especialidad = perfil.especialidad
    if cita.tipo_id and (not anterior or (cita.tipo_id, cita.especialidad_id) != (
            anterior.tipo_id, anterior.especialidad_id)):
        tipo = TipoCita.objects.filter(pk=cita.tipo_id, activo=True).first()
        if tipo is None or tipo.especialidad_id not in (None, cita.especialidad_id):
            raise ErrorDeNegocio('El tipo de cita no corresponde a la especialidad del profesional.')
    lineas = previstos.preparar_plan(cita, anterior, servicios)
    if lineas is not None:
        cita.servicios_explicitos = True
    avisos = []
    if cita.hora_inicio is None:
        cita.hora_fin = None
        if cita.estado in ('PROGRAMADA', 'CONFIRMADA'):
            cita.estado = Cita.Estado.TENTATIVA
    else:
        tenant = cita.tenant if cita.tenant_id else tenant_actual()
        duracion = cita.tipo.duracion_min if cita.tipo_id else tenant.configuracion.duracion_cita_min
        if not cita.hora_fin or cita.hora_fin <= cita.hora_inicio:
            cita.hora_fin = calcular_fin(cita.fecha, cita.hora_inicio, duracion)
        if cita.estado == Cita.Estado.TENTATIVA:
            cita.estado = Cita.Estado.PROGRAMADA
        choques = solapadas(profesional=perfil, fecha=cita.fecha, hora_inicio=cita.hora_inicio,
                            hora_fin=cita.hora_fin, excluir_pk=cita.pk)
        if choques.exists():
            if not sobrecupo:
                otra = choques.select_related('paciente').first()
                raise ErrorDeNegocio(f'{perfil} ya tiene cita a esa hora ({otra.paciente}, '
                                     f'{hora12(otra.hora_inicio)}). Marca «sobrecupo» si es a propósito.')
            cita.sobrecupo = True
        bloqueo = bloqueo_en(profesional=perfil, fecha=cita.fecha, hora_inicio=cita.hora_inicio,
                             hora_fin=cita.hora_fin)
        if bloqueo:
            raise ErrorDeNegocio(f'La agenda está bloqueada en ese horario: {bloqueo.motivo}.')
        if fuera_de_horario(profesional=perfil, fecha=cita.fecha, hora_inicio=cita.hora_inicio,
                            hora_fin=cita.hora_fin):
            avisos.append('La cita queda fuera del horario de atención cargado para ese día.')
    if cita.fecha < timezone.localdate() and cita.pk is None:
        avisos.append('La cita quedó en una fecha pasada.')
    cita.save()
    previstos.guardar_plan(cita, lineas)
    return cita, avisos


@transaction.atomic
def cambiar_estado(cita, nuevo, motivo=''):
    cita = Cita.objects.select_for_update().get(pk=cita.pk)
    if nuevo == cita.estado:
        return cita
    if nuevo not in TRANSICIONES.get(cita.estado, set()):
        raise ErrorDeNegocio(f'Una cita «{cita.get_estado_display()}» no puede pasar a '
                             f'«{Cita.Estado(nuevo).label}».')
    if nuevo == Cita.Estado.CANCELADA:
        cita.motivo_cancelacion = (motivo or '')[:200]
    cita.estado = nuevo
    cita.save(update_fields=['estado', 'motivo_cancelacion', 'actualizado_en'])
    return cita


@transaction.atomic
def iniciar_atencion(cita, perfil):
    """Abre la consulta de la cita (o vuelve a la ya abierta) y la marca atendida."""
    from apps.clinica.consultas import abrir_consulta
    from apps.cobros.servicios import bloquear_cuenta

    bloquear_cuenta(cita.paciente_id)
    cita = Cita.objects.select_for_update().get(pk=cita.pk)
    if cita.profesional_id != perfil.pk or cita.especialidad_id != perfil.especialidad_id:
        raise ErrorDeNegocio(f'La cita es con {cita.profesional}; solo esa persona puede atenderla.')
    if cita.consulta_id:
        return cita.consulta, False
    if not cita.activa:
        raise ErrorDeNegocio(f'La cita está «{cita.get_estado_display()}».')
    tipo = cita.tipo
    consulta = abrir_consulta(paciente=cita.paciente, profesional=perfil,
                              plantilla=tipo.plantilla if tipo and tipo.plantilla_id and tipo.plantilla.activa else None,
                              tipo=tipo.tipo_consulta if tipo else 'PRIMERA', lugar=cita.lugar)
    vincular_consulta(cita, consulta, perfil)
    return consulta, True


def atender(cita, perfil):
    consulta, _ = iniciar_atencion(cita, perfil)
    return consulta


@transaction.atomic
def vincular_consulta(cita, consulta, perfil):
    """Vincula una atención y genera a lo sumo un cargo por servicio previsto."""
    from apps.clinica.models import Consulta
    from apps.cobros.servicios import bloquear_cuenta, crear_cargo, validar_exoneracion

    bloquear_cuenta(consulta.paciente_id)
    cita = Cita.objects.select_for_update().get(pk=cita.pk)
    if cita.consulta_id or not cita.activa:
        return
    if (cita.paciente_id, cita.profesional_id, cita.tenant_id) != (
            consulta.paciente_id, perfil.pk, consulta.tenant_id) or consulta.profesional_id != perfil.pk:
        raise ErrorDeNegocio('La consulta no corresponde a esta cita.')
    actual = Consulta.objects.get(pk=consulta.pk)
    if actual.estado == Consulta.Estado.ANULADA:
        raise ErrorDeNegocio('No se puede vincular una consulta anulada.')
    if actual.exonerada and not cita.exonerada:
        validar_exoneracion(cita=cita, consulta=actual)
        cita.exonerada = True
    if cita.exonerada and not actual.exonerada:
        Consulta.objects.filter(pk=actual.pk).update(exonerada=True)
    consulta.exonerada = cita.exonerada
    cita.consulta = consulta
    cita.estado = Cita.Estado.ATENDIDA
    cita.save(update_fields=['consulta', 'estado', 'exonerada', 'actualizado_en'])
    if cita.exonerada or cita.cargos.exists() or consulta.cargos.exists():
        return
    for linea in previstos.lineas_de(cita):
        crear_cargo(paciente=cita.paciente, servicio=linea.servicio, descripcion=linea.nombre,
                    precio_usd=linea.precio_usd, consulta=consulta, cita=cita, profesional=perfil)


def citas_para_iniciar(paciente, profesional):
    return (Cita.objects.filter(paciente=paciente, profesional=profesional, especialidad=profesional.especialidad,
                                fecha=hoy(), estado__in=Cita.ACTIVAS, consulta__isnull=True)
            .select_related('tipo').order_by('hora_inicio', 'id'))


def turnos_libres(profesional, fecha):
    """Horas de inicio libres del día según el horario cargado (para sugerir al agendar)."""
    citas = [(c.hora_inicio, c.hora_fin) for c in Cita.objects.filter(
        profesional=profesional, fecha=fecha, estado__in=Cita.ACTIVAS, hora_inicio__isnull=False)]
    libres = []
    for h in HorarioAtencion.objects.filter(profesional=profesional, dia_semana=fecha.weekday(), activo=True):
        actual = datetime.combine(fecha, h.hora_inicio)
        fin = datetime.combine(fecha, h.hora_fin)
        paso = timedelta(minutes=h.duracion_turno_min)
        while actual + paso <= fin:
            ini, ter = actual.time(), (actual + paso).time()
            if not any(a < ter and b > ini for a, b in citas):
                libres.append((ini, h.lugar))
            actual += paso
    if fecha == timezone.localdate():
        ahora = timezone.localtime().time()
        libres = [x for x in libres if x[0] > ahora]
    return libres


def horas_del_dia(profesional, fecha, excluir=None):
    """
    Panel de horas al agendar (de Pediae): todos los turnos del día según el horario del profesional, marcando los
    ocupados (con el paciente) y los ya pasados si es hoy. Sin horario cargado ese día, turnos de 30 min de
    7:00 a. m. a 6:00 p. m. (como Pediae) y `sin_horario=True`. También devuelve las citas sin hora (tentativas).
    """
    qs = Cita.objects.filter(profesional=profesional, fecha=fecha, estado__in=Cita.ACTIVAS).select_related('paciente')
    if excluir:
        qs = qs.exclude(pk=excluir)
    citas = list(qs)
    con_hora = [c for c in citas if c.hora_inicio]
    horarios = list(HorarioAtencion.objects.filter(profesional=profesional, dia_semana=fecha.weekday(), activo=True)
                    .select_related('lugar').order_by('hora_inicio'))
    tramos = [(h.hora_inicio, h.hora_fin, h.duracion_turno_min, h.lugar) for h in horarios]
    if not tramos:
        tramos = [(time(7), time(18), 30, None)]
    ahora = timezone.localtime().time() if fecha == timezone.localdate() else None
    turnos = []
    for ini_t, fin_t, minutos, lugar in tramos:
        actual, fin, paso = datetime.combine(fecha, ini_t), datetime.combine(fecha, fin_t), timedelta(minutes=minutos)
        while actual + paso <= fin:
            ini, ter = actual.time(), (actual + paso).time()
            ocupada = next((c for c in con_hora
                            if c.hora_inicio < ter and (c.hora_fin or (datetime.combine(fecha, c.hora_inicio)
                                                                       + paso).time()) > ini), None)
            turnos.append({'hora': ini, 'lugar': lugar, 'cita': ocupada, 'pasada': ahora is not None and ini <= ahora})
            actual += paso
    return {'turnos': turnos, 'sin_horario': not horarios, 'tentativas': [c for c in citas if not c.hora_inicio]}


def semana_de(fecha):
    lunes = fecha - timedelta(days=fecha.weekday())
    return [lunes + timedelta(days=i) for i in range(7)]


def numero_whatsapp(telefono):
    """Normalización histórica utilizada por Compartir acceso de Plataforma."""
    numero = re.sub(r'[^\d+]', '', telefono or '').lstrip('+')
    if numero.startswith('0'):
        numero = '58' + numero[1:]
    return numero if len(numero) >= 10 else ''


def destinatario(paciente, *, bloquear=False):
    """Devuelve saludo y número del mismo destinatario, con preferencia por el representante."""
    representante = None
    if paciente.es_menor:
        if bloquear:
            representante = paciente.representantes.select_for_update().order_by('-es_principal', 'pk').first()
        else:
            representante = paciente.representante_principal
    if representante is not None:
        saludo = representante.nombre.split()[0]
        if representante.whatsapp_seguimiento == 'NO':
            return saludo, '', representante
        if numero := whatsapp.numero_whatsapp(representante.telefono):
            return saludo, numero, representante
    numero = '' if paciente.whatsapp_seguimiento == 'NO' else whatsapp.numero_whatsapp(paciente.telefono)
    return paciente.nombres.split()[0], numero, None


def url_whatsapp(cita, *, bloquear=False):
    """Enlace para pedir confirmación de asistencia por WhatsApp."""
    paciente = cita.paciente
    saludo, numero, representante = destinatario(paciente, bloquear=bloquear)
    if not numero:
        return None
    config = cita.tenant.configuracion
    lugar = (cita.lugar.nombre + (f' ({cita.lugar.direccion})' if cita.lugar.direccion else '')) if cita.lugar else ''
    texto = whatsapp.armar(config.plantilla_whatsapp, {
        'saludo': saludo, 'paciente': paciente.nombre_completo,
        'de_paciente': f'de {paciente.nombres} ' if representante else '',
        'profesional': cita.profesional.nombre_con_titulo, 'consultorio': config.nombre_display,
        'fecha': f'{cita.fecha:%d/%m/%Y}', 'hora': hora12(cita.hora_inicio) if cita.hora_inicio else '',
        'lugar': lugar})
    return whatsapp.enlace(numero, texto)


def se_puede_eliminar(cita):
    """Solo citas no atendidas: sin consulta, sin cobros y sin procedimientos (lo demás se cancela)."""
    return (cita.estado != Cita.Estado.ATENDIDA and not cita.consulta_id and not cita.cargos.exists()
            and not cita.procedimientos.exists())


def marcar_recordatorio(cita):
    cita.recordatorio_en = timezone.now()
    cita.save(update_fields=['recordatorio_en'])


def hoy():
    return timezone.localdate()


def fecha_de(texto, por_defecto=None):
    try:
        return date.fromisoformat(texto)
    except (TypeError, ValueError):
        return por_defecto or hoy()


@transaction.atomic
def programar_control(consulta, fecha):
    """
    «Próximo control» de una consulta → cita TENTATIVA sin hora (comportamiento de Pediae): mismo profesional y lugar,
    motivo «Control – diagnóstico». Al volver a guardar se mueve la misma cita; si se borra la fecha, se quita la
    tentativa que aún no tiene hora. No duplica si ya hay una cita activa del paciente con ese profesional ese día.
    Devuelve la cita (o None).
    """
    from apps.clinica.models import DiagnosticoConsulta
    from apps.cobros.servicios import bloquear_cuenta

    bloquear_cuenta(consulta.paciente_id)
    existente = (Cita.objects.select_for_update().filter(consulta_origen=consulta, estado__in=Cita.ACTIVAS)
                 .order_by('-creado_en').first())
    dia_consulta = timezone.localtime(consulta.fecha_hora).date() if consulta.fecha_hora else hoy()
    if not fecha or fecha <= dia_consulta:
        if (existente is not None and existente.estado == Cita.Estado.TENTATIVA
                and existente.hora_inicio is None and se_puede_eliminar(existente)):
            existente.delete()
        return None
    if existente is not None:
        if existente.fecha != fecha:
            existente.fecha = fecha
            existente.hora_inicio = existente.hora_fin = None      # la hora asignada era para el otro día
            existente.estado = Cita.Estado.TENTATIVA
            existente.save(update_fields=['fecha', 'hora_inicio', 'hora_fin', 'estado', 'actualizado_en'])
        return existente
    otra = Cita.objects.filter(paciente=consulta.paciente, profesional=consulta.profesional, fecha=fecha,
                               estado__in=Cita.ACTIVAS).first()
    if otra is not None:
        return otra
    diagnostico = (DiagnosticoConsulta.objects.filter(consulta=consulta).order_by('pk')
                   .values_list('descripcion', flat=True).first() or '')
    motivo = f'Control – {diagnostico}' if diagnostico else 'Control'
    return Cita.objects.create(
        paciente=consulta.paciente, profesional=consulta.profesional, especialidad=consulta.especialidad,
        lugar=consulta.lugar, fecha=fecha, hora_inicio=None, hora_fin=None, estado=Cita.Estado.TENTATIVA,
        motivo=motivo[:200], consulta_origen=consulta)


def pacientes_cumpleanos(fecha, membresia):
    """Cumpleaños de la fecha con el alcance de pacientes de la membresía."""
    import calendar

    from apps.pacientes.models import Paciente
    from apps.pacientes.selectors import filtrar_propios, puede_ver_todos

    dias = (28, 29) if fecha.month == 2 and fecha.day == 28 and not calendar.isleap(fecha.year) else (fecha.day,)
    qs = Paciente.objects.filter(activo=True, fecha_nacimiento__month=fecha.month, fecha_nacimiento__day__in=dias)
    return qs if puede_ver_todos(membresia) else filtrar_propios(qs, membresia)


def cumpleanos(fecha, membresia):
    return [{'paciente': p, 'edad': fecha.year - p.fecha_nacimiento.year}
            for p in pacientes_cumpleanos(fecha, membresia).order_by('nombres', 'apellidos')]


def url_cumpleanos(paciente, fecha, consultorio):
    saludo, numero, representante = destinatario(paciente, bloquear=True)
    if not numero:
        return None
    if representante is not None:
        edad = fecha.year - paciente.fecha_nacimiento.year
        anios = f'{edad} año{"s" if edad != 1 else ""}'
        texto = (f'¡Hola {saludo}! El equipo de {consultorio} le desea a {paciente.nombres.split()[0]} un muy feliz '
                 f'cumpleaños: hoy cumple {anios}. ¡Que pase un día excelente!')
    else:
        texto = (f'¡Hola {saludo}! El equipo de {consultorio} le desea un muy feliz cumpleaños. '
                 f'¡Que pase un día excelente!')
    return whatsapp.enlace(numero, texto)
