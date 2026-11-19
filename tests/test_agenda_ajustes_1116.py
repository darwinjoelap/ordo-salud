"""2026-11-16: WhatsApp Business primero (Android), recordatorio de pacientes sin consulta, eliminar citas no atendidas."""
from datetime import date, time
from urllib.parse import parse_qs, unquote, urlparse

from django.test import Client
from django.utils import timezone

from apps.agenda import servicios as srv
from apps.agenda.models import Cita
from apps.configuracion import whatsapp
from apps.core.models import Auditoria
from apps.core.permisos import Rol
from apps.equipo import servicios as equipo
from apps.equipo.models import Membresia
from apps.pacientes.models import Paciente, Representante

from .base import BaseTest, crear_consultorio


class WhatsappBusinessTest(BaseTest):
    def test_intent_con_regreso_a_wa_me(self):
        url = 'https://wa.me/584141234567?text=Hola%20Ana%2C%20%C2%BFc%C3%B3mo%20est%C3%A1%3F'
        i = whatsapp.intent_business(url)
        self.assertTrue(i.startswith('intent://send/?phone=584141234567&text=Hola%20Ana'))
        self.assertIn('package=com.whatsapp.w4b', i)
        self.assertEqual(unquote(i.split('S.browser_fallback_url=')[1].removesuffix(';end')), url)
        self.assertEqual(whatsapp.intent_business('https://ejemplo.com'), 'https://ejemplo.com')

    def crear_cita(self, telefono='04141234567', menor=False):
        perfil = Membresia.objects.get(usuario=self.titular).perfil
        with self.en_tenant():
            p = Paciente.objects.create(nombres='Ana', apellidos='Paz', sexo='F', telefono=telefono,
                                        fecha_nacimiento=date(2020, 1, 1) if menor else None)
            return Cita.objects.create(paciente=p, profesional=perfil, especialidad=perfil.especialidad,
                                       fecha=timezone.localdate(), hora_inicio=time(9), hora_fin=time(9, 30))

    def test_recordatorio_valida_registra_una_vez_y_no_confirma_cita(self):
        cita = self.crear_cita()
        detalle = self.cliente.get(f'/agenda/citas/{cita.pk}/')
        self.assertContains(detalle, 'data-whatsapp-agenda')
        self.assertNotContains(detalle, 'https://wa.me/')
        self.assertNotContains(detalle, 'package=com.whatsapp.w4b')
        self.assertContains(detalle, 'Copiar mensaje')
        self.assertContains(detalle, 'name="csrfmiddlewaretoken"')
        agenda = self.cliente.get('/agenda/')
        self.assertContains(agenda, 'data-whatsapp-agenda')
        self.assertNotContains(agenda, '04141234567')
        self.assertIn('no-store', agenda['Cache-Control'])
        ruta = f'/agenda/citas/{cita.pk}/recordatorio/'
        self.assertEqual(self.cliente.get(ruta).status_code, 405)
        self.cliente.handler.enforce_csrf_checks = True
        datos = {'accion': 'business', 'clave_intento': '00000000-0000-4000-8000-000000000001'}
        self.assertEqual(self.cliente.post(ruta, datos).status_code, 403)
        cabeceras = {'HTTP_X_CSRFTOKEN': detalle.cookies['csrftoken'].value}
        validar = self.cliente.post(ruta, {'accion': 'validar'}, **cabeceras)
        self.assertEqual(validar.status_code, 204)
        self.assertIn('no-store', validar['Cache-Control'])
        copia = self.cliente.post(ruta, {'accion': 'copiar'}, **cabeceras)
        self.assertIn('Hola Ana', copia.json()['mensaje'])
        with self.en_tenant():
            cita.refresh_from_db()
            self.assertIsNone(cita.recordatorio_en)
        intento = self.cliente.post(ruta, datos, **cabeceras)
        self.assertIn('package=com.whatsapp.w4b', intento.json()['destino'])
        r = self.cliente.post(ruta, {**datos, 'accion': 'web'}, **cabeceras)
        self.assertTrue(r.json()['destino'].startswith('https://wa.me/584141234567'))
        with self.en_tenant():
            cita.refresh_from_db()
            self.assertIsNotNone(cita.recordatorio_en)
            self.assertEqual(cita.estado, Cita.Estado.PROGRAMADA)
            self.assertEqual(Auditoria.objects.filter(detalle__startswith='Intento WhatsApp').count(), 1)
            Paciente.objects.filter(pk=cita.paciente_id).update(whatsapp_seguimiento='NO')
        rechazado = self.cliente.post(ruta, datos, **cabeceras)
        self.assertEqual(rechazado.status_code, 409)
        self.assertNotIn('destino', rechazado.json())

    def test_recordatorio_requiere_sesion_y_alcance_del_tenant(self):
        cita = self.crear_cita()
        ruta = f'/agenda/citas/{cita.pk}/recordatorio/'
        self.assertEqual(Client(HTTP_HOST='localhost').post(ruta).status_code, 302)
        otro, _ = crear_consultorio(slug='otro')
        cliente = self.entrar(otro, 'titular')
        self.assertEqual(cliente.post(ruta, {'accion': 'copiar'}).status_code, 404)
        actor = Membresia.objects.get(usuario=self.titular)
        medico, clave = equipo.agregar(self.tenant, actor, 'medico', 'Luis', 'Paz', Rol.MEDICO,
                                        especialidad=actor.perfil.especialidad)
        medico.usuario.debe_cambiar_clave = False
        medico.usuario.save()
        self.assertEqual(self.entrar(self.tenant, 'medico', clave).post(ruta, {'accion': 'copiar'}).status_code, 404)
        with self.en_tenant():
            cita.refresh_from_db()
            self.assertIsNone(cita.recordatorio_en)

    def test_representante_valido_y_fallback_con_saludo_del_paciente(self):
        cita = self.crear_cita(menor=True)
        with self.en_tenant():
            representante = Representante.objects.create(paciente=cita.paciente, nombre='María Núñez',
                                                          telefono='+58 (424) 555-6677', es_principal=True)
            config = self.tenant.configuracion
            config.plantilla_whatsapp = 'Hola {saludo} & ¿todo bien? + # /'
            config.save()
            cita = Cita.objects.get(pk=cita.pk)
            url = srv.url_whatsapp(cita)
            self.assertEqual(urlparse(url).path, '/584245556677')
            self.assertEqual(parse_qs(urlparse(url).query)['text'], ['Hola María & ¿todo bien? + # /'])
            intent = whatsapp.intent_business(url)
            self.assertIn('text=Hola%20Mar%C3%ADa%20%26%20%C2%BFtodo%20bien%3F%20%2B%20%23%20%2F', intent)
            self.assertEqual(unquote(intent.split('S.browser_fallback_url=')[1].removesuffix(';end')), url)
            representante.telefono = ''
            representante.save()
            cita = Cita.objects.get(pk=cita.pk)
            url = srv.url_whatsapp(cita)
            self.assertEqual(urlparse(url).path, '/584141234567')
            self.assertTrue(parse_qs(urlparse(url).query)['text'][0].startswith('Hola Ana'))

    def test_telefonos_invalidos(self):
        for telefono in ('', '0414', '++584141234567', '58+4141234567', '+1234567890123456', '0414ABC1234567'):
            with self.subTest(telefono=telefono):
                self.assertEqual(whatsapp.numero_whatsapp(telefono), '')
        cita = self.crear_cita(telefono='')
        r = self.cliente.post(f'/agenda/citas/{cita.pk}/recordatorio/', {'accion': 'copiar'})
        self.assertEqual(r.status_code, 409)
        self.assertNotIn('mensaje', r.json())


class EliminarCitaTest(BaseTest):
    def setUp(self):
        super().setUp()
        self.perfil = Membresia.objects.get(usuario=self.titular).perfil
        with self.en_tenant():
            self.p = Paciente.objects.create(nombres='Ana', apellidos='Paz', sexo='F')
            self.c = Cita.objects.create(paciente=self.p, profesional=self.perfil, especialidad=self.perfil.especialidad,
                                         fecha=timezone.localdate(), hora_inicio=time(9), hora_fin=time(9, 30))

    def test_eliminar_no_atendida(self):
        self.assertContains(self.cliente.get(f'/agenda/citas/{self.c.pk}/'), 'Eliminar cita')
        r = self.cliente.post(f'/agenda/citas/{self.c.pk}/eliminar/')
        self.assertEqual(r.status_code, 302)
        with self.en_tenant():
            self.assertFalse(Cita.objects.filter(pk=self.c.pk).exists())

    def test_atendida_no_se_elimina(self):
        with self.en_tenant():
            srv.atender(self.c, self.perfil)
        self.assertNotContains(self.cliente.get(f'/agenda/citas/{self.c.pk}/'), 'Eliminar cita')
        self.cliente.post(f'/agenda/citas/{self.c.pk}/eliminar/')
        with self.en_tenant():
            self.assertTrue(Cita.objects.filter(pk=self.c.pk).exists())
