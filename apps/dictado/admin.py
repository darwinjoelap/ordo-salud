from django.contrib import admin

from .models import SesionDictado


@admin.register(SesionDictado)
class SesionDictadoAdmin(admin.ModelAdmin):
    list_display = ['creado_en', 'tenant', 'profesional', 'segundos', 'estado', 'modelo_ia', 'tokens_entrada',
                    'tokens_salida']
    list_filter = ['estado', 'tenant']
    readonly_fields = [f.name for f in SesionDictado._meta.fields]
