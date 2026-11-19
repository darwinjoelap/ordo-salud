from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q

from apps.core.admin import SoloLectura, TenantModelAdmin
from apps.core.permisos import Rol
from apps.plataforma.models import Tenant

from . import servicios
from .models import Membresia, PerfilProfesional


@admin.register(Membresia)
class MembresiaAdmin(TenantModelAdmin):
    permiso_consultorio = 'usuarios.gestionar'
    list_display = ['usuario', 'tenant', 'rol', 'activa']
    list_filter = ['rol', 'activa']
    search_fields = ['usuario__username', 'usuario__first_name', 'usuario__last_name', 'tenant__nombre']
    fields = ['usuario', 'rol', 'activa']

    def has_add_permission(self, request):
        return request.user.is_superuser and self._en_alcance(request)

    def has_change_permission(self, request, obj=None):
        return False  # Los cambios de rol y las bajas se gestionan desde Equipo.

    def _cuentas_disponibles(self, request):
        # Una cuenta de plataforma puede tener varias membresías. Una cuenta local pertenece a su consultorio.
        return (get_user_model().objects.filter(Q(tenant_cuenta=request.tenant) | Q(tenant_cuenta__isnull=True),
                                                is_superuser=False, is_active=True)
                .exclude(membresias__tenant=request.tenant))

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'usuario':
            kwargs['queryset'] = self._cuentas_disponibles(request)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        if change or obj.pk or not self.has_add_permission(request):
            raise PermissionDenied
        Tenant.objects.select_for_update().get(pk=request.tenant.pk)
        if not self._cuentas_disponibles(request).filter(pk=obj.usuario_id).exists():
            raise PermissionDenied
        # La activación comprueba rol, perfil profesional y cupo mediante el mismo servicio que Equipo.
        rol, activa = obj.rol, obj.activa
        obj.tenant = request.tenant
        obj.rol, obj.activa = Rol.ASISTENTE, False
        obj.save(force_insert=True)
        servicios.actualizar(request.membresia, obj, rol, activa)
        obj.rol, obj.activa = rol, activa


@admin.register(PerfilProfesional)
class PerfilProfesionalAdmin(SoloLectura, TenantModelAdmin):
    permiso_consultorio = 'usuarios.gestionar'
    list_display = ['__str__', 'tenant', 'especialidad', 'numero_mpps', 'activo']
    list_filter = ['activo']

    def get_queryset(self, request):
        return super().get_queryset(request).filter(membresia__tenant=request.tenant)
