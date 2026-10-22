"""Fases 01–02: esqueleto, multi-tenant, login por enlace, equipo, permisos y plataforma."""
from datetime import date, time, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.test import Client, TestCase
from django.utils import timezone

from apps.core import fechas
from apps.core.permisos import Rol, permisos_de
from apps.core.tenancy import usando_tenant
from apps.equipo import servicios as equipo
from apps.equipo.models import Membresia
from apps.pacientes.models import Paciente
from apps.plataforma import servicios as plataforma
from apps.plataforma.models import Especialidad, Tenant

from .base import CLAVE, BaseTest, crear_consultorio


class EsqueletoTest(TestCase):
    def test_salud_responde_ok(self):
        r = Client(HTTP_HOST='localhost').get('/salud/')
        self.assertEqual(r.json(), {'estado': 'ok'})

    def test_manifest_y_service_worker(self):
        c = Client(HTTP_HOST='localhost')
        self.assertEqual(c.get('/manifest.webmanifest').json()['short_name'], 'Ordo Salud')
        self.assertIn('ordo-', c.get('/sw.js').content.decode())

    def test_hora12(self):
        self.assertEqual(fechas.hora12(time(13, 5)), '1:05 p. m.')
        self.assertEqual(fechas.hora12(time(0, 30)), '12:30 a. m.')
        self.assertEqual(fechas.hora12(time(12, 0)), '12:00 p. m.')

    def test_edad_texto(self):
        ref = date(2026, 10, 20)
        self.assertEqual(fechas.edad_texto(date(1990, 1, 1), ref), '36 años')
        self.assertEqual(fechas.edad_texto(date(2024, 8, 10), ref), '2 años 2 meses')
        self.assertEqual(fechas.edad_texto(date(2026, 9, 1), ref), '1 mes 19 días')
        self.assertEqual(fechas.edad_texto(date(2026, 10, 8), ref), '12 días')

    def test_sumar_meses_fin_de_mes(self):
        self.assertEqual(fechas.sumar_meses(date(2026, 1, 31), 1), date(2026, 2, 28))
        self.assertEqual(fechas.sumar_meses(date(2026, 11, 15), 3), date(2027, 2, 15))

    def test_catalogo_sincronizado_tras_migrar(self):
        self.assertTrue(Especialidad.objects.filter(codigo='pediatria').exists())
        self.assertTrue(Especialidad.objects.filter(codigo='medicina_general', modulo__endswith='general').exists())


class AislamientoTest(TestCase):
    """Obligatorio (ADR-003): un tenant nunca ve datos de otro."""

    def setUp(self):
        self.t1, _ = crear_consultorio('Uno', 'uno', usuario='ana')
        self.t2, _ = crear_consultorio('Dos', 'dos', usuario='beto')
        with usando_tenant(self.t1):
            Paciente.objects.create(nombres='Luis', apellidos='Uno', sexo='M', numero_documento='111')
        with usando_tenant(self.t2):
            Paciente.objects.create(nombres='Rosa', apellidos='Dos', sexo='F', numero_documento='222')

    def test_manager_filtra_por_tenant(self):
        with usando_tenant(self.t1):
            self.assertEqual(list(Paciente.objects.values_list('nombres', flat=True)), ['Luis'])
        with usando_tenant(self.t2):
            self.assertEqual(list(Paciente.objects.values_list('nombres', flat=True)), ['Rosa'])

    def test_sin_tenant_no_devuelve_nada(self):
        self.assertEqual(Paciente.objects.count(), 0)
        self.assertEqual(Paciente.todos.count(), 2)

    def test_guardar_sin_tenant_falla(self):
        with self.assertRaises(ImproperlyConfigured):
            Paciente.objects.create(nombres='X', apellidos='Y', sexo='F')

    def test_ficha_de_otro_tenant_da_404(self):
        otro = Paciente.todos.get(nombres='Rosa')
        c = BaseTest.entrar(self.t1, 'ana')
        self.assertEqual(c.get(f'/pacientes/{otro.pk}/').status_code, 404)
        self.assertNotContains(c.get('/pacientes/?q=Rosa'), 'Dos, Rosa')

    def test_mismo_documento_en_dos_tenants_si_se_permite(self):
        with usando_tenant(self.t2):
            Paciente.objects.create(nombres='Otro', apellidos='Luis', sexo='M', numero_documento='111')


class LoginPorEnlaceTest(TestCase):
    def setUp(self):
        self.t1, _ = crear_consultorio('Uno', 'uno', usuario='maria')
        self.t2, _ = crear_consultorio('Dos', 'dos', usuario='maria')

    def test_mismo_usuario_en_dos_consultorios_entra_al_suyo(self):
        c = BaseTest.entrar(self.t2, 'maria')
        self.assertEqual(c.get('/').context['tenant'], self.t2)

    def test_usuario_de_otro_consultorio_no_entra(self):
        U = get_user_model()
        U.objects.create_user('solo1', CLAVE, tenant_cuenta=self.t1)
        r = Client(HTTP_HOST='localhost').post('/dos/', {'username': 'solo1', 'password': CLAVE})
        self.assertEqual(r.status_code, 200)    # vuelve el formulario con error

    def test_consultorio_suspendido(self):
        self.t1.estado = Tenant.Estado.SUSPENDIDO
        self.t1.save()
        self.assertEqual(Client(HTTP_HOST='localhost').get('/uno/').status_code, 403)

    def test_consultorio_vencido_no_deja_trabajar(self):
        c = BaseTest.entrar(self.t1, 'maria')
        self.t1.activo_hasta = timezone.localdate() - timedelta(days=1)
        self.t1.save()
        r = c.get('/pacientes/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('sin-consultorio', r['Location'])


class EquipoTest(BaseTest):
    def test_titular_es_profesional_y_tiene_plantillas(self):
        m = Membresia.objects.get(usuario=self.titular)
        self.assertEqual(m.rol, Rol.TITULAR)
        self.assertTrue(m.es_profesional)
        self.assertIn('historia.ver', permisos_de(m))
        with self.en_tenant():
            from apps.clinica.models import PlantillaHistoria
            self.assertTrue(PlantillaHistoria.objects.filter(es_predeterminada=True).exists())

    def test_agregar_medico_exige_especialidad(self):
        actor = Membresia.objects.get(usuario=self.titular)
        with self.assertRaises(equipo.ErrorEquipo):
            equipo.agregar(self.tenant, actor, 'drx', 'X', 'Y', Rol.MEDICO)

    def test_especialidad_no_habilitada_se_rechaza(self):
        actor = Membresia.objects.get(usuario=self.titular)
        with self.assertRaises(equipo.ErrorEquipo):
            equipo.agregar(self.tenant, actor, 'drx', 'X', 'Y', Rol.MEDICO,
                           especialidad=Especialidad.objects.get(codigo='cardiologia'))

    def test_agregar_medico_desde_la_vista(self):
        esp = Especialidad.objects.get(codigo='medicina_general')
        r = self.cliente.post('/equipo/agregar/', {'username': 'drlopez', 'nombre': 'Juan', 'apellido': 'López',
                                                   'rol': 'MEDICO', 'especialidad': esp.pk, 'titulo': 'Dr.'})
        self.assertContains(r, 'Ordo-')
        m = Membresia.objects.get(usuario__username='drlopez')
        self.assertTrue(m.es_profesional)
        self.assertEqual(m.perfil.nombre_con_titulo, 'Dr. Juan López')

    def test_asistente_no_ve_historia_ni_equipo(self):
        actor = Membresia.objects.get(usuario=self.titular)
        m, clave = equipo.agregar(self.tenant, actor, 'asis', 'Eva', 'Gil', Rol.ASISTENTE)
        m.usuario.debe_cambiar_clave = False
        m.usuario.save()
        c = self.entrar(self.tenant, 'asis', clave)
        self.assertEqual(c.get('/equipo/').status_code, 403)
        self.assertEqual(c.get('/plantillas/').status_code, 403)
        self.assertEqual(c.get('/pacientes/').status_code, 200)
        self.assertNotIn('historia.ver', permisos_de(m))

    def test_no_queda_sin_titular(self):
        actor = Membresia.objects.get(usuario=self.titular)
        m, _ = equipo.agregar(self.tenant, actor, 'admin2', 'A', 'B', Rol.ADMIN)
        with self.assertRaises(equipo.ErrorEquipo):
            equipo.actualizar(m, actor, Rol.ADMIN, True)      # el admin no puede tocar al titular

    def test_limite_de_profesionales(self):
        self.tenant.limite_profesionales = 1
        self.tenant.save()
        actor = Membresia.objects.get(usuario=self.titular)
        with self.assertRaises(equipo.ErrorEquipo):
            equipo.agregar(self.tenant, actor, 'drz', 'Z', 'Z', Rol.MEDICO,
                           especialidad=Especialidad.objects.get(codigo='medicina_general'))

    def test_clave_temporal_obliga_a_cambiarla(self):
        actor = Membresia.objects.get(usuario=self.titular)
        m, clave = equipo.agregar(self.tenant, actor, 'nueva', 'N', 'N', Rol.ASISTENTE)
        c = self.entrar(self.tenant, 'nueva', clave)
        r = c.get('/pacientes/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/cuenta/perfil/', r['Location'])


class PlataformaTest(TestCase):
    def setUp(self):
        U = get_user_model()
        U.objects.create_superuser('root', CLAVE)
        self.c = Client(HTTP_HOST='localhost')
        self.c.post('/cuenta/entrar/', {'username': 'root', 'password': CLAVE})

    def test_crear_consultorio_desde_el_panel(self):
        esp = Especialidad.objects.get(codigo='ginecologia')
        r = self.c.post('/plataforma/nuevo/', {
            'nombre': 'Ginecología Sol', 'slug': 'gine-sol', 'usuario_titular': 'sol', 'nombre_titular': 'Sol',
            'apellido_titular': 'Ruiz', 'titular_es_profesional': 'on', 'especialidad_titular': esp.pk,
            'titulo_titular': 'Dra.'})
        self.assertContains(r, 'Consultorio creado')
        t = Tenant.objects.get(slug='gine-sol')
        self.assertIn(esp, t.especialidades.all())

    def test_enlace_reservado(self):
        r = self.c.post('/plataforma/nuevo/', {'nombre': 'X', 'slug': 'pacientes', 'usuario_titular': 'x',
                                                'nombre_titular': 'x', 'apellido_titular': 'x'})
        self.assertContains(r, 'reservado')

    def test_renovar_extiende_desde_el_vencimiento(self):
        t, _ = crear_consultorio('R', 'renovar', usuario='r')
        t.activo_hasta = timezone.localdate() + timedelta(days=5)
        t.save()
        plataforma.renovar(t, meses=1, monto_usd=30)
        t.refresh_from_db()
        self.assertEqual(t.activo_hasta, fechas.sumar_meses(timezone.localdate() + timedelta(days=6), 1)
                         - timedelta(days=1))
        self.assertEqual(t.suscripciones.count(), 1)

    def test_soporte_entra_sin_ver_historias(self):
        t, _ = crear_consultorio('S', 'soporte-x', usuario='s')
        self.c.post(f'/plataforma/{t.pk}/entrar/')
        self.assertEqual(self.c.get('/pacientes/').status_code, 200)
        self.assertNotIn('historia.ver', self.c.get('/pacientes/').context['permisos'])
