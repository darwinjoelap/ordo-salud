from django.contrib import admin
from django.core.exceptions import PermissionDenied

from .models import Auditoria, Secuencia
from .permisos import tiene_permiso


class SinBorrado:
    def has_delete_permission(self, request, obj=None):
        return False

    def delete_model(self, request, obj):
        raise PermissionDenied

    def delete_queryset(self, request, queryset):
        raise PermissionDenied


class SoloLectura(SinBorrado):
    """Los asientos, versiones y trazas se consultan aquí y se gestionan en su dominio."""
    actions = None

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        raise PermissionDenied

    def save_related(self, request, form, formsets, change):
        raise PermissionDenied


class TenantModelAdmin(SinBorrado, admin.ModelAdmin):
    """Operaciones del consultorio elegido, con permisos Django y del dominio."""
    permiso_consultorio = 'tenant.configurar'

    def _en_alcance(self, request, obj=None):
        tenant = request.tenant
        return (tenant is not None and request.membresia is not None
                and request.membresia.tenant_id == tenant.pk and tiene_permiso(request, self.permiso_consultorio)
                and (obj is None or obj.tenant_id == tenant.pk))

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(tenant=request.tenant) if self._en_alcance(request) else qs.none()

    def has_view_permission(self, request, obj=None):
        return self._en_alcance(request, obj) and super().has_view_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        return self._en_alcance(request, obj) and super().has_change_permission(request, obj)

    def has_add_permission(self, request):
        return False      # los datos de negocio se crean desde la app, dentro de su tenant

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        from apps.plataforma.models import Especialidad

        if db_field.related_model is Especialidad:
            kwargs['queryset'] = request.tenant.especialidades.all() if request.tenant else Especialidad.objects.none()
        elif any(f.name == 'tenant' for f in db_field.related_model._meta.fields):
            kwargs['queryset'] = db_field.related_model.objects.filter(tenant=request.tenant)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if (not change or not self.has_change_permission(request, obj)
                or not self.get_queryset(request).filter(pk=obj.pk).exists()):
            raise PermissionDenied
        # Un llamador de este hook tampoco puede guardar una relación fuera de las opciones autorizadas.
        for field in obj._meta.fields:
            if field.is_relation and field.editable and field.name in form.fields:
                pk = getattr(obj, field.attname)
                if pk is not None and not form.fields[field.name].queryset.filter(pk=pk).exists():
                    raise PermissionDenied
        super().save_model(request, obj, form, change)


@admin.register(Auditoria)
class AuditoriaAdmin(SoloLectura, TenantModelAdmin):
    list_display = ['creado_en', 'tenant', 'usuario', 'accion', 'objeto_tipo', 'objeto_id', 'paciente_id', 'ip']
    list_filter = ['accion']
    readonly_fields = [f.name for f in Auditoria._meta.fields]


@admin.register(Secuencia)
class SecuenciaAdmin(SoloLectura, TenantModelAdmin):
    list_display = ['tenant', 'tipo', 'anio', 'ultimo']
