"""Fase 12: modo sin conexión de consulta (idempotencia, ping, precarga y consulta nueva completa)."""
from datetime import time, timedelta

from django.utils import timezone

from apps.agenda.models import Cita, TipoCita
from apps.clinica.models import Consulta, PlantillaHistoria
from apps.cobros.models import Cargo, Servicio
from apps.core.models import Auditoria
from apps.equipo.models import Membresia
from apps.offline.models import SolicitudIdempotente
from apps.pacientes.models import Paciente

from .base import BaseTest

CLAVE = '0f6a1c2e-1111-4a2b-9c3d-000000000001'


class OfflineTest(BaseTest):
    def setUp(self):
        super().setUp()
        with self.en_tenant():
            self.perfil = Membresia.objects.get(usuario=self.titular).perfil
            self.paciente = Paciente.objects.create(nombres='Elena', apellidos='Paz', sexo='F')
            control = PlantillaHistoria.objects.get(nombre='Control')
            servicio = Servicio.objects.create(nombre='Control', precio_usd=30)
            self.tipo = TipoCita.objects.create(nombre='Control', duracion_min=20, tipo_consulta='CONTROL',
                                                plantilla=control, servicio=servicio)
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
        r1 = self.cliente.post(self.url_nueva, datos, HTTP_X_OFFLINE_FORM='1')
        r2 = self.cliente.post(self.url_nueva, datos, HTTP_X_OFFLINE_FORM='1')
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r1.json()['redirect'], r2.json()['redirect'])
        with self.en_tenant():
            self.assertEqual(Consulta.objects.count(), 1)
            self.assertEqual(Cargo.objects.count(), 1)
        self.assertEqual(SolicitudIdempotente.objects.get().estado, SolicitudIdempotente.OK)

    def test_post_viejo_sin_completa_sigue_abriendo_borrador(self):
        r = self.cliente.post(self.url_nueva, {'tipo': 'PRIMERA'})
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
    def test_sesion_vencida_responde_401_y_libera_la_clave(self):
        from django.test import Client
        anonimo = Client(HTTP_HOST='localhost')
        r = anonimo.post(self.url_nueva, {'completa': '1', '_idem_key': CLAVE}, HTTP_X_OFFLINE_FORM='1')
        self.assertEqual(r.status_code, 401)
        self.assertTrue(r.json()['login'])
        self.assertFalse(SolicitudIdempotente.objects.exists())

    # ── ping y precarga ──
    def test_ping(self):
        self.assertEqual(self.cliente.get('/offline/ping/').json(), {'ok': True, 'auth': True})
        from django.test import Client
        self.assertFalse(Client(HTTP_HOST='localhost').get('/offline/ping/').json()['auth'])

    def test_precarga_lista_paginas_de_la_agenda(self):
        urls = self.cliente.get('/offline/precache/').json()['urls']
        self.assertIn('/agenda/', urls)
        self.assertIn(f'/pacientes/{self.paciente.pk}/', urls)
        self.assertIn(f'{self.url_nueva}?cita={self.cita.pk}', urls)
        for u in urls:
            r = self.cliente.get(u, HTTP_X_OFFLINE_PREFETCH='1')
            self.assertEqual(r.status_code, 200, u)

    def test_precarga_no_audita_cada_lectura(self):
        with self.en_tenant():
            antes = Auditoria.objects.filter(accion='VER').count()
        self.cliente.get(f'/pacientes/{self.paciente.pk}/', HTTP_X_OFFLINE_PREFETCH='1')
        with self.en_tenant():
            self.assertEqual(Auditoria.objects.filter(accion='VER').count(), antes)
        self.cliente.get(f'/pacientes/{self.paciente.pk}/')
        with self.en_tenant():
            self.assertEqual(Auditoria.objects.filter(accion='VER').count(), antes + 1)

    def test_service_worker_y_script(self):
        sw = self.cliente.get('/sw.js').content.decode()
        self.assertIn('ordo-paginas-v1', sw)
        self.assertIn("const LOGIN = '/cuenta/entrar/'", sw)
        r = self.cliente.get('/agenda/')
        self.assertContains(r, 'window.OFFLINE_CFG')
        self.assertContains(r, 'js/offline.js')
