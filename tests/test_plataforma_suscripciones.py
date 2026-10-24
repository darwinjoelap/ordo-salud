"""Panel de plataforma: planes, días de gracia, anulación de renovaciones, tablero y accesos de soporte."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from apps.core import fechas
from apps.core.excepciones import ErrorDeNegocio
from apps.core.models import Auditoria
from apps.core.tenancy import usando_tenant
from apps.plataforma import servicios as plataforma
from apps.plataforma.models import AccesoSoporte, Plan, Suscripcion, Tenant

from .base import CLAVE, BaseTest, crear_consultorio


class PanelBase(TestCase):
    def setUp(self):
        get_user_model().objects.create_superuser('root', CLAVE)
        self.c = Client(HTTP_HOST='localhost')
        self.c.post('/cuenta/entrar/', {'username': 'root', 'password': CLAVE})
        self.plan = Plan.objects.create(nombre='Básico', precio_usd=Decimal('20'), dias_gracia=3)
        self.t, self.titular = crear_consultorio('Uno', 'uno')
        self.t.plan = self.plan
        self.t.save()
        self.hoy = timezone.localdate()


class GraciaTest(PanelBase):
    def test_vencido_entra_durante_la_gracia_y_luego_se_bloquea(self):
        c = BaseTest.entrar(self.t, 'titular')
        self.t.activo_hasta = self.hoy - timedelta(days=1)
        self.t.save()
        self.assertTrue(self.t.en_gracia)
        self.assertEqual(self.t.dias_de_gracia_restantes, 3)
        r = c.get('/pacientes/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'venció el')
        self.t.activo_hasta = self.hoy - timedelta(days=4)       # vencimiento + 3 días de gracia ya pasaron
        self.t.save()
        self.assertEqual(self.t.estado_servicio, 'VENCIDO')
        self.assertEqual(c.get('/pacientes/').status_code, 302)

    def test_gracia_propia_del_consultorio_reemplaza_la_del_plan(self):
        self.t.dias_gracia = 0
        self.t.activo_hasta = self.hoy - timedelta(days=1)
        self.t.save()
        self.assertFalse(self.t.esta_activo)

    def test_renovar_en_gracia_sigue_desde_el_vencimiento(self):
        self.t.activo_hasta = self.hoy - timedelta(days=2)
        self.t.save()
        plataforma.renovar(self.t, meses=1, monto_usd=20)
        self.t.refresh_from_db()
        desde = self.hoy - timedelta(days=1)
        self.assertEqual(self.t.activo_hasta, fechas.sumar_meses(desde, 1) - timedelta(days=1))


class AnularRenovacionTest(PanelBase):
    def test_anular_la_ultima_restaura_vencimiento_y_plan(self):
        antes = self.hoy + timedelta(days=10)
        self.t.activo_hasta = antes
        self.t.save()
        otro = Plan.objects.create(nombre='Clínica', precio_usd=Decimal('60'))
        r = self.c.post(f'/plataforma/{self.t.pk}/renovar/', {'meses': 3, 'monto_usd': '180', 'plan': otro.pk})
        self.assertEqual(r.status_code, 302)
        s = Suscripcion.objects.get()
        self.assertEqual(s.creado_por.username, 'root')
        r = self.c.post(f'/plataforma/renovaciones/{s.pk}/anular/', {'motivo': 'Monto equivocado'})
        self.t.refresh_from_db()
        s.refresh_from_db()
        self.assertTrue(s.anulada)
        self.assertEqual(self.t.activo_hasta, antes)
        self.assertEqual(self.t.plan, self.plan)

    def test_solo_la_ultima_y_con_motivo(self):
        plataforma.renovar(self.t, meses=1)
        plataforma.renovar(self.t, meses=1)
        primera, segunda = Suscripcion.objects.order_by('creado_en', 'pk')
        with self.assertRaises(ErrorDeNegocio):
            plataforma.anular_renovacion(primera, motivo='x')
        with self.assertRaises(ErrorDeNegocio):
            plataforma.anular_renovacion(segunda, motivo='  ')
        plataforma.anular_renovacion(segunda, motivo='Duplicada')
        plataforma.anular_renovacion(primera, motivo='Prueba')    # ahora la primera es la última vigente
        self.t.refresh_from_db()
        self.assertIsNone(self.t.activo_hasta)


class TableroYPlanesTest(PanelBase):
    def test_tablero(self):
        plataforma.renovar(self.t, meses=1, monto_usd=Decimal('20'))
        t2, _ = crear_consultorio('Dos', 'dos', usuario='dos')
        t2.plan = self.plan
        t2.activo_hasta = self.hoy - timedelta(days=1)
        t2.save()
        r = self.c.get('/plataforma/suscripciones/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['cobrado_mes'], Decimal('20'))
        self.assertEqual(r.context['mrr'], Decimal('40'))
        self.assertEqual([t.pk for t in r.context['por_estado']['GRACIA']], [t2.pk])
        self.assertEqual([t.pk for t in r.context['vencen']], [self.t.pk])

    def test_crear_y_editar_plan(self):
        r = self.c.post('/plataforma/planes/nuevo/', {'nombre': 'Pro', 'precio_usd': '35', 'dias_gracia': 5,
                                                      'minutos_dictado_mes': 0, 'precio_minuto_extra_usd': '0.04',
                                                      'tope_minutos_extra': 600,
                                                      'activo': 'on'})
        self.assertRedirects(r, '/plataforma/planes/', fetch_redirect_response=False)
        p = Plan.objects.get(nombre='Pro')
        self.c.post(f'/plataforma/planes/{p.pk}/', {'nombre': 'Pro', 'precio_usd': '40', 'dias_gracia': 5,
                                                    'minutos_dictado_mes': 0, 'precio_minuto_extra_usd': '0.04',
                                                    'tope_minutos_extra': 600})
        p.refresh_from_db()
        self.assertEqual(p.precio_usd, Decimal('40'))
        self.assertFalse(p.activo)
        self.assertContains(self.c.get('/plataforma/planes/'), 'Retirado')

    def test_panel_solo_superusuario(self):
        c = BaseTest.entrar(self.t, 'titular')
        for url in ('/plataforma/suscripciones/', '/plataforma/planes/', f'/plataforma/planes/{self.plan.pk}/'):
            self.assertEqual(c.get(url).status_code, 403, url)


class SoporteTest(PanelBase):
    def test_entrada_queda_registrada_y_se_cierra_al_salir(self):
        self.c.post(f'/plataforma/{self.t.pk}/entrar/', {'motivo': 'No le sale el récipe'})
        acceso = AccesoSoporte.objects.get()
        self.assertEqual(acceso.motivo, 'No le sale el récipe')
        self.assertIsNone(acceso.fin)
        with usando_tenant(self.t):
            self.assertTrue(Auditoria.objects.filter(accion='SOPORTE', detalle__contains='récipe').exists())
        self.c.post('/plataforma/salir/')
        acceso.refresh_from_db()
        self.assertIsNotNone(acceso.fin)
        self.assertContains(self.c.get(f'/plataforma/{self.t.pk}/'), 'No le sale el récipe')

    def test_soporte_entra_a_consultorio_suspendido_o_vencido(self):
        self.t.estado = Tenant.Estado.SUSPENDIDO
        self.t.save()
        self.c.post(f'/plataforma/{self.t.pk}/entrar/')
        self.assertEqual(self.c.get('/pacientes/').status_code, 200)
        t2, _ = crear_consultorio('Dos', 'dos', usuario='dos')
        t2.activo_hasta = self.hoy - timedelta(days=30)
        t2.save()
        self.c.post(f'/plataforma/{t2.pk}/entrar/')       # cambiar de consultorio cierra el acceso anterior
        self.assertEqual(self.c.get('/pacientes/').status_code, 200)
        self.assertEqual(AccesoSoporte.objects.filter(fin__isnull=True).count(), 1)
