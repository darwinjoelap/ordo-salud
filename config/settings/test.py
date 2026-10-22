"""Settings para tests: contraseñas rápidas y archivos en carpeta temporal."""
import tempfile

from .dev import *  # noqa: F401,F403

PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
MEDIA_ROOT = tempfile.mkdtemp(prefix='ordo-media-')
STORAGES = {**STORAGES, 'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}}  # noqa: F405
DEBUG_TOOLBAR = False

# Tests silenciosos: los 403/404 esperados no llenan la salida de trazas
LOGGING = {'version': 1, 'disable_existing_loggers': False,
           'handlers': {'nulo': {'class': 'logging.NullHandler'}},
           'root': {'handlers': ['nulo'], 'level': 'CRITICAL'}}

# Sin caché entre tests (la tasa vigente se cachea 5 minutos)
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}}
