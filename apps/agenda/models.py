"""
Agenda multi-profesional (Fase 08, ADR-013): horarios por profesional y lugar, bloqueos, tipos de cita y citas.
Con un solo profesional en el consultorio, la interfaz oculta los selectores de profesional.
"""
from datetime import datetime, timedelta

from django.db import models
from django.db.models import Q

from apps.core.fechas import hora12
from apps.core.tenancy import Auditable, TenantModel


class HorarioAtencion(TenantModel):
    class Dia(models.IntegerChoices):
        LUNES = 0, 'Lunes'
        MARTES = 1, 'Martes'
        MIERCOLES = 2, 'Miércoles'
        JUEVES = 3, 'Jueves'
        VIERNES = 4, 'Viernes'
        SABADO = 5, 'Sábado'
        DOMINGO = 6, 'Domingo'

    profesional = models.ForeignKey('equipo.PerfilProfesional', on_delete=models.CASCADE, related_name='horarios')
    lugar = models.ForeignKey('configuracion.Lugar', on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='+', verbose_name='Lugar')
    dia_semana = models.PositiveSmallIntegerField('Día', choices=Dia.choices)
    hora_inicio = models.TimeField('Desde')
    hora_fin = models.TimeField('Hasta')
    duracion_turno_min = models.PositiveSmallIntegerField('Duración del turno (min)', default=30)
    activo = models.BooleanField('Activo', default=True)

    class Meta:
        verbose_name = 'Horario de atención'
        verbose_name_plural = 'Horarios de atención'
        ordering = ['profesional', 'dia_semana', 'hora_inicio']
        constraints = [models.CheckConstraint(condition=Q(hora_fin__gt=models.F('hora_inicio')),
                                              name='horario_fin_mayor_inicio')]

    def __str__(self):
        return f'{self.get_dia_semana_display()} {hora12(self.hora_inicio)} – {hora12(self.hora_fin)}'


class Bloqueo(TenantModel, Auditable):
    """Vacaciones, congreso, feriado. Sin profesional = todo el consultorio."""
    profesional = models.ForeignKey('equipo.PerfilProfesional', on_delete=models.CASCADE, null=True, blank=True,
                                    related_name='bloqueos')
    desde = models.DateTimeField('Desde')
    hasta = models.DateTimeField('Hasta')
    motivo = models.CharField('Motivo', max_length=150)

    class Meta:
        verbose_name = 'Bloqueo de agenda'
        verbose_name_plural = 'Bloqueos de agenda'
        ordering = ['-desde']
        constraints = [models.CheckConstraint(condition=Q(hasta__gt=models.F('desde')), name='bloqueo_hasta_mayor')]

    def __str__(self):
        return self.motivo


class TipoCita(TenantModel):
    nombre = models.CharField('Nombre', max_length=80)
    duracion_min = models.PositiveSmallIntegerField('Duración (min)', default=30)
    color = models.CharField('Color', max_length=7, default='#1C8577')
    especialidad = models.ForeignKey('plataforma.Especialidad', on_delete=models.PROTECT, null=True, blank=True,
                                     related_name='+', help_text='Vacío = para cualquier especialidad.')
    tipo_consulta = models.CharField('Tipo de consulta', max_length=10, default='PRIMERA',
                                     choices=[('PRIMERA', 'Primera consulta'), ('CONTROL', 'Control'),
                                              ('EMERGENCIA', 'Emergencia'), ('OTRA', 'Otra')])
    servicio = models.ForeignKey('cobros.Servicio', on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='+', verbose_name='Servicio a cobrar')
    plantilla = models.ForeignKey('clinica.PlantillaHistoria', on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='+', verbose_name='Plantilla de historia')
    activo = models.BooleanField('Activo', default=True)

    class Meta:
        verbose_name = 'Tipo de cita'
        verbose_name_plural = 'Tipos de cita'
        ordering = ['nombre']
        constraints = [models.UniqueConstraint(fields=['tenant', 'nombre'], name='tipo_cita_unico')]

    def __str__(self):
        return self.nombre


class Cita(TenantModel, Auditable):
    class Estado(models.TextChoices):
        TENTATIVA = 'TENTATIVA', 'Tentativa'
        PROGRAMADA = 'PROGRAMADA', 'Programada'
        CONFIRMADA = 'CONFIRMADA', 'Confirmada'
        EN_SALA = 'EN_SALA', 'En sala de espera'
        ATENDIDA = 'ATENDIDA', 'Atendida'
        CANCELADA = 'CANCELADA', 'Cancelada'
        NO_ASISTIO = 'NO_ASISTIO', 'No asistió'

    # Clase de la insignia (text-bg-<color>, paleta en static/css/ordo-salud.css)
    COLORES = {'TENTATIVA': 'warning', 'PROGRAMADA': 'secondary', 'CONFIRMADA': 'info', 'EN_SALA': 'sala',
               'ATENDIDA': 'success', 'CANCELADA': 'danger', 'NO_ASISTIO': 'dark'}
    ACTIVAS = ('TENTATIVA', 'PROGRAMADA', 'CONFIRMADA', 'EN_SALA')

    paciente = models.ForeignKey('pacientes.Paciente', on_delete=models.PROTECT, related_name='citas')
    profesional = models.ForeignKey('equipo.PerfilProfesional', on_delete=models.PROTECT, related_name='citas')
    especialidad = models.ForeignKey('plataforma.Especialidad', on_delete=models.PROTECT, related_name='+')
    lugar = models.ForeignKey('configuracion.Lugar', on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='citas')
    tipo = models.ForeignKey(TipoCita, on_delete=models.SET_NULL, null=True, blank=True, related_name='citas')
    fecha = models.DateField('Fecha', db_index=True)
    hora_inicio = models.TimeField('Hora', null=True, blank=True, help_text='Vacía = cita tentativa sin hora.')
    hora_fin = models.TimeField('Hasta', null=True, blank=True)
    estado = models.CharField('Estado', max_length=10, choices=Estado.choices, default=Estado.PROGRAMADA)
    motivo = models.CharField('Motivo', max_length=200, blank=True)
    notas = models.TextField('Notas', blank=True)
    sobrecupo = models.BooleanField('Sobrecupo', default=False,
                                    help_text='Se agendó a propósito encima de otra cita.')
    consulta = models.OneToOneField('clinica.Consulta', on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='cita')
    consulta_origen = models.ForeignKey('clinica.Consulta', on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name='controles', editable=False,
                                        help_text='Consulta que indicó este control (próximo control).')
    recordatorio_en = models.DateTimeField('Recordatorio enviado', null=True, blank=True)
    motivo_cancelacion = models.CharField('Motivo de cancelación', max_length=200, blank=True)

    class Meta:
        verbose_name = 'Cita'
        verbose_name_plural = 'Citas'
        ordering = ['fecha', 'hora_inicio']
        indexes = [models.Index(fields=['tenant', 'profesional', 'fecha'], name='cita_profesional_fecha')]
        constraints = [models.CheckConstraint(
            condition=Q(hora_fin__isnull=True) | Q(hora_inicio__isnull=True) | Q(hora_fin__gt=models.F('hora_inicio')),
            name='cita_fin_mayor_inicio')]

    def __str__(self):
        return f'{self.paciente} · {self.fecha:%d/%m/%Y}'

    @property
    def color(self):
        return self.COLORES.get(self.estado, 'secondary')

    @property
    def activa(self):
        return self.estado in self.ACTIVAS

    @property
    def inicio(self):
        return datetime.combine(self.fecha, self.hora_inicio) if self.hora_inicio else None

    @property
    def duracion_min(self):
        if self.hora_inicio and self.hora_fin:
            return int((datetime.combine(self.fecha, self.hora_fin) - self.inicio) / timedelta(minutes=1))
        return None
