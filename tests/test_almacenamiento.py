"""ADR-051: archivos en Cloudflare R2 privado (sin red: solo configuración, firma de enlaces y rutas)."""
from io import StringIO
from types import SimpleNamespace

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

R2 = {
    'default': {'BACKEND': 'storages.backends.s3.S3Storage', 'OPTIONS': {
        'bucket_name': 'ordo-salud-dev', 'endpoint_url': 'https://abc123.r2.cloudflarestorage.com',
        'access_key': 'AKIAPRUEBA', 'secret_key': 'secreto', 'region_name': 'auto', 'signature_version': 's3v4',
        'default_acl': None, 'querystring_auth': True, 'querystring_expire': 3600, 'file_overwrite': False}},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}


class AlmacenamientoTest(SimpleTestCase):
    @override_settings(STORAGES=R2)
    def test_r2_da_enlaces_firmados_que_vencen(self):
        from django.core.files.storage import storages
        url = storages.create_storage(R2['default']).url('ordo-salud/x/marca/logo.png')
        self.assertTrue(url.startswith('https://abc123.r2.cloudflarestorage.com/ordo-salud-dev/'), url)
        self.assertIn('X-Amz-Signature=', url)
        self.assertIn('X-Amz-Expires=3600', url)

    def test_la_ruta_del_adjunto_no_revela_al_paciente(self):
        from apps.clinica.models.consulta import _ruta_adjunto
        instancia = SimpleNamespace(tenant=SimpleNamespace(slug='dra-sierra'), paciente_id=7)
        ruta = _ruta_adjunto(instancia, 'Eco Juan Pérez V-12345678.PDF')
        self.assertRegex(ruta, r'^ordo-salud/dra-sierra/pacientes/7/[0-9a-f]{32}\.pdf$')

    def test_settings_sin_r2_usan_carpeta_local(self):
        from django.conf import settings
        self.assertFalse(settings.USAR_R2)
        self.assertEqual(settings.STORAGES['default']['BACKEND'], 'django.core.files.storage.FileSystemStorage')

    def test_comando_de_prueba_en_local(self):
        salida = StringIO()
        call_command('probar_almacenamiento', stdout=salida)
        self.assertIn('Almacenamiento OK.', salida.getvalue())
