"""
Procedimiento sin consulta (ADR-040): lo que se hace sin abrir una historia —poner una vacuna, una nebulización, una
inyección, una cura—. Puede haber varios en el mismo día; cada uno agrupa uno o más servicios (un cargo por servicio)
y puede venir de una cita (la deja atendida). Idea de Pediae/Ginea `Procedimiento`, con los cobros de Ordo Salud.
"""
from django.db import models

from apps.core.tenancy import Auditable, TenantModel


class Procedimiento(TenantModel, Auditable):
    paciente = models.ForeignKey('pacientes.Paciente', on_delete=models.PROTECT, related_name='procedimientos')
    profesional = models.ForeignKey('equipo.PerfilProfesional', on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='procedimientos')
    cita = models.ForeignKey('agenda.Cita', on_delete=models.SET_NULL, null=True, blank=True,
                             related_name='procedimientos')
    fecha = models.DateField('Fecha', db_index=True)
    descripcion = models.CharField('Qué se hizo', max_length=250)
    notas = models.TextField('Notas', blank=True)
    anulado = models.BooleanField('Anulado', default=False)
    motivo_anulacion = models.CharField('Motivo de anulación', max_length=200, blank=True)

    class Meta:
        verbose_name = 'Procedimiento'
        verbose_name_plural = 'Procedimientos'
        ordering = ['-fecha', '-creado_en']
        indexes = [models.Index(fields=['tenant', 'fecha'], name='procedimiento_fecha')]

    def __str__(self):
        return f'{self.descripcion} · {self.paciente} ({self.fecha:%d/%m/%Y})'

    def _cargos_vigentes(self):
        return [c for c in self.cargos.all() if c.estado != 'ANULADO']

    @property
    def total_usd(self):
        return sum((c.monto_usd for c in self._cargos_vigentes()), 0)

    @property
    def saldo_usd(self):
        return sum((c.saldo_usd for c in self._cargos_vigentes()), 0)
