"""ADR-062: compartir enlace, usuario y contraseña desde la plataforma (la temporal vigente o una nueva)."""
from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase

from apps.core.cifrado import cifrar, descifrar
from apps.equipo.models import Membresia

from .base import CLAVE, crear_consultorio


class CifradoTest(SimpleTestCase):
    def test_ida_y_vuelta(self):
        self.assertEqual(descifrar(cifrar('Abc-123-xyz')), 'Abc-123-xyz')
        self.assertEqual(descifrar('basura'), '')
        self.assertEqual(cifrar(''), '')


class CompartirAccesoTest(TestCase):
    def setUp(self):
        get_user_model().objects.create_superuser('root', CLAVE)
        self.c = Client(HTTP_HOST='localhost')
        self.c.post('/cuenta/entrar/', {'username': 'root', 'password': CLAVE})
        from apps.plataforma import servicios
        from apps.plataforma.models import Especialidad
        esp = Especialidad.objects.get(codigo='pediatria')
        self.tenant, self.titular, self.clave = servicios.crear_tenant({
            'nombre': 'Sol', 'slug': 'sol', 'usuario_titular': 'dra', 'nombre_titular': 'Ana',
            'apellido_titular': 'Sol', 'titular_es_profesional': True, 'especialidad_titular': esp,
            'especialidades': [esp]})
        self.m = Membresia.objects.get(usuario=self.titular)
        self.url = f'/plataforma/{self.tenant.pk}/acceso/{self.m.pk}/'

    def test_comparte_la_temporal_vigente(self):
        self.titular.refresh_from_db()
        self.assertEqual(self.titular.clave_temporal_vigente(), self.clave)
        r = self.c.get(self.url)
        self.assertContains(r, self.clave)
        self.assertContains(r, 'wa.me/')

    def test_si_la_cambio_no_se_puede_ver(self):
        u = self.titular
        u.set_password('Su-clave-propia-2026')          # cambió su clave (p. ej. desde «Mi perfil»)
        u.save()
        self.assertEqual(u.clave_temporal_vigente(), '')
        r = self.c.get(self.url)
        self.assertNotContains(r, self.clave)
        self.assertContains(r, 'no se puede ver')

    def test_generar_nueva(self):
        r = self.c.post(self.url)
        self.titular.refresh_from_db()
        nueva = self.titular.clave_temporal_vigente()
        self.assertTrue(nueva and nueva != self.clave)
        self.assertContains(r, nueva)
        self.assertFalse(self.titular.check_password(self.clave))
        self.assertTrue(self.titular.debe_cambiar_clave)

    def test_cambio_desde_mi_perfil_borra_la_cifrada(self):
        _, titular = crear_consultorio('Dos', 'dos', usuario='doc')
        titular.poner_clave_temporal('Temporal-123-abc')
        c = Client(HTTP_HOST='localhost')
        c.post('/dos/', {'username': 'doc', 'password': 'Temporal-123-abc'})
        c.post('/cuenta/perfil/', {'accion': 'clave', 'old_password': 'Temporal-123-abc',
                                   'new_password1': 'Mi-clave-nueva-2026', 'new_password2': 'Mi-clave-nueva-2026'})
        titular.refresh_from_db()
        self.assertEqual((titular.clave_temporal_cifrada, titular.debe_cambiar_clave), ('', False))

    def test_no_plataforma_no_entra(self):
        c = Client(HTTP_HOST='localhost')
        self.assertNotEqual(c.get(self.url).status_code, 200)
