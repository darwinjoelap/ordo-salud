"""Configuración de cada tenant (identidad, documentos, historia, agenda) y sus lugares de consulta."""
from django.core.validators import RegexValidator
from django.db import models

from apps.core.tenancy import TenantModel

color_hex = RegexValidator(r'^#[0-9A-Fa-f]{6}$', 'Usa un color en formato #RRGGBB.')


def _ruta(instancia, archivo):
    return f'ordo-salud/{instancia.tenant.slug}/marca/{archivo}'


class ConfiguracionTenant(models.Model):
    class Visibilidad(models.TextChoices):
        COMPARTIDA = 'COMPARTIDA', 'Compartida: todos los médicos ven todas las consultas'
        POR_ESPECIALIDAD = 'POR_ESPECIALIDAD', 'Por especialidad: solo médicos de la misma especialidad'
        PRIVADA = 'PRIVADA', 'Privada: cada médico ve solo sus consultas'

    tenant = models.OneToOneField('plataforma.Tenant', on_delete=models.CASCADE, related_name='configuracion')
    # Identidad
    nombre_mostrar = models.CharField('Nombre del consultorio', max_length=150, blank=True,
                                      help_text='Como aparece en la app y en los documentos.')
    rif = models.CharField('RIF', max_length=20, blank=True)
    logo = models.ImageField('Logo', upload_to=_ruta, blank=True, help_text='PNG o JPG de hasta 2 MB.')
    logo_pdf = models.ImageField('Logo para PDF', upload_to=_ruta, blank=True, editable=False)
    color_primario = models.CharField('Color principal', max_length=7, default='#145F8F', validators=[color_hex])
    # Contacto
    direccion = models.TextField('Dirección', blank=True)
    telefono = models.CharField('Teléfono', max_length=40, blank=True)
    email = models.EmailField('Correo', blank=True)
    whatsapp = models.CharField('WhatsApp', max_length=20, blank=True, help_text='Formato internacional: 584121234567')
    mensaje_whatsapp = models.TextField('Mensaje adicional en recordatorios', blank=True,
                                        help_text='Se agrega al final del recordatorio de cita.')
    # Documentos
    membrete = models.ImageField('Membrete (banner)', upload_to=_ruta, blank=True,
                                 help_text='Imagen horizontal que reemplaza el encabezado de los PDF.')
    pie_documentos = models.CharField('Pie de página de documentos', max_length=200, blank=True)
    # Historia clínica
    visibilidad_historia = models.CharField('Visibilidad de la historia', max_length=20,
                                            choices=Visibilidad.choices, default=Visibilidad.COMPARTIDA)
    medicos_ven_todos_pacientes = models.BooleanField(
        'Los médicos pueden ver todos los pacientes', default=False,
        help_text='Apagado: cada médico ve sus pacientes (los que atendió, tiene citados o registró) y los nuevos '
                  'sin historia. Titular, administradores y asistentes siempre ven todos.')
    horas_edicion_consulta = models.PositiveSmallIntegerField(
        'Horas para editar una consulta', default=24,
        help_text='Pasado ese tiempo la consulta se cierra sola; después solo se corrige con una enmienda.')
    # Agenda
    hora_inicio_agenda = models.TimeField('Inicio de la jornada', null=True, blank=True)
    hora_fin_agenda = models.TimeField('Fin de la jornada', null=True, blank=True)
    duracion_cita_min = models.PositiveSmallIntegerField('Duración predeterminada de la cita (min)', default=30)
    # Módulos
    dictado_activo = models.BooleanField('Dictado por voz', default=False, editable=False,
                                         help_text='Lo activa la plataforma según el plan.')
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configuración del consultorio'
        verbose_name_plural = 'Configuraciones de consultorios'

    def __str__(self):
        return f'Configuración — {self.tenant}'

    @property
    def nombre_display(self):
        return self.nombre_mostrar or self.tenant.nombre


class Lugar(TenantModel):
    nombre = models.CharField('Nombre', max_length=100)
    ciudad = models.CharField('Ciudad', max_length=100, blank=True)
    direccion = models.CharField('Dirección', max_length=200, blank=True)
    telefono = models.CharField('Teléfono', max_length=30, blank=True)
    activo = models.BooleanField('Activo', default=True)
    orden = models.PositiveSmallIntegerField('Orden', default=0)

    class Meta:
        verbose_name = 'Lugar de consulta'
        verbose_name_plural = 'Lugares de consulta'
        ordering = ['orden', 'nombre']
        constraints = [models.UniqueConstraint(fields=['tenant', 'nombre'], name='lugar_unico')]

    def __str__(self):
        return self.nombre
