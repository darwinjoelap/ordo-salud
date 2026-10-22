"""
Reportes (Fase 11). Solo lectura: arma las cifras de un período con filtros de profesional y especialidad.
Alcance: titular/administrador ven todo el consultorio (reportes.ver); el médico, solo lo suyo (reportes.propios).
"""
from collections import Counter, OrderedDict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Min, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.core.fechas import edad_anios, sumar_meses
from apps.core.permisos import tiene_permiso

CERO = Decimal('0.00')
MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
GRUPOS_EDAD = [('Menor de 1 año', 0, 0), ('1 a 5 años', 1, 5), ('6 a 11 años', 6, 11), ('12 a 17 años', 12, 17),
               ('18 a 39 años', 18, 39), ('40 a 64 años', 40, 64), ('65 años o más', 65, 200)]


@dataclass
class Filtros:
    desde: date
    hasta: date
    profesional: object = None          # PerfilProfesional o None (= todos)
    especialidad: object = None         # Especialidad o None
    todo_el_consultorio: bool = True    # False = el médico ve solo lo suyo

    @property
    def periodo_texto(self):
        return f'{self.desde:%d/%m/%Y} al {self.hasta:%d/%m/%Y}'


def rangos_rapidos(hoy=None):
    hoy = hoy or timezone.localdate()
    inicio_mes = hoy.replace(day=1)
    mes_pasado_fin = inicio_mes - timedelta(days=1)
    return [('Este mes', inicio_mes, hoy), ('Mes pasado', mes_pasado_fin.replace(day=1), mes_pasado_fin),
            ('Últimos 3 meses', sumar_meses(inicio_mes, -2), hoy), ('Este año', hoy.replace(month=1, day=1), hoy)]


def _fecha(texto, defecto):
    try:
        return date.fromisoformat(texto)
    except (TypeError, ValueError):
        return defecto


def puede_ver_reportes(request):
    return tiene_permiso(request, 'reportes.ver') or tiene_permiso(request, 'reportes.propios')


def filtros_de(request):
    from apps.equipo.models import PerfilProfesional
    hoy = timezone.localdate()
    desde = _fecha(request.GET.get('desde'), hoy.replace(day=1))
    hasta = _fecha(request.GET.get('hasta'), hoy)
    if hasta < desde:
        desde, hasta = hasta, desde
    if tiene_permiso(request, 'reportes.ver'):
        pk = request.GET.get('profesional')
        profesional = PerfilProfesional.objects.filter(pk=pk).first() if pk and pk.isdigit() else None
        esp = request.GET.get('especialidad')
        especialidad = request.tenant.especialidades.filter(pk=esp).first() if esp and esp.isdigit() else None
        return Filtros(desde, hasta, profesional, especialidad, todo_el_consultorio=True)
    return Filtros(desde, hasta, request.membresia.perfil_activo, None, todo_el_consultorio=False)


def _aplicar(qs, f, campo_prof='profesional', campo_esp='especialidad'):
    if f.profesional is not None:
        qs = qs.filter(**{campo_prof: f.profesional})
    if f.especialidad is not None:
        qs = qs.filter(**{campo_esp: f.especialidad})
    return qs


def consultas_de(f):
    from apps.clinica.models import Consulta
    qs = Consulta.objects.filter(fecha_hora__date__range=(f.desde, f.hasta)).exclude(estado=Consulta.Estado.ANULADA)
    return _aplicar(qs, f)


def _meses(desde, hasta):
    salida, actual = [], desde.replace(day=1)
    while actual <= hasta:
        salida.append(actual)
        actual = sumar_meses(actual, 1)
    return salida


def _etiqueta_mes(d):
    return f'{MESES[d.month - 1]} {d:%y}'


def _barras(pares):
    """[(etiqueta, valor)] → [{'etiqueta', 'valor', 'pct'}] con el % respecto al mayor (para barras CSS)."""
    mayor = max((float(v) for _, v in pares), default=0) or 1
    return [{'etiqueta': e, 'valor': v, 'pct': round(float(v) * 100 / mayor, 1)} for e, v in pares]


def resumen(f):
    from apps.agenda.models import Cita
    from apps.clinica.models import Consulta

    consultas = consultas_de(f)
    total_consultas = consultas.count()
    pacientes_ids = set(consultas.values_list('paciente_id', flat=True))

    # Pacientes nuevos: su PRIMERA consulta (con este profesional/especialidad, si hay filtro) cae en el período
    base = _aplicar(Consulta.objects.exclude(estado=Consulta.Estado.ANULADA), f)
    primeras = base.values('paciente_id').annotate(primera=Min('fecha_hora'))
    nuevos = sum(1 for p in primeras if f.desde <= timezone.localtime(p['primera']).date() <= f.hasta)

    por_tipo = Counter(dict(consultas.values_list('tipo').annotate(n=Count('id'))))
    tipos = _barras([(Consulta.Tipo(t).label, n) for t, n in por_tipo.most_common()])

    # Agenda
    citas = _aplicar(Cita.objects.filter(fecha__range=(f.desde, f.hasta)), f)
    estados = Counter(dict(citas.values_list('estado').annotate(n=Count('id'))))
    atendidas, no_asistio = estados.get('ATENDIDA', 0), estados.get('NO_ASISTIO', 0)
    finalizadas = atendidas + no_asistio
    agenda = {
        'total': sum(estados.values()), 'atendidas': atendidas, 'no_asistio': no_asistio,
        'canceladas': estados.get('CANCELADA', 0),
        'pendientes': sum(estados.get(e, 0) for e in Cita.ACTIVAS),
        'tasa_asistencia': round(atendidas * 100 / finalizadas, 1) if finalizadas else None,
        'sin_cita': total_consultas - Cita.objects.filter(consulta__in=consultas).count(),
        'estados': _barras([(Cita.Estado(e).label, n) for e, n in estados.most_common()]),
    }

    # Morbilidad (CIE-10)
    morbilidad = morbilidad_de(consultas)

    # Pacientes atendidos: sexo y edad
    from apps.pacientes.models import Paciente
    pacientes = list(Paciente.objects.filter(pk__in=pacientes_ids).only('sexo', 'fecha_nacimiento'))
    sexos = Counter(p.get_sexo_display() if p.sexo else 'Sin dato' for p in pacientes)
    edades = OrderedDict((g[0], 0) for g in GRUPOS_EDAD)
    sin_edad = 0
    for p in pacientes:
        anios = edad_anios(p.fecha_nacimiento, f.hasta)
        if anios is None:
            sin_edad += 1
            continue
        for nombre, mini, maxi in GRUPOS_EDAD:
            if mini <= anios <= maxi:
                edades[nombre] += 1
                break
    if sin_edad:
        edades['Sin fecha de nacimiento'] = sin_edad

    # Por mes
    meses = _meses(f.desde, f.hasta)
    c_mes = {m.date() if hasattr(m, 'date') else m: n for m, n in
             consultas.annotate(m=TruncMonth('fecha_hora')).values_list('m').annotate(n=Count('id'))}
    a_mes = dict(citas.filter(estado='ATENDIDA').annotate(m=TruncMonth('fecha'))
             .values_list('m').annotate(n=Count('id')))
    finanzas = finanzas_de(f)
    mensual = []
    for m in meses:
        mensual.append({'mes': _etiqueta_mes(m), 'consultas': c_mes.get(m, 0), 'citas_atendidas': a_mes.get(m, 0),
                        'cobrado': finanzas['por_mes'].get(m, CERO)})
    mayor_c = max((x['consultas'] for x in mensual), default=0) or 1
    mayor_i = max((float(x['cobrado']) for x in mensual), default=0) or 1
    for x in mensual:
        x['pct_consultas'] = round(x['consultas'] * 100 / mayor_c, 1)
        x['pct_cobrado'] = round(float(x['cobrado']) * 100 / mayor_i, 1)

    return {
        'filtros': f, 'consultas': total_consultas, 'pacientes_atendidos': len(pacientes_ids),
        'pacientes_nuevos': nuevos, 'controles': total_consultas - por_tipo.get('PRIMERA', 0),
        'tipos': tipos, 'agenda': agenda, 'morbilidad': morbilidad,
        'sexos': _barras(sexos.most_common()), 'mostrar_sexo': _sexo_relevante(sexos),
        'edades': _barras([(k, v) for k, v in edades.items() if v]),
        'mensual': mensual, 'finanzas': finanzas,
        'por_profesional': por_profesional(f) if f.todo_el_consultorio and f.profesional is None else [],
    }


def morbilidad_de(consultas, limite=15):
    """Diagnósticos más frecuentes (CIE-10 o texto) de esas consultas, como barras."""
    from apps.clinica.models import DiagnosticoConsulta
    diagnosticos = (DiagnosticoConsulta.objects.filter(consulta__in=consultas)
                    .values('codigo', 'descripcion').annotate(n=Count('id')).order_by('-n', 'codigo')[:limite])
    return _barras([(f"{d['codigo']} · {d['descripcion']}".strip(' ·'), d['n']) for d in diagnosticos])


def _sexo_relevante(sexos):
    """El reporte por sexo solo se muestra si hay al menos dos sexos con peso (en GO no tiene sentido)."""
    total = sum(n for k, n in sexos.items() if k != 'Sin dato')
    return total > 0 and sum(1 for k, n in sexos.items() if k != 'Sin dato' and n * 100 / total >= 5) >= 2


def pestanas(request, activa):
    """Reportes fijos («General») + uno por cada especialidad del consultorio con reporte propio."""
    from django.urls import reverse

    from apps.clinica import registro
    query = '&'.join(f'{k}={request.GET[k]}' for k in ('desde', 'hasta', 'profesional') if request.GET.get(k))
    sufijo = f'?{query}' if query else ''
    salida = [{'codigo': 'general', 'titulo': 'General', 'icono': 'bi-bar-chart-line',
               'url': reverse('reportes:tablero') + sufijo, 'activa': activa == 'general',
               'descripcion': 'Actividad, agenda, enfermedades, edades e ingresos'}]
    codigos = set(request.tenant.especialidades.values_list('codigo', flat=True))
    for codigo in sorted(codigos):
        esp = registro.especialidad(codigo)
        for r in (esp.reportes if esp else []):
            titulo = esp.nombre if len(esp.reportes) == 1 else r.titulo
            salida.append({'codigo': r.codigo, 'titulo': titulo, 'icono': r.icono, 'url': reverse(r.url) + sufijo,
                           'activa': activa == r.codigo, 'descripcion': r.descripcion or r.titulo})
    return salida


def finanzas_de(f):
    """Cobrado = pagos aplicados a cargos del período/filtros (así se puede atribuir a cada profesional)."""
    from apps.cobros.models import Cargo, PagoAplicado
    cargos = _aplicar(Cargo.objects.filter(fecha__range=(f.desde, f.hasta)).exclude(estado=Cargo.Estado.ANULADO), f,
                      campo_esp='consulta__especialidad')
    facturado = sum((c.monto_usd for c in cargos), CERO)
    costo = sum((c.costo_usd or CERO for c in cargos if not c.exonerado), CERO)
    aplicados = _aplicar(PagoAplicado.objects.filter(pago__fecha__range=(f.desde, f.hasta), pago__anulado=False), f,
                         campo_prof='cargo__profesional', campo_esp='cargo__consulta__especialidad')
    cobrado = aplicados.aggregate(t=Sum('monto_usd'))['t'] or CERO
    metodos = {}
    for metodo, moneda, usd in aplicados.values_list('pago__metodo', 'pago__moneda', 'monto_usd'):
        clave = (metodo, moneda)
        metodos[clave] = metodos.get(clave, CERO) + usd
    from apps.cobros.models import Pago
    nombres = dict(Pago.Metodo.choices)
    por_metodo = _barras([(f"{nombres.get(m, m)} ({'Bs' if mo == 'BS' else 'USD'})", v)
                          for (m, mo), v in sorted(metodos.items(), key=lambda x: -x[1])])
    por_mes = dict(aplicados.annotate(m=TruncMonth('pago__fecha')).values_list('m')
               .annotate(t=Sum('monto_usd')))
    pendientes = _aplicar(Cargo.objects.filter(estado__in=[Cargo.Estado.PENDIENTE, Cargo.Estado.PARCIAL]), f,
                          campo_esp='consulta__especialidad')
    por_cobrar = sum((c.saldo_usd for c in pendientes), CERO)
    exonerados = cargos.filter(exonerado=True).count()
    return {'facturado': facturado, 'cobrado': cobrado, 'costo': costo, 'ingreso_real': cobrado - costo,
            'por_cobrar': por_cobrar, 'por_metodo': por_metodo, 'por_mes': por_mes, 'exonerados': exonerados}


def por_profesional(f):
    from apps.agenda.models import Cita
    from apps.cobros.models import PagoAplicado
    from apps.equipo.models import PerfilProfesional
    consultas = consultas_de(f)
    c = dict(consultas.values_list('profesional').annotate(n=Count('id')))
    p = dict(consultas.values_list('profesional').annotate(n=Count('paciente', distinct=True)))
    a = dict(_aplicar(Cita.objects.filter(fecha__range=(f.desde, f.hasta), estado='ATENDIDA'), f)
             .values_list('profesional').annotate(n=Count('id')))
    cob = dict(PagoAplicado.objects.filter(pago__fecha__range=(f.desde, f.hasta), pago__anulado=False)
               .values_list('cargo__profesional').annotate(t=Sum('monto_usd')))
    filas = []
    for perfil in PerfilProfesional.objects.select_related('membresia__usuario', 'especialidad'):
        fila = {'profesional': perfil, 'consultas': c.get(perfil.pk, 0), 'pacientes': p.get(perfil.pk, 0),
                'citas_atendidas': a.get(perfil.pk, 0), 'cobrado': cob.get(perfil.pk) or CERO}
        if fila['consultas'] or fila['citas_atendidas'] or fila['cobrado']:
            filas.append(fila)
    return sorted(filas, key=lambda x: -x['consultas'])


def detalle_consultas(f):
    """Filas para el Excel: una por consulta."""
    return (consultas_de(f).select_related('paciente', 'profesional__membresia__usuario', 'especialidad')
            .order_by('fecha_hora'))
