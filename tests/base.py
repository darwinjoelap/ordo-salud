"""Utilidades comunes de los tests: crear consultorios, usuarios y entrar por su enlace."""
from django.test import Client, TestCase

from apps.core.tenancy import usando_tenant
from apps.plataforma import servicios as plataforma
from apps.plataforma.models import Especialidad

CLAVE = 'Clave-de-prueba-123'


def crear_consultorio(nombre='Consultorio Uno', slug='uno', especialidad='medicina_general', usuario='titular',
                      profesional=True):
    esp = Especialidad.objects.get(codigo=especialidad)
    tenant, titular, _ = plataforma.crear_tenant({
        'nombre': nombre, 'slug': slug, 'usuario_titular': usuario, 'nombre_titular': 'Ana',
        'apellido_titular': 'Pérez', 'titular_es_profesional': profesional, 'especialidad_titular': esp,
        'titulo_titular': 'Dra.', 'especialidades': [esp]})
    titular.set_password(CLAVE)
    titular.debe_cambiar_clave = False
    titular.save()
    return tenant, titular


class BaseTest(TestCase):
    def setUp(self):
        self.tenant, self.titular = crear_consultorio()
        self.cliente = self.entrar(self.tenant, 'titular')

    @staticmethod
    def entrar(tenant, username, clave=CLAVE):
        c = Client(HTTP_HOST='localhost')
        r = c.post(f'/{tenant.slug}/', {'username': username, 'password': clave})
        assert r.status_code == 302, f'No pudo entrar {username}: {r.status_code}'
        return c

    def en_tenant(self, tenant=None):
        return usando_tenant(tenant or self.tenant)

    def iniciar_independiente(self, paciente, datos, *, cliente=None):
        cliente = cliente or self.cliente
        url = f'/pacientes/{paciente.pk}/consultas/nueva/'
        formulario = cliente.get(url, {'independiente': '1'})
        intento = formulario.context['intento'] if formulario.status_code == 200 else ''
        return cliente.post(url, {**datos, 'independiente': '1', 'intento': intento})
