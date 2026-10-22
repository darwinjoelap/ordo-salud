from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core import auditoria
from apps.core.excepciones import ErrorDeNegocio
from apps.core.permisos import requiere, tiene_permiso
from apps.pacientes.models import Paciente

from . import servicios as srv
from .forms import BloqueoForm, CitaForm, HorarioForm, TipoCitaForm, profesionales_activos
from .models import Bloqueo, Cita, HorarioAtencion, TipoCita


def _profesional_elegido(request, profesionales):
    """?p=<id> · ?p=todos · por defecto: el propio si es profesional, si no todos."""
    valor = request.GET.get('p')
    if valor == 'todos':
        return None
    if valor:
        return next((p for p in profesionales if str(p.pk) == valor), None)
    perfil = request.membresia.perfil_activo if request.membresia else None
    if perfil and len(profesionales) > 1:
        return perfil
    return profesionales[0] if len(profesionales) == 1 else None


def _citas(fecha_desde, fecha_hasta, profesional=None):
    qs = (Cita.objects.filter(fecha__range=(fecha_desde, fecha_hasta))
          .select_related('paciente', 'profesional__membresia__usuario', 'tipo', 'lugar')
          .order_by('fecha', 'hora_inicio'))
    return qs.filter(profesional=profesional) if profesional else qs


@login_required
@requiere('agenda.ver')
def dia(request):
    """Agenda del día como en Pediae: contadores, citas con hora, sin hora, atendidos sin cita y turnos libres."""
    from django.db.models import Prefetch

    from apps.clinica.models import Consulta, Procedimiento
    from apps.cobros.models import Cargo
    fecha = srv.fecha_de(request.GET.get('fecha'))
    profesionales = list(profesionales_activos())
    elegido = _profesional_elegido(request, profesionales)
    citas = list(_citas(fecha, fecha, elegido).prefetch_related(
        Prefetch('cargos', queryset=Cargo.objects.exclude(estado=Cargo.Estado.ANULADO)),
        Prefetch('procedimientos', queryset=Procedimiento.objects.filter(anulado=False))))
    for c in citas:
        cargos = list(c.cargos.all())
        c.cobro = None if not cargos else ('pagado' if all(x.estado == Cargo.Estado.PAGADO or x.exonerado
                                                           for x in cargos) else 'pendiente')
    consultas_sin_cita = (Consulta.objects.filter(fecha_hora__date=fecha, cita__isnull=True)
                          .exclude(estado=Consulta.Estado.ANULADA).select_related('paciente', 'profesional'))
    procedimientos_sin_cita = (Procedimiento.objects.filter(fecha=fecha, cita__isnull=True, anulado=False)
                               .select_related('paciente', 'profesional').prefetch_related('cargos'))
    if elegido:
        consultas_sin_cita = consultas_sin_cita.filter(profesional=elegido)
        procedimientos_sin_cita = procedimientos_sin_cita.filter(profesional=elegido)
    libres = []
    if fecha >= srv.hoy():
        for p in ([elegido] if elegido else profesionales):
            horas_libres = srv.turnos_libres(p, fecha)
            if horas_libres:
                libres.append({'profesional': p, 'horas': horas_libres})
    return render(request, 'agenda/dia.html', {
        'titulo': 'Agenda', 'fecha': fecha, 'anterior': fecha - timedelta(days=1), 'siguiente': fecha + timedelta(days=1),
        'hoy': srv.hoy(), 'profesionales': profesionales, 'elegido': elegido,
        'con_hora': [c for c in citas if c.hora_inicio], 'sin_hora': [c for c in citas if not c.hora_inicio],
        'resumen': {'total': sum(1 for c in citas if c.estado not in ('CANCELADA',)),
                    'atendidas': sum(1 for c in citas if c.estado == 'ATENDIDA'),
                    'pendientes': sum(1 for c in citas if c.activa)},
        'consultas_sin_cita': list(consultas_sin_cita), 'procedimientos_sin_cita': list(procedimientos_sin_cita),
        'libres': libres, 'mostrar_profesional': elegido is None and len(profesionales) > 1,
        'perfil': request.membresia.perfil_activo,
        'puede_procedimiento': tiene_permiso(request, 'consultas.crear') or tiene_permiso(request, 'cobros.gestionar'),
        'bloqueos': Bloqueo.objects.filter(desde__date__lte=fecha, hasta__date__gte=fecha),
        'cumpleanos': srv.cumpleanos(fecha, request.membresia)})


@login_required
@requiere('agenda.ver')
def horas(request):
    """Panel de horas del día para el formulario de cita (HTMX)."""
    from apps.equipo.models import PerfilProfesional
    fecha = srv.fecha_de(request.GET.get('fecha'))
    profesional = PerfilProfesional.objects.filter(pk=request.GET.get('profesional') or 0).first()
    if profesional is None:
        return render(request, 'agenda/_horas.html', {'sin_profesional': True})
    excluir = request.GET.get('excluir')
    return render(request, 'agenda/_horas.html', {
        'fecha': fecha, 'profesional': profesional,
        **srv.horas_del_dia(profesional, fecha, excluir=int(excluir) if (excluir or '').isdigit() else None)})


@login_required
@requiere('agenda.ver')
def semana(request):
    fecha = srv.fecha_de(request.GET.get('fecha'))
    dias = srv.semana_de(fecha)
    profesionales = list(profesionales_activos())
    elegido = _profesional_elegido(request, profesionales)
    citas = list(_citas(dias[0], dias[-1], elegido))
    return render(request, 'agenda/semana.html', {
        'titulo': 'Agenda de la semana', 'fecha': fecha, 'dias': [(d, [c for c in citas if c.fecha == d]) for d in dias],
        'anterior': dias[0] - timedelta(days=7), 'siguiente': dias[0] + timedelta(days=7), 'hoy': srv.hoy(),
        'profesionales': profesionales, 'elegido': elegido})


@login_required
@requiere('agenda.gestionar')
def cita_form(request, pk=None):
    cita = get_object_or_404(Cita.objects.select_related('paciente'), pk=pk) if pk else None
    if cita and not cita.activa:
        messages.warning(request, 'Esta cita ya no está activa; para cambiarla, reactívala primero.')
        return redirect('agenda:cita', pk=cita.pk)
    inicial = {}
    if cita is None:
        inicial = {'fecha': request.GET.get('fecha') or srv.hoy(), 'hora_inicio': request.GET.get('hora'),
                   'profesional': request.GET.get('p') or getattr(request.membresia.perfil_activo, 'pk', None),
                   'paciente': request.GET.get('paciente'), 'lugar': request.GET.get('lugar')}
    form = CitaForm(request.POST or None, instance=cita or Cita(tenant=request.tenant), initial=inicial)
    if request.method == 'POST' and form.is_valid():
        try:
            cita, avisos = srv.guardar_cita(form.instance, sobrecupo=form.cleaned_data.get('sobrecupo'))
        except ErrorDeNegocio as e:
            messages.error(request, str(e))
        else:
            for a in avisos:
                messages.warning(request, a)
            messages.success(request, 'Cita guardada.')
            return redirect(f'/agenda/?fecha={cita.fecha:%Y-%m-%d}&p={cita.profesional_id}')
    paciente = None
    pid = form['paciente'].value()
    if pid:
        paciente = Paciente.objects.filter(pk=pid).first()
    return render(request, 'agenda/cita_form.html', {
        'titulo': 'Editar cita' if cita else 'Nueva cita', 'form': form, 'cita': cita, 'paciente': paciente})


@login_required
@requiere('agenda.ver')
def cita(request, pk):
    c = get_object_or_404(Cita.objects.select_related('paciente', 'profesional__membresia__usuario', 'tipo', 'lugar',
                                                      'consulta'), pk=pk)
    perfil = request.membresia.perfil_activo
    return render(request, 'agenda/cita.html', {
        'titulo': f'Cita · {c.paciente}', 'cita': c, 'whatsapp': srv.url_whatsapp(c),
        'transiciones': [(e, Cita.Estado(e).label) for e in srv.TRANSICIONES.get(c.estado, ())
                         if e not in ('ATENDIDA',)],
        'puede_atender': bool(perfil and perfil.pk == c.profesional_id and (c.activa or c.consulta_id)
                              and tiene_permiso(request, 'consultas.crear'))})


@login_required
@requiere('agenda.gestionar')
@require_POST
def cita_estado(request, pk):
    c = get_object_or_404(Cita.objects.all(), pk=pk)
    srv.cambiar_estado(c, request.POST.get('estado'), request.POST.get('motivo', ''))
    messages.success(request, 'Estado actualizado.')
    destino = request.POST.get('volver', '')
    return redirect(destino if destino.startswith('/') and not destino.startswith('//') else f'/agenda/citas/{pk}/')


@login_required
@requiere('consultas.crear')
@require_POST
def atender(request, pk):
    c = get_object_or_404(Cita.objects.select_related('tipo', 'lugar', 'paciente'), pk=pk)
    consulta = srv.atender(c, request.membresia.perfil_activo)
    auditoria.registrar(request, 'CREAR', consulta, paciente_id=c.paciente_id, detalle='Desde la agenda')
    return redirect('clinica:consulta_editar', pk=consulta.pk) if consulta.editable else \
        redirect('clinica:consulta', pk=consulta.pk)


@login_required
@requiere('agenda.gestionar')
@require_POST
def recordatorio(request, pk):
    c = get_object_or_404(Cita.objects.select_related('paciente'), pk=pk)
    url = srv.url_whatsapp(c)
    if not url:
        messages.error(request, 'El paciente (o su representante) no tiene teléfono.')
        return redirect('agenda:cita', pk=pk)
    srv.marcar_recordatorio(c)
    return redirect(url)


# ── Configuración de la agenda ────────────────────────────────────────────────

@login_required
@requiere('agenda.gestionar')
def horarios(request):
    profesionales = list(profesionales_activos())
    elegido = _profesional_elegido(request, profesionales) or (profesionales[0] if profesionales else None)
    form = HorarioForm(request.POST or None)
    if request.method == 'POST' and form.is_valid() and elegido:
        for dia_semana in form.cleaned_data['dias']:
            HorarioAtencion.objects.create(profesional=elegido, dia_semana=int(dia_semana),
                                           lugar=form.cleaned_data['lugar'], hora_inicio=form.cleaned_data['hora_inicio'],
                                           hora_fin=form.cleaned_data['hora_fin'],
                                           duracion_turno_min=form.cleaned_data['duracion_turno_min'])
        messages.success(request, 'Horario agregado.')
        return redirect(f'/agenda/horarios/?p={elegido.pk}')
    return render(request, 'agenda/horarios.html', {
        'titulo': 'Horarios de atención', 'profesionales': profesionales, 'elegido': elegido, 'form': form,
        'horarios': HorarioAtencion.objects.filter(profesional=elegido).select_related('lugar') if elegido else []})


@login_required
@requiere('agenda.gestionar')
@require_POST
def horario_eliminar(request, pk):
    h = get_object_or_404(HorarioAtencion.objects.all(), pk=pk)
    p = h.profesional_id
    h.delete()
    return redirect(f'/agenda/horarios/?p={p}')


@login_required
@requiere('tenant.configurar')
def tipos(request, pk=None):
    tipo = get_object_or_404(TipoCita.objects.all(), pk=pk) if pk else None
    form = TipoCitaForm(request.POST or None, instance=tipo, tenant=request.tenant)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Tipo de cita guardado.')
        return redirect('agenda:tipos')
    return render(request, 'agenda/tipos.html', {
        'titulo': 'Tipos de cita', 'form': form, 'tipo': tipo,
        'tipos': TipoCita.objects.select_related('especialidad', 'servicio', 'plantilla')})


@login_required
@requiere('agenda.gestionar')
def bloqueos(request):
    form = BloqueoForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Bloqueo registrado.')
        return redirect('agenda:bloqueos')
    return render(request, 'agenda/bloqueos.html', {
        'titulo': 'Bloqueos de agenda', 'form': form,
        'bloqueos': Bloqueo.objects.filter(hasta__date__gte=srv.hoy()).select_related('profesional__membresia__usuario')})


@login_required
@requiere('agenda.gestionar')
@require_POST
def bloqueo_eliminar(request, pk):
    get_object_or_404(Bloqueo.objects.all(), pk=pk).delete()
    return redirect('agenda:bloqueos')
