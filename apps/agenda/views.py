from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from apps.cobros import cobro_rapido
from apps.cobros.forms import CobroRapidoForm
from apps.cobros.selectors_cita import saldos_citas
from apps.configuracion import whatsapp as enlaces_whatsapp
from apps.core import auditoria
from apps.core.excepciones import ErrorDeNegocio
from apps.core.permisos import requiere, tiene_permiso
from apps.pacientes.models import Paciente

from . import contacto_whatsapp, inactividad, selectors
from . import servicios as srv
from . import servicios_previstos as previstos
from .forms import BloqueoForm, CitaForm, HorarioForm, MensajeInactividadForm, TipoCitaForm, profesionales_activos
from .models import Bloqueo, Cita, HorarioAtencion, TipoCita
from .selectors import citas_visibles as _citas_visibles
from .selectors import solo_propia as _solo_propia


def _profesionales(request):
    propio = _solo_propia(request)
    qs = profesionales_activos()
    return list(qs.filter(pk=propio.pk) if propio else qs)


def _profesional_elegido(request, profesionales):
    """?p=<id> · ?p=todos · por defecto: el propio si es profesional, si no todos."""
    propio = _solo_propia(request)
    if propio:
        return propio
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
    fecha = srv.fecha_de(request.GET.get('fecha'))
    profesionales = _profesionales(request)
    elegido = _profesional_elegido(request, profesionales)
    citas = list(_citas(fecha, fecha, elegido).select_related('tenant__configuracion').prefetch_related(
        'paciente__representantes',
        Prefetch('procedimientos', queryset=Procedimiento.objects.filter(anulado=False))))
    saldos = saldos_citas(citas)
    puede_contactar = tiene_permiso(request, 'agenda.gestionar')
    for c in citas:
        c.saldo_cita = saldos[c.pk]
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
    sugerencias = (selectors.sugerencias_inactividad(
        fecha=fecha, membresia=request.membresia, profesional=elegido if request.GET.get('p') else None)
                   if fecha == srv.hoy() and puede_contactar else ())
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
        'cumpleanos': srv.cumpleanos(fecha, request.membresia),
        'sugerencias_inactividad': sugerencias,
        'meses_inactividad': request.tenant.configuracion.recordatorio_sin_consulta_meses})


@login_required
@requiere('agenda.ver')
def horas(request):
    """Panel de horas del día para el formulario de cita (HTMX)."""
    from apps.equipo.models import PerfilProfesional
    fecha = srv.fecha_de(request.GET.get('fecha'))
    propio = _solo_propia(request)
    profesional = propio or PerfilProfesional.objects.filter(pk=request.GET.get('profesional') or 0).first()
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
    profesionales = _profesionales(request)
    elegido = _profesional_elegido(request, profesionales)
    citas = list(_citas(dias[0], dias[-1], elegido))
    return render(request, 'agenda/semana.html', {
        'titulo': 'Agenda de la semana', 'fecha': fecha, 'dias': [(d, [c for c in citas if c.fecha == d]) for d in dias],
        'anterior': dias[0] - timedelta(days=7), 'siguiente': dias[0] + timedelta(days=7), 'hoy': srv.hoy(),
        'profesionales': profesionales, 'elegido': elegido})


@login_required
@requiere('agenda.gestionar')
def cita_form(request, pk=None):
    cita = get_object_or_404(_citas_visibles(request, Cita.objects.select_related('paciente')), pk=pk) if pk else None
    if cita and not cita.activa:
        aviso = ('La cita ya fue atendida. Revisa cualquier corrección financiera en Cobros.'
                 if cita.estado == Cita.Estado.ATENDIDA
                 else 'Esta cita ya no está activa; para cambiarla, reactívala primero.')
        messages.warning(request, aviso)
        return redirect('agenda:cita', pk=cita.pk)
    inicial = {}
    if cita is None:
        inicial = {'fecha': request.GET.get('fecha') or srv.hoy(), 'hora_inicio': request.GET.get('hora'),
                   'paciente': request.GET.get('paciente'), 'lugar': request.GET.get('lugar')}
        propio = _solo_propia(request)
        profesional = ((propio.pk if propio else None) or request.GET.get('p')
                       or getattr(request.membresia.perfil_activo, 'pk', None))
        if profesional:            # quien no es médico (administración, asistente) no se propone a sí mismo
            inicial['profesional'] = profesional
    form = CitaForm(request.POST or None, instance=cita or Cita(tenant=request.tenant), initial=inicial,
                    solo=_solo_propia(request))
    exonerada_antes = bool(cita and cita.exonerada)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                cita, avisos = srv.guardar_cita(
                    form.instance, sobrecupo=form.cleaned_data.get('sobrecupo'), servicios=form.ids_servicios(),
                    version=form.cleaned_data['version_cita'],
                )
                if cita.exonerada != exonerada_antes:
                    auditoria.registrar(request, 'EDITAR' if pk else 'CREAR', cita, paciente_id=cita.paciente_id,
                                        detalle='Atención exonerada' if cita.exonerada else 'Exoneración retirada')
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
    c = get_object_or_404(_citas_visibles(request, Cita.objects.select_related(
        'paciente', 'profesional__membresia__usuario', 'tipo', 'lugar', 'consulta')), pk=pk)
    c.saldo_cita = saldos_citas([c])[c.pk]
    perfil = request.membresia.perfil_activo
    return render(request, 'agenda/cita.html', {
        'titulo': f'Cita · {c.paciente}', 'cita': c,
        'se_puede_eliminar': srv.se_puede_eliminar(c), 'servicios_previstos': previstos.lineas_de(c),
        'transiciones': [(e, Cita.Estado(e).label) for e in srv.TRANSICIONES.get(c.estado, ())
                         if e not in ('ATENDIDA',)],
        'puede_atender': bool(perfil and perfil.pk == c.profesional_id and (c.activa or c.consulta_id)
                              and tiene_permiso(request, 'consultas.crear'))})


@login_required
@requiere('agenda.gestionar')
@require_POST
def cita_estado(request, pk):
    c = get_object_or_404(_citas_visibles(request), pk=pk)
    srv.cambiar_estado(c, request.POST.get('estado'), request.POST.get('motivo', ''))
    messages.success(request, 'Estado actualizado.')
    destino = request.POST.get('volver', '')
    return redirect(destino if destino.startswith('/') and not destino.startswith('//') else f'/agenda/citas/{pk}/')


@login_required
@requiere('consultas.crear')
@require_POST
def atender(request, pk):
    c = get_object_or_404(_citas_visibles(request, Cita.objects.select_related('tipo', 'lugar', 'paciente')), pk=pk)
    try:
        consulta, creada = srv.iniciar_atencion(c, request.membresia.perfil_activo)
    except ErrorDeNegocio as e:
        messages.warning(request, str(e))
        return redirect('agenda:cita', pk=c.pk)
    if creada:
        auditoria.registrar(request, 'CREAR', consulta, paciente_id=c.paciente_id, detalle='Desde la agenda')
    return redirect('clinica:consulta_editar', pk=consulta.pk) if consulta.editable else \
        redirect('clinica:consulta', pk=consulta.pk)


@login_required
@requiere('agenda.gestionar')
@require_POST
@transaction.atomic
def cita_eliminar(request, pk):
    """Borra una cita que no se atendió (sin consulta, cobros ni procedimientos). Queda en la auditoría."""
    c = get_object_or_404(_citas_visibles(request, Cita.objects.select_for_update()), pk=pk)
    if not srv.se_puede_eliminar(c):
        messages.error(request, 'Esta cita ya se atendió o tiene cobros o procedimientos: no se puede eliminar '
                                '(puedes cancelarla).')
        return redirect('agenda:cita', pk=pk)
    fecha, profesional = c.fecha, c.profesional_id
    auditoria.registrar(request, 'ANULAR', c, paciente_id=c.paciente_id,
                        detalle=f'Cita eliminada ({c.fecha:%d/%m/%Y}, {c.get_estado_display()})')
    c.delete()
    messages.success(request, 'Cita eliminada.')
    return redirect(f'/agenda/?fecha={fecha:%Y-%m-%d}&p={profesional}')


@login_required
@requiere('agenda.gestionar')
@never_cache
@require_POST
@transaction.atomic
def recordatorio(request, pk):
    from apps.cobros.servicios import bloquear_cuenta

    accion = request.POST.get('accion')
    clave = contacto_whatsapp.clave_intento(request)
    if accion not in contacto_whatsapp.ACCIONES or (accion in contacto_whatsapp.APERTURAS and clave is None):
        return HttpResponse(status=400)
    citas = _citas_visibles(request, Cita.objects.filter(estado__in=Cita.ACTIVAS))
    cita = get_object_or_404(citas, pk=pk)
    bloquear_cuenta(cita.paciente_id)
    cita = get_object_or_404(citas.select_for_update(), pk=pk)
    url = srv.url_whatsapp(cita, bloquear=True) if cita.paciente.activo else None
    if url and accion in contacto_whatsapp.APERTURAS and contacto_whatsapp.registrar_intento(
            request, objetivo=cita, paciente_id=cita.paciente_id, clave=clave, contexto='cita'):
        srv.marcar_recordatorio(cita)
    return contacto_whatsapp.respuesta(accion, url)


@login_required
@requiere('agenda.gestionar')
@never_cache
@require_POST
@transaction.atomic
def contacto_cumpleanos(request, pk, fecha):
    accion = request.POST.get('accion')
    clave = contacto_whatsapp.clave_intento(request)
    if accion not in contacto_whatsapp.ACCIONES or (accion in contacto_whatsapp.APERTURAS and clave is None):
        return HttpResponse(status=400)
    try:
        fecha = date.fromisoformat(fecha)
    except ValueError:
        return HttpResponse(status=404)
    pacientes = srv.pacientes_cumpleanos(fecha, request.membresia)
    paciente = get_object_or_404(pacientes.select_for_update(no_key=True), pk=pk)
    url = srv.url_cumpleanos(paciente, fecha, request.tenant.configuracion.nombre_display)
    if url and accion in contacto_whatsapp.APERTURAS:
        contacto_whatsapp.registrar_intento(
            request, objetivo=paciente, paciente_id=pk, clave=clave, contexto=f'cumpleaños {fecha}')
    return contacto_whatsapp.respuesta(accion, url)


# ── Configuración de la agenda ────────────────────────────────────────────────

@login_required
@requiere('agenda.gestionar')
def horarios(request):
    profesionales = _profesionales(request)
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
    propio = _solo_propia(request)
    qs = HorarioAtencion.objects.filter(profesional=propio) if propio else HorarioAtencion.objects.all()
    h = get_object_or_404(qs, pk=pk)
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
    from django.db.models import Q
    propio = _solo_propia(request)
    form = BloqueoForm(request.POST or None, solo=propio)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Bloqueo registrado.')
        return redirect('agenda:bloqueos')
    lista = Bloqueo.objects.filter(hasta__date__gte=srv.hoy()).select_related('profesional__membresia__usuario')
    if propio:              # los suyos y los de todo el consultorio (feriados), no los de otros médicos
        lista = lista.filter(Q(profesional=propio) | Q(profesional__isnull=True))
    return render(request, 'agenda/bloqueos.html', {
        'titulo': 'Bloqueos de agenda', 'form': form, 'bloqueos': lista, 'propio': propio})


@login_required
@requiere('agenda.gestionar')
@require_POST
def bloqueo_eliminar(request, pk):
    propio = _solo_propia(request)
    get_object_or_404(Bloqueo.objects.filter(profesional=propio) if propio else Bloqueo.objects.all(), pk=pk).delete()
    return redirect('agenda:bloqueos')



@login_required
@requiere('agenda.gestionar')
@never_cache
def recordatorio_inactividad(request, pk, ultima, meses):
    if request.method not in ('GET', 'POST'):
        return HttpResponse(status=405, headers={'Allow': 'GET, POST'})
    try:
        ultima = date.fromisoformat(ultima)
    except ValueError:
        return HttpResponse(status=404)
    accion = request.POST.get('accion')
    if request.method == 'POST':
        if accion in contacto_whatsapp.ACCIONES:
            form = MensajeInactividadForm(request.POST)
            if not form.is_valid():
                return JsonResponse({'error': 'Revisa el mensaje antes de continuar.'}, status=400)
            numero = inactividad.validar_contacto(
                request=request, paciente_id=pk, ultima=ultima, meses=meses,
                token=request.POST.get('token_contacto', ''), registrar=accion in contacto_whatsapp.APERTURAS)
            url = enlaces_whatsapp.enlace(numero, form.cleaned_data['mensaje']) if numero else None
            return contacto_whatsapp.respuesta(accion, url)
        if accion in ('IGNORADO', 'ENVIADO'):
            registrado = inactividad.registrar_decision(
                request=request, paciente_id=pk, ultima=ultima, meses=meses, estado=accion,
                token=request.POST.get('token_contacto', ''))
            if not registrado:
                messages.warning(request, 'El recordatorio cambió o todavía no se registró el intento. Revisa la agenda.')
            return redirect('agenda:dia')
        if accion != 'preparar':
            return HttpResponse(status=400)

    if meses != request.tenant.configuracion.recordatorio_sin_consulta_meses:
        return redirect('agenda:dia')
    paciente = get_object_or_404(selectors.sugerencias_inactividad(fecha=srv.hoy(), membresia=request.membresia),
                                 pk=pk, ultima_asistencia=ultima)
    contacto, numero = inactividad.contacto_autorizado(paciente)
    consultorio = request.tenant.configuracion.nombre_display
    form = MensajeInactividadForm(request.POST or None, initial={
        'mensaje': f'Hola, le escribimos de {consultorio}. Si desea agendar una cita, estamos a su disposición.'
    })
    token = ''
    if numero and request.method == 'POST' and form.is_valid():
        token = inactividad.token_contacto(request=request, paciente_id=pk, ultima=ultima, meses=meses,
                                           contacto=contacto, numero=numero)
    return render(request, 'agenda/recordatorio_inactividad.html', {
        'titulo': 'Enviar recordatorio', 'paciente': paciente, 'contacto': contacto, 'autorizado': bool(numero),
        'form': form, 'token_contacto': token,
    })



@login_required
@requiere('cobros.gestionar')
@never_cache
@require_http_methods(['GET', 'POST'])
def cobrar_cita(request, pk):
    cita = get_object_or_404(_citas_visibles(request), pk=pk)
    form = CobroRapidoForm(request.POST) if request.method == 'POST' else None
    pago, advertencia = None, ''
    registrado = False
    if form is not None and form.is_valid():
        try:
            pago, registrado = cobro_rapido.registrar(
                request=request, cita=cita, **{campo: valor for campo, valor in form.cleaned_data.items()
                                               if campo != 'recibido'})
        except ErrorDeNegocio as e:
            advertencia = str(e)

    cita = get_object_or_404(_citas_visibles(request), pk=pk)
    cita.saldo_cita = saldo = saldos_citas([cita])[cita.pk]
    tasa, tasa_ref = None, None
    saldo_bs = None
    if saldo.cobrable:
        tasa, tasa_ref = cobro_rapido.tasa_actual()
        saldo_bs = cobro_rapido.maximo_bs(saldo.saldo, tasa) if tasa and tasa > 0 else None
        if pago is None and (form is None or advertencia):
            inicial = {
                'moneda': 'USD', 'metodo': 'EFECTIVO', 'monto': saldo.saldo,
                'confirmacion': cobro_rapido.confirmar(cita=cita, resumen=saldo, tasa=tasa, tasa_ref=tasa_ref,
                                                       usuario=request.user),
            }
            if advertencia:
                inicial.update({campo: form.cleaned_data[campo] for campo in ('monto', 'moneda', 'metodo', 'referencia')})
            form = CobroRapidoForm(initial=inicial)
    fragmento = request.headers.get('HX-Request') == 'true'
    return render(request, 'agenda/_cobro_cita.html' if fragmento else 'agenda/cobro_cita.html', {
        'titulo': 'Cobro rápido', 'cita': cita, 'form': form, 'pago': pago, 'registrado': registrado,
        'advertencia': advertencia, 'tasa': tasa, 'tasa_ref': tasa_ref, 'saldo_bs': saldo_bs,
        'actualizar_indicador': fragmento and request.method == 'POST',
    })
