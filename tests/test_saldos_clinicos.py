"""Lectura de históricos clínicos y financieros en las pantallas de cobros."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

from django.db import connection, connections
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.agenda.models import Cita
from apps.clinica import consultas, procedimientos
from apps.clinica.models import Consulta, Procedimiento
from apps.cobros import servicios as cobros
from apps.cobros.models import Cargo, Pago, PagoAplicado
from apps.cobros.selectors_cita import saldos_citas
from apps.core.excepciones import ErrorDeNegocio
from apps.core.permisos import Rol
from apps.core.tenancy import usando_tenant
from apps.equipo import servicios as equipo
from apps.equipo.models import Membresia
from apps.pacientes.models import Paciente
from apps.reportes.selectors import Filtros, finanzas_de

from .base import BaseTest, crear_consultorio


class SaldosClinicosTest(BaseTest):
    def setUp(self):
        super().setUp()
        self.hoy = timezone.localdate()
        self.perfil = Membresia.objects.get(usuario=self.titular).perfil
        with self.en_tenant():
            self.paciente = Paciente.objects.create(nombres='Prueba', apellidos='Sintética')
            self.consulta = consultas.abrir_consulta(paciente=self.paciente, profesional=self.perfil)
            self.cita = Cita.objects.create(paciente=self.paciente, profesional=self.perfil,
                                            especialidad=self.perfil.especialidad, consulta=self.consulta,
                                            fecha=self.hoy, estado=Cita.Estado.ATENDIDA)
            self.cargo = cobros.crear_cargo(paciente=self.paciente, cita=self.cita, descripcion='Histórico',
                                            precio_usd=25, descuento_usd=5)

    def test_anular_y_recibir_20_sin_destino(self):
        with self.en_tenant():
            consultas.anular_consulta(self.consulta, 'Corrección sintética')
            self.assertEqual(cobros.estado_cuenta(self.paciente)['saldo'], 0)
            self.assertEqual(cobros.por_cobrar(), [])
            pago = cobros.registrar_pago(paciente=self.paciente, monto=20, moneda='USD', metodo='EFECTIVO')
            self.assertEqual(pago.sin_aplicar_usd, 20)
            self.assertEqual(saldos_citas([self.cita])[self.cita.pk].estado, 'revision')
            self.assertFalse(PagoAplicado.objects.exists())
            antes = self.historico()
        cuenta = self.cliente.get(f'/cobros/pacientes/{self.paciente.pk}/')
        pendientes = self.cliente.get('/cobros/por-cobrar/')
        caja = self.cliente.get('/cobros/caja/')
        self.assertEqual((cuenta.context['saldo'], cuenta.context['saldo_revision'], cuenta.context['a_favor']),
                         (0, 20, 20))
        self.assertEqual((pendientes.context['total'], pendientes.context['total_revision']), (0, 20))
        self.assertEqual((caja.context['total_usd'], caja.context['sin_aplicar']), (20, 20))
        for pantalla, etiqueta in ((cuenta, 'Fondos sin aplicar'), (pendientes, 'En revisión'),
                                   (caja, 'Sin aplicar')):
            self.assertContains(pantalla, etiqueta)
        with self.en_tenant():
            self.assertEqual(self.historico(), antes)

    @staticmethod
    def historico():
        return [list(modelo.objects.order_by('pk').values()) for modelo in (Cargo, Pago, PagoAplicado)]

    def verificar_historico_pagado(self, monto):
        with self.en_tenant():
            pago = cobros.registrar_pago(paciente=self.paciente, monto=monto * 40, moneda='BS',
                                        metodo='PAGO_MOVIL', tasa=40)
            with self.assertRaisesMessage(ErrorDeNegocio, 'pagos aplicados'):
                consultas.anular_consulta(self.consulta, 'Ensayo de la regla actual')
            # Estado histórico anterior a la protección. Solo se construye en la base sintética.
            Consulta.objects.filter(pk=self.consulta.pk).update(estado=Consulta.Estado.ANULADA)
            antes = self.historico()
            with CaptureQueriesContext(connection) as sql:
                cuenta = cobros.estado_cuenta(self.paciente)
                pendientes = cobros.informe_por_cobrar()
                caja = cobros.caja(self.hoy)
                agenda = saldos_citas([self.cita])[self.cita.pk]
                tablero = finanzas_de(Filtros(self.hoy, self.hoy))
            self.assertFalse(any(q['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE'))
                                 for q in sql.captured_queries))
            self.assertEqual((cuenta['saldo'], cuenta['a_favor'], cuenta['saldo_revision']), (0, 0, 20 - monto))
            self.assertTrue(cuenta['hay_revision'])
            self.assertEqual((pendientes['total'], pendientes['total_revision']), (0, 20 - monto))
            self.assertEqual(pendientes['revision'][0][2], [self.cargo])
            self.assertEqual((caja['total_usd'], caja['sin_aplicar'], caja['resumen'][0]['monto']), (monto, 0, monto * 40))
            self.assertEqual((agenda.estado, tablero['por_cobrar']), ('revision', 0))
            self.assertEqual((pago.aplicaciones.get().cargo_id, pago.tasa, pago.tasa_ref), (self.cargo.pk, 40, 'USD'))
            self.assertEqual(self.historico(), antes)

    def test_historico_totalmente_aplicado(self):
        self.verificar_historico_pagado(20)

    def test_historico_parcialmente_aplicado(self):
        self.verificar_historico_pagado(7)

    def test_cargos_validos_de_otras_citas_y_fondos_sin_compensar(self):
        with self.en_tenant():
            consultas.anular_consulta(self.consulta, 'Corrección sintética')
            otra = Cita.objects.create(paciente=self.paciente, profesional=self.perfil,
                                       especialidad=self.perfil.especialidad, fecha=self.hoy - timedelta(days=2))
            anterior = cobros.crear_cargo(paciente=self.paciente, cita=otra, descripcion='Otra cita', precio_usd=12,
                                          descuento_usd=2, fecha=otra.fecha)
            cobros.crear_cargo(paciente=self.paciente, descripcion='Exonerado', precio_usd=30, exonerado=True)
            valido = cobros.crear_cargo(paciente=self.paciente, descripcion='Independiente', precio_usd=9)
            cobros.registrar_pago(paciente=self.paciente, monto=12, moneda='USD', metodo='EFECTIVO')
            # Ingreso histórico no conciliado: leer la cuenta no ordena su aplicación.
            Pago.objects.create(paciente=self.paciente, monto=8, monto_usd=8, fecha=self.hoy)
            cuenta = cobros.estado_cuenta(self.paciente)
            self.assertEqual((cuenta['saldo'], cuenta['a_favor'], cuenta['saldo_revision']), (7, 8, 20))
            self.assertEqual((anterior.pagado_usd, valido.pagado_usd, self.cargo.pagado_usd), (10, 2, 0))
            informe = cobros.informe_por_cobrar()
            self.assertEqual((informe['total'], informe['total_revision']), (7, 20))
            self.assertEqual(saldos_citas([otra])[otra.pk].estado, 'pagado')
            self.assertEqual(finanzas_de(Filtros(otra.fecha, self.hoy))['por_cobrar'], 7)

    def test_anulacion_procedimiento_cargos_directos_y_cargo_financieramente_anulado(self):
        with self.en_tenant():
            cita = Cita.objects.create(paciente=self.paciente, profesional=self.perfil,
                                       especialidad=self.perfil.especialidad, fecha=self.hoy)
            proc = Procedimiento.objects.create(cita=cita, paciente=self.paciente, profesional=self.perfil,
                                               fecha=self.hoy, descripcion='Sintético')
            directo = cobros.crear_cargo(paciente=self.paciente, cita=cita, descripcion='Directo', precio_usd=12)
            asociado = cobros.crear_cargo(paciente=self.paciente, cita=cita, descripcion='Asociado', precio_usd=15)
            Cargo.objects.filter(pk=asociado.pk).update(procedimiento=proc)
            procedimientos.anular(proc, 'Corrección sintética')
            cuenta = cobros.estado_cuenta(self.paciente)
            self.assertEqual((cuenta['saldo'], cuenta['saldo_revision']), (20, 12))
            self.assertEqual(cobros.informe_por_cobrar()['revision'][0][2], [directo])
            self.assertEqual(saldos_citas([cita])[cita.pk].estado, 'revision')
            asociado.refresh_from_db()
            self.assertEqual((asociado.estado, asociado.precio_usd), (Cargo.Estado.ANULADO, 15))

    def test_ambiguedad_de_cita_queda_en_revision_en_ambos_caminos(self):
        with self.en_tenant():
            otra = Cita.objects.create(paciente=self.paciente, profesional=self.perfil,
                                       especialidad=self.perfil.especialidad, fecha=self.hoy)
            Cargo.objects.filter(pk=self.cargo.pk).update(cita=otra, consulta=self.consulta)
            pago = cobros.registrar_pago(paciente=self.paciente, monto=20, moneda='USD', metodo='EFECTIVO')
            self.assertEqual(pago.sin_aplicar_usd, 20)
            self.assertEqual(cobros.informe_por_cobrar()['total'], 0)
            self.assertEqual(cobros.estado_cuenta(self.paciente)['saldo_revision'], 20)
            self.assertTrue(all(s.estado == 'revision' for s in saldos_citas([self.cita, otra]).values()))

    def test_revision_y_fondos_aislados_por_consultorio_y_permiso(self):
        with self.en_tenant():
            consultas.anular_consulta(self.consulta, 'Corrección sintética')
            cobros.registrar_pago(paciente=self.paciente, monto=20, moneda='USD', metodo='EFECTIVO')
        otro, _ = crear_consultorio(slug='otro')
        cliente = self.entrar(otro, 'titular')
        url = f'/cobros/pacientes/{self.paciente.pk}/'
        self.assertEqual(cliente.get(url).status_code, 404)
        self.assertEqual(cliente.get('/cobros/por-cobrar/').context['revision'], [])
        self.assertEqual(cliente.get('/cobros/caja/').context['sin_aplicar'], 0)
        actor = self.perfil.membresia
        medico, clave = equipo.agregar(self.tenant, actor, 'medico', 'Médico', 'Sintético', Rol.MEDICO,
                                       especialidad=self.perfil.especialidad)
        medico.usuario.debe_cambiar_clave = False
        medico.usuario.save()
        cliente = self.entrar(self.tenant, 'medico', clave)
        for ruta in (url, '/cobros/por-cobrar/', '/cobros/caja/'):
            self.assertEqual(cliente.get(ruta).status_code, 403)

    def test_aplicacion_cruzada_historica_no_libera_fondos_ni_expone_el_otro_cargo(self):
        otro, _ = crear_consultorio(slug='otro')
        with self.en_tenant(otro):
            ajeno = Paciente.objects.create(nombres='Otro', apellidos='Consultorio')
            cargo = cobros.crear_cargo(paciente=ajeno, descripcion='Concepto ajeno', precio_usd=7)
        with self.en_tenant():
            pago = Pago.objects.create(paciente=self.paciente, fecha=self.hoy, monto=25, monto_usd=25)
            PagoAplicado.objects.create(pago=pago, cargo=cargo, monto_usd=7)
            antes = self.historico()
            cobros.conciliar(self.paciente)
            self.assertEqual(self.historico(), antes)
            cuenta = cobros.estado_cuenta(self.paciente)
            self.assertEqual((cuenta['saldo'], cuenta['a_favor']), (20, 0))
            self.assertTrue(cuenta['pagos'][0].revision)
            self.assertEqual(cobros.caja(self.hoy)['total_usd'], 25)
        resp = self.cliente.get(f'/cobros/pacientes/{self.paciente.pk}/')
        self.assertContains(resp, 'Aplicaciones en revisión')
        self.assertNotContains(resp, 'Concepto ajeno')
        with self.en_tenant(otro):
            self.assertEqual((cobros.informe_por_cobrar()['total'], cobros.caja(self.hoy)['total_usd']), (0, 0))


class LecturaConcurrenteTest(TransactionTestCase):
    def test_pago_confirmado_entre_lecturas_se_ve_entero_en_la_siguiente_cuenta(self):
        if connection.vendor != 'postgresql':
            self.skipTest('Requiere instantáneas y conexiones independientes de PostgreSQL')
        tenant, _ = crear_consultorio()
        with usando_tenant(tenant), ThreadPoolExecutor(max_workers=1) as pool:
            paciente = Paciente.objects.create(nombres='Prueba', apellidos='Concurrente')
            cobros.crear_cargo(paciente=paciente, descripcion='Cargo', precio_usd=20)

            def ingresar():
                try:
                    with usando_tenant(tenant):
                        cobros.registrar_pago(paciente=paciente, monto=25, moneda='USD', metodo='EFECTIVO')
                finally:
                    connections.close_all()

            leer_pagos = cobros.pagos_con_saldo

            def tras_confirmar(qs):
                if not qs.query.select_for_update:
                    pool.submit(ingresar).result(timeout=10)
                return leer_pagos(qs)

            with patch.object(cobros, 'pagos_con_saldo', side_effect=tras_confirmar):
                antes = cobros.estado_cuenta(paciente)
            despues = cobros.estado_cuenta(paciente)
            self.assertEqual((antes['saldo'], antes['total_pagos'], antes['a_favor']), (20, 0, 0))
            self.assertEqual((despues['saldo'], despues['total_pagos'], despues['a_favor']), (0, 25, 5))
