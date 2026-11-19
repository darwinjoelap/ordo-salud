from django.contrib import admin

from apps.core.admin import SoloLectura, TenantModelAdmin

from .models import SesionDictado


@admin.register(SesionDictado)
class SesionDictadoAdmin(SoloLectura, TenantModelAdmin):
    list_display = ['creado_en', 'tenant', 'profesional_id', 'segundos', 'estado', 'modelo_ia', 'tokens_entrada',
                    'tokens_salida']
    list_filter = ['estado']
    fields = readonly_fields = list_display

    def get_queryset(self, request):
        return super().get_queryset(request).filter(paciente__tenant=request.tenant)
