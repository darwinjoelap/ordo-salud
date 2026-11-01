"""
Comprueba el almacenamiento de archivos (R2 o carpeta local): escribe, lee, firma un enlace y borra un archivo de prueba.

    python manage.py probar_almacenamiento
"""
import uuid

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Escribe, lee y borra un archivo de prueba en el almacenamiento configurado.'

    def handle(self, **op):
        destino = f'R2 · depósito «{settings.R2_BUCKET}»' if settings.USAR_R2 else f'carpeta local {settings.MEDIA_ROOT}'
        self.stdout.write(f'Almacenamiento: {destino}')
        nombre = f'_prueba/{uuid.uuid4().hex}.txt'
        contenido = b'Ordo Salud: prueba de almacenamiento'
        try:
            guardado = default_storage.save(nombre, ContentFile(contenido))
            self.stdout.write(f'  ✔ escrito: {guardado}')
            with default_storage.open(guardado, 'rb') as f:
                if f.read() != contenido:
                    raise CommandError('Lo leído no coincide con lo escrito.')
            self.stdout.write('  ✔ leído')
            url = default_storage.url(guardado)
            firmado = 'X-Amz-Signature' in url
            self.stdout.write(f"  ✔ enlace{' firmado (vence)' if firmado else ''}: {url[:90]}…")
            default_storage.delete(guardado)
            self.stdout.write('  ✔ borrado')
        except CommandError:
            raise
        except Exception as e:  # noqa: BLE001
            raise CommandError(f'Falló: {e.__class__.__name__}: {e}. Revisa R2_ACCOUNT_ID, las claves y que el token '
                               'tenga permiso «Object Read & Write» sobre ese depósito.') from e
        self.stdout.write(self.style.SUCCESS('Almacenamiento OK.'))
