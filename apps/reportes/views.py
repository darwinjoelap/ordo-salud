from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import render

from apps.core import auditoria
from apps.core.pdf import nombre_archivo, respuesta_pdf
from apps.core.permisos import tiene_permiso

from . import exportar, selectors


def _contexto(request):
    if not selectors.puede_ver_reportes(request):
        raise PermissionDenied
    f = selectors.filtros_de(request)
    return f, selectors.resumen(f)


def _query(f):
    datos = {'desde': f.desde.isoformat(), 'hasta': f.hasta.isoformat()}
    if f.todo_el_consultorio and f.profesional is not None:
        datos['profesional'] = f.profesional.pk
    if f.especialidad is not None:
        datos['especialidad'] = f.especialidad.pk
    if f.diagnostico:
        datos['diagnostico'] = f.diagnostico
    return urlencode(datos)


@login_required
def tablero(request):
    f, datos = _contexto(request)
    from apps.equipo.models import PerfilProfesional
    gestion = tiene_permiso(request, 'reportes.ver')
    return render(request, 'reportes/tablero.html', {
        'titulo': 'Reportes', **datos, 'query': _query(f), 'gestion': gestion,
        've_finanzas': gestion or tiene_permiso(request, 'cobros.gestionar') or not f.todo_el_consultorio,
        'profesionales': PerfilProfesional.objects.select_related('membresia__usuario') if gestion else [],
        'especialidades': request.tenant.especialidades.all() if gestion else [],
        'rangos': selectors.rangos_rapidos(), 'pestanas': selectors.pestanas(request, 'general'),
        'query_sin_dx': selectors.query_sin(request, 'diagnostico')})


@login_required
def pdf(request):
    f, datos = _contexto(request)
    auditoria.registrar(request, 'EXPORTAR', 'reportes', detalle=f'Reporte PDF {f.periodo_texto}')
    return respuesta_pdf(exportar.pdf(request.tenant, datos), 'reporte', f.desde, f.hasta)


@login_required
def excel(request):
    f, datos = _contexto(request)
    auditoria.registrar(request, 'EXPORTAR', 'reportes', detalle=f'Reporte Excel {f.periodo_texto}')
    contenido = exportar.excel(request.tenant, datos, selectors.detalle_consultas(f))
    r = HttpResponse(contenido, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    r['Content-Disposition'] = f'attachment; filename="{nombre_archivo("reporte", f.desde, f.hasta, extension="xlsx")}"'
    return r
