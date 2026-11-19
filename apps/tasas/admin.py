from decimal import Decimal

from django import forms
from django.contrib import admin
from django.core.exceptions import PermissionDenied

from apps.core.admin import SinBorrado, TenantModelAdmin

from . import servicios
from .models import TasaCambio, TasaTenant


class FormTasaReferencia(forms.ModelForm):
    bs_por_usd = forms.DecimalField(label='Bs por USD', min_value=Decimal('0.0001'), max_digits=14, decimal_places=4)
    bs_por_eur = forms.DecimalField(label='Bs por EUR', min_value=Decimal('0.0001'), max_digits=14, decimal_places=4,
                                    required=False)

    def clean(self):
        datos = super().clean()
        if (isinstance(self.instance, TasaTenant) and self.instance.tenant_id
                and servicios.referencia(self.instance.tenant) == 'EUR' and not datos.get('bs_por_eur')):
            self.add_error('bs_por_eur', 'El consultorio utiliza la tasa en euros.')
        return datos


@admin.register(TasaCambio)
class TasaCambioAdmin(SinBorrado, admin.ModelAdmin):
    form = FormTasaReferencia
    list_display = ['fecha', 'bs_por_usd', 'bs_por_eur', 'fuente', 'registrada_por', 'actualizado_en']
    readonly_fields = ['registrada_por', 'fuente']

    def save_model(self, request, obj, form, change):
        if not change or {'bs_por_usd', 'bs_por_eur'} & set(form.changed_data):
            obj.fuente = TasaCambio.Fuente.MANUAL
            obj.registrada_por = request.user
        super().save_model(request, obj, form, change)
        servicios.limpiar_cache()


@admin.register(TasaTenant)
class TasaTenantAdmin(TenantModelAdmin):
    form = FormTasaReferencia
    permiso_consultorio = 'tasa.cargar'
    fields = ['fecha', 'bs_por_usd', 'bs_por_eur', 'registrada_por']
    readonly_fields = ['fecha', 'registrada_por']
    list_display = ['fecha', 'tenant', 'bs_por_usd', 'bs_por_eur', 'registrada_por', 'actualizado_en']

    def save_model(self, request, obj, form, change):
        if not change or not self.has_change_permission(request, obj):
            raise PermissionDenied
        anterior = self.get_queryset(request).select_for_update().filter(pk=obj.pk).first()
        if anterior is None or anterior.fecha != obj.fecha:
            raise PermissionDenied
        servicios.registrar_del_tenant(request.tenant, obj.bs_por_usd, request.user,
                                      fecha=anterior.fecha, eur=obj.bs_por_eur)
