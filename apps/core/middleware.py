"""
Fija request.tenant, request.membresia y request.membresias para cada request autenticado
(patrón de Ordo). También deja el usuario en el contexto para `Auditable.creado_por`.
"""
from django.apps import apps
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import Resolver404, resolve, reverse

from .excepciones import ErrorDeNegocio
from .permisos import Rol
from .tenancy import fijar_tenant, fijar_usuario, restaurar_tenant, restaurar_usuario

SESION_TENANT = 'tenant_id'
SESION_SOPORTE = 'soporte_tenant_id'   # superusuario dentro de un tenant sin ser miembro

# Rutas que funcionan sin tenant elegido
PREFIJOS_LIBRES = ('/static/', '/media/', '/admin/', '/salud/', '/cuenta/', '/__debug__/', '/plataforma/',
                   '/favicon.ico', '/manifest.webmanifest', '/sw.js', '/offline/', '/instalar/')


def membresia_soporte(usuario, tenant):
    """Membresía virtual (no se guarda) con la que un superusuario opera dentro de cualquier tenant."""
    Membresia = apps.get_model('equipo', 'Membresia')
    m = Membresia(usuario=usuario, tenant=tenant, rol=Rol.TITULAR, activa=True)
    m.soporte = True
    return m


class TenantActivoMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.tenant = None
        request.membresia = None
        request.membresias = []
        token = None
        token_u = fijar_usuario(request.user if request.user.is_authenticated else None)

        if request.user.is_authenticated:
            Membresia = apps.get_model('equipo', 'Membresia')
            Tenant = apps.get_model('plataforma', 'Tenant')
            membresias = [
                m for m in Membresia.objects.filter(usuario=request.user, activa=True)
                .select_related('tenant', 'tenant__configuracion', 'perfil', 'perfil__especialidad')
                if m.tenant.esta_activo
            ]
            request.membresias = membresias
            elegida = None
            tenant_host = getattr(request, 'tenant_host', None)
            if tenant_host is not None:        # subdominio del consultorio: manda el host, no la sesión
                elegida = next((m for m in membresias if m.tenant_id == tenant_host.pk), None)
                if elegida is None and request.user.is_superuser:
                    elegida = membresia_soporte(request.user, tenant_host)
                suspendido = not tenant_host.esta_activo and not request.user.is_superuser
                if (elegida is None or suspendido) and not request.path.startswith(('/static/', '/cuenta/salir/')):
                    restaurar_usuario(token_u)
                    from django.shortcuts import render
                    plantilla = 'plataforma/suspendido.html' if suspendido else 'plataforma/sin_acceso.html'
                    return render(request, plantilla, {'tenant_marca': tenant_host}, status=403)
            else:
                tenant_id = request.session.get(SESION_TENANT)
                if tenant_id:
                    elegida = next((m for m in membresias if m.tenant_id == tenant_id), None)
                soporte_id = request.session.get(SESION_SOPORTE) if request.user.is_superuser else None
                if soporte_id:
                    tenant = Tenant.objects.select_related('configuracion').filter(pk=soporte_id).first()
                    elegida = membresia_soporte(request.user, tenant) if tenant else None
                if elegida is None and len(membresias) == 1 and not request.user.is_superuser:
                    elegida = membresias[0]
                    request.session[SESION_TENANT] = elegida.tenant_id

            if elegida:
                request.membresia = elegida
                request.tenant = elegida.tenant
                token = fijar_tenant(elegida.tenant)
            elif not request.path.startswith(PREFIJOS_LIBRES) and not self._es_ruta_libre(request):
                restaurar_usuario(token_u)
                if request.user.is_superuser:
                    return redirect('plataforma:lista')
                if membresias:
                    return redirect(f"{reverse('equipo:seleccionar')}?next={request.get_full_path()}")
                return redirect('equipo:sin_tenant')

        try:
            return self.get_response(request)
        finally:
            if token is not None:
                restaurar_tenant(token)
            restaurar_usuario(token_u)

    @staticmethod
    def _es_ruta_libre(request):
        if request.path in (reverse('equipo:seleccionar'), reverse('equipo:sin_tenant')):
            return True
        try:                                   # enlace propio de un tenant: /<slug>/
            return resolve(request.path_info).url_name == 'entrada_tenant'
        except Resolver404:
            return False


class ErrorDeNegocioMiddleware:
    """Un ErrorDeNegocio no capturado en la vista se muestra como mensaje y vuelve a la página anterior."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if isinstance(exception, ErrorDeNegocio):
            messages.error(request, str(exception))
            destino = request.META.get('HTTP_REFERER') or '/'
            return redirect(destino)
        return None
