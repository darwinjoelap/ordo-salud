from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from functools import partial
from threading import Barrier, Event
from types import SimpleNamespace

from django.db import connection, connections, transaction
from django.test import TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from apps.agenda.models import Cita, ServicioPrevisto
from apps.clinica import consultas, procedimientos
from apps.clinica.models import Consulta, Procedimiento
from apps.cobros import cobro_rapido
from apps.cobros import servicios as cuenta
from apps.cobros.models import Cargo, Pago, PagoAplicado, Servicio
from apps.cobros.selectors_cita import saldos_citas
from apps.core.excepciones import ErrorDeNegocio
from apps.core.models import Auditoria
from apps.core.permisos import Rol
from apps.core.tenancy import usando_tenant
from apps.equipo import servicios as equipo
from apps.equipo.models import Membresia
from apps.pacientes.models import Paciente
from apps.plataforma.models import Especialidad

from .base import BaseTest, crear_consultorio


def cita_para(paciente, perfil, consulta=None):
    return Cita.objects.create(paciente=paciente, profesional=perfil, especialidad=perfil.especialidad,
                               consulta=consulta, estado='ATENDIDA' if consulta else 'PROGRAMADA',
                               fecha=timezone.localdate())


class IntegridadAtencionTest(BaseTest):
    def setUp(self):
        super().setUp()
        self.actor = Membresia.objects.get(usuario=self.titular)
        self.perfil = self.actor.perfil
        with self.en_tenant():
            self.paciente = Paciente.objects.create(nombres='Paciente', apellidos='Sintético')
            self.cita = cita_para(self.paciente, self.perfil)
        self.url = reverse('clinica:consulta_nueva', args=[self.paciente.pk])

    def test_reintento_http_tras_timeout_y_consulta_independiente(self):
        datos = {'cita': self.cita.pk, 'completa': '1', 'accion': 'guardar'}
        primera = self.cliente.post(self.url, datos)  # La respuesta original se pierde para el cliente.
        self.assertEqual(primera.status_code, 302)
        for datos_repetidos in (datos, {'cita': self.cita.pk}):
            self.assertEqual(self.cliente.post(self.url, datos_repetidos).url, primera.url)
        with self.en_tenant():
            original = Consulta.objects.get()
            self.assertEqual(Auditoria.objects.filter(objeto_tipo='clinica.Consulta', accion='CREAR').count(), 1)
            pendiente = cita_para(self.paciente, self.perfil)
        formulario = self.cliente.get(self.url, {'independiente': '1'})
        self.assertContains(formulario, 'name="independiente"')
        datos = {'independiente': '1', 'completa': '1', 'intento': formulario.context['intento']}
        respuesta = self.cliente.post(self.url, datos)
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(self.cliente.post(self.url, datos).url, respuesta.url)
        with self.en_tenant():
            self.cita.refresh_from_db()
            pendiente.refresh_from_db()
            self.assertEqual(self.cita.consulta_id, original.pk)
            self.assertIsNone(pendiente.consulta_id)
            self.assertEqual(Consulta.objects.count(), 2)
        nueva = self.iniciar_independiente(self.paciente, {'completa': '1'})
        self.assertEqual(nueva.status_code, 302)
        self.assertNotEqual(nueva.url, respuesta.url)

    def test_ficha_con_dos_citas_reintenta_la_elegida_y_cobra_cada_plan_una_vez(self):
        with self.en_tenant():
            otra = cita_para(self.paciente, self.perfil)
            servicio = Servicio.objects.create(nombre='Servicio de prueba', precio_usd=99)
            for cita, precio in ((self.cita, 10), (otra, 20)):
                cita.servicios_explicitos = True
                cita.save()
                ServicioPrevisto.objects.create(cita=cita, servicio=servicio, nombre=servicio.nombre, precio_usd=precio)
        ficha = self.cliente.get(reverse('pacientes:detalle', args=[self.paciente.pk]))
        for cita in (self.cita, otra):
            self.assertContains(ficha, f'name="cita" value="{cita.pk}"')
        for _ in range(2):
            self.assertEqual(self.cliente.post(self.url, {'completa': '1'}).status_code, 409)
        form = self.cliente.get(self.url, {'cita': otra.pk})
        self.assertContains(form, f'name="cita" value="{otra.pk}"')
        datos = {'completa': '1', 'cita': otra.pk}
        primera = self.cliente.post(self.url, datos)
        self.assertEqual(primera.status_code, 302)
        self.assertEqual(self.cliente.post(self.url, datos).url, primera.url)
        with self.en_tenant():
            self.cita.refresh_from_db()
            self.assertIsNone(self.cita.consulta_id)
            self.assertEqual(Consulta.objects.count(), 1)
            self.assertEqual((Cargo.objects.get().cita_id, Cargo.objects.get().precio_usd), (otra.pk, 20))
        self.assertEqual(self.cliente.post(self.url, {**datos, 'cita': self.cita.pk}).status_code, 302)
        with self.en_tenant():
            self.assertEqual(Consulta.objects.count(), 2)
            self.assertCountEqual(Cargo.objects.values_list('cita_id', 'precio_usd'), [(self.cita.pk, 10), (otra.pk, 20)])

    def test_cancelacion_sin_sustitucion_y_token_ajeno(self):
        token = self.cliente.get(self.url, {'independiente': '1'}).context['intento']
        with self.en_tenant():
            cita_para(self.paciente, self.perfil)
            Cita.objects.filter(pk=self.cita.pk).update(estado=Cita.Estado.CANCELADA)
            otro = Paciente.objects.create(nombres='Otro', apellidos='Paciente')
        self.assertEqual(self.cliente.post(self.url, {'cita': self.cita.pk}).status_code, 409)
        ajena = reverse('clinica:consulta_nueva', args=[otro.pk])
        self.assertEqual(self.cliente.post(ajena, {'independiente': '1', 'intento': token}).status_code, 409)
        with self.en_tenant():
            self.assertFalse(Consulta.objects.exists())
            self.assertFalse(Cargo.objects.exists())

    def test_permiso_y_aislamiento_en_inicio_explicito(self):
        otro, _ = crear_consultorio(slug='otro')
        otro_cliente = self.entrar(otro, 'titular')
        self.assertEqual(otro_cliente.post(self.url, {'cita': self.cita.pk}).status_code, 404)
        token = self.cliente.get(self.url, {'independiente': '1'}).context['intento']
        with self.en_tenant(otro):
            ajeno = Paciente.objects.create(nombres='Otro', apellidos='Consultorio')
        url_ajena = reverse('clinica:consulta_nueva', args=[ajeno.pk])
        self.assertEqual(otro_cliente.post(url_ajena, {'independiente': '1', 'intento': token}).status_code, 409)
        asistente, clave = equipo.agregar(self.tenant, self.actor, 'recepcion', 'Recepcion', 'Sintética', Rol.ASISTENTE)
        asistente.usuario.debe_cambiar_clave = False
        asistente.usuario.save()
        cliente = self.entrar(self.tenant, 'recepcion', clave)
        self.assertEqual(cliente.post(self.url, {'independiente': '1'}).status_code, 403)
        with self.en_tenant():
            especialidad = Especialidad.objects.exclude(pk=self.perfil.especialidad_id).first()
            Cita.objects.filter(pk=self.cita.pk).update(especialidad=especialidad)
        self.assertEqual(self.cliente.post(self.url, {'cita': self.cita.pk}).status_code, 404)
        with self.en_tenant():
            self.assertFalse(Consulta.objects.exists())

    def test_anular_procedimiento_sin_pago_y_preservar_cargos_historicos(self):
        with self.en_tenant():
            proc = Procedimiento.objects.create(paciente=self.paciente, profesional=self.perfil, cita=self.cita,
                                                descripcion='Sintético', fecha=timezone.localdate())
            cargo = cuenta.crear_cargo(paciente=self.paciente, cita=self.cita, descripcion='Sintético', precio_usd=20)
            Cargo.objects.filter(pk=cargo.pk).update(procedimiento=proc)
            procedimientos.anular(proc, 'Corrección sintética')
            proc.refresh_from_db()
            cargo.refresh_from_db()
            self.assertTrue(proc.anulado)
            self.assertEqual((cargo.estado, cargo.precio_usd), (Cargo.Estado.ANULADO, Decimal('20')))
            self.assertFalse(Pago.objects.exists())

    def test_anular_con_pago_directo_historico_exige_revision_y_conserva_registros(self):
        with self.en_tenant():
            consulta = consultas.abrir_consulta(paciente=self.paciente, profesional=self.perfil)
            consulta = consultas.cerrar_consulta(consulta) if not consultas.faltantes(consulta) else consulta
            cita = cita_para(self.paciente, self.perfil, consulta)
            cargo = cuenta.crear_cargo(paciente=self.paciente, cita=cita, descripcion='Histórico', precio_usd=20)
            pago = cuenta.registrar_pago(paciente=self.paciente, monto=10, moneda='USD', metodo='EFECTIVO')
            aplicacion = pago.aplicaciones.get()
            with self.assertRaisesMessage(ErrorDeNegocio, 'pagos aplicados'):
                consultas.anular_consulta(consulta, 'Corrección sintética')
            cargo.refresh_from_db()
            pago.refresh_from_db()
            consulta.refresh_from_db()
            self.assertEqual((cargo.precio_usd, cargo.pagado_usd), (Decimal('20'), Decimal('10')))
            self.assertFalse(pago.anulado)
            self.assertNotEqual(consulta.estado, Consulta.Estado.ANULADA)
            self.assertTrue(PagoAplicado.objects.filter(pk=aplicacion.pk, cargo=cargo, pago=pago).exists())


class ConcurrenciaIntegridadTest(TransactionTestCase):
    def setUp(self):
        if connection.vendor != 'postgresql':
            self.skipTest('Requiere bloqueo de filas de PostgreSQL')
        self.tenant, self.usuario = crear_consultorio()
        self.perfil = Membresia.objects.get(usuario=self.usuario).perfil
        self.request = SimpleNamespace(user=self.usuario, META={})

    def paciente(self):
        return Paciente.objects.create(nombres='Paciente', apellidos='Concurrente')

    def atencion(self, *, procedimiento=False):
        paciente = self.paciente()
        consulta = None if procedimiento else consultas.abrir_consulta(paciente=paciente, profesional=self.perfil)
        cita = cita_para(paciente, self.perfil, consulta)
        if procedimiento:
            proc = Procedimiento.objects.create(paciente=paciente, profesional=self.perfil, cita=cita,
                                                descripcion='Sintético', fecha=timezone.localdate())
        cargo = cuenta.crear_cargo(paciente=paciente, cita=cita, consulta=consulta, descripcion='Sintético', precio_usd=20)
        if procedimiento:
            Cargo.objects.filter(pk=cargo.pk).update(procedimiento=proc)
        return paciente, cita, cargo, proc if procedimiento else consulta

    def confirmar(self, cita):
        resumen = saldos_citas([cita])[cita.pk]
        tasa, referencia = cobro_rapido.tasa_actual()
        return cobro_rapido.confirmar(cita=cita, resumen=resumen, tasa=tasa, tasa_ref=referencia, usuario=self.usuario)

    def rapido(self, cita, token):
        return cobro_rapido.registrar(request=self.request, cita=cita, monto=Decimal('20'), moneda='USD',
                                     metodo='EFECTIVO', referencia='', confirmacion=token)

    def lanzar(self, pool, funcion):
        inicio = Event()

        def ejecutar():
            try:
                with usando_tenant(self.tenant):
                    inicio.set()
                    return funcion()
            finally:
                connections.close_all()

        futuro = pool.submit(ejecutar)
        self.assertTrue(inicio.wait(5))
        return futuro

    def test_cobro_rapido_y_anulacion_en_ambos_ordenes(self):
        with usando_tenant(self.tenant), ThreadPoolExecutor(max_workers=1) as pool:
            for anulacion_primero in (True, False):
                _, cita, cargo, consulta = self.atencion()
                token = self.confirmar(cita)
                with transaction.atomic():
                    cuenta.bloquear_cuenta(cita.paciente_id)
                    if anulacion_primero:
                        futuro = self.lanzar(pool, partial(self.rapido, cita, token))
                        consultas.anular_consulta(consulta, 'Corrección sintética')
                    else:
                        futuro = self.lanzar(pool, partial(consultas.anular_consulta, consulta, 'Corrección sintética'))
                        self.rapido(cita, token)
                with self.assertRaises(ErrorDeNegocio):
                    futuro.result(timeout=15)
                consulta.refresh_from_db()
                self.assertEqual(consulta.estado == Consulta.Estado.ANULADA, anulacion_primero)
                self.assertEqual(cargo.pagado_usd, 0 if anulacion_primero else 20)

    def test_cuenta_concurrente_excluye_cargo_de_procedimiento_anulado(self):
        with usando_tenant(self.tenant), ThreadPoolExecutor(max_workers=1) as pool:
            paciente, cita, cargo, proc = self.atencion(procedimiento=True)
            token = self.confirmar(cita)
            with transaction.atomic():
                cuenta.bloquear_cuenta(paciente.pk)
                futuro = self.lanzar(pool, lambda: cuenta.registrar_pago(
                    paciente=paciente, monto=20, moneda='USD', metodo='EFECTIVO'))
                procedimientos.anular(proc, 'Corrección sintética')
            pago = futuro.result(timeout=15)
            self.assertEqual(pago.sin_aplicar_usd, Decimal('20'))
            with self.assertRaises(ErrorDeNegocio):
                self.rapido(cita, token)
            self.assertEqual(cargo.pagado_usd, 0)

    def test_cuenta_concurrente_con_anulacion_de_consulta_deja_cargo_sin_aplicar(self):
        with usando_tenant(self.tenant), ThreadPoolExecutor(max_workers=1) as pool:
            paciente, cita, cargo, consulta = self.atencion()
            with transaction.atomic():
                cuenta.bloquear_cuenta(paciente.pk)
                futuro = self.lanzar(pool, lambda: cuenta.registrar_pago(
                    paciente=paciente, monto=20, moneda='USD', metodo='EFECTIVO'))
                consultas.anular_consulta(consulta, 'Corrección sintética')
            pago = futuro.result(timeout=15)
            cargo.refresh_from_db()
            self.assertEqual((cargo.estado, cargo.precio_usd), (Cargo.Estado.PENDIENTE, Decimal('20')))
            self.assertEqual(pago.sin_aplicar_usd, Decimal('20'))
            self.assertEqual(saldos_citas([cita])[cita.pk].estado, 'revision')

    def test_dos_solicitudes_concurrentes_de_consulta_completa(self):
        with usando_tenant(self.tenant):
            paciente = self.paciente()
            cita = cita_para(paciente, self.perfil)
            otra = cita_para(paciente, self.perfil)
        self.dos_inicios(paciente, {'completa': '1', 'cita': cita.pk, 'accion': 'guardar'})
        with usando_tenant(self.tenant):
            cita.refresh_from_db()
            self.assertEqual(Consulta.objects.get().pk, cita.consulta_id)
            otra.refresh_from_db()
            self.assertIsNone(otra.consulta_id)

    def test_consulta_independiente_concurrente(self):
        with usando_tenant(self.tenant):
            paciente = self.paciente()
            pendiente = cita_para(paciente, self.perfil)
        url = reverse('clinica:consulta_nueva', args=[paciente.pk])
        cliente = BaseTest.entrar(self.tenant, 'titular')
        intento = cliente.get(url, {'independiente': '1'}).context['intento']
        self.dos_inicios(paciente, {'completa': '1', 'independiente': '1', 'intento': intento})
        with usando_tenant(self.tenant):
            self.assertIsNotNone(Consulta.objects.get().inicio_independiente)
            pendiente.refresh_from_db()
            self.assertIsNone(pendiente.consulta_id)
            self.assertFalse(Cargo.objects.exists())

    def dos_inicios(self, paciente, datos):
        barrera = Barrier(2)
        url = reverse('clinica:consulta_nueva', args=[paciente.pk])

        def iniciar():
            cliente = BaseTest.entrar(self.tenant, 'titular')
            barrera.wait(timeout=5)
            return cliente.post(url, datos)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futuros = [self.lanzar(pool, iniciar) for _ in range(2)]
            resultados = [futuro.result(timeout=15) for futuro in futuros]
        self.assertEqual([r.status_code for r in resultados], [302, 302])
        self.assertEqual(resultados[0].url, resultados[1].url)
