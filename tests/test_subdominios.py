"""ADR-049: subdominio por consultorio (<slug>.BASE_DOMAIN) con respaldo por ruta."""
from django.contrib.auth import get_user_model
from django.test import Client, override_settings

from .base import CLAVE, BaseTest, crear_consultorio

BASE = 'salud.test'
HOSTS = ['.salud.test', 'localhost', 'testserver']


@override_settings(BASE_DOMAIN=BASE, ALLOWED_HOSTS=HOSTS)
class SubdominioTest(BaseTest):
    def setUp(self):
        super().setUp()
        self.otro, _ = crear_consultorio('Otro', 'otro', usuario='titular')

    def cliente_en(self, sub):
        return Client(HTTP_HOST=f'{sub}.{BASE}')

    def test_la_raiz_del_subdominio_es_el_login_con_su_marca(self):
        r = self.cliente_en('uno').get('/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['tenant_marca'], self.tenant)

    def test_entra_en_su_subdominio_y_trabaja_sin_ruta(self):
        c = self.cliente_en('uno')
        r = c.post('/', {'username': 'titular', 'password': CLAVE})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(c.get('/pacientes/').status_code, 200)
        self.assertEqual(c.get('/pacientes/').wsgi_request.tenant, self.tenant)

    def test_mismo_usuario_en_otro_consultorio_entra_al_suyo(self):
        # «titular» existe en los dos: el host decide de qué consultorio es la cuenta
        c = self.cliente_en('otro')
        c.post('/', {'username': 'titular', 'password': CLAVE})
        self.assertEqual(c.get('/pacientes/').wsgi_request.tenant, self.otro)

    def test_la_sesion_de_un_consultorio_no_sirve_en_otro_host(self):
        c = self.cliente_en('uno')
        c.post('/', {'username': 'titular', 'password': CLAVE})
        sesion = c.cookies['sessionid'].value
        intruso = self.cliente_en('otro')
        intruso.cookies['sessionid'] = sesion          # aunque copie la cookie, la cuenta no es de «otro»
        r = intruso.get('/pacientes/')
        self.assertEqual(r.status_code, 403)

    def test_consultorio_inexistente_y_plataforma_bloqueada(self):
        self.assertEqual(self.cliente_en('nadie').get('/').status_code, 404)
        self.assertEqual(self.cliente_en('uno').get('/plataforma/').status_code, 404)

    def test_admin_es_el_panel_de_plataforma(self):
        r = self.cliente_en('admin').get('/')
        self.assertRedirects(r, '/cuenta/entrar/?plataforma=1', fetch_redirect_response=False)
        get_user_model().objects.create_superuser('raiz', CLAVE)
        c = self.cliente_en('admin')
        self.assertEqual(c.post('/cuenta/entrar/?plataforma=1', {'username': 'raiz', 'password': CLAVE}).status_code,
                         302)
        self.assertEqual(c.get('/plataforma/').status_code, 200)

    def test_dominio_base_con_ruta_redirige_al_subdominio(self):
        r = Client(HTTP_HOST=BASE).get('/uno/')
        self.assertRedirects(r, 'http://uno.salud.test/', fetch_redirect_response=False)

    def test_la_ruta_sigue_funcionando_en_otro_host(self):
        # p. ej. la dirección de Railway antes de tener el dominio
        self.assertEqual(Client(HTTP_HOST='localhost').get('/uno/').status_code, 200)

    def test_enlace_que_muestra_la_plataforma(self):
        from django.test import RequestFactory

        from apps.core.subdominios import enlace
        self.assertEqual(enlace(RequestFactory().get('/', secure=True), 'dra-sierra'), 'https://dra-sierra.salud.test/')
