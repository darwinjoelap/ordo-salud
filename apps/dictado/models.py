"""
Dictado de toda la consulta con IA (ADR-045). El audio NO se guarda: se transcribe en memoria y se descarta.
Queda la transcripción, el resultado ordenado por sección y el uso (minutos, tokens) para cobrar por plan.
"""
from django.db import models

from apps.core.tenancy import Auditable, TenantModel


class SesionDictado(TenantModel, Auditable):
    class Estado(models.TextChoices):
        PROCESANDO = 'PROCESANDO', 'Procesando'
        LISTO = 'LISTO', 'Listo'
        ERROR = 'ERROR', 'Error'

    paciente = models.ForeignKey('pacientes.Paciente', on_delete=models.CASCADE, related_name='dictados')
    profesional = models.ForeignKey('equipo.PerfilProfesional', on_delete=models.PROTECT, related_name='dictados')
    consulta = models.ForeignKey('clinica.Consulta', on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='dictados')
    plantilla = models.ForeignKey('clinica.PlantillaHistoria', on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='+')
    estado = models.CharField('Estado', max_length=10, choices=Estado.choices, default=Estado.PROCESANDO)
    consentimiento = models.BooleanField('El paciente o su representante autorizó la grabación', default=False)
    segundos = models.PositiveIntegerField('Duración (s)', default=0)
    transcripcion = models.TextField('Transcripción', blank=True)
    resultado = models.JSONField('Resultado por sección', default=dict, blank=True)
    no_ubicado = models.TextField('Lo que la IA no supo dónde poner', blank=True)
    error = models.CharField('Error', max_length=300, blank=True)
    modelo_transcripcion = models.CharField(max_length=60, blank=True)
    modelo_ia = models.CharField(max_length=60, blank=True)
    tokens_entrada = models.PositiveIntegerField(default=0)
    tokens_salida = models.PositiveIntegerField(default=0)
    terminado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Sesión de dictado'
        verbose_name_plural = 'Sesiones de dictado'
        ordering = ['-creado_en']

    def __str__(self):
        return f'Dictado {self.pk} · {self.paciente} · {self.segundos // 60} min'

    @property
    def minutos(self):
        return round(self.segundos / 60, 1)
