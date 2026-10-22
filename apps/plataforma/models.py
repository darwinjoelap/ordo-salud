"""
Plataforma (sin tenant): consultorios/clínicas cliente, planes, renovaciones y catálogo de especialidades.
"""
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class Plan(models.Model):
    nombre = models.CharField('Nombre', max_length=80, unique=True)
    precio_usd = models.DecimalField('Precio mensual (USD)', max_digits=8, decimal_places=2, default=0)
    precio_anual_usd = models.DecimalField('Precio anual (USD)', max_digits=9, decimal_places=2, null=True, blank=True)
    max_profesionales = models.PositiveSmallIntegerField('Máx. profesionales', null=True, blank=True,
                                                         help_text='Vacío = sin límite.')
    max_usuarios = models.PositiveSmallIntegerField('Máx. usuarios activos', null=True, blank=True,
                                                    help_text='Vacío = sin límite.')
    incluye_dictado = models.BooleanField('Incluye dictado por voz', default=False)
    minutos_dictado_mes = models.PositiveIntegerField('Minutos de dictado al mes', default=0,
                                                      help_text='Dictado con IA. 0 = sin límite.')
    dias_gracia = models.PositiveSmallIntegerField(
        'Días de gracia', default=3,
        help_text='Días después del vencimiento en que el consultorio sigue entrando (con aviso) antes del bloqueo.')
    descripcion = models.CharField('Descripción', max_length=200, blank=True)
    activo = models.BooleanField('Activo', default=True, help_text='Inactivo = no se ofrece a consultorios nuevos.')

    class Meta:
        verbose_name = 'Plan'
        verbose_name_plural = 'Planes'
        ordering = ['precio_usd', 'nombre']

    def __str__(self):
        return self.nombre


class Especialidad(models.Model):
    """Catálogo global. Las filas las crea/actualiza `sincronizar_especialidades` desde los módulos instalados."""
    codigo = models.SlugField('Código', max_length=40, unique=True)
    nombre = models.CharField('Nombre', max_length=100)
    color = models.CharField('Color', max_length=7, default='#145F8F')
    icono = models.CharField('Ícono (Bootstrap Icons)', max_length=40, default='bi-heart-pulse')
    modulo = models.CharField('Módulo', max_length=120, blank=True,
                              help_text='App que la implementa. Vacío = sin módulo (solo secciones generales).')
    activa = models.BooleanField('Activa', default=True)
    orden = models.PositiveSmallIntegerField('Orden', default=100)

    class Meta:
        verbose_name = 'Especialidad'
        verbose_name_plural = 'Especialidades'
        ordering = ['orden', 'nombre']

    def __str__(self):
        return self.nombre


class Tenant(models.Model):
    """Un consultorio o una clínica cliente de Ordo Salud."""

    class Estado(models.TextChoices):
        ACTIVO = 'ACTIVO', 'Activo'
        SUSPENDIDO = 'SUSPENDIDO', 'Suspendido'

    nombre = models.CharField('Nombre', max_length=150)
    slug = models.SlugField('Enlace', max_length=60, unique=True,
                            help_text='Se usa en el enlace de entrada (/enlace/) y en carpetas de Cloudinary.')
    estado = models.CharField('Estado', max_length=12, choices=Estado.choices, default=Estado.ACTIVO)
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, null=True, blank=True, related_name='tenants')
    activo_hasta = models.DateField('Activo hasta', null=True, blank=True, help_text='Vacío = sin vencimiento.')
    limite_usuarios = models.PositiveSmallIntegerField('Límite de usuarios activos', null=True, blank=True,
                                                       help_text='Vacío = el del plan.')
    limite_profesionales = models.PositiveSmallIntegerField('Límite de profesionales', null=True, blank=True,
                                                            help_text='Vacío = el del plan.')
    dias_gracia = models.PositiveSmallIntegerField('Días de gracia', null=True, blank=True,
                                                   help_text='Vacío = los del plan.')
    especialidades = models.ManyToManyField(Especialidad, blank=True, related_name='tenants',
                                            verbose_name='Especialidades habilitadas')
    notas = models.TextField('Notas internas (solo plataforma)', blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Tenant (consultorio o clínica)'
        verbose_name_plural = 'Tenants (consultorios y clínicas)'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.nombre)[:50] or 'consultorio'
            slug, n = base, 2
            while Tenant.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug, n = f'{base}-{n}', n + 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def dias_para_vencer(self):
        if not self.activo_hasta:
            return None
        return (self.activo_hasta - timezone.localdate()).days

    @property
    def gracia(self):
        """Días de gracia que aplican: los propios, si no los del plan; sin plan, ninguno."""
        if self.dias_gracia is not None:
            return self.dias_gracia
        return self.plan.dias_gracia if self.plan_id else 0

    @property
    def bloqueo_el(self):
        """Primer día sin acceso (vencimiento + gracia + 1). None = sin vencimiento."""
        return self.activo_hasta + timedelta(days=self.gracia + 1) if self.activo_hasta else None

    @property
    def en_gracia(self):
        hoy = timezone.localdate()
        return (self.estado == self.Estado.ACTIVO and self.activo_hasta is not None
                and self.activo_hasta < hoy < self.bloqueo_el)

    @property
    def dias_de_gracia_restantes(self):
        return (self.bloqueo_el - timezone.localdate()).days if self.en_gracia else None

    @property
    def esta_activo(self):
        """Puede entrar: estado activo y sin vencer (o dentro de los días de gracia)."""
        if self.estado != self.Estado.ACTIVO:
            return False
        return not (self.activo_hasta and timezone.localdate() >= self.bloqueo_el)

    @property
    def estado_servicio(self):
        """ACTIVO · GRACIA · VENCIDO · SUSPENDIDO (para listas y tableros)."""
        if self.estado != self.Estado.ACTIVO:
            return 'SUSPENDIDO'
        if self.en_gracia:
            return 'GRACIA'
        return 'ACTIVO' if self.esta_activo else 'VENCIDO'

    @property
    def max_usuarios(self):
        if self.limite_usuarios is not None:
            return self.limite_usuarios
        return self.plan.max_usuarios if self.plan_id else None

    @property
    def max_profesionales(self):
        if self.limite_profesionales is not None:
            return self.limite_profesionales
        return self.plan.max_profesionales if self.plan_id else None


class Suscripcion(models.Model):
    """Historial de renovaciones/pagos del servicio. Registrar una extiende `Tenant.activo_hasta`."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='suscripciones')
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, null=True, blank=True)
    desde = models.DateField('Desde')
    hasta = models.DateField('Hasta')
    monto_usd = models.DecimalField('Monto (USD)', max_digits=9, decimal_places=2, default=0)
    referencia = models.CharField('Referencia de pago', max_length=100, blank=True)
    notas = models.CharField('Notas', max_length=200, blank=True)
    # Cómo estaba el consultorio antes de esta renovación (para poder anularla)
    hasta_anterior = models.DateField('Vencía antes', null=True, blank=True)
    plan_anterior = models.ForeignKey(Plan, on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='+')
    anulada = models.BooleanField('Anulada', default=False)
    motivo_anulacion = models.CharField('Motivo de la anulación', max_length=200, blank=True)
    anulada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='+')
    anulada_en = models.DateTimeField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Renovación'
        verbose_name_plural = 'Renovaciones'
        ordering = ['-creado_en']

    def __str__(self):
        return f'{self.tenant} · {self.desde:%d/%m/%Y} → {self.hasta:%d/%m/%Y}'


class AccesoSoporte(models.Model):
    """Cada vez que un administrador de Ordo Salud entra a un consultorio como soporte (trazabilidad)."""
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='accesos_soporte')
    inicio = models.DateTimeField(auto_now_add=True)
    fin = models.DateTimeField(null=True, blank=True)
    motivo = models.CharField('Motivo', max_length=200, blank=True)

    class Meta:
        verbose_name = 'Acceso de soporte'
        verbose_name_plural = 'Accesos de soporte'
        ordering = ['-inicio']

    def __str__(self):
        return f'{self.usuario} → {self.tenant} · {self.inicio:%d/%m/%Y %H:%M}'
