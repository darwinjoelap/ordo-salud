"""
Reglas de cobro (Fase 09). Toda escritura de cargos y pagos pasa por aquí.
"""
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.excepciones import ErrorDeNegocio
from apps.core.tenancy import tenant_actual

from .models import CERO, Cargo, Pago, PagoAplicado

DOS = Decimal('0.01')


def _tasa():
    """(Bs por divisa, 'USD'|'EUR') con la tasa que eligió el consultorio (ADR-059), o (None, 'USD')."""
    from apps.tasas.servicios import tasa_vigente
    t = tasa_vigente(tenant_actual())
    return (t.valor, t.moneda) if t else (None, 'USD')


def _actualizar_estado(cargo):
    if cargo.estado == Cargo.Estado.ANULADO:
        return
    pagado = cargo.pagado_usd
    if cargo.monto_usd == CERO or pagado >= cargo.monto_usd:
        nuevo = Cargo.Estado.PAGADO
    elif pagado > CERO:
        nuevo = Cargo.Estado.PARCIAL
    else:
        nuevo = Cargo.Estado.PENDIENTE
    if nuevo != cargo.estado:
        cargo.estado = nuevo
        cargo.save(update_fields=['estado', 'actualizado_en'])


@transaction.atomic
def conciliar(paciente):
    """Aplica el dinero sin aplicar del paciente a sus cargos pendientes, del más viejo al más nuevo."""
    pagos = [p for p in Pago.objects.select_for_update().filter(paciente=paciente, anulado=False).order_by('fecha', 'id')
             if p.sin_aplicar_usd > CERO]
    if not pagos:
        return
    cargos = list(Cargo.objects.select_for_update().filter(
        paciente=paciente, estado__in=[Cargo.Estado.PENDIENTE, Cargo.Estado.PARCIAL]).order_by('fecha', 'id'))
    for pago in pagos:
        disponible = pago.sin_aplicar_usd
        for cargo in cargos:
            if disponible <= CERO:
                break
            saldo = cargo.saldo_usd
            if saldo <= CERO:
                continue
            monto = min(saldo, disponible)
            PagoAplicado.objects.create(pago=pago, cargo=cargo, monto_usd=monto)
            disponible -= monto
            _actualizar_estado(cargo)


@transaction.atomic
def crear_cargo(*, paciente, descripcion, precio_usd, descuento_usd=CERO, exonerado=False, servicio=None,
                consulta=None, cita=None, profesional=None, fecha=None):
    precio_usd = Decimal(precio_usd).quantize(DOS)
    descuento_usd = Decimal(descuento_usd or 0).quantize(DOS)
    if precio_usd < 0 or descuento_usd < 0 or descuento_usd > precio_usd:
        raise ErrorDeNegocio('El descuento no puede ser mayor que el precio.')
    tasa, tasa_ref = _tasa()
    cargo = Cargo.objects.create(
        paciente=paciente, descripcion=(descripcion or (servicio.nombre if servicio else 'Servicio'))[:200],
        precio_usd=precio_usd, descuento_usd=descuento_usd, exonerado=exonerado, servicio=servicio,
        costo_usd=servicio.costo_usd if servicio else None, consulta=consulta, cita=cita,
        profesional=profesional or (consulta.profesional if consulta else None),
        fecha=fecha or timezone.localdate(), tasa=tasa, tasa_ref=tasa_ref)
    _actualizar_estado(cargo)
    conciliar(paciente)
    return cargo


@transaction.atomic
def registrar_pago(*, paciente, monto, moneda, metodo, referencia='', notas='', fecha=None, tasa=None):
    monto = Decimal(monto).quantize(DOS)
    if monto <= 0:
        raise ErrorDeNegocio('El monto debe ser mayor que cero.')
    tasa_ref = 'USD'
    if tasa:
        tasa = Decimal(tasa)
    else:
        tasa, tasa_ref = _tasa()
    if moneda == Pago.Moneda.BS:
        if not tasa:
            raise ErrorDeNegocio('No hay tasa del día: cárgala antes de registrar un pago en bolívares.')
        monto_usd = (monto / tasa).quantize(DOS, rounding=ROUND_HALF_UP)
    else:
        monto_usd = monto
    pago = Pago.objects.create(paciente=paciente, fecha=fecha or timezone.localdate(), moneda=moneda, monto=monto,
                               tasa=tasa, tasa_ref=tasa_ref, monto_usd=monto_usd, metodo=metodo, referencia=referencia[:60],
                               notas=notas[:200])
    conciliar(paciente)
    return pago


@transaction.atomic
def anular_cargo(cargo, motivo):
    if cargo.pagado_usd > CERO:
        raise ErrorDeNegocio('El cargo tiene pagos aplicados: anula primero el pago (o haz un descuento).')
    cargo.estado = Cargo.Estado.ANULADO
    cargo.motivo_anulacion = (motivo or '')[:200]
    cargo.save(update_fields=['estado', 'motivo_anulacion', 'actualizado_en'])


@transaction.atomic
def anular_pago(pago, motivo):
    if pago.anulado:
        raise ErrorDeNegocio('El pago ya está anulado.')
    if len((motivo or '').strip()) < 3:
        raise ErrorDeNegocio('Indica el motivo de la anulación.')
    cargos = [a.cargo for a in pago.aplicaciones.select_related('cargo')]
    pago.aplicaciones.all().delete()
    pago.anulado = True
    pago.motivo_anulacion = motivo[:200]
    pago.save(update_fields=['anulado', 'motivo_anulacion', 'actualizado_en'])
    for cargo in cargos:
        _actualizar_estado(cargo)
    conciliar(pago.paciente)


def estado_cuenta(paciente):
    cargos = list(Cargo.objects.filter(paciente=paciente).select_related('servicio', 'consulta', 'profesional')
                  .prefetch_related('aplicaciones__pago'))
    pagos = list(Pago.objects.filter(paciente=paciente).prefetch_related('aplicaciones'))
    total_cargos = sum((c.monto_usd for c in cargos), CERO)
    total_pagos = sum((p.monto_usd for p in pagos if not p.anulado), CERO)
    return {'cargos': cargos, 'pagos': pagos, 'total_cargos': total_cargos, 'total_pagos': total_pagos,
            'saldo': total_cargos - total_pagos, 'a_favor': max(total_pagos - total_cargos, CERO)}


def por_cobrar():
    """Pacientes con saldo pendiente: [(paciente, saldo_usd, cargos_pendientes)]."""
    from apps.pacientes.models import Paciente
    pendientes = (Cargo.objects.filter(estado__in=[Cargo.Estado.PENDIENTE, Cargo.Estado.PARCIAL])
                  .select_related('paciente'))
    por_paciente = {}
    for c in pendientes:
        por_paciente.setdefault(c.paciente_id, []).append(c)
    pacientes = Paciente.objects.in_bulk(por_paciente.keys())
    filas = [(pacientes[pid], sum((c.saldo_usd for c in cs), CERO), cs) for pid, cs in por_paciente.items()]
    return sorted([f for f in filas if f[1] > CERO], key=lambda f: -f[1])


def caja(fecha):
    pagos = list(Pago.objects.filter(fecha=fecha, anulado=False).select_related('paciente', 'creado_por'))
    resumen = {}
    for p in pagos:
        r = resumen.setdefault((p.metodo, p.moneda), {'metodo': p.get_metodo_display(), 'moneda': p.moneda,
                                                     'monto': CERO, 'usd': CERO, 'n': 0})
        r['monto'] += p.monto
        r['usd'] += p.monto_usd
        r['n'] += 1
    return {'pagos': pagos, 'resumen': sorted(resumen.values(), key=lambda r: r['metodo']),
            'total_usd': sum((p.monto_usd for p in pagos), CERO),
            'cargos_usd': sum((c.monto_usd for c in Cargo.objects.filter(fecha=fecha)), CERO)}
