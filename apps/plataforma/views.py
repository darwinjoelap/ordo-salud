import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.excepciones import ErrorDeNegocio
from apps.core.middleware import SESION_SOPORTE, SESION_TENANT
from apps.core.numeros import numero

from . import servicios
from .forms import EditarTenantForm, NuevoTenantForm, PlanForm, RenovarForm
from .models import Plan, Suscripcion, Tenant

SESION_ACCESO = 'ordo_soporte_acceso'

log = logging.getLogger('apps.plataforma')


def solo_plataforma(vista):
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied
        return vista(request, *args, **kwargs)
    return login_required(envoltura)


def _enlace(request, tenant):
    from apps.core.subdominios import enlace
    return enlace(request, tenant.slug)


@solo_plataforma
def lista(request):
    q = request.GET.get('q', '').strip()
    tenants = (Tenant.objects.select_related('plan', 'configuracion').prefetch_related('especialidades')
               .annotate(n_activos=Count('membresias', filter=Q(membresias__activa=True,
                                                               membresias__usuario__is_superuser=False)))
               .order_by('nombre'))
    if q:
        tenants = tenants.filter(Q(nombre__icontains=q) | Q(slug__icontains=q) | Q(configuracion__rif__icontains=q))
    tenants = list(tenants)
    for t in tenants:
        t.enlace = _enlace(request, t)
    return render(request, 'plataforma/lista.html', {'titulo': 'Consultorios y clínicas', 'tenants': tenants, 'q': q})


@solo_plataforma
def nuevo(request):
    form = NuevoTenantForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        tenant, titular, clave = servicios.crear_tenant(form.cleaned_data)
        log.warning('Plataforma: %s creó el tenant %s (%s)', request.user.username, tenant.nombre, tenant.pk)
        return render(request, 'plataforma/creado.html', {
            'titulo': 'Consultorio creado', 'tenant': tenant, 'titular': titular, 'clave': clave,
            **_texto_acceso(request, tenant, titular, clave)})
    return render(request, 'plataforma/form.html', {'titulo': 'Nuevo consultorio o clínica', 'form': form})


@solo_plataforma
def editar(request, pk):
    tenant = get_object_or_404(Tenant.objects.select_related('configuracion', 'plan'), pk=pk)
    inicial = {'nombre': tenant.nombre, 'slug': tenant.slug, 'plan': tenant.plan, 'estado': tenant.estado,
               'activo_hasta': tenant.activo_hasta, 'limite_usuarios': tenant.limite_usuarios,
               'limite_profesionales': tenant.limite_profesionales, 'dias_gracia': tenant.dias_gracia,
               'notas': tenant.notas,
               'especialidades': list(tenant.especialidades.all()),
               'dictado_activo': tenant.configuracion.dictado_activo,
               'sugerencias_ia': tenant.configuracion.sugerencias_ia}
    form = EditarTenantForm(request.POST or None, initial=inicial, tenant=tenant)
    if request.method == 'POST' and form.is_valid():
        servicios.actualizar_tenant(tenant, form.cleaned_data)
        messages.success(request, f'{tenant.nombre}: cambios guardados.')
        return redirect('plataforma:editar', pk=pk)
    from apps.equipo.models import Membresia
    miembros = (Membresia.objects.filter(tenant=tenant, usuario__is_superuser=False)
                .select_related('usuario', 'perfil', 'perfil__especialidad').order_by('-activa', 'rol'))
    return render(request, 'plataforma/form.html', {
        'titulo': tenant.nombre, 'form': form, 'tenant_obj': tenant, 'miembros': miembros,
        'renovaciones': tenant.suscripciones.select_related('plan', 'creado_por', 'anulada_por')[:12],
        'ultima_renovacion': tenant.suscripciones.filter(anulada=False).order_by('-creado_en', '-pk').first(),
        'accesos': tenant.accesos_soporte.select_related('usuario')[:8],
        'form_renovar': RenovarForm(initial={'plan': tenant.plan}), 'enlace': _enlace(request, tenant),
        'dictado_uso': _dictado_uso(tenant), 'sugerencias_uso': _sugerencias_uso(tenant)})


def _sugerencias_uso(tenant):
    from apps.dictado import indicaciones
    return indicaciones.uso_mes(tenant)


def _dictado_uso(tenant):
    from apps.dictado import servicios as dictado
    from apps.dictado.models import SesionDictado
    return {**dictado.uso(tenant), 'anterior': dictado.uso(tenant, mes_anterior=True),
            'sesiones': SesionDictado.todos.filter(tenant=tenant).count()}


@solo_plataforma
@require_POST
def renovar(request, pk):
    tenant = get_object_or_404(Tenant, pk=pk)
    form = RenovarForm(request.POST)
    if form.is_valid():
        d = form.cleaned_data
        servicios.renovar(tenant, meses=d['meses'], monto_usd=d['monto_usd'], referencia=d['referencia'],
                          notas=d['notas'], plan=d['plan'], usuario=request.user)
        messages.success(request, f'{tenant.nombre}: activo hasta el {tenant.activo_hasta:%d/%m/%Y}.')
    else:
        messages.error(request, 'Revisa los datos de la renovación.')
    return redirect('plataforma:editar', pk=pk)


@solo_plataforma
@require_POST
def entrar(request, pk):
    """El superusuario entra al tenant como Soporte (permisos de Titular, sin ver historias clínicas)."""
    tenant = get_object_or_404(Tenant, pk=pk)
    servicios.salir_soporte(request.session.get(SESION_ACCESO))       # cambia de consultorio sin "salir"
    acceso = servicios.entrar_soporte(tenant, request.user, request.POST.get('motivo', ''))
    request.session[SESION_SOPORTE] = tenant.pk
    request.session[SESION_ACCESO] = acceso.pk
    request.session.pop(SESION_TENANT, None)
    log.warning('Soporte: %s entró al tenant %s (%s)', request.user.username, tenant.nombre, tenant.pk)
    if not tenant.esta_activo:
        messages.warning(request, f'{tenant.nombre} está {tenant.estado_servicio.lower()}: su equipo no puede entrar, '
                                  'pero soporte sí.')
    return redirect('core:inicio')


@solo_plataforma
@require_POST
def salir(request):
    servicios.salir_soporte(request.session.pop(SESION_ACCESO, None))
    request.session.pop(SESION_SOPORTE, None)
    request.session.pop(SESION_TENANT, None)
    return redirect('plataforma:lista')


@solo_plataforma
@require_POST
def anular_renovacion(request, pk):
    suscripcion = get_object_or_404(Suscripcion.objects.select_related('tenant'), pk=pk)
    try:
        servicios.anular_renovacion(suscripcion, motivo=request.POST.get('motivo', ''), usuario=request.user)
        t = Tenant.objects.get(pk=suscripcion.tenant_id)
        vence = f'vence el {t.activo_hasta:%d/%m/%Y}' if t.activo_hasta else 'sin vencimiento'
        messages.success(request, f'Renovación anulada. {t.nombre} {vence}.')
        log.warning('Plataforma: %s anuló la renovación %s de %s', request.user.username, pk, t.nombre)
    except ErrorDeNegocio as e:
        messages.error(request, str(e))
    return redirect('plataforma:editar', pk=suscripcion.tenant_id)


@solo_plataforma
def suscripciones(request):
    datos = servicios.tablero_suscripciones()
    return render(request, 'plataforma/suscripciones.html', {'titulo': 'Suscripciones', **datos})


@solo_plataforma
def planes(request):
    lista = Plan.objects.annotate(n_tenants=Count('tenants')).order_by('-activo', 'precio_usd', 'nombre')
    return render(request, 'plataforma/planes.html', {'titulo': 'Planes', 'planes': lista})


@solo_plataforma
def plan_form(request, pk=None):
    plan = get_object_or_404(Plan, pk=pk) if pk else None
    form = PlanForm(request.POST or None, instance=plan)
    if request.method == 'POST' and form.is_valid():
        plan = form.save()
        messages.success(request, f'Plan «{plan.nombre}» guardado.')
        return redirect('plataforma:planes')
    return render(request, 'plataforma/plan_form.html', {
        'titulo': plan.nombre if plan else 'Nuevo plan', 'form': form, 'plan': plan,
        'n_tenants': plan.tenants.count() if plan else 0})


@solo_plataforma
def tasas(request):
    """Tasa BCV (única para todos): historial, carga manual y consulta al BCV."""
    from apps.tasas import servicios as tasas_srv
    from apps.tasas.models import TasaCambio
    if request.method == 'POST':
        if request.POST.get('accion') == 'bcv':
            try:
                t = tasas_srv.actualizar_desde_bcv()
                eur = f' · EUR {t.bs_por_eur}' if t.bs_por_eur else ' (sin euro)'
                messages.success(request, f'Tasa BCV registrada: USD {t.bs_por_usd}{eur} ({t.fecha:%d/%m/%Y}).')
            except Exception as e:  # noqa: BLE001 - el BCV falla seguido: se informa y se carga a mano
                logging.getLogger('apps.tasas').warning('Consulta manual al BCV falló: %s', e)
                messages.error(request, f'No se pudo consultar el BCV ({e.__class__.__name__}). Cárgala a mano.')
        else:
            try:
                valor = numero(request.POST.get('valor', ''))
                eur = numero(request.POST.get('valor_eur', '')) if (request.POST.get('valor_eur') or '').strip() else None
                if eur is not None and eur <= 0:
                    raise ValueError
                fecha = date.fromisoformat(request.POST.get('fecha') or timezone.localdate().isoformat())
                if valor is None or valor <= 0 or fecha > timezone.localdate():
                    raise ValueError
            except (InvalidOperation, ValueError):
                messages.error(request, 'Indica una tasa mayor que cero y una fecha que no sea futura.')
            else:
                tasas_srv.registrar(valor.quantize(Decimal('0.0001')), TasaCambio.Fuente.MANUAL, request.user, fecha,
                                    eur=eur.quantize(Decimal('0.0001')) if eur else None)
                messages.success(request, f'Tasa del {fecha:%d/%m/%Y} guardada: Bs {valor}.')
        return redirect('plataforma:tasas')
    return render(request, 'plataforma/tasas.html', {
        'titulo': 'Tasa BCV', 'tasas': TasaCambio.objects.select_related('registrada_por')[:60],
        'vigente': tasas_srv.tasa_global(), 'hoy': timezone.localdate()})


@solo_plataforma
def acceso(request, pk, membresia_pk):
    """
    Compartir el acceso de un miembro (ADR-062): enlace + usuario + contraseña. Se muestra la temporal VIGENTE si el
    usuario no la ha cambiado; si ya tiene la suya, solo se puede generar una nueva (POST).
    """
    from apps.equipo.models import Membresia
    tenant = get_object_or_404(Tenant, pk=pk)
    m = get_object_or_404(Membresia.objects.select_related('usuario'), pk=membresia_pk, tenant=tenant)
    clave, nueva = '', False
    if request.method == 'POST':
        clave, nueva = servicios.restablecer_acceso(m, request.user), True
        messages.success(request, f'Contraseña temporal nueva para {m.usuario.username}: la anterior ya no sirve.')
    else:
        clave = m.usuario.clave_temporal_vigente()
    return render(request, 'plataforma/acceso.html', {
        'titulo': f'Acceso · {m.usuario.nombre_visible}', 'tenant_obj': tenant, 'm': m, 'clave': clave,
        'nueva': nueva, **_texto_acceso(request, tenant, m.usuario, clave)})


def _texto_acceso(request, tenant, usuario, clave):
    """Texto listo para copiar o mandar por WhatsApp."""
    import urllib.parse

    from apps.agenda.servicios import numero_whatsapp
    enlace = _enlace(request, tenant)
    lineas = [f'{tenant.nombre} en Ordo Salud', f'Enlace: {enlace}', f'Usuario: {usuario.username}']
    if clave:
        lineas.append(f'Contraseña temporal: {clave} (al entrar te pedirá cambiarla)')
    texto = '\n'.join(lineas)
    numero = numero_whatsapp(usuario.telefono)
    return {'enlace': enlace, 'texto_acceso': texto,
            'url_whatsapp': f'https://wa.me/{numero}?text={urllib.parse.quote(texto)}' if numero
            else f'https://wa.me/?text={urllib.parse.quote(texto)}'}
