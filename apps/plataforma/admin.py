from django.contrib import admin

from apps.core.admin import SinBorrado, SoloLectura

from .models import AccesoSoporte, Especialidad, Plan, Suscripcion, Tenant


class SuscripcionInline(SoloLectura, admin.TabularInline):
    model = Suscripcion
    extra = 0


@admin.register(Tenant)
class TenantAdmin(SinBorrado, admin.ModelAdmin):
    list_display = ['nombre', 'slug', 'estado', 'plan', 'activo_hasta', 'creado_en']
    list_filter = ['estado', 'plan']
    search_fields = ['nombre', 'slug']
    filter_horizontal = ['especialidades']
    inlines = [SuscripcionInline]


@admin.register(Plan)
class PlanAdmin(SinBorrado, admin.ModelAdmin):
    list_display = ['nombre', 'precio_usd', 'precio_anual_usd', 'max_profesionales', 'max_usuarios',
                    'incluye_dictado', 'activo']


@admin.register(Especialidad)
class EspecialidadAdmin(SinBorrado, admin.ModelAdmin):
    list_display = ['nombre', 'codigo', 'modulo', 'activa', 'orden']
    readonly_fields = ['codigo', 'modulo']


@admin.register(AccesoSoporte)
class AccesoSoporteAdmin(SoloLectura, admin.ModelAdmin):
    list_display = ['inicio', 'usuario', 'tenant', 'fin', 'motivo']
    list_filter = ['tenant']
    readonly_fields = ['usuario', 'tenant', 'inicio', 'fin', 'motivo']
