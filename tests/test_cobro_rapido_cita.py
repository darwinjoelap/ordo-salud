from concurrent.futures import ThreadPoolExecutor
from datetime import time, timedelta
from decimal import Decimal
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch

from django.db import connection, connections
from django.test import Client, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from apps.agenda import servicios as agenda
from apps.agenda.models import Cita
from apps.clinica.consultas import abrir_consulta
from apps.clinica.models import Procedimiento
from apps.cobros import cobro_rapido
from apps.cobros import servicios as cobros
from apps.cobros.models import Cargo, CobroRapidoCita, Pago, PagoAplicado, Servicio
from apps.cobros.selectors_cita import saldos_citas
from apps.core.excepciones import ErrorDeNegocio
from apps.core.models import Auditoria
from apps.core.permisos import Rol
from apps.core.tenancy import usando_tenant
from apps.equipo import servicios as equipo
from apps.equipo.models import Membresia
from apps.pacientes.models import Paciente
from apps.tasas import servicios as tasas

from .base import BaseTest, crear_consultorio


def url(cita):
    return reverse('agenda:cobrar_cita', args=[cita.pk])


class CobroRapidoTest(BaseTest):
    def setUp(self):
        super().setUp()
        self.actor = Membresia.objects.get(usuario=self.titular)
        self.perfil = self.actor.perfil
        self.hoy = timezone.localdate()
        with self.en_tenant():
            self.paciente = Paciente.objects.create(nombres='Paciente', apellidos='Sintético')
            self.cita = self.nueva_cita(hora_inicio=time(9))
            self.otra = self.nueva_cita()

    def nueva_cita(self, **datos):
        return Cita.objects.create(paciente=self.paciente, profesional=self.perfil, especialidad=self.perfil.especialidad,
                                   fecha=self.hoy, **datos)

    def cargo(self, precio=20, **datos):
        return cobros.crear_cargo(paciente=self.paciente, descripcion='Concepto sintético', precio_usd=precio, **datos)

    def datos(self, cita, monto, **extra):
        r = self.cliente.get(url(cita))
        self.assertEqual(r.status_code, 200)
        return {'monto': monto, 'moneda': 'USD', 'metodo': 'EFECTIVO', 'recibido': 'on',
                'confirmacion': r.context['form'].initial['confirmacion'], **extra}

    def estado(self, cita):
        with self.en_tenant():
            cita.refresh_from_db()
            return saldos_citas([cita])[cita.pk].estado

    def test_parcial_total_reintento_y_otra_deuda_intacta(self):
        with self.en_tenant():
            vieja = self.cargo(100, fecha=self.hoy - timedelta(days=15))
            posterior = self.cargo(30, fecha=self.hoy + timedelta(days=3))
            otra = self.cargo(40, cita=self.otra)
            propia = self.cargo(20, cita=self.cita)
        datos = self.datos(self.cita, '7,50')
        r = self.cliente.post(url(self.cita), datos, HTTP_HX_REQUEST='true')
        self.assertContains(r, 'Pago registrado para esta cita')
        self.assertContains(r, 'hx-swap-oob="true"')
        self.assertContains(r, 'Abonado')
        self.assertEqual(self.estado(self.cita), 'abonado')
        with patch('apps.cobros.cobro_rapido.VIGENCIA', -1):
            self.assertContains(self.cliente.post(url(self.cita), datos), 'Este pago ya estaba registrado')
        self.assertContains(self.cliente.post(url(self.cita), {**datos, 'monto': '8'}),
                            'ya se usó para un cobro distinto')
        self.assertContains(self.cliente.post(url(self.cita), self.datos(self.cita, '12.50')), 'Pago registrado')
        self.assertEqual(self.estado(self.cita), 'pagado')
        with self.en_tenant():
            self.assertEqual(Pago.objects.count(), 2)
            self.assertEqual(CobroRapidoCita.objects.count(), 2)
            self.assertEqual(set(PagoAplicado.objects.values_list('cargo_id', flat=True)), {propia.pk})
            for cargo in (vieja, otra, posterior):
                self.assertEqual(cargo.pagado_usd, 0)
            self.assertEqual(Auditoria.objects.filter(objeto_tipo='cobros.PagoAplicado').count(), 2)
            self.assertTrue(all(p.sin_aplicar_usd == 0 for p in Pago.objects.all()))
            general = cobros.registrar_pago(paciente=self.paciente, monto=10, moneda='USD', metodo='EFECTIVO')
            self.assertEqual(general.aplicaciones.get().cargo_id, vieja.pk)

    def test_consulta_y_procedimiento_sin_cita_directa_y_deduplicados(self):
        with self.en_tenant():
            consulta = abrir_consulta(paciente=self.paciente, profesional=self.perfil)
            agenda.vincular_consulta(self.cita, consulta, self.perfil)
            proc = Procedimiento.objects.create(paciente=self.paciente, profesional=self.perfil, cita=self.cita,
                                                fecha=self.hoy, descripcion='Procedimiento sintético')
            uno = self.cargo(5, consulta=consulta)
            dos = self.cargo(6, cita=self.cita, consulta=consulta)
            tres = self.cargo(7)
            Cargo.objects.filter(pk=tres.pk).update(procedimiento=proc)
        self.assertContains(self.cliente.get('/agenda/'), f'estado-cobro-cita-{self.otra.pk}')
        self.assertContains(self.cliente.get(f'/agenda/citas/{self.cita.pk}/'), '$ 18,00')
        self.cliente.post(url(self.cita), self.datos(self.cita, '18'))
        with self.en_tenant():
            self.assertEqual(set(PagoAplicado.objects.values_list('cargo_id', flat=True)), {uno.pk, dos.pk, tres.pk})
            self.assertEqual(PagoAplicado.objects.count(), 3)

    def test_anulados_exonerados_descuento_y_sin_cargo(self):
        self.assertEqual(self.estado(self.cita), 'sin_cargo')
        self.assertNotContains(self.cliente.get(url(self.cita)), 'Confirmar cobro')
        with self.en_tenant():
            anulado = self.cargo(150, cita=self.cita)
            cobros.anular_cargo(anulado, 'Anulado de prueba')
        self.assertEqual(self.estado(self.cita), 'sin_cargo')
        with self.en_tenant():
            exonerado = self.cargo(100, cita=self.cita, exonerado=True)
        self.assertEqual(self.estado(self.cita), 'exonerado')
        with self.en_tenant():
            exigible = self.cargo(20, cita=self.cita, descuento_usd=5)
        self.assertContains(self.cliente.post(url(self.cita), self.datos(self.cita, '15.01')), 'supera el saldo')
        self.cliente.post(url(self.cita), self.datos(self.cita, '15'))
        with self.en_tenant():
            self.assertEqual(PagoAplicado.objects.get().cargo_id, exigible.pk)
            self.assertEqual(exonerado.pagado_usd, 0)
            self.assertEqual(anulado.pagado_usd, 0)

    def test_relacion_ambigua_bloquea_incluso_si_hay_otro_cargo_valido(self):
        with self.en_tenant():
            car = self.cargo(5, cita=self.cita)
        datos = self.datos(self.cita, '5')
        with self.en_tenant():
            consulta = abrir_consulta(paciente=self.paciente, profesional=self.perfil)
            agenda.vincular_consulta(self.cita, consulta, self.perfil)
            self.cargo(20, consulta=consulta, cita=self.otra)
        self.assertEqual(self.estado(self.cita), 'revision')
        self.assertEqual(self.estado(self.otra), 'revision')
        r = self.cliente.post(url(self.cita), datos)
        self.assertContains(r, 'Abrir Cuenta')
        self.assertNotContains(r, 'Confirmar cobro')
        with self.en_tenant():
            self.assertFalse(Pago.objects.exists())
            self.assertEqual(car.pagado_usd, 0)

    def test_tasa_bs_redondeo_y_reconfirmacion_con_tasa_actual(self):
        tasas.registrar_del_tenant(self.tenant, Decimal('150.0000'), self.titular)
        with self.en_tenant():
            self.cargo(10, cita=self.cita)
        datos = self.datos(self.cita, '151,00', moneda='BS', metodo='PAGO_MOVIL')
        tasas.registrar_del_tenant(self.tenant, Decimal('151.0000'), self.titular)
        r = self.cliente.post(url(self.cita), datos)
        self.assertContains(r, 'Cambió el saldo, los conceptos o la tasa')
        with self.en_tenant():
            self.assertFalse(Pago.objects.exists())
        datos['confirmacion'] = r.context['form'].initial['confirmacion']
        self.cliente.post(url(self.cita), datos)
        datos = self.datos(self.cita, '0,01', moneda='BS')
        self.assertContains(self.cliente.post(url(self.cita), datos), 'menos de un céntimo')
        sobrepago = self.datos(self.cita, '1359.01', moneda='BS')
        self.assertContains(self.cliente.post(url(self.cita), sobrepago), 'supera el saldo')
        with self.en_tenant():
            p = Pago.objects.get()
            self.assertEqual((p.monto_usd, p.tasa, p.tasa_ref, p.moneda), (Decimal('1'), Decimal('151'), 'USD', 'BS'))

    def test_permiso_csrf_confirmacion_y_aislamiento(self):
        with self.en_tenant():
            self.cargo(5, cita=self.cita)
        otro_tenant, _ = crear_consultorio(slug='otro')
        otro_cliente = self.entrar(otro_tenant, 'titular')
        self.assertEqual(otro_cliente.get(url(self.cita)).status_code, 404)
        medico, clave = equipo.agregar(self.tenant, self.actor, 'medico', 'Médico', 'Sintético', Rol.MEDICO,
                                        especialidad=self.perfil.especialidad)
        medico.usuario.debe_cambiar_clave = False
        medico.usuario.save()
        self.assertEqual(self.entrar(self.tenant, 'medico', clave).get(url(self.cita)).status_code, 403)
        self.assertEqual(Client(HTTP_HOST='localhost').get(url(self.cita)).status_code, 302)
        datos = self.datos(self.cita, '5')
        self.assertContains(self.cliente.post(url(self.cita), {**datos, 'recibido': ''}), 'Este campo es obligatorio')
        self.cliente.handler.enforce_csrf_checks = True
        self.assertEqual(self.cliente.post(url(self.cita), datos).status_code, 403)
        r = self.cliente.post(url(self.cita), datos, HTTP_X_CSRFTOKEN=self.cliente.cookies['csrftoken'].value)
        self.assertContains(r, 'Pago registrado para esta cita')

    def test_respeta_servicio_previsto_y_anulacion_desde_cuenta(self):
        with self.en_tenant():
            servicio = Servicio.objects.create(nombre='Previsto', precio_usd=25)
            cita, _ = agenda.guardar_cita(self.cita, servicios=[servicio.pk])
            self.assertEqual(saldos_citas([cita])[cita.pk].estado, 'sin_cargo')
            agenda.atender(cita, self.perfil)
        self.cliente.post(url(cita), self.datos(cita, '25'))
        with self.en_tenant():
            pago = Pago.objects.get()
            self.assertEqual(PagoAplicado.objects.get().cargo.servicio_id, servicio.pk)
            cobros.anular_pago(pago, 'Anulación de prueba')
        self.assertEqual(self.estado(cita), 'pendiente')
        with self.en_tenant():
            self.assertTrue(CobroRapidoCita.objects.get().pago.anulado)


class CobroRapidoConcurrenteTest(TransactionTestCase):
    def test_dos_operadores_solo_uno_cobra_el_saldo(self):
        if connection.vendor != 'postgresql':
            self.skipTest('Requiere bloqueo de filas de PostgreSQL')
        tenant, titular = crear_consultorio()
        actor = Membresia.objects.get(usuario=titular)
        operador, _ = equipo.agregar(tenant, actor, 'caja', 'Caja', 'Sintética', Rol.ASISTENTE)
        usuarios = (titular, operador.usuario)
        with usando_tenant(tenant):
            paciente = Paciente.objects.create(nombres='Prueba', apellidos='Concurrente')
            cita = Cita.objects.create(paciente=paciente, profesional=actor.perfil, especialidad=actor.perfil.especialidad,
                                       fecha=timezone.localdate())
            cobros.crear_cargo(paciente=paciente, cita=cita, descripcion='Único', precio_usd=20)
            resumen = saldos_citas([cita])[cita.pk]
            tasa, tasa_ref = cobro_rapido.tasa_actual()
        barrera = Barrier(2)

        def cobrar(usuario):
            token = cobro_rapido.confirmar(cita=cita, resumen=resumen, tasa=tasa, tasa_ref=tasa_ref, usuario=usuario)
            try:
                with usando_tenant(tenant):
                    barrera.wait(timeout=5)
                    request = SimpleNamespace(user=usuario, META={})
                    return cobro_rapido.registrar(
                        request=request, cita=cita, monto=Decimal('20'), moneda='USD', metodo='EFECTIVO',
                        referencia='', confirmacion=token,
                    )[1]
            except ErrorDeNegocio as e:
                self.assertIn('Cambió el saldo', str(e))
                return False
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = [pool.submit(cobrar, usuario) for usuario in usuarios]
            self.assertEqual(sorted([a.result(timeout=20), b.result(timeout=20)]), [False, True])
        with usando_tenant(tenant):
            self.assertEqual(Pago.objects.count(), 1)
            self.assertEqual(PagoAplicado.objects.count(), 1)
