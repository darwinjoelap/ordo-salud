"""
Usuario de Ordo Salud.

- Se inicia sesión con NOMBRE DE USUARIO (no con correo; el correo es opcional).
- Cada tenant (consultorio o clínica) tiene sus propios usuarios: `tenant_cuenta` + `username` es único.
  'maria' puede existir en dos tenants distintos; se entra por el enlace del tenant (/<slug>/).
- Las cuentas de plataforma (superusuarios) no tienen tenant y se entran por la dirección principal.
- El ROL no vive aquí: vive en la membresía usuario↔tenant.
"""
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import models
from django.db.models import Q


def normalizar_usuario(username):
    return (username or '').strip().lower()


class UsuarioManager(BaseUserManager):
    use_in_migrations = True

    def get_by_natural_key(self, username):
        """Solo cuentas de plataforma (sin tenant): lo usan createsuperuser y el login principal/admin."""
        return self.get(username=normalizar_usuario(username), tenant_cuenta__isnull=True)

    def _crear(self, username, password, **extra):
        username = normalizar_usuario(username)
        if not username:
            raise ValueError('El nombre de usuario es obligatorio.')
        email = extra.pop('email', '') or ''
        usuario = self.model(username=username, email=self.normalize_email(email).lower(), **extra)
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_user(self, username, password=None, **extra):
        extra.setdefault('is_staff', False)
        extra.setdefault('is_superuser', False)
        return self._crear(username, password, **extra)

    def create_superuser(self, username, password=None, **extra):
        extra.setdefault('is_staff', True)
        extra.setdefault('is_superuser', True)
        extra['tenant_cuenta'] = None
        if not extra['is_staff'] or not extra['is_superuser']:
            raise ValueError('El superusuario necesita is_staff e is_superuser.')
        return self._crear(username, password, **extra)


class Usuario(AbstractUser):
    username = models.CharField(
        'Usuario', max_length=60, validators=[UnicodeUsernameValidator()],
        help_text='Letras, números y . _ - @ (sin espacios). Se guarda en minúsculas.')
    tenant_cuenta = models.ForeignKey(
        'plataforma.Tenant', on_delete=models.PROTECT, null=True, blank=True, related_name='cuentas',
        verbose_name='Consultorio de la cuenta', help_text='Vacío = cuenta de plataforma (administración de Ordo Salud).')
    email = models.EmailField('Correo (opcional)', blank=True)
    telefono = models.CharField('Teléfono', max_length=30, blank=True)
    debe_cambiar_clave = models.BooleanField(
        'Debe cambiar la contraseña', default=False,
        help_text='Se activa al asignar una contraseña temporal; se pide cambiarla al entrar.')

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = []

    objects = UsuarioManager()

    class Meta:
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'
        ordering = ['first_name', 'last_name', 'username']
        constraints = [
            models.UniqueConstraint(fields=['tenant_cuenta', 'username'], name='usuario_unico_por_tenant'),
            models.UniqueConstraint(fields=['username'], condition=Q(tenant_cuenta__isnull=True),
                                    name='usuario_plataforma_unico'),
        ]

    def save(self, *args, **kwargs):
        self.username = normalizar_usuario(self.username)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre_visible

    @property
    def nombre_visible(self):
        return self.get_full_name() or self.username

    @property
    def iniciales(self):
        partes = [self.first_name[:1], self.last_name[:1]]
        texto = ''.join(p for p in partes if p) or self.username[:1]
        return texto.upper()
