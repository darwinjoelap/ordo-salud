"""
Tasa oficial BCV (Bs por USD y Bs por EUR, ADR-059).
- TasaCambio es GLOBAL: la consulta el cron cada día (o la carga a mano la plataforma).
- TasaTenant: el consultorio puede cargar su propia tasa del día si el BCV no respondió; solo lo afecta a él.
La que se usa es la más reciente de las dos (`servicios.tasa_vigente(tenant)`).
"""
from django.conf import settings
from django.db import models

from apps.core.tenancy import TenantModel


class TasaCambio(models.Model):
    class Fuente(models.TextChoices):
        BCV = 'BCV', 'BCV automático'
        MANUAL = 'MANUAL', 'Carga manual'

    fecha = models.DateField('Fecha', unique=True)
    bs_por_usd = models.DecimalField('Bs por USD', max_digits=14, decimal_places=4)
    bs_por_eur = models.DecimalField('Bs por EUR', max_digits=14, decimal_places=4, null=True, blank=True)
    fuente = models.CharField('Fuente', max_length=8, choices=Fuente.choices, default=Fuente.BCV)
    registrada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='+')
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Tasa de cambio'
        verbose_name_plural = 'Tasas de cambio'
        ordering = ['-fecha']

    def __str__(self):
        return f'{self.fecha:%d/%m/%Y}: Bs {self.bs_por_usd}'


class TasaTenant(TenantModel):
    """
    Tasa cargada a mano por un consultorio para un día (cuando el BCV no respondió o usa otra).
    Solo afecta a ese consultorio. Manda sobre la tasa global del mismo día; una tasa global más reciente la reemplaza.
    """
    fecha = models.DateField('Fecha')
    bs_por_usd = models.DecimalField('Bs por USD', max_digits=14, decimal_places=4)
    bs_por_eur = models.DecimalField('Bs por EUR', max_digits=14, decimal_places=4, null=True, blank=True)
    registrada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='+')
    actualizado_en = models.DateTimeField(auto_now=True)

    fuente = 'TENANT'

    class Meta:
        verbose_name = 'Tasa del consultorio'
        verbose_name_plural = 'Tasas de los consultorios'
        ordering = ['-fecha']
        base_manager_name = 'todos'
        constraints = [models.UniqueConstraint(fields=['tenant', 'fecha'], name='tasa_tenant_fecha_unica')]

    def __str__(self):
        return f'{self.fecha:%d/%m/%Y}: Bs {self.bs_por_usd} (consultorio)'

    def get_fuente_display(self):
        return 'Carga manual del consultorio'
