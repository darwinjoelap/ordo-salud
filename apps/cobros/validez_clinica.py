"""Relaciones de cargos cuyo cobro depende de una atención clínica vigente."""
from django.db.models import Exists, OuterRef, Q

from apps.clinica.models import Consulta, Procedimiento
from apps.core.excepciones import ErrorDeNegocio

from .models import CERO, Cargo

DIRECTOS = Q(consulta__isnull=True, procedimiento__isnull=True)


def cargos_invalidos():
    """Un cargo directo sin atención propia depende de los vínculos clínicos de su cita."""
    procedimientos = Procedimiento.objects.filter(cita_id=OuterRef('cita_id'), anulado=True)
    return (Cargo.objects.alias(procedimiento_anulado=Exists(procedimientos))
            .filter(Q(consulta__estado=Consulta.Estado.ANULADA) | Q(procedimiento__anulado=True)
                    | (DIRECTOS & (Q(cita__consulta__estado=Consulta.Estado.ANULADA)
                                   | Q(procedimiento_anulado=True)))))


def exigir_reversion_si_hay_pagos(*, consulta=None, procedimiento=None):
    if consulta is not None:
        filtro = Q(consulta=consulta) | (DIRECTOS & Q(cita__consulta=consulta))
    else:
        filtro = Q(procedimiento=procedimiento)
        if procedimiento.cita_id:
            filtro |= DIRECTOS & Q(cita_id=procedimiento.cita_id)
    pagos = Q(aplicaciones__pago__anulado=False, aplicaciones__monto_usd__gt=CERO)
    if Cargo.objects.filter(filtro & pagos).exists():
        raise ErrorDeNegocio('La atención tiene pagos aplicados. Gestiona la reversión o el ajuste autorizado en Cuenta.')
