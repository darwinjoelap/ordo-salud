from django.contrib import admin

from apps.core.admin import SoloLectura

from .models import SolicitudIdempotente


@admin.register(SolicitudIdempotente)
class SolicitudIdempotenteAdmin(SoloLectura, admin.ModelAdmin):
    list_display = ('ruta', 'estado', 'usuario_id', 'creado')
    list_filter = ('estado',)

    def has_view_permission(self, request, obj=None):
        # El registro técnico legado carece de una identidad verificable de consultorio.
        return request.user.is_superuser and super().has_view_permission(request, obj)
