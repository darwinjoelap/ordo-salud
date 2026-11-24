"""Procedimientos sin consulta (ADR-040): registrar (cargos + cita atendida + extras de módulos) y anular."""
from decimal import Decimal, InvalidOperation

from django.core import signing
from django.db import transaction
from django.utils import timezone

from apps.core.excepciones import ErrorDeNegocio

from .models import Procedimiento

_FIRMA_CARGOS = 'clinica.procedimiento.cargos_manuales'


def _cargos_manuales(cita, fecha, servicios):
    from apps.cobros.models import Cargo
    from apps.cobros.saldos import lineas_de_cargos

    grupos = {}
    cargos = Cargo.objects.filter(
        paciente_id=cita.paciente_id, fecha__in=(cita.fecha, fecha), servicio_id__in=servicios,
        cita__isnull=True, consulta__isnull=True, procedimiento__isnull=True,
    ).exclude(estado=Cargo.Estado.ANULADO).order_by('fecha', 'pk')
    for linea in lineas_de_cargos(cargos):
        grupos.setdefault(linea.cargo.servicio_id, []).append(linea)
    return grupos


def _revision(cita, servicio_id, lineas):
    return [cita.tenant_id, cita.pk, servicio_id,
            [[linea.cargo.pk, linea.cargo.actualizado_en.isoformat(), str(linea.pagado), linea.revision]
             for linea in lineas]]


def opciones_cargos(cita, fecha, servicios):
    from apps.cobros.saldos import lectura_financiera

    with lectura_financiera():
        return {
            pk: {'lineas': lineas, 'firma': signing.dumps(_revision(cita, pk, lineas), salt=_FIRMA_CARGOS)}
            for pk, lineas in _cargos_manuales(cita, fecha, servicios).items()
        }


def _resolver_cargos(cita, fecha, servicios, decisiones):
    """Revalida las opciones mostradas con la cuenta y la cita ya bloqueadas."""
    grupos = _cargos_manuales(cita, fecha, servicios)
    if grupos.keys() != decisiones.keys():
        raise ErrorDeNegocio(
            'Revisa los cargos existentes para los servicios seleccionados. La revisión requiere permiso de cobros.')
    vinculados = {}
    for servicio_id, lineas in grupos.items():
        token, seleccion = decisiones[servicio_id]
        try:
            anterior = signing.loads(token, salt=_FIRMA_CARGOS, max_age=60 * 60)
        except signing.BadSignature:
            anterior = None
        if anterior != _revision(cita, servicio_id, lineas):
            raise ErrorDeNegocio('Los cargos existentes cambiaron o la revisión venció. Verifica las opciones de nuevo.')
        if seleccion == 'nuevo':
            continue
        elegida = next((linea for linea in lineas if str(linea.cargo.pk) == seleccion), None)
        if elegida is None:
            raise ErrorDeNegocio('Elige un cargo existente o confirma un cargo adicional por cada servicio señalado.')
        if elegida.revision:
            raise ErrorDeNegocio('El cargo elegido tiene inconsistencias. Revísalo en Cuenta antes de vincularlo.')
        vinculados[servicio_id] = elegida.cargo
    return vinculados


def _monto(valor):
    try:
        return Decimal(str(valor).replace(',', '.')) if valor not in (None, '') else None
    except InvalidOperation:
        raise ErrorDeNegocio('El monto del concepto no es un número.') from None


@transaction.atomic
def registrar(*, paciente, profesional, servicios=(), otro_concepto='', otro_monto=None, notas='', cita=None,
              fecha=None, descripciones_extra=(), version_cita=None, decisiones_cargos=None):
    """
    Crea el procedimiento con un cargo por servicio (+ un concepto libre opcional) y deja atendida la cita.
    `descripciones_extra`: lo que registraron los módulos (p. ej. «Vacuna Pentavalente dosis 2»).
    """
    from apps.agenda import servicios_previstos as previstos
    from apps.agenda.models import Cita
    from apps.cobros.servicios import bloquear_cuenta, crear_cargo
    servicios = list({s.pk: s for s in servicios}.values())
    otro_concepto = (otro_concepto or '').strip()
    monto = _monto(otro_monto)
    if otro_concepto and monto is None:
        raise ErrorDeNegocio('Indica el monto del concepto (0 si no se cobra).')
    if not servicios and not otro_concepto and not descripciones_extra:
        raise ErrorDeNegocio('Elige al menos un servicio o escribe qué se hizo.')
    fecha = fecha or timezone.localdate()
    bloquear_cuenta(paciente.pk)
    plan = {}
    existentes = {}
    if cita is not None:
        cita = Cita.objects.select_for_update().get(pk=cita.pk)
        if cita.paciente_id != paciente.pk:
            raise ErrorDeNegocio('La cita es de otro paciente.')
        if not cita.activa or cita.consulta_id or cita.procedimientos.exists():
            raise ErrorDeNegocio('La cita ya no está disponible para registrar un procedimiento.')
        if version_cita is not None and version_cita != cita.actualizado_en:
            raise ErrorDeNegocio('La cita cambió. Abre de nuevo el procedimiento para revisar los servicios previstos.')
        if cita.cargos.exists() and (servicios or monto):
            raise ErrorDeNegocio('La cita ya tiene cargos. Revisa los cobros antes de registrar otros importes.')
        lineas = previstos.lineas_de(cita)
        plan = {linea.servicio_id: linea for linea in lineas} if cita.servicios_explicitos else {}
        ids = {s.pk for s in servicios}
        disponibles = previstos.catalogo_procedimiento(cita, lineas).in_bulk(ids)
        if disponibles.keys() != ids:
            raise ErrorDeNegocio('Algún servicio no está disponible para esta cita.')
        servicios = [disponibles[s.pk] for s in servicios]
        existentes = _resolver_cargos(cita, fecha, ids, decisiones_cargos or {})
    nombres = [plan.get(s.pk, s).nombre for s in servicios]
    if otro_concepto:
        nombres.append(otro_concepto)
    descripcion = ', '.join(list(descripciones_extra) + [n for n in nombres if n not in descripciones_extra])
    proc = Procedimiento.objects.create(paciente=paciente, profesional=profesional, cita=cita,
                                        fecha=fecha, descripcion=descripcion[:250],
                                        notas=notas.strip())
    for servicio in servicios:
        cargo = existentes.get(servicio.pk)
        if cargo is None:
            linea = plan.get(servicio.pk, servicio)
            cargo = crear_cargo(paciente=paciente, servicio=servicio, descripcion=linea.nombre,
                                precio_usd=linea.precio_usd, cita=cita, profesional=profesional, fecha=proc.fecha)
        else:
            cargo.cita = cita
        cargo.procedimiento = proc
        cargo.save(update_fields=['cita', 'procedimiento', 'actualizado_en'])
    if otro_concepto and monto:
        cargo = crear_cargo(paciente=paciente, descripcion=otro_concepto, precio_usd=monto, cita=cita,
                            profesional=profesional, fecha=proc.fecha)
        cargo.procedimiento = proc
        cargo.save(update_fields=['procedimiento'])
    if cita is not None and cita.estado != Cita.Estado.ATENDIDA:
        cita.estado = Cita.Estado.ATENDIDA
        cita.save(update_fields=['estado', 'actualizado_en'])
    return proc


@transaction.atomic
def anular(proc, motivo):
    from apps.cobros.models import Cargo
    from apps.cobros.servicios import anular_cargo, bloquear_cuenta
    from apps.cobros.validez_clinica import exigir_reversion_si_hay_pagos

    bloquear_cuenta(proc.paciente_id)
    proc = Procedimiento.objects.select_for_update(no_key=True).get(pk=proc.pk)
    if proc.anulado:
        raise ErrorDeNegocio('El procedimiento ya está anulado.')
    if not (motivo or '').strip():
        raise ErrorDeNegocio('Indica el motivo de la anulación.')
    exigir_reversion_si_hay_pagos(procedimiento=proc)
    for cargo in proc.cargos.exclude(estado=Cargo.Estado.ANULADO):
        anular_cargo(cargo, f'Procedimiento anulado: {motivo}')
    proc.anulado = True
    proc.motivo_anulacion = motivo.strip()[:200]
    proc.save(update_fields=['anulado', 'motivo_anulacion', 'actualizado_en'])
    return proc
