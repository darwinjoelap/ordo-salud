"""Estado financiero y relaciones explícitas de una cita."""
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Q

from apps.agenda.models import Cita
from apps.core.tenancy import tenant_actual

from .models import CERO, Cargo
from .saldos import lectura_financiera, lineas_de_cargos


@dataclass
class SaldoCita:
    estado: str
    lineas: list
    saldo: Decimal

    @property
    def cobrable(self):
        return self.estado in ('pendiente', 'abonado')


@lectura_financiera()
def saldos_citas(citas):
    """Resuelve el lote por IDs y conserva una sola línea por cargo."""
    tenant = tenant_actual()
    por_id = {c.pk: c for c in citas if tenant is not None and c.tenant_id == tenant.pk}
    if not por_id:
        return {}
    por_consulta = {c.consulta_id: c.pk for c in por_id.values() if c.consulta_id}
    filtro = Q(cita_id__in=por_id) | Q(consulta_id__in=por_consulta) | Q(procedimiento__cita_id__in=por_id)

    # Solo se consultan identificadores enlazados explícitamente para detectar una relación cruzada corrupta.
    cruzados = Cargo.todos.filter(filtro).exclude(tenant=tenant).values_list(
        'cita_id', 'consulta_id', 'procedimiento__cita_id')
    revisar = {pk for directa, consulta, procedimiento in cruzados
               for pk in (directa, por_consulta.get(consulta), procedimiento) if pk in por_id}
    cargos = Cargo.objects.filter(filtro).order_by('fecha', 'pk')
    lineas = defaultdict(list)
    for linea in lineas_de_cargos(cargos):
        for pk in linea.citas & por_id.keys():
            if linea.revision:
                revisar.add(pk)
            else:
                lineas[pk].append(linea)
    return {pk: _resumen(cita, lineas[pk], pk in revisar) for pk, cita in por_id.items()}


def _resumen(cita, lineas, revisar):
    saldo = sum((linea.saldo for linea in lineas), CERO)
    if revisar or (saldo > CERO and cita.estado in (Cita.Estado.CANCELADA, Cita.Estado.NO_ASISTIO)):
        return SaldoCita('revision', lineas, saldo)
    if saldo:
        estado = 'abonado' if any(linea.pagado for linea in lineas) else 'pendiente'
    elif any(linea.pagado for linea in lineas):
        estado = 'pagado'
    elif any(linea.cargo.exonerado and linea.cargo.estado != Cargo.Estado.ANULADO for linea in lineas):
        estado = 'exonerado'
    else:
        estado = 'sin_cargo'
    return SaldoCita(estado, lineas, saldo)
