from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

from django.db import connection, connections
from django.test import TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from apps.agenda import servicios as agenda
from apps.agenda.models import Cita, ServicioPrevisto, TipoCita
from apps.clinica.consultas import crear_consulta_completa
from apps.clinica.models import Procedimiento
from apps.cobros import servicios as cobros
from apps.cobros.models import Cargo, Pago, PagoAplicado, Servicio
from apps.cobros.selectors_cita import saldos_citas
from apps.core.models import Auditoria
from apps.core.tenancy import usando_tenant
from apps.equipo import servicios as equipo
from apps.equipo.models import Membresia
from apps.pacientes.models import Paciente
from apps.plataforma.models import Especialidad

from .base import BaseTest, crear_consultorio


class ServiciosPrevistosTest(BaseTest):
    def setUp(self):
        super().setUp()
        self.membresia = Membresia.objects.get(usuario=self.titular)
        self.perfil = self.membresia.perfil
        self.especialidad = self.perfil.especialidad
        self.pediatria = Especialidad.objects.get(codigo='pediatria')
        self.hoy = timezone.localdate()
        with self.en_tenant():
            self.paciente = Paciente.objects.create(nombres='Paciente', apellidos='Sintético')
            self.general = Servicio.objects.create(nombre='Servicio general', precio_usd=Decimal('10'))
            self.propio = Servicio.objects.create(nombre='Consulta general', precio_usd=Decimal('20'),
                                                   especialidad=self.especialidad)
            self.otro = Servicio.objects.create(nombre='Servicio pediátrico', precio_usd=Decimal('30'),
                                                especialidad=self.pediatria)
            self.inactivo = Servicio.objects.create(nombre='Servicio inactivo', precio_usd=Decimal('5'), activo=False)
            self.tipo = TipoCita.objects.get(nombre='Control')
            self.tipo.servicio = self.propio
            self.tipo.duracion_min = 45
            self.tipo.save()

    def datos(self, servicios, **extra):
        return {'paciente': self.paciente.pk, 'profesional': self.perfil.pk, 'fecha': self.hoy.isoformat(),
                'servicios_presentes': 'True', 'servicios': servicios, **extra}

    def agendar(self, servicios, **extra):
        r = self.cliente.post('/agenda/citas/nueva/', self.datos(servicios, **extra))
        self.assertEqual(r.status_code, 302, r.context['form'].errors if r.status_code == 200 else '')
        with self.en_tenant():
            return Cita.objects.latest('pk')

    def editar(self, cita, servicios, **extra):
        return self.cliente.post(f'/agenda/citas/{cita.pk}/editar/', self.datos(servicios, **extra))


    def test_tipos_de_cita_iniciales_y_servicios_de_ficha(self):
        with self.en_tenant():
            nombres = set(TipoCita.objects.values_list('nombre', flat=True))
            self.assertTrue({'Primera consulta', 'Control', 'Emergencia', 'Otra'} <= nombres)
        self.assertContains(self.cliente.get('/agenda/citas/nueva/'), 'Primera consulta')
        ficha = self.cliente.get(f'/pacientes/{self.paciente.pk}/')
        self.assertContains(ficha, 'Servicios para consulta independiente')
        self.assertContains(ficha, self.general.nombre)
        self.assertNotContains(ficha, self.otro.nombre)

    def test_consulta_independiente_cobra_servicios_una_vez(self):
        url = reverse('clinica:consulta_nueva', args=(self.paciente.pk,))
        r = self.cliente.get(url, {'independiente': '1',
                                   'servicios': [self.general.pk, self.propio.pk]})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Servicios de esta consulta')
        self.assertContains(r, self.general.nombre)
        datos = {'completa': '1', 'accion': 'guardar', 'independiente': '1',
                 'intento': r.context['intento'],
                 'servicios': [self.general.pk, self.propio.pk]}
        respuesta = self.cliente.post(url, datos)
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(self.cliente.post(url, datos).status_code, 302)
        with self.en_tenant():
            cargos = list(Cargo.objects.filter(consulta__paciente=self.paciente))
            self.assertEqual(len(cargos), 2)
            self.assertEqual({(c.servicio_id, c.precio_usd) for c in cargos},
                             {(self.general.pk, Decimal('10')), (self.propio.pk, Decimal('20'))})
            self.assertTrue(all(c.cita_id is None for c in cargos))

    def test_consulta_independiente_rechaza_servicios_ajenos_o_inactivos(self):
        url = reverse('clinica:consulta_nueva', args=(self.paciente.pk,))
        otro, _ = crear_consultorio(slug='otro-servicios')
        with self.en_tenant(otro):
            ajeno = Servicio.objects.create(nombre='Externo', precio_usd=Decimal('99'))
        for servicio in (self.otro, self.inactivo, ajeno):
            r = self.cliente.get(url, {'independiente': '1'})
            datos = {'completa': '1', 'accion': 'guardar', 'independiente': '1',
                     'intento': r.context['intento'], 'servicios': [servicio.pk]}
            respuesta = self.cliente.post(url, datos)
            self.assertEqual(respuesta.status_code, 200)
            self.assertContains(respuesta, 'servicios no disponibles')
        with self.en_tenant():
            self.assertFalse(Cargo.objects.exists())
            from apps.clinica.models import Consulta
            self.assertFalse(Consulta.objects.exists())

    def test_consulta_vinculada_respeta_plan_y_no_agrega_servicio_inyectado(self):
        cita = self.agendar([self.general.pk])
        url = reverse('clinica:consulta_nueva', args=(self.paciente.pk,))
        respuesta = self.cliente.post(url, {'cita': cita.pk, 'completa': '1',
                                            'accion': 'guardar', 'servicios': [self.propio.pk]})
        self.assertEqual(respuesta.status_code, 302)
        with self.en_tenant():
            self.assertEqual(list(Cargo.objects.filter(cita=cita).values_list('servicio_id', flat=True)),
                             [self.general.pk])

    def test_creacion_edicion_sin_cargo_y_precio_congelado(self):
        cita = self.agendar([self.general.pk, self.propio.pk], tipo=self.tipo.pk)
        detalle = self.cliente.get(f'/agenda/citas/{cita.pk}/')
        self.assertContains(detalle, 'Servicios previstos')
        self.assertContains(detalle, self.general.nombre)
        with self.en_tenant():
            Servicio.objects.filter(pk=self.general.pk).update(precio_usd=99)
        self.assertEqual(self.editar(cita, [self.general.pk], tipo=self.tipo.pk).status_code, 302)
        with self.en_tenant():
            self.assertEqual(ServicioPrevisto.objects.get(cita=cita).precio_usd, Decimal('10'))
            self.assertFalse(Cargo.objects.exists())
        self.assertFalse(ServicioPrevisto.objects.exists())

    def test_preseleccion_compatible_y_vacio_explicito(self):
        r = self.cliente.get('/agenda/citas/nueva/')
        self.assertContains(r, 'tipos-servicios')
        datos = self.datos([], tipo=self.tipo.pk)
        del datos['servicios_presentes']
        self.assertEqual(self.cliente.post('/agenda/citas/nueva/', datos).status_code, 302)
        with self.en_tenant():
            self.assertEqual(ServicioPrevisto.objects.get().servicio_id, self.propio.pk)
        cita = self.agendar([], tipo=self.tipo.pk)
        with self.en_tenant():
            agenda.atender(cita, self.perfil)
            self.assertFalse(Cargo.objects.filter(cita=cita).exists())

    def test_inactivo_incompatible_ajeno_y_cambio_de_profesional(self):
        otro_tenant, _ = crear_consultorio(slug='otro')
        with self.en_tenant(otro_tenant):
            ajeno = Servicio.objects.create(nombre='Ajeno', precio_usd=Decimal('9'))
        for servicio in (self.inactivo, self.otro, ajeno):
            r = self.cliente.post('/agenda/citas/nueva/', self.datos([servicio.pk]))
            self.assertEqual(r.status_code, 200)
        with self.en_tenant():
            self.assertFalse(Cita.objects.exists())
        self.tenant.especialidades.add(self.pediatria)
        medico, clave = equipo.agregar(self.tenant, self.membresia, 'pediatra', 'Paz', 'Prueba', 'MEDICO',
                                    especialidad=self.pediatria)
        cita = self.agendar([self.propio.pk])
        self.assertContains(self.editar(cita, [self.propio.pk], profesional=medico.perfil.pk),
                            'alguna opción no está disponible')
        self.assertEqual(self.editar(cita, [self.general.pk, self.otro.pk], profesional=medico.perfil.pk).status_code, 302)
        with self.en_tenant():
            cita.refresh_from_db()
            self.assertEqual(cita.especialidad, self.pediatria)
            self.assertEqual(set(ServicioPrevisto.objects.filter(cita=cita).values_list('servicio_id', flat=True)),
                             {self.general.pk, self.otro.pk})
        medico.usuario.debe_cambiar_clave = False
        medico.usuario.save()
        cliente_medico = self.entrar(self.tenant, 'pediatra', clave)
        self.assertEqual(cliente_medico.get(f'/agenda/citas/{cita.pk}/editar/').status_code, 200)
        r = cliente_medico.post(f'/agenda/citas/{cita.pk}/editar/', self.datos([self.general.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context['form']['profesional'].errors)
        otro_cliente = self.entrar(otro_tenant, 'titular')
        self.assertEqual(otro_cliente.get(f'/agenda/citas/{cita.pk}/editar/').status_code, 404)

    def test_consulta_cobra_el_plan_una_vez_y_conserva_el_precio(self):
        cita = self.agendar([self.general.pk, self.propio.pk])
        with self.en_tenant():
            Servicio.objects.filter(pk=self.propio.pk).update(activo=False, nombre='Nombre nuevo', precio_usd=99)
            consulta = agenda.atender(cita, self.perfil)
            self.assertEqual(agenda.atender(cita, self.perfil).pk, consulta.pk)
            cargos = Cargo.objects.filter(cita=cita, consulta=consulta).values_list('descripcion', 'precio_usd')
            self.assertEqual(set(cargos), {(self.general.nombre, Decimal('10')), (self.propio.nombre, Decimal('20'))})
        self.assertEqual(self.editar(cita, []).status_code, 302)
        with self.en_tenant():
            self.assertEqual(ServicioPrevisto.objects.filter(cita=cita).count(), 2)

    def test_consulta_completa_y_cita_historica_predeterminada(self):
        cita = self.agendar([self.general.pk])
        with self.en_tenant():
            consulta = crear_consulta_completa(paciente=self.paciente, profesional=self.perfil, plantilla=None,
                                               tipo='PRIMERA', lugar=None, datos_por_seccion={}, cita=cita)
            self.assertEqual(Cargo.objects.get(consulta=consulta).servicio_id, self.general.pk)
            historica = Cita.objects.create(paciente=self.paciente, profesional=self.perfil, especialidad=self.especialidad,
                                           fecha=self.hoy, tipo=self.tipo)
            Servicio.objects.filter(pk=self.propio.pk).update(precio_usd=32)
            agenda.atender(historica, self.perfil)
            self.assertEqual(Cargo.objects.get(cita=historica).precio_usd, Decimal('32'))

    def test_reintento_consulta_explicita_no_cobra_otra_cita(self):
        atendida = self.agendar([self.general.pk])
        pendiente = self.agendar([self.propio.pk])
        with self.en_tenant():
            agenda.atender(atendida, self.perfil)
            atendida.refresh_from_db()
            crear_consulta_completa(paciente=self.paciente, profesional=self.perfil, plantilla=None, tipo='PRIMERA',
                                    lugar=None, datos_por_seccion={}, cita=atendida)
            self.assertFalse(Cargo.objects.filter(cita=pendiente).exists())
        url = reverse('clinica:consulta_nueva', args=(self.paciente.pk,))
        self.assertEqual(self.cliente.post(url, {'cita': pendiente.pk}).status_code, 302)
        with self.en_tenant():
            self.assertEqual(Cargo.objects.get(cita=pendiente).servicio_id, self.propio.pk)

    def test_procedimiento_preselecciona_y_cobra_solo_lo_confirmado_una_vez(self):
        cita = self.agendar([self.general.pk, self.propio.pk])
        with self.en_tenant():
            Servicio.objects.filter(pk=self.general.pk).update(activo=False, precio_usd=99)
        url = reverse('clinica:procedimiento_nuevo', args=(self.paciente.pk,))
        r = self.cliente.get(url, {'cita': cita.pk})
        self.assertEqual(r.context['preseleccion'], {str(self.general.pk), str(self.propio.pk)})
        datos = {'cita': cita.pk, 'servicios': [self.general.pk], 'version_cita': cita.actualizado_en.isoformat()}
        for _ in range(2):
            self.assertEqual(self.cliente.post(url, datos).status_code, 302)
        with self.en_tenant():
            proc = Procedimiento.objects.get(cita=cita)
            self.assertEqual(Cargo.objects.get(procedimiento=proc).precio_usd, Decimal('10'))

    def test_procedimiento_conserva_cargos_y_pago_hechos_en_cuenta(self):
        servicios = [self.general.pk, self.propio.pk]
        cita = self.agendar(servicios)
        cuenta = reverse('cobros:cuenta', args=(self.paciente.pk,))
        for servicio in servicios:
            self.assertEqual(self.cliente.post(cuenta, {'accion': 'cargo', 'servicio': servicio}).status_code, 302)
        pago = {'accion': 'pago', 'monto': '30', 'moneda': 'USD', 'metodo': 'EFECTIVO'}
        self.assertEqual(self.cliente.post(cuenta, pago).status_code, 302)
        with self.en_tenant():
            cargos = {cargo.servicio_id: cargo.pk for cargo in Cargo.objects.all()}
            aplicaciones = list(PagoAplicado.objects.order_by('pk').values_list('pk', 'pago_id', 'cargo_id', 'monto_usd'))
        url = reverse('clinica:procedimiento_nuevo', args=(self.paciente.pk,))
        datos = {'cita': cita.pk, 'servicios': servicios, 'version_cita': cita.actualizado_en.isoformat()}
        revision = self.cliente.post(url, datos)
        self.assertContains(revision, 'Revisa los cargos existentes')
        with self.en_tenant():
            self.assertFalse(Procedimiento.objects.exists())
            self.assertEqual(Cargo.objects.count(), 2)
        for opcion in revision.context['servicios']:
            pk = opcion['servicio'].pk
            if pk in cargos:
                self.assertContains(revision, f'Vincular cargo #{cargos[pk]}')
                datos.update({f'revision_{pk}': opcion['revision']['firma'], f'cargo_{pk}': cargos[pk]})
        self.assertEqual(self.cliente.post(url, datos).status_code, 302)
        self.assertEqual(self.cliente.post(url, datos).status_code, 302)
        with self.en_tenant():
            proc = Procedimiento.objects.get(cita=cita)
            self.assertEqual(set(proc.cargos.values_list('pk', flat=True)), set(cargos.values()))
            self.assertEqual(Cargo.objects.count(), 2)
            self.assertEqual(Pago.objects.count(), 1)
            self.assertEqual(list(PagoAplicado.objects.order_by('pk').values_list('pk', 'pago_id', 'cargo_id', 'monto_usd')),
                             aplicaciones)
            self.assertEqual(saldos_citas([cita])[cita.pk].estado, 'pagado')
            self.assertEqual(proc.saldo_usd, Decimal('0'))
            eventos = Auditoria.objects.filter(accion='EDITAR', objeto_tipo='cobros.Cargo')
            self.assertEqual(set(eventos.values_list('objeto_id', flat=True)), {str(pk) for pk in cargos.values()})
        rapido = self.cliente.get(reverse('agenda:cobrar_cita', args=(cita.pk,)))
        self.assertNotContains(rapido, 'Confirmo que recibí este pago')

    def test_procedimiento_revalida_revision_y_permite_un_cargo_adicional_explicito(self):
        pk = self.general.pk
        cita = self.agendar([pk])
        url = reverse('clinica:procedimiento_nuevo', args=(self.paciente.pk,))
        datos = {'cita': cita.pk, 'servicios': [pk], 'version_cita': cita.actualizado_en.isoformat()}
        with self.en_tenant():
            anterior = cobros.crear_cargo(paciente=self.paciente, servicio=self.general, descripcion='', precio_usd=10)
        formulario = self.cliente.get(url, {'cita': cita.pk})
        opcion = next(o for o in formulario.context['servicios'] if o['servicio'].pk == pk)
        datos.update({f'revision_{pk}': opcion['revision']['firma'], f'cargo_{pk}': 'nuevo'})
        with self.en_tenant():
            cobros.registrar_pago(paciente=self.paciente, monto=4, moneda='USD', metodo='EFECTIVO')
        revision = self.cliente.post(url, datos)
        self.assertContains(revision, 'Los cargos existentes cambiaron')
        self.assertContains(revision, 'Abonado')
        with self.en_tenant():
            self.assertEqual(Cargo.objects.count(), 1)
            self.assertFalse(Procedimiento.objects.exists())
        opcion = next(o for o in revision.context['servicios'] if o['servicio'].pk == pk)
        datos[f'revision_{pk}'] = opcion['revision']['firma']
        self.assertEqual(self.cliente.post(url, datos).status_code, 302)
        with self.en_tenant():
            anterior.refresh_from_db()
            self.assertIsNone(anterior.cita_id)
            self.assertEqual(anterior.pagado_usd, Decimal('4'))
            self.assertEqual(Cargo.objects.count(), 2)
            self.assertEqual(Cargo.objects.get(cita=cita).saldo_usd, Decimal('10'))

    def test_procedimiento_rechaza_vincular_cargo_de_otro_paciente(self):
        pk = self.general.pk
        cita = self.agendar([pk])
        url = reverse('clinica:procedimiento_nuevo', args=(self.paciente.pk,))
        with self.en_tenant():
            otro = Paciente.objects.create(nombres='Otro', apellidos='Paciente')
            ajeno = cobros.crear_cargo(paciente=otro, servicio=self.general, descripcion='', precio_usd=10)
            propio = cobros.crear_cargo(paciente=self.paciente, servicio=self.general, descripcion='', precio_usd=10)
        formulario = self.cliente.get(url, {'cita': cita.pk})
        self.assertNotContains(formulario, f'Vincular cargo #{ajeno.pk}')
        opcion = next(o for o in formulario.context['servicios'] if o['servicio'].pk == pk)
        datos = {'cita': cita.pk, 'servicios': [pk], 'version_cita': cita.actualizado_en.isoformat(),
                 f'revision_{pk}': opcion['revision']['firma'], f'cargo_{pk}': ajeno.pk}
        self.assertContains(self.cliente.post(url, datos), 'Elige un cargo existente')
        with self.en_tenant():
            self.assertFalse(Procedimiento.objects.exists())
        datos[f'cargo_{pk}'] = propio.pk
        self.assertEqual(self.cliente.post(url, datos).status_code, 302)
        with self.en_tenant():
            self.assertEqual(Cargo.objects.get(cita=cita).pk, propio.pk)

    def test_cargos_y_pagos_previos_y_formulario_desactualizado(self):
        cita = self.agendar([self.general.pk])
        version = cita.actualizado_en.isoformat()
        self.assertEqual(self.editar(cita, [self.propio.pk]).status_code, 302)
        r = self.editar(cita, [self.general.pk], version_cita=version)
        self.assertContains(r, 'La cita cambió')
        with self.en_tenant():
            cargo = cobros.crear_cargo(paciente=self.paciente, cita=cita, descripcion='Cargo previo', precio_usd=50)
            cobros.registrar_pago(paciente=self.paciente, monto=15, moneda='USD', metodo='EFECTIVO')
        self.assertContains(self.editar(cita, [self.general.pk]), 'La cita tiene atención o cargos')
        with self.en_tenant():
            agenda.atender(cita, self.perfil)
            self.assertEqual(Cargo.objects.get(cita=cita).pk, cargo.pk)
            self.assertEqual(Cargo.objects.get(cita=cita).pagado_usd, Decimal('15'))


class ConcurrenciaServiciosTest(TransactionTestCase):
    def test_dos_atenciones_concurrentes_solo_generan_un_cargo(self):
        if connection.vendor != 'postgresql':
            self.skipTest('Requiere bloqueo de filas de PostgreSQL')
        tenant, usuario = crear_consultorio()
        perfil = Membresia.objects.get(usuario=usuario).perfil
        with usando_tenant(tenant):
            paciente = Paciente.objects.create(nombres='Prueba', apellidos='Concurrente')
            servicio = Servicio.objects.create(nombre='Servicio', precio_usd=12)
            cita, _ = agenda.guardar_cita(Cita(paciente=paciente, profesional=perfil, fecha=timezone.localdate()),
                                          servicios=[servicio.pk])
        barrera = Barrier(2)

        def atender():
            try:
                with usando_tenant(tenant):
                    barrera.wait(timeout=5)
                    return agenda.atender(cita, perfil).pk
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = [pool.submit(atender) for _ in range(2)]
            self.assertEqual(a.result(timeout=15), b.result(timeout=15))
        with usando_tenant(tenant):
            self.assertEqual(Cargo.objects.filter(cita=cita).count(), 1)
