from django.contrib import admin

from apps.core.admin import SoloLectura, TenantModelAdmin

from .models import Paciente, Representante


@admin.register(Paciente)
class PacienteAdmin(SoloLectura, TenantModelAdmin):
    list_display = ['nombre_completo', 'documento', 'tenant', 'fecha_nacimiento', 'activo']
    search_fields = ['nombres', 'apellidos', 'numero_documento']
    fields = ['nombres', 'apellidos', 'documento', 'fecha_nacimiento', 'activo']
    readonly_fields = fields


@admin.register(Representante)
class RepresentanteAdmin(SoloLectura, TenantModelAdmin):
    list_display = ['nombre', 'paciente', 'parentesco', 'tenant']

    def get_queryset(self, request):
        return super().get_queryset(request).filter(paciente__tenant=request.tenant)


# La historia y sus antecedentes se leen y corrigen en la ficha con alcance clínico y auditoría.
