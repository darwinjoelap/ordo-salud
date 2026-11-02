"""
Ordo Salud — settings base (comunes a desarrollo y producción).
Todo lo sensible viene de variables de entorno (.env en local, Railway en la nube).
"""
from pathlib import Path

import dj_database_url
from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config('SECRET_KEY', default='dev-inseguro-cambiar')
DEBUG = False
ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=Csv(), default='localhost,127.0.0.1')
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', cast=Csv(), default='')
# Subdominio por consultorio (ADR-049): 'salud.ordove.com' → https://<slug>.salud.ordove.com. Vacío = solo por ruta.
BASE_DOMAIN = config('BASE_DOMAIN', default='')

PRODUCTO = 'Ordo Salud'
# Versión visible y usada para invalidar la caché de la PWA en cada despliegue
ORDO_VERSION = config('RAILWAY_GIT_COMMIT_SHA', default='dev')[:7]

# ── Aplicaciones ──────────────────────────────────────────────────────────────
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

ORDO_APPS = [
    'apps.core',
    'apps.usuarios',
    'apps.plataforma',
    'apps.equipo',
    'apps.configuracion',
    'apps.tasas',
    'apps.cobros',
    'apps.pacientes',
    'apps.agenda',
    'apps.clinica',
    'apps.documentos',
    'apps.reportes',
    'apps.offline',
    'apps.dictado',
    # Especialidades (módulos enchufables): agregar aquí + `sincronizar_especialidades`
    'apps.especialidades.general',
    'apps.especialidades.pediatria',
    'apps.especialidades.ginecologia',
    'apps.especialidades.cardiologia_pediatrica',
]

# apps.usuarios primero para que su `createsuperuser` reemplace al de Django
INSTALLED_APPS = ['apps.usuarios'] + DJANGO_APPS + [a for a in ORDO_APPS if a != 'apps.usuarios']

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.core.subdominios.SubdominioMiddleware',       # <slug>.BASE_DOMAIN → consultorio (ADR-049)
    'apps.usuarios.middleware.CambioClaveObligatorioMiddleware',
    'apps.core.middleware.TenantActivoMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.core.middleware.ErrorDeNegocioMiddleware',
    'apps.offline.middleware.IdempotenciaMiddleware',   # al final: necesita usuario y mensajes
]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.core.context_processors.marca',
            ],
            'builtins': ['apps.core.templatetags.ordo'],
        },
    },
]

# ── Base de datos ─────────────────────────────────────────────────────────────
# DATABASE_URL vacío o ausente = SQLite local
DATABASE_URL = config('DATABASE_URL', default='') or f'sqlite:///{BASE_DIR / "db.sqlite3"}'
DATABASES = {'default': dj_database_url.parse(DATABASE_URL, conn_max_age=600, conn_health_checks=True)}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── Usuarios ──────────────────────────────────────────────────────────────────
AUTH_USER_MODEL = 'usuarios.Usuario'
AUTHENTICATION_BACKENDS = ['apps.usuarios.backends.UsuarioPorTenantBackend']
# El usuario es único por tenant (no global): lo garantiza una restricción propia y el backend de arriba.
SILENCED_SYSTEM_CHECKS = ['auth.W004']
LOGIN_URL = 'usuarios:login'
LOGIN_REDIRECT_URL = 'core:inicio'
LOGOUT_REDIRECT_URL = 'usuarios:login'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ── Idioma y zona horaria ─────────────────────────────────────────────────────
LANGUAGE_CODE = 'es-ve'
TIME_ZONE = 'America/Caracas'
USE_I18N = True
USE_TZ = True

# ── Estáticos (WhiteNoise) y archivos (Cloudflare R2, ADR-051) ──────────────────
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Depósito PRIVADO: nada es público. Los adjuntos clínicos se sirven por una vista con permisos; logos, firmas y
# banners con enlaces firmados que vencen. Sin R2_BUCKET (tests, desarrollo sin red) = carpeta media/ local.
R2_BUCKET = config('R2_BUCKET', default='')
USAR_R2 = bool(R2_BUCKET)
_ARCHIVOS = {'BACKEND': 'django.core.files.storage.FileSystemStorage'}
if USAR_R2:
    _ARCHIVOS = {
        'BACKEND': 'storages.backends.s3.S3Storage',
        'OPTIONS': {
            'bucket_name': R2_BUCKET,
            'endpoint_url': f"https://{config('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
            'access_key': config('R2_ACCESS_KEY_ID'),
            'secret_key': config('R2_SECRET_ACCESS_KEY'),
            'region_name': 'auto',
            'signature_version': 's3v4',
            'default_acl': None,                 # R2 no usa ACL; el depósito es privado
            'querystring_auth': True,            # .url = enlace firmado
            'querystring_expire': config('R2_URL_EXPIRA', default=3600, cast=int),
            'file_overwrite': False,             # nunca pisar un archivo con el mismo nombre
            'location': config('R2_PREFIJO', default=''),
        },
    }
STORAGES = {
    'default': _ARCHIVOS,
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}

# ── Correo ────────────────────────────────────────────────────────────────────
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='Ordo Salud <no-responder@ordosalud.app>')

# ── Mensajes con clases de Bootstrap ──────────────────────────────────────────
from django.contrib.messages import constants as messages  # noqa: E402

MESSAGE_TAGS = {
    messages.DEBUG: 'secondary',
    messages.INFO: 'info',
    messages.SUCCESS: 'success',
    messages.WARNING: 'warning',
    messages.ERROR: 'danger',
}

# ── Logging a consola (Railway lo recoge) ─────────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {'simple': {'format': '[{levelname}] {asctime} {name}: {message}', 'style': '{'}},
    'handlers': {'console': {'class': 'logging.StreamHandler', 'formatter': 'simple'}},
    'root': {'handlers': ['console'], 'level': 'WARNING'},
    'loggers': {'apps': {'handlers': ['console'], 'level': 'INFO', 'propagate': False}},
}

# ── Dictado de la consulta con IA (ADR-045) ───────────────────────────────────
# Sin claves funciona en modo de prueba (no sale a internet). El audio nunca se guarda.
DICTADO_PROVEEDOR = config('DICTADO_PROVEEDOR', default='gemini')    # gemini | openai_claude
GEMINI_API_KEY = config('GEMINI_API_KEY', default='')
DICTADO_RAZONAMIENTO = config('DICTADO_RAZONAMIENTO', default='low')   # minimal | low | medium | high
DICTADO_MODELO_GEMINI = config('DICTADO_MODELO_GEMINI', default='gemini-3.8-flash')
OPENAI_API_KEY = config('OPENAI_API_KEY', default='')
ANTHROPIC_API_KEY = config('ANTHROPIC_API_KEY', default='')
DICTADO_MODO = config('DICTADO_MODO', default='')                 # 'prueba' fuerza el modo de prueba
DICTADO_MODELO_TRANSCRIPCION = config('DICTADO_MODELO_TRANSCRIPCION', default='gpt-4o-transcribe')
DICTADO_MODELO_IA = config('DICTADO_MODELO_IA', default='claude-sonnet-5-5')
DICTADO_SINCRONO = config('DICTADO_SINCRONO', default=False, cast=bool)
