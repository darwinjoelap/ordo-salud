"""Servicios previstos y precios de referencia de la cita."""
from django.db.models import Q

from apps.cobros.models import CobroRapidoCita, Servicio
from apps.core.excepciones import ErrorDeNegocio

from .models import ServicioPrevisto


def catalogo(*, especialidad_id, conservar=()):
    return (Servicio.objects.filter(Q(activo=True) | Q(pk__in=conservar))
            .filter(Q(especialidad__isnull=True) | Q(especialidad_id=especialidad_id)))


def predeterminado(tipo, especialidad_id):
    if tipo and tipo.especialidad_id in (None, especialidad_id):
        return catalogo(especialidad_id=especialidad_id).filter(pk=tipo.servicio_id).first()
    return None


def lineas_de(cita):
    """Las citas anteriores conservan el servicio del tipo y su precio de catálogo al atender."""
    if cita.servicios_explicitos:
        return list(ServicioPrevisto.objects.filter(cita=cita).select_related('servicio'))
    if cita.tipo_id:
        servicio = Servicio.objects.filter(pk=cita.tipo.servicio_id, activo=True).first()
        if servicio:
            return [ServicioPrevisto(cita=cita, servicio=servicio, nombre=servicio.nombre, precio_usd=servicio.precio_usd)]
    return []


def plan_bloqueado(cita):
    return (not cita.activa or cita.consulta_id is not None or cita.cargos.exists() or cita.procedimientos.exists()
            or CobroRapidoCita.objects.filter(cita=cita).exists())


def preparar_plan(cita, anterior, servicios):
    if anterior and plan_bloqueado(anterior):
        if (cita.fecha, cita.hora_inicio, cita.hora_fin, cita.lugar_id) != (
                anterior.fecha, anterior.hora_inicio, anterior.hora_fin, anterior.lugar_id):
            raise ErrorDeNegocio('La cita tiene atención o cargos registrados. No se puede cambiar el horario ni el lugar.')
        actuales = {linea.servicio_id for linea in lineas_de(anterior)}
        if ((cita.profesional_id, cita.tipo_id, cita.especialidad_id) != (
                anterior.profesional_id, anterior.tipo_id, anterior.especialidad_id)
                or (servicios is not None and set(servicios) != actuales)):
            raise ErrorDeNegocio('La cita tiene atención o cargos registrados. Revisa cualquier corrección en Cobros.')
        return None

    if servicios is None:
        if anterior and not anterior.servicios_explicitos:
            return None
        if anterior:
            servicios = ServicioPrevisto.objects.filter(cita=anterior).values_list('servicio_id', flat=True)
        else:
            servicio = predeterminado(cita.tipo if cita.tipo_id else None, cita.especialidad_id)
            servicios = [servicio.pk] if servicio else []
    elegidos = set(servicios)
    actuales = {linea.servicio_id: linea for linea in ServicioPrevisto.objects.filter(cita=anterior)} if anterior else {}
    disponibles = catalogo(especialidad_id=cita.especialidad_id, conservar=actuales).in_bulk(elegidos)
    if elegidos != disponibles.keys():
        raise ErrorDeNegocio('Revisa los servicios: alguna opción no está disponible para la especialidad seleccionada.')
    return [actuales.get(pk) or ServicioPrevisto(
        cita=cita, servicio=servicio, nombre=servicio.nombre, precio_usd=servicio.precio_usd,
    ) for pk, servicio in disponibles.items()]


def guardar_plan(cita, lineas):
    if lineas is None:
        return
    ServicioPrevisto.objects.filter(cita=cita).exclude(servicio_id__in=[linea.servicio_id for linea in lineas]).delete()
    ServicioPrevisto.objects.bulk_create([
        ServicioPrevisto(tenant_id=cita.tenant_id, cita=cita, servicio_id=linea.servicio_id,
                         nombre=linea.nombre, precio_usd=linea.precio_usd)
        for linea in lineas if linea.pk is None
    ])


def catalogo_procedimiento(cita, lineas):
    ids = {linea.servicio_id for linea in lineas}
    if not cita or not cita.servicios_explicitos:
        return Servicio.objects.filter(activo=True)
    # Un servicio previsto previamente sigue visible aunque haya cambiado el catálogo.
    return Servicio.objects.filter(pk__in=ids) | catalogo(especialidad_id=cita.especialidad_id)
