from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.core.admin import SinBorrado

from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(SinBorrado, UserAdmin):
    def get_readonly_fields(self, request, obj=None):
        return [*super().get_readonly_fields(request, obj), *(['tenant_cuenta'] if obj else [])]

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser and super().has_change_permission(request, obj)

    def has_add_permission(self, request):
        return request.user.is_superuser and super().has_add_permission(request)
    ordering = ['tenant_cuenta', 'username']
    list_display = ['username', 'tenant_cuenta', 'first_name', 'last_name', 'is_active', 'is_superuser', 'last_login']
    list_filter = ['is_superuser', 'is_active', 'tenant_cuenta']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    fieldsets = (
        (None, {'fields': ('username', 'tenant_cuenta', 'password')}),
        ('Datos personales', {'fields': ('first_name', 'last_name', 'email', 'telefono')}),
        ('Permisos', {'fields': ('is_active', 'debe_cambiar_clave', 'is_staff', 'is_superuser', 'groups',
                                 'user_permissions')}),
        ('Fechas', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {'classes': ('wide',), 'fields': ('username', 'tenant_cuenta', 'password1', 'password2')}),
    )
