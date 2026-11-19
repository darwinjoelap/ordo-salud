from django.contrib import admin

from apps.core.admin import SoloLectura, TenantModelAdmin
from apps.core.permisos import es_soporte

from .models import DocumentoEmitido


@admin.register(DocumentoEmitido)
class DocumentoEmitidoAdmin(SoloLectura, TenantModelAdmin):
    list_display = ('numero', 'tipo', 'paciente_id', 'profesional_id', 'fecha', 'anulado')
    fields = readonly_fields = list_display
    list_filter = ('tipo', 'anulado')
    search_fields = ('numero',)

    def get_queryset(self, request):
        qs = super().get_queryset(request).filter(paciente__tenant=request.tenant)
        # Las historias privadas se consultan en la vista de documentos con su alcance profesional.
        return qs if es_soporte(request.membresia) else qs.filter(tipo='recibo')
