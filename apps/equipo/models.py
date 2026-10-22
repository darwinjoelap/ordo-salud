"""
Equipo de un tenant: membresías usuario↔tenant con rol y perfil profesional (ADR-005).

- Un usuario puede tener membresías en varios tenants (médico que atiende en dos clínicas).
- PROFESIONAL = membresía con PerfilProfesional activo. Cada profesional tiene UNA especialidad en el tenant.
"""
from django.conf import settings
from django.db import models

from apps.core.permisos import Rol
from apps.core.tenancy import Auditable, TenantModel


class Membresia(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='membresias', verbose_name='Usuario')
    tenant = models.ForeignKey('plataforma.Tenant', on_delete=models.CASCADE,
                               related_name='membresias', verbose_name='Consultorio')
    rol = models.CharField('Rol', max_length=10, choices=Rol.choices, default=Rol.ASISTENTE)
    activa = models.BooleanField('Activa', default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Membresía'
        verbose_name_plural = 'Membresías'
        ordering = ['tenant__nombre', 'usuario__first_name', 'usuario__username']
        constraints = [models.UniqueConstraint(fields=['usuario', 'tenant'], name='membresia_unica')]

    def __str__(self):
        return f'{self.usuario} — {self.tenant} ({self.get_rol_display()})'

    @property
    def perfil_activo(self):
        """PerfilProfesional activo o None (usa la caché de select_related si existe)."""
        try:
            perfil = self.perfil
        except PerfilProfesional.DoesNotExist:
            return None
        except ValueError:          # membresía sin guardar (soporte virtual)
            return None
        return perfil if perfil.activo else None

    @property
    def es_profesional(self):
        return self.perfil_activo is not None


def _ruta_firma(instancia, archivo):
    return f'ordo-salud/{instancia.tenant.slug}/profesionales/{instancia.membresia_id}/{archivo}'


class PerfilProfesional(TenantModel, Auditable):
    class Titulo(models.TextChoices):
        DR = 'Dr.', 'Dr.'
        DRA = 'Dra.', 'Dra.'
        LIC = 'Lic.', 'Lic.'
        NINGUNO = '', '(sin título)'

    membresia = models.OneToOneField(Membresia, on_delete=models.CASCADE, related_name='perfil')
    especialidad = models.ForeignKey('plataforma.Especialidad', on_delete=models.PROTECT, related_name='+',
                                     verbose_name='Especialidad')
    subespecialidad = models.CharField('Subespecialidad', max_length=120, blank=True)
    titulo = models.CharField('Título', max_length=5, choices=Titulo.choices, default=Titulo.DR, blank=True)
    credenciales = models.CharField('Credenciales / posgrado', max_length=300, blank=True,
                                    help_text='Ej.: Especialista en Pediatría y Puericultura (UCV)')
    numero_mpps = models.CharField('N.º MPPS', max_length=30, blank=True)
    numero_colegio = models.CharField('N.º Colegio de Médicos', max_length=40, blank=True,
                                      help_text='Ej.: CMEL 12345')
    telefono_consulta = models.CharField('Teléfono de consulta', max_length=30, blank=True)
    firma = models.ImageField('Firma', upload_to=_ruta_firma, blank=True,
                              help_text='PNG con fondo transparente; aparece sobre la línea de firma de los PDF.')
    sello = models.ImageField('Sello', upload_to=_ruta_firma, blank=True,
                              help_text='PNG con fondo transparente; aparece junto a la firma.')
    membrete = models.ImageField('Banner del encabezado', upload_to=_ruta_firma, blank=True,
                                 help_text='Imagen horizontal de 1200 × 200 px (6:1), PNG o JPG con fondo blanco '
                                           'o transparente. Reemplaza el encabezado escrito.')
    usar_membrete_propio = models.BooleanField('Usar mi banner en los PDF', default=False,
                                               help_text='Reemplaza el encabezado escrito por la imagen del banner.')
    logo = models.ImageField('Logo propio', upload_to=_ruta_firma, blank=True,
                             help_text='Aparece junto a su nombre en el encabezado y como marca de agua. '
                                       'Si no carga uno, se usa el logo del consultorio.')
    marca_agua = models.BooleanField('Logo de fondo (marca de agua) en los PDF', default=True,
                                     help_text='Logo tenue en el centro de récipes, informes y constancias.')
    color_agenda = models.CharField('Color en la agenda', max_length=7, default='#1C8577')
    activo = models.BooleanField('Activo', default=True)

    class Meta:
        verbose_name = 'Perfil profesional'
        verbose_name_plural = 'Perfiles profesionales'
        ordering = ['membresia__usuario__first_name']

    def __str__(self):
        return self.nombre_con_titulo

    @property
    def usuario(self):
        return self.membresia.usuario

    @property
    def nombre_con_titulo(self):
        nombre = self.membresia.usuario.nombre_visible
        return f'{self.titulo} {nombre}'.strip()

    @property
    def especialidad_texto(self):
        partes = [self.especialidad.nombre if self.especialidad_id else '', self.subespecialidad]
        return ' · '.join(p for p in partes if p)

    @property
    def registros_texto(self):
        partes = [f'MPPS {self.numero_mpps}' if self.numero_mpps else '', self.numero_colegio]
        return ' · '.join(p for p in partes if p)

    @property
    def tiene_firma(self):
        return bool(self.firma or self.sello)
