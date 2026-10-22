from django.conf import settings
from django.db import models

from .tenancy import TenantModel


class Secuencia(TenantModel):
    """Correlativos por tenant, tipo de documento y año (sin carreras: select_for_update)."""
    tipo = models.CharField('Tipo', max_length=10)
    anio = models.PositiveSmallIntegerField('Año')
    ultimo = models.PositiveIntegerField('Último número', default=0)

    class Meta:
        verbose_name = 'Secuencia'
        verbose_name_plural = 'Secuencias'
        constraints = [models.UniqueConstraint(fields=['tenant', 'tipo', 'anio'], name='secuencia_unica')]

    def __str__(self):
        return f'{self.tipo}-{self.anio}: {self.ultimo}'


class Auditoria(TenantModel):
    """Quién vio, creó, modificó o imprimió qué (ADR-018). Solo se agrega; nunca se edita."""

    class Accion(models.TextChoices):
        VER = 'VER', 'Ver'
        CREAR = 'CREAR', 'Crear'
        EDITAR = 'EDITAR', 'Editar'
        CERRAR = 'CERRAR', 'Cerrar'
        ENMENDAR = 'ENMENDAR', 'Enmendar'
        ANULAR = 'ANULAR', 'Anular'
        IMPRIMIR = 'IMPRIMIR', 'Imprimir'
        EXPORTAR = 'EXPORTAR', 'Exportar'
        ACCESO_EXCEPCIONAL = 'EXCEPCION', 'Acceso excepcional'
        SOPORTE = 'SOPORTE', 'Soporte de Ordo Salud'

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    accion = models.CharField('Acción', max_length=10, choices=Accion.choices)
    objeto_tipo = models.CharField('Tipo de objeto', max_length=60)
    objeto_id = models.CharField('Id del objeto', max_length=40, blank=True)
    paciente_id = models.BigIntegerField('Paciente', null=True, blank=True, db_index=True)
    detalle = models.CharField('Detalle', max_length=300, blank=True)
    ip = models.GenericIPAddressField('IP', null=True, blank=True)
    creado_en = models.DateTimeField('Fecha', auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Registro de auditoría'
        verbose_name_plural = 'Auditoría'
        ordering = ['-creado_en']

    def __str__(self):
        return f'{self.creado_en:%d/%m/%Y %H:%M} {self.usuario} {self.get_accion_display()} {self.objeto_tipo}'
