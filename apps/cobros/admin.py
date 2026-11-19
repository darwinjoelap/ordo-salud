from django.contrib import admin
from django.db.models import F
from django.urls import reverse
from django.utils.html import format_html

from apps.core.admin import SoloLectura, TenantModelAdmin

from .models import Cargo, Pago, PagoAplicado, Servicio


def enlace_cuenta(paciente_id):
    return format_html('<a href="{}">Abrir Cuenta</a>', reverse('cobros:cuenta', args=[paciente_id]))


@admin.register(Servicio)
class ServicioAdmin(TenantModelAdmin):
    permiso_consultorio = 'servicios.gestionar'
    list_display = ['nombre', 'tenant', 'precio_usd', 'activo']


class MovimientoAdmin(SoloLectura, TenantModelAdmin):
    permiso_consultorio = 'cobros.gestionar'

    def get_queryset(self, request):
        return super().get_queryset(request).filter(paciente__tenant_id=F('tenant_id'))

    @admin.display(description='Gestión del movimiento')
    def cuenta(self, obj):
        return enlace_cuenta(obj.paciente_id)

    def get_fields(self, request, obj=None):
        # Un vínculo histórico incoherente nunca debe resolver el nombre de otro consultorio.
        return [f.attname for f in self.model._meta.fields] + ['cuenta']

    get_readonly_fields = get_fields


@admin.register(Cargo)
class CargoAdmin(MovimientoAdmin):
    list_display = ['pk', 'fecha', 'descripcion', 'estado', 'precio_usd']


@admin.register(Pago)
class PagoAdmin(MovimientoAdmin):
    list_display = ['pk', 'fecha', 'metodo', 'moneda', 'monto', 'anulado']


@admin.register(PagoAplicado)
class PagoAplicadoAdmin(SoloLectura, TenantModelAdmin):
    permiso_consultorio = 'cobros.gestionar'
    list_display = ['pk', 'pago_id', 'cargo_id', 'monto_usd']
    fields = readonly_fields = ['pago_id', 'cargo_id', 'monto_usd', 'cuenta']

    @admin.display(description='Gestión de la aplicación')
    def cuenta(self, obj):
        return enlace_cuenta(obj.pago.paciente_id)

    def get_queryset(self, request):
        return super().get_queryset(request).filter(pago__tenant_id=F('tenant_id'), cargo__tenant_id=F('tenant_id'),
                                                    pago__paciente__tenant_id=F('tenant_id'),
                                                    cargo__paciente_id=F('pago__paciente_id'))
