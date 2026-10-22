"""Procedimientos sin consulta (ADR-040): registrar desde la ficha o la agenda, y anular."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core import auditoria
from apps.core.excepciones import ErrorDeNegocio
from apps.core.permisos import tiene_permiso
from apps.pacientes.models import Paciente
from apps.pacientes.selectors import puede_ver_paciente

from . import procedimientos as srv
from . import registro
from .models import Procedimiento


def puede_registrar(request):
    return tiene_permiso(request, 'consultas.crear') or tiene_permiso(request, 'cobros.gestionar')


def _extras(request, paciente):
    salida = []
    for extra in registro.extras_procedimiento():
        ctx = extra.contexto(request, paciente)
        if ctx is not None:
            salida.append({'def': extra, 'ctx': ctx})
    return salida


def _volver(request, paciente):
    destino = request.POST.get('volver') or request.GET.get('volver') or ''
    return destino if destino.startswith('/') and not destino.startswith('//') else f'/pacientes/{paciente.pk}/'


@login_required
def nuevo(request, paciente_pk):
    from apps.agenda.models import Cita
    from apps.cobros.models import Servicio
    if not puede_registrar(request):
        raise PermissionDenied
    paciente = get_object_or_404(Paciente.objects.all(), pk=paciente_pk)
    if not puede_ver_paciente(request.membresia, paciente):
        raise PermissionDenied
    cita_id = request.POST.get('cita') or request.GET.get('cita')
    cita = Cita.objects.filter(pk=cita_id, paciente=paciente).select_related('tipo').first() if cita_id else None
    servicios = list(Servicio.objects.filter(activo=True).order_by('nombre'))
    extras = _extras(request, paciente)
    perfil = request.membresia.perfil_activo
    if request.method == 'POST':
        elegidos = [s for s in servicios if str(s.pk) in request.POST.getlist('servicios')]
        try:
            with transaction.atomic():
                hechos = []
                fecha = timezone.localdate()
                for x in extras:
                    hechos += x['def'].guardar(request, paciente, request.POST, fecha) or []
                proc = srv.registrar(
                    paciente=paciente, profesional=perfil or (cita.profesional if cita else None), servicios=elegidos,
                    otro_concepto=request.POST.get('otro_concepto', ''), otro_monto=request.POST.get('otro_monto'),
                    notas=request.POST.get('notas', ''), cita=cita, fecha=fecha, descripciones_extra=hechos)
        except ErrorDeNegocio as e:
            messages.error(request, str(e))
        else:
            auditoria.registrar(request, 'CREAR', proc, paciente_id=paciente.pk, detalle=proc.descripcion)
            total = f' · ${proc.total_usd:.2f} por cobrar' if proc.total_usd else ''
            messages.success(request, f'Procedimiento registrado: {proc.descripcion}{total}.')
            return redirect(_volver(request, paciente))
    preseleccion = {str(cita.tipo.servicio_id)} if cita and cita.tipo and cita.tipo.servicio_id else set()
    if request.method == 'POST':
        preseleccion = set(request.POST.getlist('servicios'))
    return render(request, 'clinica/procedimiento_form.html', {
        'titulo': f'Procedimiento · {paciente}', 'paciente': paciente, 'cita': cita, 'servicios': servicios,
        'preseleccion': preseleccion, 'extras': extras, 'datos': request.POST,
        'volver': request.GET.get('volver', '')})


@login_required
@require_POST
def anular(request, pk):
    if not puede_registrar(request):
        raise PermissionDenied
    proc = get_object_or_404(Procedimiento.objects.select_related('paciente'), pk=pk)
    try:
        srv.anular(proc, request.POST.get('motivo', ''))
    except ErrorDeNegocio as e:
        messages.error(request, str(e))
    else:
        auditoria.registrar(request, 'ANULAR', proc, paciente_id=proc.paciente_id, detalle=proc.motivo_anulacion)
        messages.success(request, 'Procedimiento anulado (y sus cargos).')
    return redirect(_volver(request, proc.paciente))
