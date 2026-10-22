from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core import auditoria
from apps.core.excepciones import ErrorDeNegocio
from apps.core.permisos import requiere, tiene_permiso

from . import selectors, servicios
from .forms import AntecedenteBaseForm, PacienteForm, RepresentanteForm
from .models import Paciente, Representante


def _paciente(request, pk):
    paciente = get_object_or_404(Paciente.objects.all(), pk=pk)
    if not selectors.puede_ver_paciente(request.membresia, paciente):
        raise PermissionDenied
    return paciente


@login_required
@requiere('pacientes.ver')
def lista(request):
    q = request.GET.get('q', '').strip()
    alcance = selectors.alcance_inicial(request.membresia, request.GET.get('ver'))
    pagina = Paginator(selectors.buscar(q, solo_activos=request.GET.get('inactivos') != '1',
                                        membresia=request.membresia, alcance=alcance), 25)
    parametros = {k: v for k, v in {'q': q, 'ver': alcance}.items() if v}
    contexto = {'titulo': 'Pacientes', 'q': q, 'pagina': pagina.get_page(request.GET.get('page')),
                'alcance': alcance, 'es_profesional': request.membresia.perfil_activo is not None,
                'puede_ver_todos': selectors.puede_ver_todos(request.membresia),
                'querystring': urlencode(parametros)}
    if request.headers.get('HX-Request'):
        return render(request, 'pacientes/_resultados.html', contexto)
    return render(request, 'pacientes/lista.html', contexto)


@login_required
@requiere('pacientes.gestionar')
def nuevo(request):
    form = PacienteForm(request.POST or None, instance=Paciente(tenant=request.tenant,
                                                                sexo=servicios.sexo_por_defecto(request)))
    form_rep = RepresentanteForm(request.POST or None, prefix='rep', opcional=True,
                                 instance=Representante(tenant=request.tenant))
    duplicado = None
    if request.method == 'POST' and form.is_valid() and form_rep.is_valid():
        rep = form_rep.instance if form_rep.cleaned_data.get('nombre') else None
        try:
            paciente = servicios.crear_paciente(paciente=form.instance, representante=rep,
                                                alergias=request.POST.get('alergias', ''))
        except servicios.PacienteDuplicado as e:
            duplicado = e.paciente
            messages.warning(request, str(e))
        except ErrorDeNegocio as e:
            messages.error(request, str(e))
        else:
            auditoria.registrar(request, 'CREAR', paciente, paciente_id=paciente.pk)
            messages.success(request, f'Paciente registrado: {paciente}.')
            if paciente.aviso:
                messages.info(request, paciente.aviso)
            siguiente = request.POST.get('next') or ''
            if siguiente.startswith('/') and not siguiente.startswith('//'):
                return redirect(f'{siguiente}{"&" if "?" in siguiente else "?"}paciente={paciente.pk}')
            despues = request.POST.get('despues')
            if despues == 'historia' and tiene_permiso(request, 'consultas.crear'):
                return redirect('clinica:consulta_nueva', paciente_pk=paciente.pk)
            if despues == 'agendar' and tiene_permiso(request, 'agenda.gestionar'):
                return redirect(f"{reverse('agenda:cita_nueva')}?paciente={paciente.pk}")
            return redirect('pacientes:detalle', pk=paciente.pk)
    return render(request, 'pacientes/form.html', {
        'titulo': 'Nuevo paciente', 'form': form, 'form_rep': form_rep, 'duplicado': duplicado, 'nuevo': True,
        'es_menor': _es_menor(form),
        'next': request.GET.get('next') or request.POST.get('next', '')})


@login_required
@requiere('pacientes.ver')
def detalle(request, pk):
    try:
        paciente = selectors.ficha(pk)
    except Paciente.DoesNotExist:
        raise Http404
    if not selectors.puede_ver_paciente(request.membresia, paciente):
        raise PermissionDenied
    ve_historia = tiene_permiso(request, 'historia.ver')
    if ve_historia:
        auditoria.registrar(request, 'VER', paciente, paciente_id=paciente.pk)
    contexto = {'titulo': paciente.nombre_completo, 'paciente': paciente, 've_historia': ve_historia,
                'antecedentes': getattr(paciente, 'antecedentes', None)}
    from apps.agenda.models import Cita
    contexto['proximas_citas'] = (Cita.objects.filter(paciente=paciente, fecha__gte=timezone.localdate(),
                                                      estado__in=Cita.ACTIVAS)
                                  .select_related('profesional__membresia__usuario').order_by('fecha', 'hora_inicio')[:5])
    if ve_historia:
        from apps.clinica.selectors import resumen_paciente
        contexto.update(resumen_paciente(request, paciente))
    from apps.clinica.views_procedimientos import puede_registrar
    contexto['puede_procedimiento'] = puede_registrar(request)
    if not ve_historia and contexto['puede_procedimiento']:      # la asistente ve los procedimientos (no la historia)
        from apps.clinica.models import Procedimiento
        contexto['procedimientos'] = Procedimiento.objects.filter(paciente=paciente).prefetch_related('cargos')[:20]
    return render(request, 'pacientes/detalle.html', contexto)


@login_required
@requiere('pacientes.gestionar')
def editar(request, pk):
    paciente = _paciente(request, pk)
    form = PacienteForm(request.POST or None, instance=paciente)
    duplicado = None
    if request.method == 'POST' and form.is_valid():
        try:
            servicios.actualizar_paciente(paciente=form.instance)
        except servicios.PacienteDuplicado as e:
            duplicado = e.paciente
            messages.warning(request, str(e))
        except ErrorDeNegocio as e:
            messages.error(request, str(e))
        else:
            auditoria.registrar(request, 'EDITAR', paciente, paciente_id=paciente.pk)
            messages.success(request, 'Datos del paciente guardados.')
            if getattr(form.instance, 'aviso', None):
                messages.info(request, form.instance.aviso)
            return redirect('pacientes:detalle', pk=pk)
    return render(request, 'pacientes/form.html', {
        'titulo': f'Editar · {paciente}', 'form': form, 'paciente': paciente, 'duplicado': duplicado,
        'es_menor': _es_menor(form)})


def _es_menor(form):
    """Con la fecha que muestra el formulario (lo escrito o lo guardado): ¿menor de 18?"""
    from apps.core import fechas
    valor = form['fecha_nacimiento'].value()
    if isinstance(valor, str):
        try:
            from datetime import date
            valor = date.fromisoformat(valor)
        except ValueError:
            return False
    anios = fechas.edad_anios(valor) if valor else None
    return anios is not None and anios < 18


@login_required
@requiere('pacientes.gestionar')
def representante(request, pk, rep_pk=None):
    paciente = _paciente(request, pk)
    instancia = (get_object_or_404(paciente.representantes.all(), pk=rep_pk) if rep_pk
                 else Representante(tenant=request.tenant, paciente=paciente))
    form = RepresentanteForm(request.POST or None, instance=instancia)
    if request.method == 'POST' and form.is_valid():
        servicios.guardar_representante(paciente=paciente, representante=form.instance)
        messages.success(request, 'Representante guardado.')
        return redirect('pacientes:detalle', pk=pk)
    return render(request, 'pacientes/representante_form.html', {
        'titulo': f'Representante · {paciente}', 'form': form, 'paciente': paciente})


@login_required
@requiere('pacientes.gestionar')
@require_POST
def representante_eliminar(request, pk, rep_pk):
    paciente = _paciente(request, pk)
    rep = get_object_or_404(paciente.representantes.all(), pk=rep_pk)
    servicios.eliminar_representante(representante=rep)
    messages.success(request, 'Representante eliminado.')
    return redirect('pacientes:detalle', pk=pk)


@login_required
@requiere('historia.ver')
def antecedentes(request, pk):
    paciente = _paciente(request, pk)
    form = AntecedenteBaseForm(request.POST or None, instance=servicios.antecedentes_de(paciente))
    if request.method == 'POST' and form.is_valid():
        form.save()
        auditoria.registrar(request, 'EDITAR', form.instance, paciente_id=paciente.pk, detalle='Antecedentes base')
        messages.success(request, 'Antecedentes guardados.')
        return redirect('pacientes:detalle', pk=pk)
    return render(request, 'pacientes/antecedentes_form.html', {
        'titulo': f'Antecedentes · {paciente}', 'form': form, 'paciente': paciente})


@login_required
@requiere('pacientes.ver')
def buscar_opciones(request):
    """HTMX: lista corta para elegir un paciente (agenda, consulta)."""
    q = request.GET.get('q', '').strip()
    alcance = 'todos' if selectors.puede_ver_todos(request.membresia) else 'mios'
    pacientes = selectors.buscar(q, membresia=request.membresia, alcance=alcance)[:12] if len(q) >= 2 else []
    return render(request, 'pacientes/_opciones.html', {'pacientes': pacientes, 'q': q})
