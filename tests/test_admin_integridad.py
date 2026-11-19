"""Permisos efectivos de Admin sobre movimientos, citas y sus dependencias."""
from datetime import timedelta

from django.contrib import admin
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.agenda.models import Cita, TipoCita
from apps.clinica.models import Consulta, PlantillaHistoria, Procedimiento
from apps.cobros import servicios as cobros
from apps.cobros.models import Cargo, CobroRapidoCita, Pago, PagoAplicado, Servicio
from apps.core.permisos import Rol
from apps.equipo.models import Membresia
from apps.equipo.servicios import crear_perfil
from apps.pacientes.models import Paciente
from apps.plataforma.models import Suscripcion
from apps.tasas import servicios as tasas
from apps.usuarios.models import Usuario

from .base import BaseTest, crear_consultorio


def url_admin(obj, accion='change'):
    meta = obj._meta
    args = [] if accion in ('add', 'changelist') else [obj.pk]
    return reverse(f'admin:{meta.app_label}_{meta.model_name}_{accion}', args=args)


class AdminIntegridadTest(BaseTest):
    def setUp(self):
        super().setUp()
        self.otro, _ = crear_consultorio(slug='otro')
        self.soporte = Usuario.objects.create_superuser('soporte-prueba', 'sintetica')
        self.admin = Client(HTTP_HOST='localhost')
        self.admin.force_login(self.soporte)
        self.entrar_soporte(self.tenant)
        self.hoy = timezone.localdate()
        self.perfil = Membresia.objects.get(usuario=self.titular).perfil
        with self.en_tenant():
            self.paciente = Paciente.objects.create(nombres='Prueba', apellidos='Local')
            self.cita = Cita.objects.create(paciente=self.paciente, profesional=self.perfil,
                                           especialidad=self.perfil.especialidad, fecha=self.hoy)
            self.cargo = cobros.crear_cargo(paciente=self.paciente, cita=self.cita, precio_usd=20, descripcion='Local')
            self.pago = cobros.registrar_pago(paciente=self.paciente, monto=200, moneda='BS', metodo='EFECTIVO', tasa=40)
            self.aplicacion = self.pago.aplicaciones.get()
        with self.en_tenant(self.otro):
            self.ajeno = Paciente.objects.create(nombres='Prueba', apellidos='Ajena')
            self.otro_cargo = cobros.crear_cargo(paciente=self.ajeno, precio_usd=30, descripcion='Concepto reservado B')

    def entrar_soporte(self, tenant):
        resp = self.admin.post(reverse('plataforma:entrar', args=[tenant.pk]), {'motivo': 'Control sintético'})
        self.assertEqual(resp.status_code, 302)

    def asientos(self):
        with self.en_tenant():
            return [list(m.objects.order_by('pk').values()) for m in (Pago, Cargo, PagoAplicado, Cita)]

    def test_movimientos_inmutables_por_formulario_hooks_acciones_y_url_directa(self):
        antes = self.asientos()
        for obj, cambios in (
                (self.cargo, {'paciente': self.ajeno.pk, 'cita': '', 'precio_usd': 1, 'estado': 'ANULADO'}),
                (self.pago, {'tasa': 1, 'monto': 1, 'monto_usd': 200, 'anulado': 'on'}),
                (self.aplicacion, {'cargo': self.otro_cargo.pk, 'monto_usd': 99, 'pago': 9999})):
            with self.subTest(modelo=obj._meta.label):
                detalle = self.admin.get(url_admin(obj))
                self.assertEqual(detalle.status_code, 200)
                self.assertFalse(detalle.context['adminform'].form.fields)
                self.assertEqual(self.admin.post(url_admin(obj), cambios).status_code, 403)
                self.assertEqual(self.admin.post(url_admin(obj, 'add'), cambios).status_code, 403)
                self.assertEqual(self.admin.post(url_admin(obj, 'delete'), {'post': 'yes'}).status_code, 403)
                lista = self.admin.post(url_admin(obj, 'changelist'), {
                    'action': 'delete_selected', '_selected_action': obj.pk, 'post': 'yes'})
                self.assertEqual(lista.status_code, 200)
                ma = admin.site.get_model_admin(type(obj))
                request = detalle.wsgi_request
                with self.assertRaises(PermissionDenied):
                    ma.save_model(request, obj, None, True)
                with self.assertRaises(PermissionDenied):
                    ma.save_related(request, None, [], True)
                with self.assertRaises(PermissionDenied):
                    ma.delete_model(request, obj)
                with self.assertRaises(PermissionDenied):
                    ma.delete_queryset(request, type(obj).todos.filter(pk=obj.pk))
        self.assertEqual(self.asientos(), antes)

    def test_soporte_aislado_en_listas_detalle_historial_y_cambio_de_tenant(self):
        self.assertNotContains(self.admin.get(url_admin(Cargo, 'changelist')), 'Concepto reservado B')
        for accion in ('change', 'history', 'delete'):
            self.assertIn(self.admin.get(url_admin(self.otro_cargo, accion)).status_code, (302, 403, 404))
        self.entrar_soporte(self.otro)
        self.assertContains(self.admin.get(url_admin(Cargo, 'changelist')), 'Concepto reservado B')
        self.assertNotEqual(self.admin.get(url_admin(self.cargo)).status_code, 200)
        self.admin.post(reverse('plataforma:salir'))
        self.assertEqual(self.admin.get(url_admin(Cargo, 'changelist')).status_code, 403)

    def test_rol_de_consultorio_y_permisos_django_son_independientes(self):
        permiso = Permission.objects.get(codename='view_pago', content_type__app_label='cobros')
        self.titular.is_staff = True
        self.titular.save(update_fields=['is_staff'])
        self.titular.user_permissions.add(permiso)
        self.assertEqual(self.cliente.get('/cobros/caja/').status_code, 200)
        self.assertEqual(self.cliente.get(url_admin(self.pago)).status_code, 302)
        lector = Usuario.objects.create_user('lector-plataforma', 'sintetica', is_staff=True)
        miembro = Membresia.objects.create(usuario=lector, tenant=self.tenant, rol=Rol.ASISTENTE)
        cliente = Client(HTTP_HOST='localhost')
        cliente.force_login(lector)
        self.assertEqual(cliente.get(url_admin(self.pago)).status_code, 403)
        lector.user_permissions.add(permiso)
        self.assertContains(cliente.get(url_admin(self.pago)), 'Abrir Cuenta')
        self.assertEqual(cliente.post(url_admin(self.pago), {'monto': 99}).status_code, 403)
        miembro.rol = Rol.MEDICO
        miembro.save()
        self.assertEqual(cliente.get(url_admin(self.pago)).status_code, 403)
        perfil = crear_perfil(miembro, self.perfil.especialidad)
        lector.user_permissions.add(Permission.objects.get(codename='view_cita', content_type__app_label='agenda'))
        with self.en_tenant():
            propia = Cita.objects.create(paciente=self.paciente, profesional=perfil,
                                         especialidad=perfil.especialidad, fecha=self.hoy)
        self.assertEqual(cliente.get(url_admin(propia)).status_code, 200)
        self.assertNotEqual(cliente.get(url_admin(self.cita)).status_code, 200)

    def test_catalogo_editable_valida_relaciones_en_servidor(self):
        with self.en_tenant():
            tipo = TipoCita.objects.create(nombre='Tipo A')
            servicio = Servicio.objects.create(nombre='Servicio A', precio_usd=9)
        with self.en_tenant(self.otro):
            ajeno = Servicio.objects.create(nombre='Servicio reservado B', precio_usd=17)
        url = url_admin(tipo)
        respuesta = self.admin.get(url)
        self.assertNotContains(respuesta, 'Servicio reservado B')
        datos = {'nombre': 'Tipo A actualizado', 'duracion_min': 30, 'color': '#005588',
                 'tipo_consulta': 'PRIMERA', 'activo': 'on', 'servicio': ajeno.pk}
        form = self.admin.post(url, datos).context['adminform'].form
        self.assertIn('servicio', form.errors)
        tipo.refresh_from_db()
        self.assertIsNone(tipo.servicio_id)
        self.assertEqual(self.admin.post(url, {**datos, 'servicio': servicio.pk}).status_code, 302)
        tipo.refresh_from_db()
        self.assertEqual((tipo.tenant_id, tipo.servicio_id), (self.tenant.pk, servicio.pk))

    def test_plataforma_vincula_cuenta_compartida_sin_trasladar_una_cuenta_local(self):
        compartida = Usuario.objects.create_user('cuenta-compartida', 'sintetica', is_staff=True)
        url = url_admin(Membresia, 'add')
        ajena = Membresia.objects.get(tenant=self.otro, rol=Rol.TITULAR).usuario
        datos = {'usuario': ajena.pk, 'rol': Rol.ADMIN, 'activa': 'on'}
        self.assertIn('usuario', self.admin.post(url, datos).context['adminform'].form.errors)
        for tenant in (self.tenant, self.otro):
            self.entrar_soporte(tenant)
            self.assertEqual(self.admin.post(url, {**datos, 'usuario': compartida.pk}).status_code, 302)
            vinculo = Membresia.objects.get(usuario=compartida, tenant=tenant)
            self.assertTrue(vinculo.activa)
            self.assertEqual(vinculo.rol, Rol.ADMIN)
            self.assertEqual(self.admin.post(url_admin(vinculo), {'usuario': ajena.pk}).status_code, 403)
        self.assertEqual(Membresia.objects.filter(usuario=compartida).count(), 2)

    def test_cita_editable_en_agenda_formulario_antiguo_y_atencion(self):
        with self.en_tenant():
            cita = Cita.objects.create(paciente=self.paciente, profesional=self.perfil,
                                       especialidad=self.perfil.especialidad, fecha=self.hoy)
        url = reverse('agenda:cita_editar', args=[cita.pk])
        self.assertContains(self.admin.get(url_admin(cita)), url)
        datos = {'paciente': self.paciente.pk, 'profesional': self.perfil.pk, 'fecha': self.hoy, 'motivo': 'Actualizado',
                 'version_cita': cita.actualizado_en.isoformat()}
        self.assertEqual(self.admin.post(url, datos).status_code, 302)
        cita.refresh_from_db()
        self.assertEqual(cita.motivo, 'Actualizado')
        datos.update(version_cita=cita.actualizado_en.isoformat(), fecha=self.hoy + timedelta(days=1))
        with self.en_tenant():
            cobros.crear_cargo(paciente=self.paciente, cita=cita, precio_usd=10, descripcion='Cita con cargo')
        self.assertContains(self.admin.get(url_admin(cita)), 'Revisar atención en Agenda')
        self.assertEqual(self.admin.post(url_admin(cita), datos).status_code, 403)
        self.assertContains(self.admin.post(url, datos), 'La cita tiene atención o cargos registrados')
        cita.refresh_from_db()
        self.assertEqual(cita.fecha, self.hoy)
        self.cliente.post(reverse('agenda:atender', args=[cita.pk]))
        cita.refresh_from_db()
        self.assertEqual(cita.estado, Cita.Estado.ATENDIDA)
        self.assertEqual(self.admin.post(url_admin(cita), datos).status_code, 403)
        self.assertEqual(self.admin.post(url, datos).status_code, 302)
        cita.refresh_from_db()
        self.assertEqual(cita.fecha, self.hoy)

    def test_reversion_autorizada_en_cuenta_y_cifras(self):
        enlace = reverse('cobros:cuenta', args=[self.paciente.pk])
        self.assertContains(self.admin.get(url_admin(self.pago)), enlace)
        self.assertEqual(self.admin.get(enlace).context['saldo'], 15)
        url = reverse('cobros:pago_anular', args=[self.pago.pk])
        self.assertEqual(self.admin.post(url, {'motivo': 'Corrección autorizada sintética'}).status_code, 302)
        self.assertEqual(self.admin.get(enlace).context['saldo'], 20)
        self.assertEqual(self.admin.get('/cobros/por-cobrar/').context['total'], 20)
        self.assertEqual(self.admin.get('/cobros/caja/').context['total_usd'], 0)
        self.pago.refresh_from_db()
        self.assertTrue(self.pago.anulado)
        self.assertEqual((self.pago.monto, self.pago.tasa, self.pago.monto_usd), (200, 40, 5))

    def test_tasa_de_referencia_corregible_sin_reescribir_asientos(self):
        with self.en_tenant():
            referencia = tasas.registrar_del_tenant(self.tenant, 40, self.titular)
        antes = self.asientos()
        url = url_admin(referencia)
        self.assertEqual(self.admin.post(url, {'bs_por_usd': '50', 'registrada_por': self.titular.pk}).status_code, 302)
        referencia.refresh_from_db()
        self.assertEqual((referencia.bs_por_usd, referencia.registrada_por_id), (50, self.soporte.pk))
        self.assertIn('bs_por_usd', self.admin.post(url, {'bs_por_usd': '-1'}).context['adminform'].form.errors)
        self.assertEqual(self.asientos(), antes)

    def test_inline_de_plataforma_preserva_la_renovacion(self):
        renovacion = Suscripcion.objects.create(tenant=self.tenant, desde=self.hoy, hasta=self.hoy, monto_usd=30)
        url = url_admin(self.tenant)
        respuesta = self.admin.get(url)
        self.assertEqual(respuesta.status_code, 200)
        inline = respuesta.context['inline_admin_formsets'][0]
        self.assertFalse(inline.has_add_permission or inline.has_change_permission or inline.has_delete_permission)
        datos = {k: v for k, v in respuesta.context['adminform'].form.initial.items() if v is not None}
        datos['especialidades'] = list(self.tenant.especialidades.values_list('pk', flat=True))
        prefijo = inline.formset.prefix
        datos.update({f'{prefijo}-TOTAL_FORMS': 1, f'{prefijo}-INITIAL_FORMS': 1, f'{prefijo}-0-id': renovacion.pk,
                      f'{prefijo}-0-monto_usd': '1', f'{prefijo}-0-DELETE': 'on'})
        self.assertEqual(self.admin.post(url, datos).status_code, 302)
        renovacion.refresh_from_db()
        self.assertEqual(renovacion.monto_usd, 30)

    def test_sin_rutas_alternas_para_atenciones_y_plantillas(self):
        for modelo in (Consulta, Procedimiento, CobroRapidoCita):
            self.assertFalse(admin.site.is_registered(modelo))
        with self.en_tenant():
            plantilla = PlantillaHistoria.objects.filter(profesional=None).first()
        antes = list(plantilla.items.model.todos.filter(plantilla=plantilla).values())
        self.assertEqual(self.admin.post(url_admin(plantilla), {'items-TOTAL_FORMS': 0}).status_code, 403)
        self.assertEqual(list(plantilla.items.model.todos.filter(plantilla=plantilla).values()), antes)
