"""Registro de pagos dirigidos exclusivamente a los cargos de una cita."""
import hashlib
import json
from decimal import ROUND_HALF_UP
from uuid import UUID, uuid4

from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.agenda.models import Cita
from apps.core import auditoria
from apps.core.excepciones import ErrorDeNegocio

from . import servicios as srv
from .models import CERO, CobroRapidoCita, Pago, PagoAplicado
from .selectors_cita import saldos_citas

FIRMA = 'cobros.cita.confirmacion'
VIGENCIA = 30 * 60


def _huella(datos):
    return hashlib.sha256(json.dumps(datos, sort_keys=True, default=str).encode()).hexdigest()


def _revision(cita, resumen, tasa, tasa_ref):
    return _huella([cita.estado, resumen.estado, tasa, tasa_ref, [
        [linea.cargo.pk, linea.cargo.estado, linea.cargo.descripcion, linea.cargo.monto_usd,
         linea.pagado, linea.saldo] for linea in resumen.lineas
    ]])


def tasa_actual():
    tasa, referencia = srv._tasa(sin_cache=True)
    return (tasa, referencia) if tasa and tasa > CERO else (None, referencia)


def maximo_bs(saldo, tasa):
    return (saldo * tasa).quantize(srv.DOS, rounding=ROUND_HALF_UP)


def confirmar(*, cita, resumen, tasa, tasa_ref, usuario):
    return signing.dumps({
        'tenant': cita.tenant_id, 'cita': cita.pk, 'usuario': usuario.pk,
        'clave': str(uuid4()), 'revision': _revision(cita, resumen, tasa, tasa_ref),
    }, salt=FIRMA)


def _abrir_confirmacion(token, cita, usuario, *, max_age=None):
    try:
        datos = signing.loads(token, salt=FIRMA, max_age=max_age)
        if (datos['tenant'], datos['cita'], datos['usuario']) != (cita.tenant_id, cita.pk, usuario.pk):
            raise signing.BadSignature
        return UUID(datos['clave']), datos['revision']
    except (signing.BadSignature, KeyError, ValueError) as e:
        raise ErrorDeNegocio(
            'La confirmación venció o no corresponde a esta cita. Revisa los datos y confirma de nuevo.'
        ) from e


@transaction.atomic
def registrar(*, request, cita, monto, moneda, metodo, referencia, confirmacion):
    clave, revision = _abrir_confirmacion(confirmacion, cita, request.user)
    paciente = srv.bloquear_cuenta(cita.paciente_id)
    cita = Cita.objects.select_for_update().filter(pk=cita.pk, paciente=paciente).first()
    if cita is None:
        raise ErrorDeNegocio('Esta cita ya no está disponible.')
    importe = monto.quantize(srv.DOS)
    huella = _huella([cita.pk, request.user.pk, importe, moneda, metodo, referencia])
    anterior = CobroRapidoCita.objects.filter(clave=clave).select_related('pago').first()
    if anterior is not None:
        if anterior.huella != huella:
            raise ErrorDeNegocio('Esta confirmación ya se usó para un cobro distinto. Revisa el saldo antes de continuar.')
        return anterior.pago, False

    _abrir_confirmacion(confirmacion, cita, request.user, max_age=VIGENCIA)
    resumen = saldos_citas([cita])[cita.pk]
    tasa, tasa_ref = tasa_actual()
    if _revision(cita, resumen, tasa, tasa_ref) != revision:
        raise ErrorDeNegocio('Cambió el saldo, los conceptos o la tasa. Revisa los datos y confirma de nuevo.')
    if not resumen.cobrable:
        raise ErrorDeNegocio('La cita no tiene saldo exigible para cobro rápido. Revisa Cuenta.')
    if moneda not in Pago.Moneda.values or metodo not in Pago.Metodo.values or importe <= CERO:
        raise ErrorDeNegocio('Indica un importe positivo, una moneda y un método válidos.')
    monto_usd = srv.equivalente_usd(importe, moneda, tasa)
    if monto_usd <= CERO:
        raise ErrorDeNegocio('El importe equivale a menos de un céntimo de dólar.')
    if monto_usd > resumen.saldo or (moneda == Pago.Moneda.BS and importe > maximo_bs(resumen.saldo, tasa)):
        raise ErrorDeNegocio('El importe supera el saldo exigible de esta cita.')
    try:
        Pago._meta.get_field('monto_usd').run_validators(monto_usd)
    except ValidationError as e:
        raise ErrorDeNegocio('El importe en dólares excede el máximo permitido para un pago.') from e

    pago = Pago.objects.create(paciente=paciente, monto=importe, moneda=moneda, monto_usd=monto_usd,
                               tasa=tasa, tasa_ref=tasa_ref, metodo=metodo, referencia=referencia,
                               fecha=timezone.localdate(), creado_por=request.user)
    CobroRapidoCita.objects.create(cita=cita, pago=pago, clave=clave, huella=huella, creado_por=request.user)
    auditoria.registrar(request, 'CREAR', pago, paciente_id=paciente.pk, detalle=f'Cobro rápido · cita {cita.pk}')
    restante = monto_usd
    for linea in resumen.lineas:
        aplicado = min(restante, linea.saldo)
        if aplicado <= CERO:
            continue
        aplicacion = PagoAplicado.objects.create(pago=pago, cargo=linea.cargo, monto_usd=aplicado)
        srv._actualizar_estado(linea.cargo)
        auditoria.registrar(request, 'CREAR', aplicacion, paciente_id=paciente.pk,
                            detalle=f'Cita {cita.pk} · pago {pago.pk} · cargo {linea.cargo.pk} · USD {aplicado:.2f}')
        restante -= aplicado
        if not restante:
            break
    if restante:
        raise ErrorDeNegocio('No se pudo aplicar el importe completo a esta cita. Revisa el saldo.')
    return pago, True
