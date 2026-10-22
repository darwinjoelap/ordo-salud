from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from apps.plataforma.views_entrada import entrada


def urls_de_especialidades():
    """Cada módulo de especialidad con `urls.py` queda en /esp/<código>/ (sin tocar este archivo)."""
    import importlib

    from apps.clinica import registro
    rutas = []
    for codigo, esp in sorted(registro.especialidades().items()):
        if not esp.modulo:
            continue
        try:
            importlib.import_module(f'{esp.modulo}.urls')
        except ModuleNotFoundError:
            continue
        rutas.append(path(f'esp/{codigo}/', include(f'{esp.modulo}.urls')))
    return rutas


admin.site.site_header = 'Ordo Salud — administración'
admin.site.site_title = 'Ordo Salud'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('cuenta/', include('apps.usuarios.urls')),
    path('plataforma/', include('apps.plataforma.urls')),
    path('equipo/', include('apps.equipo.urls')),
    path('configuracion/', include('apps.configuracion.urls')),
    path('tasa/', include('apps.tasas.urls')),
    path('cobros/', include('apps.cobros.urls')),
    path('documentos/', include('apps.documentos.urls')),
    path('reportes/', include('apps.reportes.urls')),
    path('offline/', include('apps.offline.urls')),
    path('pacientes/', include('apps.pacientes.urls')),
    path('agenda/', include('apps.agenda.urls')),
    *urls_de_especialidades(),
    path('', include('apps.clinica.urls')),
    path('', include('apps.core.urls')),
]

if settings.DEBUG:
    from django.conf.urls.static import static
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    if getattr(settings, 'DEBUG_TOOLBAR', False):
        urlpatterns = [path('__debug__/', include('debug_toolbar.urls')), *urlpatterns]

# El enlace propio de cada consultorio (/<slug>/) va AL FINAL: los prefijos de arriba están en RESERVADOS
urlpatterns += [path('<slug:slug>/', entrada, name='entrada_tenant')]

handler403 = 'apps.core.views.prohibido'
