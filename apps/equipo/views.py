from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.core.middleware import SESION_TENANT
from apps.core.permisos import Rol, requiere
from apps.core.subdominios import enlace

from . import servicios
from .forms import AgregarForm, PerfilProfesionalForm
from .models import Membresia, PerfilProfesional


def _miembros(request):
    # El soporte de la plataforma no aparece ni se gestiona desde el equipo
    return (Membresia.objects.filter(tenant=request.tenant, usuario__is_superuser=False)
            .select_related('usuario', 'perfil', 'perfil__especialidad'))


@login_required
def seleccionar(request):
    """Elegir con qué consultorio trabajar (usuarios con varias membresías)."""
    siguiente = request.GET.get('next') or request.POST.get('next') or '/'
    if not url_has_allowed_host_and_scheme(siguiente, {request.get_host()}):
        siguiente = '/'
    if request.method == 'POST':
        try:
            tenant_id = int(request.POST.get('tenant'))
        except (TypeError, ValueError):
            raise Http404
        if not any(m.tenant_id == tenant_id for m in request.membresias):
            raise Http404
        request.session[SESION_TENANT] = tenant_id
        return redirect(siguiente)
    if not request.membresias:
        return redirect('equipo:sin_tenant')
    return render(request, 'equipo/seleccionar.html', {'titulo': 'Elige un consultorio', 'siguiente': siguiente})


@login_required
def sin_tenant(request):
    if request.membresias:
        return redirect('core:inicio')
    suspendidos = [m.tenant for m in Membresia.objects.filter(usuario=request.user, activa=True)
                   .select_related('tenant') if not m.tenant.esta_activo]
    return render(request, 'equipo/sin_tenant.html', {'titulo': 'Sin consultorio asignado',
                                                      'suspendidos': suspendidos})


@login_required
@requiere('usuarios.gestionar')
def lista(request):
    actor = request.membresia
    miembros = list(_miembros(request).order_by('-activa', 'usuario__first_name', 'usuario__username'))
    for m in miembros:
        m.gestionable = servicios.puede_gestionar(actor, m)
        m.clave_restablecible = m.gestionable and servicios.solo_en_este_tenant(m.usuario, request.tenant)
    roles = servicios.roles_asignables(actor)
    return render(request, 'equipo/lista.html', {
        'titulo': 'Equipo', 'miembros': miembros, 'roles': roles,
        'form': AgregarForm(roles=roles, tenant=request.tenant, initial={'rol': Rol.ASISTENTE, 'titulo': 'Dr.'}),
        'max_usuarios': request.tenant.max_usuarios, 'max_profesionales': request.tenant.max_profesionales,
    })


@login_required
@requiere('usuarios.gestionar')
@require_POST
def agregar(request):
    roles = servicios.roles_asignables(request.membresia)
    form = AgregarForm(request.POST, roles=roles, tenant=request.tenant)
    if form.is_valid():
        d = form.cleaned_data
        try:
            m, clave = servicios.agregar(request.tenant, request.membresia, d['username'], d['nombre'],
                                         d['apellido'], d['rol'], d['email'], especialidad=d['especialidad'],
                                         titulo=d.get('titulo') or '')
        except servicios.ErrorEquipo as e:
            messages.error(request, str(e))
        else:
            return render(request, 'equipo/credenciales.html', {
                'titulo': 'Acceso creado', 'usuario': m.usuario, 'clave': clave, 'nuevo': True,
                'enlace': enlace(request, request.tenant.slug)})
        return redirect('equipo:lista')
    for campo, errores in form.errors.items():
        etiqueta = form.fields[campo].label if campo in form.fields else ''
        messages.error(request, f'{etiqueta}: {" ".join(errores)}' if etiqueta else ' '.join(errores))
    return redirect('equipo:lista')


@login_required
@requiere('usuarios.gestionar')
@require_POST
def actualizar(request, pk):
    m = get_object_or_404(_miembros(request), pk=pk)
    try:
        servicios.actualizar(request.membresia, m, request.POST.get('rol', m.rol), request.POST.get('activa') == '1')
    except servicios.ErrorEquipo as e:
        messages.error(request, str(e))
    else:
        messages.success(request, f'{m.usuario}: cambios guardados.')
    return redirect('equipo:lista')


@login_required
@requiere('usuarios.gestionar')
@require_POST
def restablecer_clave(request, pk):
    m = get_object_or_404(_miembros(request), pk=pk)
    try:
        clave = servicios.restablecer_clave(request.membresia, m)
    except servicios.ErrorEquipo as e:
        messages.error(request, str(e))
        return redirect('equipo:lista')
    return render(request, 'equipo/credenciales.html', {
        'titulo': 'Contraseña temporal', 'usuario': m.usuario, 'clave': clave, 'nuevo': False,
        'enlace': enlace(request, request.tenant.slug)})


def _editar_perfil(request, m, volver, puede_cambiar_especialidad):
    perfil = PerfilProfesional.todos.filter(membresia=m).first()
    instancia = perfil or PerfilProfesional(membresia=m, tenant=request.tenant)
    form = PerfilProfesionalForm(request.POST or None, request.FILES or None, instance=instancia,
                                 tenant=request.tenant,
                                 puede_cambiar_especialidad=puede_cambiar_especialidad or perfil is None)
    if request.method == 'POST' and form.is_valid():
        try:
            servicios.guardar_perfil(m, form)
        except servicios.ErrorEquipo as e:
            messages.error(request, str(e))
        else:
            messages.success(request, 'Perfil profesional guardado.')
            return redirect(volver)
    return render(request, 'equipo/perfil_profesional.html', {
        'titulo': f'Perfil profesional · {m.usuario}', 'form': form, 'miembro': m, 'perfil': perfil})


@login_required
@requiere('usuarios.gestionar')
def perfil_profesional(request, pk):
    m = get_object_or_404(_miembros(request), pk=pk)
    return _editar_perfil(request, m, volver=request.path, puede_cambiar_especialidad=True)


@login_required
@requiere('usuarios.gestionar')
@require_POST
def quitar_perfil(request, pk):
    m = get_object_or_404(_miembros(request), pk=pk)
    try:
        servicios.desactivar_perfil(request.membresia, m)
    except servicios.ErrorEquipo as e:
        messages.error(request, str(e))
    else:
        messages.success(request, f'{m.usuario} ya no figura como profesional.')
    return redirect('equipo:lista')


@login_required
def mi_perfil_profesional(request):
    """El profesional actualiza su firma, sello, membrete y registros (no su especialidad)."""
    m = request.membresia
    if m is None or getattr(m, 'soporte', False) or not m.es_profesional:
        raise Http404
    return _editar_perfil(request, m, volver=request.path, puede_cambiar_especialidad=False)
