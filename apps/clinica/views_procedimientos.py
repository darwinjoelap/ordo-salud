"""Procedimientos sin consulta (ADR-040): registrar desde la ficha o la agenda, y anular."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_POST

from apps.core import auditoria
from apps.core.excepciones import ErrorDeNegocio
from apps.core.permisos import tiene_permiso
from apps.pacientes.models import Paciente
from apps.pacientes.selectors import puede_ver_paciente, puede_ver_todos

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
    from apps.agenda import servicios_previstos as previstos
    from apps.agenda.models import Cita
    from apps.cobros.servicios import bloquear_cuenta
    if not puede_registrar(request):
        raise PermissionDenied
    paciente = get_object_or_404(Paciente.objects.all(), pk=paciente_pk)
    if not puede_ver_paciente(request.membresia, paciente):
        raise PermissionDenied
    cita_id = request.POST.get('cita') or request.GET.get('cita')
    cita = None
    perfil = request.membresia.perfil_activo
    if cita_id:
        citas = Cita.objects.filter(paciente=paciente).select_related('tipo')
        if not puede_ver_todos(request.membresia):
            citas = citas.filter(profesional=perfil)
        if not cita_id.isdigit():
            raise Http404
        cita = get_object_or_404(citas, pk=cita_id)
        if not cita.activa or cita.consulta_id or cita.procedimientos.exists():
            messages.warning(request, 'La cita ya no está disponible para registrar un procedimiento.')
            return redirect('agenda:cita', pk=cita.pk)
    lineas = previstos.lineas_de(cita) if cita else []
    plan = {linea.servicio_id: linea for linea in lineas} if cita and cita.servicios_explicitos else {}
    servicios = list(previstos.catalogo_procedimiento(cita, lineas).order_by('nombre'))
    puede_conciliar = cita is not None and not cita.exonerada and tiene_permiso(request, 'cobros.gestionar')
    fecha = timezone.localdate()
    extras = _extras(request, paciente)
    if request.method == 'POST':
        pedidos = set(request.POST.getlist('servicios'))
        elegidos = [s for s in servicios if str(s.pk) in pedidos]
        try:
            if {str(s.pk) for s in elegidos} != pedidos:
                raise ErrorDeNegocio('Algún servicio no está disponible.')
            version = request.POST.get('version_cita')
            try:
                version_cita = parse_datetime(version) if cita and version else None
            except ValueError:
                version_cita = None
            if cita and version and version_cita is None:
                raise ErrorDeNegocio('No se pudo verificar la versión de la cita. Vuelve a abrir el procedimiento.')
            decisiones = {}
            if puede_conciliar:
                for servicio in elegidos:
                    seleccion = request.POST.get(f'cargo_{servicio.pk}')
                    if seleccion:
                        decisiones[servicio.pk] = (request.POST.get(f'revision_{servicio.pk}', ''), seleccion)
            with transaction.atomic():
                bloquear_cuenta(paciente.pk)
                hechos = []
                for x in extras:
                    hechos += x['def'].guardar(request, paciente, request.POST, fecha) or []
                proc = srv.registrar(
                    paciente=paciente, profesional=perfil or (cita.profesional if cita else None), servicios=elegidos,
                    otro_concepto=request.POST.get('otro_concepto', ''), otro_monto=request.POST.get('otro_monto'),
                    notas=request.POST.get('notas', ''), cita=cita, fecha=fecha, descripciones_extra=hechos,
                    version_cita=version_cita, decisiones_cargos=decisiones)
                vinculados = [seleccion for _, seleccion in decisiones.values() if seleccion != 'nuevo']
                for cargo in proc.cargos.filter(pk__in=vinculados):
                    auditoria.registrar(request, 'EDITAR', cargo, paciente_id=paciente.pk,
                                        detalle=f'Cargo vinculado al procedimiento {proc.pk} y a la cita {cita.pk}.')
                auditoria.registrar(request, 'CREAR', proc, paciente_id=paciente.pk, detalle=proc.descripcion)
        except ErrorDeNegocio as e:
            messages.error(request, str(e))
        else:
            saldo = proc.saldo_usd
            estado = f' · ${saldo:.2f} por cobrar' if saldo else (' · Pagado' if proc.total_usd else '')
            messages.success(request, f'Procedimiento registrado: {proc.descripcion}{estado}.')
            return redirect(_volver(request, paciente))
    preseleccion = {str(linea.servicio_id) for linea in lineas}
    if request.method == 'POST':
        preseleccion = set(request.POST.getlist('servicios'))
    revisiones = srv.opciones_cargos(cita, fecha, [s.pk for s in servicios]) if puede_conciliar else {}
    opciones = [{'servicio': s, 'nombre': plan.get(s.pk, s).nombre, 'precio': plan.get(s.pk, s).precio_usd,
                 'revision': revisiones.get(s.pk)} for s in servicios]
    return render(request, 'clinica/procedimiento_form.html', {
        'titulo': f'Procedimiento · {paciente}', 'paciente': paciente, 'cita': cita, 'servicios': opciones,
        'preseleccion': preseleccion, 'extras': extras, 'datos': request.POST,
        'volver': request.POST.get('volver') or request.GET.get('volver', '')})


@login_required
@require_POST
def anular(request, pk):
    if not puede_registrar(request):
        raise PermissionDenied
    proc = get_object_or_404(Procedimiento.objects.select_related('paciente'), pk=pk)
    try:
        proc = srv.anular(proc, request.POST.get('motivo', ''))
    except ErrorDeNegocio as e:
        messages.error(request, str(e))
    else:
        auditoria.registrar(request, 'ANULAR', proc, paciente_id=proc.paciente_id, detalle=proc.motivo_anulacion)
        messages.success(request, 'Procedimiento anulado (y sus cargos).')
    return redirect(_volver(request, proc.paciente))
