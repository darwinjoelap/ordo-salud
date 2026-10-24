"""
Subdominio por consultorio (ADR-049): https://<slug>.<BASE_DOMAIN>/  →  ese consultorio.

- Sin BASE_DOMAIN (desarrollo, dirección de Railway) todo sigue por ruta: /<slug>/.
- <slug>.salud.ordove.com: el consultorio sale del host; sin sesión, la raíz es su login con su marca.
  Con sesión, solo vale una membresía de ESE consultorio (o soporte de plataforma). /plataforma/ y /admin/ no existen.
- admin.salud.ordove.com: panel de plataforma (cuentas sin consultorio).
- salud.ordove.com/<slug>/: redirige al subdominio.
Las cookies quedan en cada subdominio (no se fija SESSION_COOKIE_DOMAIN): cada consultorio tiene su sesión.
"""
from django.conf import settings
from django.http import Http404
from django.shortcuts import redirect

ADMIN = 'admin'
NO_CONSULTORIO = {ADMIN, 'www', 'app', 'api', 'static', 'media', 'mail'}


def base():
    return (getattr(settings, 'BASE_DOMAIN', '') or '').strip().lower().strip('.')


def host_de(request):
    return request.get_host().split(':')[0].lower()


def subdominio(request):
    """'' si el host no es un subdominio de BASE_DOMAIN; si no, el primer nivel ('dra-sierra', 'admin'…)."""
    dominio = base()
    host = host_de(request)
    if not dominio or not host.endswith('.' + dominio):
        return ''
    resto = host[:-len(dominio) - 1]
    return '' if '.' in resto else resto


def enlace(request, slug):
    """Dirección que se le da al consultorio: su subdominio si hay BASE_DOMAIN, si no /<slug>/ en este host."""
    dominio = base()
    if dominio:
        return f"{'https' if request.is_secure() else 'http'}://{slug}.{dominio}/"
    return request.build_absolute_uri(f'/{slug}/')


class SubdominioMiddleware:
    """Va después de AuthenticationMiddleware y antes de TenantActivoMiddleware."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.tenant_host = None
        request.es_admin_host = False
        sub = subdominio(request)
        if sub == ADMIN:
            request.es_admin_host = True
            if request.path == '/':
                return redirect('plataforma:lista' if request.user.is_authenticated else '/cuenta/entrar/?plataforma=1')
        elif sub and sub not in NO_CONSULTORIO:
            from apps.plataforma.models import Tenant
            tenant = Tenant.objects.select_related('configuracion').filter(slug=sub).first()
            if tenant is None:
                raise Http404('Consultorio no encontrado')
            request.tenant_host = tenant
            request.tenant_login = tenant          # cualquier login en este host busca el usuario de este consultorio
            if request.path.startswith(('/plataforma/', '/admin/')):
                raise Http404
            if not request.user.is_authenticated and request.path in ('/', '/cuenta/entrar/'):
                from apps.plataforma.views_entrada import EntradaTenant
                respuesta = EntradaTenant.as_view()(request, slug=tenant.slug)
                return respuesta.render() if hasattr(respuesta, 'render') else respuesta
        return self.get_response(request)
