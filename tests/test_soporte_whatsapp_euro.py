"""ADR-057 soporte con control total · ADR-058 plantilla de WhatsApp · ADR-059 tasa euro por consultorio."""
from datetime import time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import Client, SimpleTestCase, TestCase
from django.utils import timezone

from apps.cobros import servicios as cobros
from apps.cobros.models import Servicio
from apps.configuracion import whatsapp
from apps.equipo.models import Membresia
from apps.pacientes.models import Paciente
from apps.tasas import servicios as tasas
from apps.tasas.models import TasaCambio

from .base import CLAVE, BaseTest, crear_consultorio

D = Decimal


class SoporteTotalTest(TestCase):
    def setUp(self):
        get_user_model().objects.create_superuser('root', CLAVE)
        self.tenant, titular = crear_consultorio('Soporte', 'soporte-y')
        from apps.clinica.consultas import abrir_consulta
        from apps.core.tenancy import usando_tenant
        with usando_tenant(self.tenant):
            self.paciente = Paciente.objects.create(nombres='Rosa', apellidos='Mar', sexo='F')
            perfil = Membresia.objects.get(usuario=titular).perfil
            self.consulta = abrir_consulta(paciente=self.paciente, profesional=perfil)
        self.c = Client(HTTP_HOST='localhost')
        self.c.post('/cuenta/entrar/', {'username': 'root', 'password': CLAVE})
        self.c.post(f'/plataforma/{self.tenant.pk}/entrar/', {'motivo': 'prueba'})

    def test_ve_y_edita_la_historia(self):
        self.assertEqual(self.c.get(f'/consultas/{self.consulta.pk}/').status_code, 200)
        self.assertEqual(self.c.get(f'/consultas/{self.consulta.pk}/editar/').status_code, 200)

    def test_no_crea_consultas(self):
        permisos = self.c.get('/pacientes/').context['permisos']
        self.assertNotIn('consultas.crear', permisos)


class PlantillaWhatsappTest(SimpleTestCase):
    VALORES = {'saludo': 'Ana', 'paciente': 'Ana Paz', 'de_paciente': '', 'profesional': 'Dra. Gil',
               'consultorio': 'Sol', 'fecha': '10/11/2026', 'hora': '3:00 p. m.', 'lugar': 'Torre A'}

    def test_vacia_usa_la_estandar(self):
        texto = whatsapp.armar('', self.VALORES)
        self.assertTrue(texto.startswith('Hola Ana, le recordamos la cita con Dra. Gil (Sol) el 10/11/2026 a las 3:00'))
        self.assertIn('en Torre A.', texto)

    def test_sin_hora_ni_lugar_no_deja_huecos(self):
        texto = whatsapp.armar('', {**self.VALORES, 'hora': '', 'lugar': ''})
        self.assertIn('el 10/11/2026. Por favor', texto)
        self.assertNotIn('a las', texto)

    def test_propia(self):
        texto = whatsapp.armar('Buen día {saludo}: su cita es el {fecha}. ¡Le esperamos!', self.VALORES)
        self.assertEqual(texto, 'Buen día Ana: su cita es el 10/11/2026. ¡Le esperamos!')

    def test_marcador_desconocido(self):
        with self.assertRaises(ValidationError):
            whatsapp.validar('Hola {nombre}')
        whatsapp.validar('Hola {saludo}')


class PlantillaWhatsappEnCitaTest(BaseTest):
    def test_url_usa_la_plantilla_del_consultorio(self):
        from apps.agenda import servicios as agenda
        from apps.agenda.models import Cita
        config = self.tenant.configuracion
        config.plantilla_whatsapp = 'Hola {saludo}, le esperamos el {fecha} a las {hora}.'
        config.save()
        with self.en_tenant():
            p = Paciente.objects.create(nombres='Luis', apellidos='Mora', sexo='M', telefono='0414-1112233')
            perfil = Membresia.objects.get(usuario=self.titular).perfil
            cita = Cita.objects.create(paciente=p, profesional=perfil, especialidad=perfil.especialidad,
                                       fecha=timezone.localdate(), hora_inicio=time(9, 0), hora_fin=time(9, 20))
            url = agenda.url_whatsapp(Cita.objects.get(pk=cita.pk))
        self.assertIn('le%20esperamos', url)
        self.assertNotIn('recordamos', url)


class TasaEuroTest(BaseTest):
    def setUp(self):
        super().setUp()
        cache.clear()
        TasaCambio.objects.create(fecha=timezone.localdate(), bs_por_usd=D('40'), bs_por_eur=D('45'), fuente='BCV')

    def tearDown(self):
        cache.clear()

    def test_lee_euro_del_bcv(self):
        html = '<div id="euro"><strong> 45,12340000 </strong></div><div id="dolar"><strong>40,0</strong></div>'
        self.assertEqual(tasas.leer_tasa_html(html, 'euro'), D('45.1234'))

    def test_dolar_por_defecto(self):
        t = tasas.tasa_vigente(self.tenant)
        self.assertEqual((t.valor, t.moneda), (D('40'), 'USD'))

    def test_consultorio_en_euro_cobra_con_euro(self):
        config = self.tenant.configuracion
        config.tasa_referencia = 'EUR'
        config.save()
        self.tenant.refresh_from_db()
        t = tasas.tasa_vigente(self.tenant)
        self.assertEqual((t.valor, t.moneda, t.sin_euro), (D('45'), 'EUR', False))
        with self.en_tenant():
            p = Paciente.objects.create(nombres='Eva', apellidos='Rey', sexo='F')
            s = Servicio.objects.create(nombre='Consulta', precio_usd=D('30'))
            cargo = cobros.crear_cargo(paciente=p, servicio=s, descripcion='', precio_usd=D('30'))
            self.assertEqual((cargo.tasa, cargo.tasa_ref), (D('45'), 'EUR'))
            pago = cobros.registrar_pago(paciente=p, monto=D('1350'), moneda='BS', metodo='PAGO_MOVIL')
            self.assertEqual((pago.monto_usd, pago.tasa_ref), (D('30.00'), 'EUR'))

    def test_euro_sin_tasa_avisa_y_usa_dolar(self):
        TasaCambio.objects.update(bs_por_eur=None)
        cache.clear()
        config = self.tenant.configuracion
        config.tasa_referencia = 'EUR'
        config.save()
        self.tenant.refresh_from_db()
        t = tasas.tasa_vigente(self.tenant)
        self.assertEqual((t.valor, t.moneda, t.sin_euro), (D('40'), 'USD', True))

    def test_paginas_con_euro(self):
        config = self.tenant.configuracion
        config.tasa_referencia = 'EUR'
        config.save()
        r = self.cliente.get('/tasa/')
        self.assertContains(r, 'por EUR')
        r = self.cliente.get('/configuracion/?tab=contacto')
        self.assertContains(r, 'Así se verá')
        self.assertContains(r, 'Tasa para calcular bolívares')
