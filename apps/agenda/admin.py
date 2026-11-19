from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from apps.core.admin import SoloLectura, TenantModelAdmin

from .models import Bloqueo, Cita, HorarioAtencion, TipoCita
from .selectors import citas_visibles
from .servicios_previstos import plan_bloqueado


@admin.register(Cita)
class CitaAdmin(SoloLectura, TenantModelAdmin):
    permiso_consultorio = 'agenda.ver'
    list_display = ['fecha', 'hora_inicio', 'paciente', 'profesional', 'estado']
    list_filter = ['estado']
    fields = readonly_fields = ['paciente_id', 'profesional_id', 'fecha', 'hora_inicio', 'hora_fin', 'tipo_id',
                                'especialidad_id', 'consulta_id', 'estado', 'abrir_agenda']

    def get_queryset(self, request):
        qs = super().get_queryset(request).filter(paciente__tenant=request.tenant, profesional__tenant=request.tenant,
                                                  profesional__membresia__tenant=request.tenant)
        return citas_visibles(request, qs)

    @admin.display(description='Gestión de la cita')
    def abrir_agenda(self, obj):
        if plan_bloqueado(obj):
            return format_html('<a href="{}">Revisar atención en Agenda</a>', reverse('agenda:cita', args=[obj.pk]))
        return format_html('<a href="{}">Editar en Agenda</a>', reverse('agenda:cita_editar', args=[obj.pk]))


for modelo in (HorarioAtencion, Bloqueo, TipoCita):
    admin.site.register(modelo, TenantModelAdmin)
