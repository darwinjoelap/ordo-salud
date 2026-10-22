"""Modelos propios de ginecología: lo que se sigue en el tiempo y se cuenta (guía de especialidades §3)."""
from datetime import timedelta

from django.db import models
from django.utils import timezone

from apps.core.tenancy import TenantModel

from . import obstetricia as ob

PRESENTACIONES = [('CEFALICA', 'Cefálica'), ('PELVICA', 'Pélvica'), ('TRANSVERSA', 'Transversa'),
                  ('NO_EVALUABLE', 'No evaluable')]
EDEMAS = [('NO', 'No'), ('1', '+'), ('2', '++'), ('3', '+++')]


class ControlPrenatal(TenantModel):
    """
    Un control prenatal (uno por consulta). Se escribe al guardar la sección «Control prenatal» y alimenta el panel del
    embarazo, el carnet prenatal y el reporte. Peso y tensión arterial se leen de los signos vitales de la consulta.
    """
    paciente = models.ForeignKey('pacientes.Paciente', on_delete=models.CASCADE, related_name='controles_prenatales')
    consulta = models.OneToOneField('clinica.Consulta', on_delete=models.CASCADE, null=True, blank=True,
                                    related_name='control_prenatal')
    fecha = models.DateField('Fecha', db_index=True)
    fur = models.DateField('FUR', null=True, blank=True)
    eco_fecha = models.DateField('Ecografía de referencia', null=True, blank=True)
    eco_semanas = models.PositiveSmallIntegerField(null=True, blank=True)
    eco_dias = models.PositiveSmallIntegerField(null=True, blank=True)
    eg_dias = models.PositiveSmallIntegerField('EG (días)', null=True, blank=True)
    metodo_eg = models.CharField('EG por', max_length=3, blank=True)          # FUR | ECO
    fpp = models.DateField('Fecha probable de parto', null=True, blank=True, db_index=True)
    altura_uterina = models.DecimalField('Altura uterina (cm)', max_digits=4, decimal_places=1, null=True, blank=True)
    fcf = models.PositiveSmallIntegerField('FCF (lpm)', null=True, blank=True)
    presentacion = models.CharField('Presentación', max_length=15, choices=PRESENTACIONES, blank=True)
    movimientos = models.BooleanField('Movimientos fetales', null=True, blank=True)
    edemas = models.CharField('Edemas', max_length=3, choices=EDEMAS, blank=True)

    class Meta:
        verbose_name = 'Control prenatal'
        verbose_name_plural = 'Controles prenatales'
        ordering = ['paciente', 'fecha']
        indexes = [models.Index(fields=['tenant', 'paciente', 'fecha'], name='control_prenatal_pac_fecha')]

    def __str__(self):
        return f'{self.paciente} · {self.fecha:%d/%m/%Y} · {self.eg_texto}'

    @property
    def eg_texto(self):
        return ob.texto_eg(self.eg_dias)

    def eg_dias_en(self, fecha=None):
        """EG a otra fecha (hoy por defecto), contando desde este control."""
        if self.eg_dias is None:
            return None
        fecha = fecha or timezone.localdate()
        return self.eg_dias + (fecha - self.fecha).days

    @property
    def en_curso(self):
        hoy = timezone.localdate()
        return bool(self.fpp and self.fpp + timedelta(days=14) >= hoy and (self.eg_dias_en(hoy) or 0) <= ob.POSTERMINO)

    @property
    def signos(self):
        from apps.clinica.models import SignosVitales
        return SignosVitales.objects.filter(consulta_id=self.consulta_id).first() if self.consulta_id else None
