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
from apps.cobros.models import Cargo, Servicio
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
            self.tipo = TipoCita.objects.create(nombre='Control', servicio=self.propio, duracion_min=45)

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
