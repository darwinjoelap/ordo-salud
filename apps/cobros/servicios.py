"""
Reglas de cobro (Fase 09). Toda escritura de cargos y pagos pasa por aquí.
"""
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.excepciones import ErrorDeNegocio
from apps.core.tenancy import tenant_actual

from .models import CERO, Cargo, Pago, PagoAplicado
from .saldos import lectura_financiera, lineas_de_cargos, pagos_con_saldo

DOS = Decimal('0.01')


def _tasa(*, sin_cache=False):
    """(Bs por divisa, 'USD'|'EUR') con la tasa que eligió el consultorio (ADR-059), o (None, 'USD')."""
    from apps.tasas.servicios import tasa_vigente
    t = tasa_vigente(tenant_actual(), sin_cache=sin_cache)
    return (t.valor, t.moneda) if t else (None, 'USD')


def bloquear_cuenta(paciente_id):
    """Bloqueo común. Orden: paciente, cita si aplica, atención clínica y filas financieras."""
    from apps.pacientes.models import Paciente

    return Paciente.objects.select_for_update(no_key=True).get(pk=paciente_id)


def equivalente_usd(monto, moneda, tasa):
    if moneda == Pago.Moneda.BS:
        if not tasa:
            raise ErrorDeNegocio('No hay tasa del día: cárgala antes de registrar un pago en bolívares.')
        return (monto / tasa).quantize(DOS, rounding=ROUND_HALF_UP)
    return monto


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
    bloquear_cuenta(paciente.pk)
    recibidos = Pago.objects.select_for_update().filter(paciente=paciente, anulado=False).order_by('fecha', 'id')
    pagos = [p for p in pagos_con_saldo(recibidos) if p.sin_aplicar > CERO]
    if not pagos:
        return
    pendientes = Cargo.objects.select_for_update(of=('self',)).filter(
        paciente=paciente, estado__in=[Cargo.Estado.PENDIENTE, Cargo.Estado.PARCIAL]).order_by('fecha', 'id')
    cargos = [linea.cargo for linea in lineas_de_cargos(pendientes) if linea.exigible]
    for pago in pagos:
        disponible = pago.sin_aplicar
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
    bloquear_cuenta(paciente.pk)
    if cita is not None:
        from apps.agenda.models import Cita

        cita = Cita.objects.select_for_update().filter(pk=cita.pk, paciente=paciente).first()
        if cita is None:
            raise ErrorDeNegocio('El cargo no corresponde a la cita del paciente.')
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
    bloquear_cuenta(paciente.pk)
    monto = Decimal(monto).quantize(DOS)
    if monto <= 0:
        raise ErrorDeNegocio('El monto debe ser mayor que cero.')
    tasa_ref = 'USD'
    if tasa:
        tasa = Decimal(tasa)
    else:
        tasa, tasa_ref = _tasa()
    monto_usd = equivalente_usd(monto, moneda, tasa)
    pago = Pago.objects.create(paciente=paciente, fecha=fecha or timezone.localdate(), moneda=moneda, monto=monto,
                               tasa=tasa, tasa_ref=tasa_ref, monto_usd=monto_usd, metodo=metodo, referencia=referencia[:60],
                               notas=notas[:200])
    conciliar(paciente)
    return pago


@transaction.atomic
def anular_cargo(cargo, motivo):
    bloquear_cuenta(cargo.paciente_id)
    cargo = Cargo.objects.select_for_update().get(pk=cargo.pk)
    if cargo.pagado_usd > CERO:
        raise ErrorDeNegocio('El cargo tiene pagos aplicados: anula primero el pago (o haz un descuento).')
    cargo.estado = Cargo.Estado.ANULADO
    cargo.motivo_anulacion = (motivo or '')[:200]
    cargo.save(update_fields=['estado', 'motivo_anulacion', 'actualizado_en'])


@transaction.atomic
def anular_pago(pago, motivo):
    bloquear_cuenta(pago.paciente_id)
    pago = Pago.objects.select_for_update().get(pk=pago.pk)
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


@lectura_financiera()
def estado_cuenta(paciente):
    qs = Cargo.objects.filter(paciente=paciente).select_related('profesional__membresia__usuario')
    lineas = list(lineas_de_cargos(qs))
    pagos = pagos_con_saldo(Pago.objects.filter(paciente=paciente))
    return {'lineas': lineas, 'cargos': [linea.cargo for linea in lineas], 'pagos': pagos,
            'total_cargos': sum((linea.cargo.monto_usd for linea in lineas), CERO),
            'total_pagos': sum((p.monto_usd for p in pagos if not p.anulado), CERO),
            'saldo': sum((linea.exigible for linea in lineas), CERO),
            'saldo_revision': sum((linea.saldo for linea in lineas if linea.revision), CERO),
            'hay_revision': any(linea.revision for linea in lineas),
            'a_favor': sum((p.sin_aplicar for p in pagos), CERO)}


@lectura_financiera()
def informe_por_cobrar():
    por_exigir, por_revisar = {}, {}
    for linea in lineas_de_cargos(Cargo.objects.filter(paciente__tenant=tenant_actual()).select_related('paciente')):
        if not linea.exigible and not linea.revision:
            continue
        grupo = por_revisar if linea.revision else por_exigir
        grupo.setdefault(linea.cargo.paciente, []).append(linea)

    def filas(grupo):
        return sorted([(paciente, sum((linea.saldo for linea in lineas), CERO), [linea.cargo for linea in lineas])
                       for paciente, lineas in grupo.items()], key=lambda f: -f[1])

    exigibles, revision = filas(por_exigir), filas(por_revisar)
    return {'filas': exigibles, 'revision': revision,
            'total': sum((f[1] for f in exigibles), CERO), 'total_revision': sum((f[1] for f in revision), CERO)}


def por_cobrar():
    return informe_por_cobrar()['filas']


@lectura_financiera()
def caja(fecha):
    pagos = pagos_con_saldo(Pago.objects.filter(fecha=fecha, anulado=False, paciente__tenant=tenant_actual())
                            .select_related('paciente', 'creado_por'))
    resumen = {}
    for p in pagos:
        r = resumen.setdefault((p.metodo, p.moneda), {'metodo': p.get_metodo_display(), 'moneda': p.moneda,
                                                     'monto': CERO, 'usd': CERO, 'n': 0})
        r['monto'] += p.monto
        r['usd'] += p.monto_usd
        r['n'] += 1
    return {'pagos': pagos, 'resumen': sorted(resumen.values(), key=lambda r: r['metodo']),
            'total_usd': sum((p.monto_usd for p in pagos), CERO), 'sin_aplicar': sum((p.sin_aplicar for p in pagos), CERO),
            'cargos_usd': sum((c.monto_usd for c in Cargo.objects.filter(fecha=fecha)), CERO)}
