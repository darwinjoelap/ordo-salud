"""Lectura de saldos a partir de los cargos y sus aplicaciones históricas."""
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from itertools import batched

from django.db import connection, transaction
from django.db.models import Count, Exists, F, OuterRef, Q, Subquery, Sum

from apps.agenda.models import Cita

from .models import CERO, Cargo, PagoAplicado
from .validez_clinica import cargos_invalidos

MISMO_TITULAR = Q(tenant_id=F('pago__tenant_id'), cargo__tenant_id=F('pago__tenant_id'),
                  cargo__paciente_id=F('pago__paciente_id'))


@contextmanager
def lectura_financiera():
    """Un informe ve un solo instante. Dentro de una escritura rige el bloqueo de su transacción."""
    exterior = not connection.in_atomic_block
    with transaction.atomic():
        if exterior and connection.vendor == 'postgresql':
            with connection.cursor() as cursor:
                cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        yield


@dataclass
class LineaCargo:
    cargo: Cargo
    citas: set
    pagado: Decimal
    saldo: Decimal
    revision: bool

    @property
    def exigible(self):
        return CERO if self.revision else self.saldo


def _aplicaciones(cargos):
    """Detecta cruces incluso en otra aplicación del mismo pago. Solo devuelve importes del titular."""
    por_cargo = defaultdict(lambda: CERO)
    malos = set()
    ids = {c.pk: c for c in cargos}
    aplicaciones = list(PagoAplicado.todos.filter(cargo_id__in=ids).values(
        'cargo_id', 'monto_usd', 'tenant_id', 'pago_id', 'pago__tenant_id', 'pago__paciente_id',
        'pago__anulado', 'pago__monto_usd'))
    pagos = PagoAplicado.todos.filter(pago_id__in={a['pago_id'] for a in aplicaciones})
    totales = {pk: (total, invalidas) for pk, total, invalidas in pagos.values('pago_id')
               .annotate(total=Sum('monto_usd'), invalidas=Count('pk', filter=~MISMO_TITULAR))
               .values_list('pago_id', 'total', 'invalidas')}
    for a in aplicaciones:
        cargo = ids[a['cargo_id']]
        if (a['pago_id'] not in totales or a['tenant_id'] != cargo.tenant_id or a['pago__tenant_id'] != cargo.tenant_id
                or a['pago__anulado'] or a['pago__paciente_id'] != cargo.paciente_id or a['monto_usd'] <= CERO):
            malos.add(cargo.pk)
            continue
        por_cargo[cargo.pk] += a['monto_usd']
        total, invalidas = totales[a['pago_id']]
        if invalidas or total > a['pago__monto_usd']:
            malos.add(cargo.pk)
    return por_cargo, malos


def _linea(cargo, pagado, revision):
    consulta, proc = cargo.consulta, cargo.procedimiento
    citas = [c for c in (cargo.cita, getattr(consulta, 'cita', None), proc.cita if proc else None) if c]
    ids = {c.pk for c in citas}
    titular = (cargo.tenant_id, cargo.paciente_id)
    if any((obj.tenant_id, obj.paciente_id) != titular for obj in (consulta, proc, *citas) if obj):
        revision = True
    if len(ids) > 1 or any((consulta and c.consulta_id != consulta.pk) or (proc and proc.cita_id != c.pk) for c in citas):
        revision = True
    saldo = max(CERO, cargo.monto_usd - pagado)
    if saldo and any(c.estado in (Cita.Estado.CANCELADA, Cita.Estado.NO_ASISTIO) for c in citas):
        revision = True
    if cargo.estado != Cargo.Estado.ANULADO:
        esperado = Cargo.Estado.PAGADO if not saldo else Cargo.Estado.PARCIAL if pagado else Cargo.Estado.PENDIENTE
        revision |= cargo.invalido or cargo.estado != esperado
    return LineaCargo(cargo, ids, pagado, saldo, revision or pagado > cargo.monto_usd)


def lineas_de_cargos(qs):
    """El llamador mantiene una lectura consistente o el bloqueo del paciente mientras consume el iterador."""
    campos = [f.name for f in Cargo._meta.fields]
    # La clasificación solo necesita identidad y estado de la atención, incluso en el informe de todo el consultorio.
    campos.extend(['consulta__tenant', 'consulta__paciente', 'procedimiento__tenant', 'procedimiento__paciente'])
    for ruta in ('cita', 'consulta__cita', 'procedimiento__cita'):
        campos.extend(f'{ruta}__{campo}' for campo in ('tenant', 'paciente', 'estado', 'consulta'))
    qs = (qs.annotate(invalido=Exists(cargos_invalidos().filter(pk=OuterRef('pk'))))
          .select_related('cita', 'consulta__cita', 'procedimiento__cita').only(*campos))
    for lote in batched(qs.iterator(chunk_size=400), 400, strict=False):
        pagados, invalidas = _aplicaciones(lote)
        for cargo in lote:
            yield _linea(cargo, pagados[cargo.pk], cargo.pk in invalidas)


def pagos_con_saldo(qs):
    """Importe sin destino calculado en USD al valor del asiento original."""
    # Inspeccionar solo relaciones de cada pago ya acotado. Una relación cruzada requiere revisión.
    aplicaciones = PagoAplicado.todos.filter(pago_id=OuterRef('pk'))
    total = aplicaciones.values('pago_id').annotate(total=Sum('monto_usd')).values('total')
    pagos = list(qs.annotate(asignado=Subquery(total), cruce=Exists(aplicaciones.exclude(MISMO_TITULAR))))
    for pago in pagos:
        asignado = pago.asignado or CERO
        pago.revision = pago.cruce or asignado > pago.monto_usd or (pago.anulado and asignado > CERO)
        pago.sin_aplicar = CERO if pago.anulado or pago.revision else pago.monto_usd - asignado
    return pagos
