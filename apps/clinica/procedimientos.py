"""Procedimientos sin consulta (ADR-040): registrar (cargos + cita atendida + extras de módulos) y anular."""
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from apps.core.excepciones import ErrorDeNegocio

from .models import Procedimiento


def _monto(valor):
    try:
        return Decimal(str(valor).replace(',', '.')) if valor not in (None, '') else None
    except InvalidOperation:
        raise ErrorDeNegocio('El monto del concepto no es un número.') from None


@transaction.atomic
def registrar(*, paciente, profesional, servicios=(), otro_concepto='', otro_monto=None, notas='', cita=None,
              fecha=None, descripciones_extra=()):
    """
    Crea el procedimiento con un cargo por servicio (+ un concepto libre opcional) y deja atendida la cita.
    `descripciones_extra`: lo que registraron los módulos (p. ej. «Vacuna Pentavalente dosis 2»).
    """
    from apps.agenda.models import Cita
    from apps.cobros.servicios import crear_cargo
    servicios = list(servicios)
    otro_concepto = (otro_concepto or '').strip()
    monto = _monto(otro_monto)
    if otro_concepto and monto is None:
        raise ErrorDeNegocio('Indica el monto del concepto (0 si no se cobra).')
    if not servicios and not otro_concepto and not descripciones_extra:
        raise ErrorDeNegocio('Elige al menos un servicio o escribe qué se hizo.')
    if cita is not None:
        cita = Cita.objects.select_for_update().get(pk=cita.pk)
        if cita.paciente_id != paciente.pk:
            raise ErrorDeNegocio('La cita es de otro paciente.')
    nombres = [s.nombre for s in servicios] + ([otro_concepto] if otro_concepto else [])
    descripcion = ', '.join(list(descripciones_extra) + [n for n in nombres if n not in descripciones_extra])
    proc = Procedimiento.objects.create(paciente=paciente, profesional=profesional, cita=cita,
                                        fecha=fecha or timezone.localdate(), descripcion=descripcion[:250],
                                        notas=notas.strip())
    for s in servicios:
        cargo = crear_cargo(paciente=paciente, servicio=s, descripcion=s.nombre, precio_usd=s.precio_usd, cita=cita,
                            profesional=profesional, fecha=proc.fecha)
        cargo.procedimiento = proc
        cargo.save(update_fields=['procedimiento'])
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
    from apps.cobros.servicios import anular_cargo
    if proc.anulado:
        raise ErrorDeNegocio('El procedimiento ya está anulado.')
    if not (motivo or '').strip():
        raise ErrorDeNegocio('Indica el motivo de la anulación.')
    for cargo in proc.cargos.exclude(estado=Cargo.Estado.ANULADO):
        anular_cargo(cargo, f'Procedimiento anulado: {motivo}')
    proc.anulado = True
    proc.motivo_anulacion = motivo.strip()[:200]
    proc.save(update_fields=['anulado', 'motivo_anulacion', 'actualizado_en'])
