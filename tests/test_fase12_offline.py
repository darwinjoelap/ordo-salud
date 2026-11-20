"""Fase 12: modo sin conexión de consulta (idempotencia, ping, precarga y consulta nueva completa)."""
from datetime import time, timedelta

from django.utils import timezone

from apps.agenda.models import Cita, TipoCita
from apps.clinica.models import Consulta, PlantillaHistoria, Procedimiento
from apps.cobros.models import Cargo, Pago, PagoAplicado, Servicio
from apps.core.models import Auditoria
from apps.equipo.models import Membresia
from apps.offline.models import SolicitudIdempotente
from apps.pacientes.models import Paciente

from .base import BaseTest, crear_consultorio

CLAVE = '0f6a1c2e-1111-4a2b-9c3d-000000000001'


class OfflineTest(BaseTest):
    def setUp(self):
        super().setUp()
        with self.en_tenant():
            self.perfil = Membresia.objects.get(usuario=self.titular).perfil
            self.paciente = Paciente.objects.create(nombres='Elena', apellidos='Paz', sexo='F')
            control = PlantillaHistoria.objects.get(nombre='Control')
            servicio = Servicio.objects.create(nombre='Control', precio_usd=30)
            self.tipo = TipoCita.objects.get(nombre='Control')
            self.tipo.duracion_min = 20
            self.tipo.tipo_consulta = 'CONTROL'
            self.tipo.plantilla = control
            self.tipo.servicio = servicio
            self.tipo.save()
            self.cita = Cita.objects.create(paciente=self.paciente, profesional=self.perfil, tipo=self.tipo,
                                            especialidad=self.perfil.especialidad, fecha=timezone.localdate(),
                                            hora_inicio=time(9), hora_fin=time(9, 20), estado='EN_SALA')
        self.url_nueva = f'/pacientes/{self.paciente.pk}/consultas/nueva/'

    def datos_completos(self, **extra):
        """Arma el POST de la consulta nueva a partir del formulario que muestra el GET."""
        r = self.cliente.get(f'{self.url_nueva}?cita={self.cita.pk}')
        self.assertEqual(r.status_code, 200)
        datos = {'completa': '1', 'plantilla': r.context['consulta'].plantilla_id, 'tipo': 'CONTROL',
                 'cita': self.cita.pk, 'accion': 'guardar'}
        item, form = r.context['formularios'][0]
        for nombre, campo in form.fields.items():
            if campo.__class__.__name__ == 'CharField':
                datos[f'{form.prefix}-{nombre}'] = 'Fiebre de dos días'
                break
        datos.update(extra)
        return datos

    # ── consulta nueva completa ──
    def test_get_muestra_formulario_sin_crear_nada(self):
        r = self.cliente.get(f'{self.url_nueva}?cita={self.cita.pk}')
        self.assertContains(r, 'name="completa"')
        self.assertContains(r, 'data-os-inicio')
        self.assertEqual(r.context['consulta'].plantilla.nombre, 'Control')
        with self.en_tenant():
            self.assertFalse(Consulta.objects.exists())

    def test_post_completa_crea_consulta_vincula_cita_y_cobra(self):
        inicio = (timezone.now() - timedelta(hours=2)).isoformat()
        r = self.cliente.post(self.url_nueva, self.datos_completos(inicio=inicio))
        with self.en_tenant():
            consulta = Consulta.objects.get()
            self.cita.refresh_from_db()
            self.assertEqual(self.cita.consulta, consulta)
            self.assertEqual(self.cita.estado, Cita.Estado.ATENDIDA)
            self.assertEqual(Cargo.objects.filter(consulta=consulta).count(), 1)
            self.assertLess(abs((consulta.fecha_hora - (timezone.now() - timedelta(hours=2))).total_seconds()), 60)
        self.assertRedirects(r, f'/consultas/{consulta.pk}/editar/', fetch_redirect_response=False)

    def test_hora_de_inicio_vieja_se_ignora(self):
        self.cliente.post(self.url_nueva, self.datos_completos(inicio='2020-01-01T08:00:00Z'))
        with self.en_tenant():
            self.assertLess((timezone.now() - Consulta.objects.get().fecha_hora).total_seconds(), 60)

    def test_misma_clave_dos_veces_una_sola_consulta(self):
        datos = self.datos_completos(_idem_key=CLAVE)
        r1 = self.cliente.post(self.url_nueva, datos)
        r2 = self.cliente.post(self.url_nueva, datos, HTTP_X_IDEMPOTENCY_KEY=CLAVE)
        self.assertEqual(r1.status_code, 302)
        self.assertEqual(r1['Location'], r2['Location'])
        with self.en_tenant():
            self.assertEqual(Consulta.objects.count(), 1)
            self.assertEqual(Cargo.objects.count(), 1)
        self.assertEqual(SolicitudIdempotente.objects.get().estado, SolicitudIdempotente.OK)

    def test_post_sin_completa_con_cita_abre_borrador(self):
        r = self.cliente.post(self.url_nueva, {'tipo': 'PRIMERA', 'cita': self.cita.pk})
        with self.en_tenant():
            consulta = Consulta.objects.get()
        self.assertRedirects(r, f'/consultas/{consulta.pk}/editar/', fetch_redirect_response=False)

    def test_cita_ya_atendida_lleva_a_su_consulta(self):
        self.cliente.post(self.url_nueva, self.datos_completos())
        with self.en_tenant():
            consulta = Consulta.objects.get()
        r = self.cliente.get(f'{self.url_nueva}?cita={self.cita.pk}')
        self.assertRedirects(r, f'/consultas/{consulta.pk}/', fetch_redirect_response=False)

    # ── idempotencia ──
    def test_recibo_de_navegacion_no_confirma_inicio_independiente(self):
        recibo = SolicitudIdempotente.objects.create(
            usuario_id=self.titular.pk, clave=f'{self.titular.pk}:{CLAVE}',
            ruta='/otro-formulario/', location='/destino-anterior/', estado=SolicitudIdempotente.OK)
        formulario = self.cliente.get(self.url_nueva, {'independiente': '1'})
        datos = {'independiente': '1', 'intento': formulario.context['intento'], '_idem_key': CLAVE}
        respuesta = self.cliente.post(self.url_nueva, datos)
        with self.en_tenant():
            consulta = Consulta.objects.get()
        self.assertRedirects(respuesta, f'/consultas/{consulta.pk}/editar/', fetch_redirect_response=False)
        self.assertEqual(self.cliente.post(self.url_nueva, datos).url, respuesta.url)
        self.assertEqual(self.cliente.post(self.url_nueva, {**datos, 'intento': ''}).status_code, 409)
        with self.en_tenant():
            self.cita.refresh_from_db()
            self.assertIsNone(self.cita.consulta_id)
            self.assertEqual(Consulta.objects.count(), 1)
        recibo.refresh_from_db()
        self.assertEqual((recibo.ruta, recibo.location, recibo.estado),
                         ('/otro-formulario/', '/destino-anterior/', SolicitudIdempotente.OK))

    def test_cobro_firmado_con_clave_nativa_conserva_su_propia_idempotencia(self):
        self.cliente.post(self.url_nueva, self.datos_completos(_idem_key=CLAVE))
        recibo = SolicitudIdempotente.objects.values().get()
        url = f'/agenda/citas/{self.cita.pk}/cobrar/'
        token = self.cliente.get(url).context['form'].initial['confirmacion']
        datos = {'_idem_key': CLAVE, 'confirmacion': token, 'recibido': 'on',
                 'metodo': 'EFECTIVO', 'moneda': 'USD', 'monto': '10'}
        self.assertContains(self.cliente.post(url, datos), 'Pago registrado para esta cita')
        self.assertContains(self.cliente.post(url, datos), 'Este pago ya estaba registrado')
        self.assertContains(self.cliente.post(url, {**datos, 'monto': '15'}), 'un cobro distinto')
        with self.en_tenant():
            self.assertEqual(Pago.objects.get().monto_usd, 10)
            self.assertEqual(PagoAplicado.objects.get().cargo.cita_id, self.cita.pk)
        self.assertEqual(SolicitudIdempotente.objects.values().get(), recibo)

    def test_procedimiento_ya_guardado_y_reintento_de_cola(self):
        url = f'/pacientes/{self.paciente.pk}/procedimientos/nuevo/'
        datos = {'otro_concepto': 'Prueba', 'otro_monto': '10', '_idem_key': CLAVE}
        primera = self.cliente.post(url, datos)
        self.assertEqual(primera.status_code, 302)
        self.assertEqual(self.cliente.post(url, datos, HTTP_X_OFFLINE_FORM='1').status_code, 403)
        self.assertEqual(self.cliente.post(url, datos).url, primera.url)
        with self.en_tenant():
            proc = Procedimiento.objects.get()
            self.assertEqual(Cargo.objects.get().procedimiento_id, proc.pk)
            self.assertFalse(Pago.objects.exists())

    def test_inicio_firmado_nativo_al_cambiar_sesion_o_consultorio(self):
        token = self.cliente.get(self.url_nueva, {'independiente': '1'}).context['intento']
        datos = {'intento': token, 'independiente': '1', '_idem_key': CLAVE}
        otro, segundo = crear_consultorio('Otro', 'otro', usuario='segundo')
        Membresia.objects.create(usuario=self.titular, tenant=otro)
        cambio_usuario = self.entrar(otro, segundo.username)
        self.assertEqual(self.cliente.get(f'/{otro.slug}/').status_code, 302)
        for cliente in (self.cliente, cambio_usuario):
            self.assertEqual(cliente.session['tenant_id'], otro.pk)
            respuesta = cliente.post(self.url_nueva, datos)
            self.assertIn(respuesta.status_code, (403, 404))
            self.assertNotIn('Location', respuesta)
        for tenant in (self.tenant, otro):
            with self.en_tenant(tenant):
                self.assertFalse(Consulta.objects.exists())
                self.assertFalse(Cargo.objects.exists())
        self.assertFalse(SolicitudIdempotente.objects.exists())

    def test_cola_bloqueada_al_cambiar_usuario_o_consultorio(self):
        datos = self.datos_completos(_idem_key=CLAVE)
        otro, usuario_b = crear_consultorio('Otro', 'otro', usuario='titular_b')
        cliente_b = self.entrar(otro, usuario_b.username)
        Membresia.objects.create(usuario=self.titular, tenant=otro)
        misma_persona_otro_tenant = self.entrar(self.tenant, 'titular')
        self.assertEqual(misma_persona_otro_tenant.get(f'/{otro.slug}/').status_code, 302)
        self.assertEqual(misma_persona_otro_tenant.session['tenant_id'], otro.pk)
        for cliente in (cliente_b, misma_persona_otro_tenant, self.cliente):
            r = cliente.post(self.url_nueva, datos, HTTP_X_OFFLINE_FORM='1', HTTP_X_IDEMPOTENCY_KEY=CLAVE)
            self.assertEqual(r.status_code, 403)
            self.assertEqual(r.json(), {'estado': 'revision_necesaria'})
            self.assertIn('no-store', r['Cache-Control'])
        self.assertFalse(SolicitudIdempotente.objects.exists())
        for tenant in (self.tenant, otro):
            with self.en_tenant(tenant):
                self.assertFalse(Consulta.objects.exists())
                self.assertFalse(Cargo.objects.exists())

    def test_sesion_vencida_con_cola_conserva_el_pendiente(self):
        from django.test import Client
        anonimo = Client(HTTP_HOST='localhost')
        r = anonimo.post(self.url_nueva, {'completa': '1', '_idem_key': CLAVE}, HTTP_X_OFFLINE_FORM='1')
        self.assertEqual(r.status_code, 403)
        self.assertNotIn('redirect', r.json())
        self.assertFalse(SolicitudIdempotente.objects.exists())

    # ── ping y precarga ──
    def test_ping(self):
        self.assertEqual(self.cliente.get('/offline/ping/').json(), {'ok': True, 'auth': True})
        from django.test import Client
        self.assertFalse(Client(HTTP_HOST='localhost').get('/offline/ping/').json()['auth'])

    def test_precarga_no_enumera_datos_ni_silencia_auditoria(self):
        r = self.cliente.get('/offline/precache/')
        self.assertEqual(r.json()['urls'], [])
        self.assertIn('no-store', r['Cache-Control'])
        with self.en_tenant():
            antes = Auditoria.objects.filter(accion='VER').count()
        r = self.cliente.get(f'/pacientes/{self.paciente.pk}/', HTTP_X_OFFLINE_PREFETCH='1')
        self.assertIn('no-store', r['Cache-Control'])
        with self.en_tenant():
            self.assertEqual(Auditoria.objects.filter(accion='VER').count(), antes + 1)

    def test_service_worker_solo_recursos_publicos_y_respuestas_no_cacheables(self):
        sw = self.cliente.get('/sw.js').content.decode()
        self.assertNotIn('networkFirstPagina', sw)
        self.assertNotIn('ordo-paginas-v1', sw)
        self.assertIn("cache: 'no-store'", sw)
        self.assertIn("credentials: 'omit'", sw)
        r = self.cliente.get('/agenda/')
        self.assertNotContains(r, 'window.OFFLINE_CFG')
        self.assertNotContains(r, 'js/offline.js')
        self.assertIn('no-store', r['Cache-Control'])
        manifiesto = self.cliente.get('/manifest.webmanifest')
        self.assertIn('public', manifiesto['Cache-Control'])
