from django.contrib.admin import AdminSite
from django.contrib.admin.apps import AdminConfig


class SitioPlataforma(AdminSite):
    def has_permission(self, request):
        # También se comprueba en cada petición con sesión previamente autenticada.
        return super().has_permission(request) and request.user.tenant_cuenta_id is None

    def get_log_entries(self, request):
        # LogEntry no guarda tenant. El historial por objeto sigue acotado por su ModelAdmin.
        entradas = super().get_log_entries(request)
        if request.tenant or not request.user.is_superuser:
            return entradas.none()
        return entradas.filter(
            content_type__app_label__in=('plataforma', 'auth', 'usuarios'))


class AdminPlataformaConfig(AdminConfig):
    default_site = 'apps.core.admin_site.SitioPlataforma'
