from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.clinica import consultas
from apps.clinica.models import Consulta, SeccionClinica, SignosVitales
from apps.clinica.models.consulta import EvaluacionPreoperatoria
from apps.configuracion.models import ConfiguracionTenant
from apps.core.permisos import Rol, puede_usar_preoperatorio
from apps.equipo import servicios as equipo
from apps.equipo.models import Membresia
from apps.pacientes.models import AntecedenteBase, Paciente
from apps.plataforma.models import Especialidad

from .base import BaseTest, CLAVE, crear_consultorio


class EvaluacionPreoperatoriaTest(BaseTest):
    def setUp(self):
        super().setUp()
        self.especialidad = self.tenant.especialidades.get()
        with self.en_tenant():
            self.paciente = Paciente.objects.create(nombres='Paciente', apellidos='Sintético')
            self.secciones = dict(SeccionClinica.objects.visibles().values_list('codigo', 'pk'))
        self.ficha = reverse('pacientes:detalle', args=[self.paciente.pk])
        self.nueva = reverse('clinica:preoperatorio_nuevo', args=[self.paciente.pk])

    def configurar(self, *, activo=True, especialidades=None):
        config = self.tenant.configuracion
        config.preoperatorio_activo = activo
        config.save(update_fields=['preoperatorio_activo'])
        config.preoperatorio_especialidades.set([self.especialidad] if especialidades is None else especialidades)

    def inicio(self):
        r = self.cliente.get(self.nueva)
        self.assertEqual(r.status_code, 200)
        return {'completa': '1', 'independiente': '1', 'intento': r.context['intento']}

    def campo(self, seccion, clave):
        return f's{self.secciones["nucleo." + seccion]}-{clave}'

    def cirugia(self):
        return {'cirugia-procedimiento': 'Procedimiento sintético', 'cirugia-motivo': 'Motivo quirúrgico',
                'cirugia-caracter': 'ELECTIVA', 'cirugia-fecha_prevista': '2027-01-12',
                'cirugia-cirujano': 'Profesional sintético', 'cirugia-centro': 'Centro sintético',
                'cirugia-anestesia': 'Regional'}

    def segundo_usuario(self, rol, especialidad=None):
        usuario = get_user_model().objects.create_user(
            username='segundo', password=CLAVE, tenant_cuenta=self.tenant, debe_cambiar_clave=False)
        miembro = Membresia.objects.create(usuario=usuario, tenant=self.tenant, rol=rol)
        if especialidad:
            equipo.crear_perfil(miembro, especialidad)
        return self.entrar(self.tenant, usuario.username)

    def test_configuracion_y_acceso_por_especialidad(self):
        self.assertFalse(ConfiguracionTenant.objects.get(tenant=self.tenant).preoperatorio_activo)
        self.assertNotContains(self.cliente.get(self.ficha), self.nueva)
        self.assertEqual(self.cliente.get(self.nueva).status_code, 403)
        self.configurar(especialidades=[])
        self.assertEqual(self.cliente.get(self.nueva).status_code, 403)
        otra = Especialidad.objects.exclude(pk=self.especialidad.pk).first()
        datos = {
            'tab': 'preoperatorio', 'nombre_mostrar': 'Consultorio sintético', 'color_primario': '#145F8F',
            'visibilidad_historia': 'COMPARTIDA', 'observaciones_visibles': 'TODOS', 'horas_edicion_consulta': 24,
            'formula_sc': 'MOSTELLER', 'duracion_cita_min': 30, 'recordatorio_sin_consulta_meses': 12,
            'tasa_referencia': 'USD', 'preoperatorio_activo': 'on',
        }
        url = reverse('configuracion:editar')
        r = self.cliente.post(url, {**datos, 'preoperatorio_especialidades': [otra.pk]})
        self.assertIn('preoperatorio_especialidades', r.context['form'].errors)
        r = self.cliente.post(url, {**datos, 'preoperatorio_especialidades': [self.especialidad.pk]})
        self.assertRedirects(r, url + '?tab=preoperatorio')
        self.assertContains(self.cliente.get(self.ficha), self.nueva)
        self.inicio()
        self.tenant.especialidades.add(otra)
        no_autorizado = self.segundo_usuario(Rol.MEDICO, otra)
        self.assertNotContains(no_autorizado.get(self.ficha), self.nueva)
        self.assertEqual(no_autorizado.get(self.nueva).status_code, 403)
        self.assertEqual(no_autorizado.post(self.nueva, {'completa': '1'}).status_code, 403)

    def test_asistente_no_puede_iniciar(self):
        self.configurar()
        asistente = self.segundo_usuario(Rol.ASISTENTE)
        self.assertNotContains(asistente.get(self.ficha), self.nueva)
        self.assertEqual(asistente.get(self.nueva).status_code, 403)

    def test_guardado_parcial_recuperacion_reintento_y_multiples(self):
        self.configurar()
        with self.en_tenant():
            AntecedenteBase.objects.create(paciente=self.paciente, alergias='Alergia sintética')
        datos = self.inicio()
        with self.en_tenant():
            self.assertFalse(Consulta.objects.exists())
        r = self.cliente.post(self.nueva, {**datos, 'cirugia-procedimiento': 'Primer procedimiento'})
        self.assertEqual(r.status_code, 302)
        repetida = self.cliente.post(self.nueva, {**datos, 'cirugia-procedimiento': 'Intento repetido'})
        self.assertEqual(repetida.url, r.url)
        formulario = self.cliente.get(r.url)
        self.assertContains(formulario, 'Primer procedimiento')
        self.assertContains(formulario, 'Alergia sintética')
        self.assertContains(self.cliente.get(self.ficha), r.url)
        with self.en_tenant():
            primera = EvaluacionPreoperatoria.objects.get()
            self.assertEqual(primera.procedimiento, 'Primer procedimiento')
            self.assertEqual(primera.consulta.estado, Consulta.Estado.BORRADOR)
            self.assertEqual(AntecedenteBase.objects.get().alergias, 'Alergia sintética')
        segunda = self.cliente.post(self.nueva, {**self.inicio(), 'cirugia-procedimiento': 'Segundo procedimiento'})
        self.assertEqual(segunda.status_code, 302)
        self.assertNotEqual(segunda.url, r.url)
        with self.en_tenant():
            self.assertEqual(EvaluacionPreoperatoria.objects.count(), 2)
            self.assertEqual(Consulta.objects.filter(paciente=self.paciente).count(), 2)

    def test_datos_quirurgicos_invalidos_no_crean_consulta(self):
        self.configurar()
        datos = {**self.inicio(), 'cirugia-caracter': 'INVALIDO', 'cirugia-fecha_prevista': '2027-02-31'}
        r = self.cliente.post(self.nueva, datos)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(set(r.context['form_cirugia'].errors), {'caracter', 'fecha_prevista'})
        with self.en_tenant():
            self.assertFalse(Consulta.objects.exists())

    def test_cierre_y_antecedentes_historicos(self):
        self.configurar()
        with self.en_tenant():
            AntecedenteBase.objects.create(paciente=self.paciente, alergias='Alergia al cierre')
        r = self.cliente.post(self.nueva, {**self.inicio(), 'accion': 'cerrar'})
        self.assertEqual(r.status_code, 302)
        with self.en_tenant():
            evaluacion = EvaluacionPreoperatoria.objects.get()
            self.assertTrue(evaluacion.consulta.editable)
        datos = {**self.cirugia(), 'accion': 'cerrar',
                 self.campo('motivo', 'motivo'): 'Valoración quirúrgica',
                 self.campo('examen_fisico', 'general'): 'Hallazgo sintético',
                 self.campo('signos_vitales', 'spo2'): '97'}
        cerrada = self.cliente.post(r.url, datos)
        self.assertRedirects(cerrada, reverse('clinica:consulta', args=[evaluacion.consulta_id]))
        with self.en_tenant():
            evaluacion.refresh_from_db()
            self.assertEqual(evaluacion.fecha_prevista, date(2027, 1, 12))
            self.assertEqual(SignosVitales.objects.get(consulta=evaluacion.consulta).spo2, 97)
            AntecedenteBase.objects.filter(paciente=self.paciente).update(alergias='Alergia posterior')
        self.cliente.post(r.url, {'cirugia-procedimiento': 'Sobrescribir'})
        self.configurar(activo=False)
        detalle = self.cliente.get(cerrada.url)
        self.assertContains(detalle, 'Procedimiento sintético')
        self.assertContains(detalle, 'Hallazgo sintético')
        self.assertContains(detalle, 'Alergia al cierre')
        self.assertNotContains(detalle, 'Alergia posterior')
        self.assertRedirects(self.cliente.post(r.url, datos), cerrada.url)

    def test_cierre_automatico_exige_cirugia(self):
        self.configurar()
        datos = {**self.inicio(), self.campo('motivo', 'motivo'): 'Valoración quirúrgica'}
        r = self.cliente.post(self.nueva, datos)
        self.assertEqual(r.status_code, 302)
        with self.en_tenant():
            Consulta.objects.update(fecha_hora=timezone.now() - timedelta(days=3))
        self.assertEqual(consultas.cerrar_vencidas(), 0)
        self.assertEqual(self.cliente.post(r.url, self.cirugia()).status_code, 302)
        self.assertEqual(consultas.cerrar_vencidas(), 1)

    def test_aislamiento_y_autoria(self):
        self.configurar()
        r = self.cliente.post(self.nueva, {**self.inicio(), **self.cirugia()})
        self.assertEqual(r.status_code, 302)
        otro_tenant, _ = crear_consultorio(nombre='Segundo', slug='segundo-tenant', usuario='otro')
        config = otro_tenant.configuracion
        config.preoperatorio_activo = True
        config.save()
        config.preoperatorio_especialidades.set(otro_tenant.especialidades.all())
        ajeno = self.entrar(otro_tenant, 'otro')
        self.assertEqual(ajeno.get(self.nueva).status_code, 404)
        self.assertEqual(ajeno.post(r.url, {'cirugia-motivo': 'Intruso'}).status_code, 404)
        with self.en_tenant(otro_tenant):
            self.assertFalse(EvaluacionPreoperatoria.objects.exists())
        miembro = Membresia.objects.get(tenant=self.tenant, usuario=self.titular)
        self.assertFalse(puede_usar_preoperatorio(miembro))
        self.assertFalse(EvaluacionPreoperatoria.objects.exists())
        colega = self.segundo_usuario(Rol.TITULAR, self.especialidad)
        self.assertEqual(colega.post(r.url, {'cirugia-motivo': 'Otro autor'}).status_code, 302)
        with self.en_tenant():
            self.assertEqual(EvaluacionPreoperatoria.objects.get().motivo, 'Motivo quirúrgico')
        self.configurar(especialidades=[])
        self.assertNotContains(self.cliente.get(self.ficha), r.url)
        self.assertEqual(self.cliente.get(r.url).status_code, 403)
        self.assertEqual(self.cliente.post(r.url, self.cirugia()).status_code, 403)

    def test_borrador_se_recupera_al_restaurar_autorizacion(self):
        self.configurar()
        datos = {
            **self.cirugia(),
            self.campo('motivo', 'motivo'): 'Valoración de recuperación',
            self.campo('examen_fisico', 'general'): 'Hallazgo conservado',
            self.campo('signos_vitales', 'spo2'): '97',
        }
        respuesta = self.cliente.post(self.nueva, {**self.inicio(), **datos})
        self.assertEqual(respuesta.status_code, 302)
        ruta = respuesta.url

        for revocacion in ({'especialidades': []}, {'activo': False}):
            with self.subTest(**revocacion):
                self.configurar(**revocacion)
                self.assertNotContains(self.cliente.get(self.ficha), ruta)
                self.assertEqual(self.cliente.get(ruta).status_code, 403)
                self.assertEqual(self.cliente.post(ruta, {'cirugia-procedimiento': 'Cambio denegado'}).status_code, 403)

                self.configurar()
                self.assertContains(self.cliente.get(self.ficha), ruta)
                recuperado = self.cliente.get(ruta)
                for texto in ('Procedimiento sintético', 'Valoración de recuperación', 'Hallazgo conservado'):
                    self.assertContains(recuperado, texto)
                with self.en_tenant():
                    evaluacion = EvaluacionPreoperatoria.objects.get()
                    self.assertEqual(evaluacion.consulta.estado, Consulta.Estado.BORRADOR)
                    self.assertEqual(evaluacion.fecha_prevista, date(2027, 1, 12))
                    self.assertEqual(SignosVitales.objects.get(consulta=evaluacion.consulta).spo2, 97)

    def test_consulta_ordinaria_y_token_separados(self):
        self.configurar()
        ordinaria = reverse('clinica:consulta_nueva', args=[self.paciente.pk])
        inicio_preop = self.inicio()
        self.assertEqual(self.cliente.post(ordinaria, inicio_preop).status_code, 409)
        r = self.iniciar_independiente(self.paciente, {'completa': '1', **self.cirugia()})
        self.assertEqual(r.status_code, 302)
        with self.en_tenant():
            self.assertEqual(Consulta.objects.count(), 1)
            self.assertFalse(EvaluacionPreoperatoria.objects.exists())
        self.assertNotContains(self.cliente.get(r.url), 'Cirugía prevista')
        preoperatoria = self.cliente.post(self.nueva, {**inicio_preop, **self.cirugia()})
        self.assertEqual(preoperatoria.status_code, 302)
        ficha = self.cliente.get(self.ficha)
        self.assertContains(ficha, r.url)
        self.assertContains(ficha, preoperatoria.url)
