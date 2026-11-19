from django.contrib import admin
from django.db.models import Q
from django.urls import reverse
from django.utils.html import format_html

from apps.core.admin import SoloLectura, TenantModelAdmin
from apps.core.permisos import tiene_permiso

from .models import PlantillaHistoria, SeccionClinica, SeccionClinicaVersion
from .selectors import plantillas_visibles


def tenant_del_catalogo(request):
    if tiene_permiso(request, 'plantillas.clinica') or tiene_permiso(request, 'plantillas.propias'):
        return request.tenant
    return None


@admin.register(SeccionClinica)
class SeccionClinicaAdmin(SoloLectura, admin.ModelAdmin):
    list_display = ['nombre', 'codigo', 'tipo', 'ambito', 'especialidad', 'version', 'activa']
    list_filter = ['tipo', 'ambito', 'activa']
    search_fields = ['nombre', 'codigo']

    def get_queryset(self, request):
        return super().get_queryset(request).filter(Q(tenant__isnull=True) | Q(tenant=tenant_del_catalogo(request)))


@admin.register(SeccionClinicaVersion)
class SeccionClinicaVersionAdmin(SoloLectura, admin.ModelAdmin):
    list_display = ['seccion', 'version', 'creado_en']

    def get_queryset(self, request):
        tenant = tenant_del_catalogo(request)
        return super().get_queryset(request).filter(Q(seccion__tenant__isnull=True) | Q(seccion__tenant=tenant))


@admin.register(PlantillaHistoria)
class PlantillaHistoriaAdmin(SoloLectura, TenantModelAdmin):
    permiso_consultorio = 'plantillas.clinica'
    list_display = ['nombre', 'tenant', 'especialidad', 'es_predeterminada', 'activa']
    fields = readonly_fields = ['nombre', 'especialidad', 'es_predeterminada', 'activa', 'plantilla']

    def get_queryset(self, request):
        return super().get_queryset(request).filter(pk__in=plantillas_visibles(request.membresia).values('pk'))

    @admin.display(description='Secciones y ajustes')
    def plantilla(self, obj):
        return format_html('<a href="{}">Abrir plantilla</a>', reverse('clinica:plantilla', args=[obj.pk]))
