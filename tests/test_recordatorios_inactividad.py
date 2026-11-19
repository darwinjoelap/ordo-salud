from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta
from threading import Barrier
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from dateutil.relativedelta import relativedelta
from django.db import connection, connections
from django.test import TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from apps.agenda import inactividad, selectors
from apps.agenda.models import Cita, RecordatorioInactividad
from apps.clinica.models import Consulta, Procedimiento
from apps.core.models import Auditoria
from apps.core.permisos import Rol
from apps.core.tenancy import usando_tenant
from apps.equipo import servicios as equipo
from apps.equipo.models import Membresia
from apps.pacientes.models import Paciente, Representante

from .base import BaseTest, crear_consultorio


def consulta(paciente, perfil, fecha, estado=Consulta.Estado.CERRADA):
    return Consulta.objects.create(
        paciente=paciente, profesional=perfil, especialidad=perfil.especialidad,
        fecha_hora=timezone.make_aware(datetime.combine(fecha, time(12))), estado=estado,
    )


def ruta(paciente, ultima, meses=12):
    return reverse('agenda:recordatorio_inactividad', args=(paciente.pk, ultima.isoformat(), meses))


class RecordatorioInactividadTest(BaseTest):
    def setUp(self):
        super().setUp()
        self.membresia = Membresia.objects.get(usuario=self.titular)
        self.perfil = self.membresia.perfil
        self.hoy = timezone.localdate()
        self.ultima = self.hoy - relativedelta(months=13)

    def paciente(self, nombre, ultima=None, estado=Consulta.Estado.CERRADA, **datos):
        with self.en_tenant():
            paciente = Paciente.objects.create(nombres=nombre, apellidos='Prueba', **datos)
            if ultima:
                consulta(paciente, self.perfil, ultima, estado)
            return paciente

    def configurar(self, meses):
        config = self.tenant.configuracion
        config.recordatorio_sin_consulta_meses = meses
        config.save(update_fields=['recordatorio_sin_consulta_meses'])

    def ids(self, fecha=None):
        with self.en_tenant():
            return set(selectors.sugerencias_inactividad(
                fecha=fecha or self.hoy, membresia=self.membresia).values_list('pk', flat=True))

    def test_umbral_acumulado_fin_de_mes_y_desactivacion(self):
        fecha = date(2026, 2, 28)
        anterior = self.paciente('Anterior', date(2024, 12, 1))
        exacta = self.paciente('Exacta', date(2025, 2, 28))
        self.paciente('Reciente', date(2025, 3, 1))
        adicional = self.paciente('Dia 31', date(2025, 8, 31))
        self.assertEqual(self.ids(fecha), {anterior.pk, exacta.pk})
        self.configurar(6)
        self.assertIn(adicional.pk, self.ids(fecha))
        self.configurar(0)
        self.assertEqual(self.ids(fecha), set())

    def test_evidencia_clinica_y_citas(self):
        self.paciente('Sin consulta')
        self.paciente('Borrador', self.ultima, Consulta.Estado.BORRADOR)
        self.paciente('Anulada', self.ultima, Consulta.Estado.ANULADA)
        con_cita = self.paciente('Con cita', self.ultima)
        cancelada = self.paciente('Cancelada', self.ultima)
        ausencia = self.paciente('Ausencia', self.ultima)
        procedimiento = self.paciente('Procedimiento')
        anulado = self.paciente('Procedimiento anulado')
        sin_evidencia = self.paciente('Cita atendida sin respaldo')
        with self.en_tenant():
            for paciente, estado, fecha in [
                (con_cita, Cita.Estado.TENTATIVA, self.hoy + timedelta(days=2)),
                (cancelada, Cita.Estado.CANCELADA, self.ultima),
                (ausencia, Cita.Estado.NO_ASISTIO, self.ultima),
                (sin_evidencia, Cita.Estado.ATENDIDA, self.ultima),
            ]:
                Cita.objects.create(paciente=paciente, profesional=self.perfil, especialidad=self.perfil.especialidad,
                                    fecha=fecha, estado=estado,
                                    consulta=paciente.consultas.first() if fecha == self.ultima else None)
            for paciente, es_anulado in [(procedimiento, False), (anulado, True)]:
                Procedimiento.objects.create(paciente=paciente, profesional=self.perfil, fecha=self.ultima,
                                              descripcion='Procedimiento sintético', anulado=es_anulado)
        self.assertEqual(self.ids(), {procedimiento.pk})

    def test_ignorar_oculta_el_episodio_y_reaparece_tras_nueva_asistencia(self):
        paciente = self.paciente('Ignorado', self.ultima)
        url = ruta(paciente, self.ultima)
        with self.en_tenant():
            consulta(paciente, self.perfil, self.ultima - timedelta(days=2))
        self.assertContains(self.cliente.get('/agenda/'), 'Recordatorios sugeridos')
        for _ in range(2):
            self.assertEqual(self.cliente.post(url, {'accion': 'IGNORADO'}).status_code, 302)
        self.assertNotContains(self.cliente.get('/agenda/'), 'Recordatorios sugeridos')
        self.configurar(6)
        self.assertNotIn(paciente.pk, self.ids())
        with self.en_tenant():
            decision = RecordatorioInactividad.objects.get(paciente=paciente)
            self.assertEqual(decision.resuelto_por, self.titular)
            self.assertEqual(decision.estado, 'IGNORADO')
            self.assertEqual(decision.meses, 12)
            self.assertEqual(Auditoria.objects.filter(objeto_tipo='agenda.RecordatorioInactividad').count(), 1)
            anterior = paciente.consultas.latest('fecha_hora')
            anterior.estado = Consulta.Estado.ANULADA
            anterior.save(update_fields=['estado'])
        self.assertNotIn(paciente.pk, self.ids())
        with self.en_tenant():
            consulta(paciente, self.perfil, self.hoy)
        self.assertNotIn(paciente.pk, self.ids())
        self.assertIn(paciente.pk, self.ids(self.hoy + relativedelta(months=6)))

    def test_editar_abrir_y_confirmar_sin_persistir_mensaje(self):
        paciente = self.paciente('Autorizado', self.ultima, telefono='04141234567',
                                  whatsapp_seguimiento='584141234567')
        url = ruta(paciente, self.ultima)
        inicial = self.cliente.get(url)
        self.assertNotContains(inicial, 'data-whatsapp-agenda')
        self.assertIn('no-store', inicial.headers['Cache-Control'])
        self.cliente.post(url, {'accion': 'ENVIADO'})
        texto = 'Hola, ¿podemos conversar? & +'
        preparado = self.cliente.post(url, {'accion': 'preparar', 'mensaje': texto})
        self.assertContains(preparado, 'data-whatsapp-agenda')
        self.assertNotContains(preparado, 'https://wa.me/')
        self.assertNotContains(preparado, 'intent://')
        with self.en_tenant():
            self.assertFalse(RecordatorioInactividad.objects.exists())
        intento = {'accion': 'web', 'mensaje': texto, 'token_contacto': preparado.context['token_contacto']}
        copia = self.cliente.post(url, {**intento, 'accion': 'copiar'})
        self.assertEqual(copia.json(), {'mensaje': texto})
        with self.en_tenant():
            self.assertFalse(RecordatorioInactividad.objects.exists())
        for _ in range(2):
            r = self.cliente.post(url, intento)
            self.assertEqual(parse_qs(urlparse(r.json()['destino']).query)['text'], [texto])
        self.assertContains(self.cliente.get('/agenda/'), 'Intento registrado')
        self.assertContains(self.cliente.get(url), 'Confirmar que envié el mensaje')
        self.cliente.post(url, {'accion': 'ENVIADO'})
        self.assertNotContains(self.cliente.get('/agenda/'), 'Recordatorios sugeridos')
        with self.en_tenant():
            decision = RecordatorioInactividad.objects.get()
            self.assertEqual((decision.estado, decision.canal, decision.resuelto_por), ('ENVIADO', 'WHATSAPP', self.titular))
            eventos = list(Auditoria.objects.filter(objeto_tipo='agenda.RecordatorioInactividad'))
            self.assertEqual(len(eventos), 2)
            self.assertTrue(all(texto not in evento.detalle for evento in eventos))
        self.assertFalse(RecordatorioInactividad.objects.exists())  # Sin tenant activo.

    def test_menor_solo_representante_autorizado_y_revocacion(self):
        paciente = self.paciente('Menor', self.ultima, fecha_nacimiento=self.hoy - relativedelta(years=5),
                                  telefono='04141234567', whatsapp_seguimiento='584141234567')
        url = ruta(paciente, self.ultima)
        envio = {'accion': 'preparar', 'mensaje': 'Hola'}
        self.assertNotContains(self.cliente.post(url, envio), 'data-whatsapp-agenda')
        with self.en_tenant():
            rep = Representante.objects.create(paciente=paciente, nombre='Representante sintético',
                                               telefono='04241234567', es_principal=True)
        self.assertNotContains(self.cliente.post(url, envio), 'data-whatsapp-agenda')
        editar = reverse('pacientes:representante', args=(paciente.pk, rep.pk))
        datos = {'nombre': rep.nombre, 'parentesco': rep.parentesco, 'tipo_documento': rep.tipo_documento,
                 'telefono': rep.telefono, 'es_principal': 'on', 'permiso_whatsapp': 'SI'}
        self.assertEqual(self.cliente.post(editar, datos).status_code, 302)
        preparado = self.cliente.post(url, envio)
        intento = {**envio, 'accion': 'web', 'token_contacto': preparado.context['token_contacto']}
        self.assertNotContains(preparado, 'https://wa.me/')
        self.assertEqual(self.cliente.post(url, {**intento, 'accion': 'validar'}).status_code, 204)
        datos['permiso_whatsapp'] = 'NO'
        self.assertEqual(self.cliente.post(editar, datos).status_code, 302)
        for accion in ('web', 'business', 'copiar', 'validar'):
            r = self.cliente.post(url, {**intento, 'accion': accion})
            self.assertEqual(r.status_code, 409)
            self.assertNotIn('destino', r.json())
            self.assertNotIn('mensaje', r.json())
        self.assertNotContains(self.cliente.post(url, envio), 'data-whatsapp-agenda')
        datos['permiso_whatsapp'] = 'SI'
        self.assertEqual(self.cliente.post(editar, datos).status_code, 302)
        self.assertEqual(self.cliente.post(url, intento).status_code, 409)
        datos['permiso_whatsapp'] = 'NO'
        self.assertEqual(self.cliente.post(editar, datos).status_code, 302)
        datos.update(telefono='04247654321', permiso_whatsapp='SI')
        self.assertEqual(self.cliente.post(editar, datos).status_code, 302)
        self.assertEqual(self.cliente.post(url, intento).status_code, 409)
        preparado = self.cliente.post(url, envio)
        enviado = self.cliente.post(url, {**intento, 'token_contacto': preparado.context['token_contacto']})
        self.assertEqual(urlparse(enviado.json()['destino']).path, '/584247654321')

    def test_alcance_profesional_y_tenant(self):
        paciente = self.paciente('Fuera de alcance', self.ultima)
        url = ruta(paciente, self.ultima)
        otro, _ = crear_consultorio(slug='otro')
        cliente = self.entrar(otro, 'titular')
        self.assertEqual(cliente.get(url).status_code, 404)
        cliente.post(url, {'accion': 'IGNORADO'})
        medico, clave = equipo.agregar(self.tenant, self.membresia, 'medico', 'Luis', 'Paz', Rol.MEDICO,
                                        especialidad=self.perfil.especialidad)
        medico.usuario.debe_cambiar_clave = False
        medico.usuario.save()
        cliente = self.entrar(self.tenant, 'medico', clave)
        self.assertEqual(cliente.get(url).status_code, 404)
        cliente.post(url, {'accion': 'IGNORADO'})
        self.assertIn(paciente.pk, self.ids())


class ConcurrenciaRecordatorioTest(TransactionTestCase):
    def test_dos_descartes_simultaneos_registran_una_sola_decision(self):
        if connection.vendor != 'postgresql':
            self.skipTest('Requiere bloqueo de filas de PostgreSQL')
        tenant, usuario = crear_consultorio()
        membresia = Membresia.objects.get(usuario=usuario)
        ultima = timezone.localdate() - relativedelta(months=13)
        with usando_tenant(tenant):
            paciente = Paciente.objects.create(nombres='Evento', apellidos='Concurrente')
            consulta(paciente, membresia.perfil, ultima)
        barrera = Barrier(2)

        def ignorar():
            try:
                with usando_tenant(tenant):
                    barrera.wait(timeout=5)
                    request = SimpleNamespace(tenant=tenant, user=usuario, membresia=membresia, META={})
                    return inactividad.registrar_decision(request=request, paciente_id=paciente.pk, ultima=ultima,
                                                          meses=12, estado=inactividad.Estado.IGNORADO)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            resultados = [pool.submit(ignorar) for _ in range(2)]
            self.assertEqual([f.result(timeout=15) for f in resultados], [True, True])
        with usando_tenant(tenant):
            self.assertEqual(RecordatorioInactividad.objects.count(), 1)
            self.assertEqual(Auditoria.objects.filter(objeto_tipo='agenda.RecordatorioInactividad').count(), 1)
