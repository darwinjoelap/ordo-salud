from concurrent.futures import ThreadPoolExecutor
from datetime import date
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections, connections
from django.test import TransactionTestCase, skipUnlessDBFeature
from django.urls import reverse
from PIL import Image, ImageDraw
from pypdf import PdfReader

from apps.clinica import consultas, preoperatorio
from apps.clinica.models import Adjunto, Consulta, SeccionClinica
from apps.clinica.models.consulta import InformePreoperatorio, ValoracionPreoperatoria
from apps.core.models import Auditoria
from apps.core.permisos import Rol
from apps.core.tenancy import usando_tenant
from apps.documentos.models import DocumentoEmitido
from apps.equipo import servicios as equipo
from apps.equipo.models import Membresia
from apps.pacientes.models import Paciente

from .base import BaseTest, CLAVE, crear_consultorio


class FlujoPreoperatorio:
    def configurar_evaluacion(self):
        config = self.tenant.configuracion
        config.preoperatorio_activo = True
        config.save(update_fields=['preoperatorio_activo'])
        config.preoperatorio_especialidades.set(self.tenant.especialidades.all())
        self.actor = Membresia.objects.get(usuario=self.titular, tenant=self.tenant)
        with usando_tenant(self.tenant):
            self.paciente = Paciente.objects.create(nombres='Paciente', apellidos='Sintético')
            self.motivo = SeccionClinica.objects.visibles().get(codigo='nucleo.motivo')
        inicio = reverse('clinica:preoperatorio_nuevo', args=[self.paciente.pk])
        formulario = self.cliente.get(inicio)
        self.assertEqual(formulario.status_code, 200)
        respuesta = self.cliente.post(inicio, {
            'completa': '1', 'independiente': '1', 'intento': formulario.context['intento'],
            'accion': 'valorar', 'cirugia-procedimiento': 'Procedimiento sintético',
            'cirugia-motivo': 'Motivo quirúrgico', 'cirugia-caracter': 'EMERGENCIA',
            f's{self.motivo.pk}-motivo': 'Valoración quirúrgica',
        })
        with usando_tenant(self.tenant):
            self.consulta = Consulta.objects.get(paciente=self.paciente)
        self.valorar = reverse('clinica:preoperatorio_valorar', args=[self.consulta.pk])
        self.editar = reverse('clinica:consulta_editar', args=[self.consulta.pk])
        self.detalle = reverse('clinica:consulta', args=[self.consulta.pk])
        self.emitir = reverse('clinica:preoperatorio_emitir', args=[self.consulta.pk])
        self.assertRedirects(respuesta, self.valorar)

    @staticmethod
    def valoracion(*, version=0, estudios=(), iniciales=0, **extras):
        datos = {
            'version': version, 'asa': 'II', 'asa_emergencia': 'on',
            'asa_justificacion': 'Justificación por el profesional', 'asa_observaciones': 'Observación ASA',
            'mets_estado': 'REGISTRADO', 'mets': '4,5', 'mets_metodo': 'Estimación clínica documentada',
            'mets_fecha': '2026-10-12', 'mets_observaciones': 'Observación funcional',
            'riesgos': 'Hallazgo sintético', 'recomendaciones': 'Recomendación documentada',
            'pendientes': 'Interconsulta pendiente', 'optimizacion': 'Condición pendiente',
            'equipo_quirurgico': 'Aviso al equipo', 'conclusion': 'Conclusión inicial del médico', 'validada': 'on',
            'estudios-TOTAL_FORMS': len(estudios) + 1, 'estudios-INITIAL_FORMS': iniciales,
        }
        for i, estudio in enumerate(estudios):
            for clave, valor in estudio.items():
                datos[f'estudios-{i}-{clave}'] = valor
        return {**datos, **extras}

    def cerrar(self):
        respuesta = self.cliente.post(self.editar, {
            'accion': 'cerrar', 'cirugia-procedimiento': 'Procedimiento sintético',
            'cirugia-motivo': 'Motivo quirúrgico', 'cirugia-caracter': 'EMERGENCIA',
        })
        self.assertRedirects(respuesta, self.detalle)

    def pdf_url(self, documento):
        return reverse('documentos:pdf', args=[documento.pk])


class EvaluacionPreoperatoriaEtapa2Test(FlujoPreoperatorio, BaseTest):
    def setUp(self):
        super().setUp()
        self.configurar_evaluacion()

    def colega(self):
        usuario = get_user_model().objects.create_user(
            username='colega', password=CLAVE, tenant_cuenta=self.tenant, debe_cambiar_clave=False)
        miembro = Membresia.objects.create(usuario=usuario, tenant=self.tenant, rol=Rol.MEDICO)
        perfil = equipo.crear_perfil(miembro, self.actor.perfil.especialidad)
        return self.entrar(self.tenant, usuario.username), perfil

    @staticmethod
    def archivo(paciente, nombre, consulta=None):
        return Adjunto.objects.create(
            paciente=paciente, consulta=consulta, nombre=nombre,
            archivo=SimpleUploadedFile('resultado.txt', b'Archivo sintetico', content_type='text/plain'),
            tipo_contenido='text/plain',
        )

    def test_estudios_reutilizan_adjuntos_y_documentan_estados_manuales(self):
        with self.en_tenant():
            archivo = self.archivo(self.paciente, 'Resultado existente')
        estudios = [
            {'tipo': 'LAB', 'fecha': '2026-10-11', 'resultado': 'Hallazgo de laboratorio', 'adjuntos': [archivo.pk]},
            {'tipo': 'ECG', 'resultado': 'Hallazgo de ECG'},
            {'tipo': 'RX', 'resultado': 'Hallazgo radiográfico'},
            {'tipo': 'OTRO', 'resultado': 'Otro hallazgo', 'observaciones': 'Observación del estudio'},
        ]
        self.assertRedirects(self.cliente.post(self.valorar, self.valoracion(estudios=estudios)), self.detalle)
        vista = self.cliente.get(self.detalle)
        for texto in ('Hallazgo de laboratorio', 'Hallazgo de ECG', 'Hallazgo radiográfico', 'Otro hallazgo',
                      'ASA IIE', '4.5 METS', 'Interconsulta pendiente', 'Condición pendiente', 'Conclusión inicial'):
            self.assertContains(vista, texto)
        ruta = reverse('clinica:preoperatorio_adjunto', args=[self.consulta.pk, archivo.pk])
        respuesta = self.cliente.get(ruta)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(b''.join(respuesta.streaming_content), b'Archivo sintetico')
        with self.en_tenant():
            valoracion = ValoracionPreoperatoria.objects.get()
            self.assertEqual(valoracion.creado_por, self.titular)
            self.assertEqual(valoracion.estudios.get(tipo='LAB').fecha, date(2026, 10, 11))
            self.assertEqual(valoracion.estudios.get(tipo='LAB').adjuntos.get(), archivo)
            self.assertEqual(Adjunto.objects.count(), 1)
            self.assertTrue(Auditoria.objects.filter(objeto_tipo='clinica.Adjunto', accion='VER').exists())

    def test_validacion_de_asa_mets_y_conclusion(self):
        r = self.cliente.post(self.valorar, self.valoracion(
            asa='', asa_emergencia='on', mets='', mets_metodo='', mets_fecha='', conclusion=''))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(set(r.context['form'].errors), {'asa_emergencia', 'mets', 'mets_metodo', 'mets_fecha',
                                                        'conclusion'})
        self.assertEqual(self.cliente.post(self.valorar, self.valoracion(asa_justificacion='')).status_code, 200)
        with self.en_tenant():
            self.assertFalse(ValoracionPreoperatoria.objects.exists())
        for i, (estado, etiqueta) in enumerate((('NO_EVALUADO', 'No evaluado'),
                                                ('INSUFICIENTES', 'Datos insuficientes'))):
            with self.en_tenant():
                anterior = ValoracionPreoperatoria.objects.first()
            datos = self.valoracion(version=anterior.pk if i else 0, mets_estado=estado,
                                    mets='', mets_fecha='', mets_metodo='')
            self.assertRedirects(self.cliente.post(self.valorar, datos), self.detalle)
            self.assertContains(self.cliente.get(self.detalle), etiqueta)

    def test_adjuntos_de_otro_paciente_tenant_o_consulta_privada(self):
        _, perfil = self.colega()
        config = self.tenant.configuracion
        config.visibilidad_historia = 'PRIVADA'
        config.save(update_fields=['visibilidad_historia'])
        with self.en_tenant():
            otro = Paciente.objects.create(nombres='Paciente', apellidos='Distinto')
            ajeno = self.archivo(otro, 'Ajeno por paciente')
            privada = consultas.abrir_consulta(paciente=self.paciente, profesional=perfil)
            restringido = self.archivo(self.paciente, 'Adjunto privado', consulta=privada)
        otro_tenant, _ = crear_consultorio(slug='otro', usuario='otro')
        with usando_tenant(otro_tenant):
            otro = Paciente.objects.create(nombres='Paciente', apellidos='Otro tenant')
            externo = self.archivo(otro, 'Ajeno por consultorio')
        for archivo in (ajeno, restringido, externo):
            with self.subTest(archivo=archivo.pk):
                estudios = [{'tipo': 'ECG', 'resultado': 'Hallazgo', 'adjuntos': [archivo.pk]}]
                r = self.cliente.post(self.valorar, self.valoracion(estudios=estudios))
                self.assertEqual(r.status_code, 200)
                self.assertIn('adjuntos', r.context['estudios'].forms[0].errors)
        with self.en_tenant():
            self.assertFalse(ValoracionPreoperatoria.objects.exists())

        config.visibilidad_historia = 'COMPARTIDA'
        config.save(update_fields=['visibilidad_historia'])
        estudios = [{'tipo': 'ECG', 'resultado': 'Hallazgo', 'adjuntos': [restringido.pk]}]
        self.assertRedirects(self.cliente.post(self.valorar, self.valoracion(estudios=estudios)), self.detalle)
        ruta = reverse('clinica:preoperatorio_adjunto', args=[self.consulta.pk, restringido.pk])
        respuesta = self.cliente.get(ruta)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(b''.join(respuesta.streaming_content), b'Archivo sintetico')
        config.visibilidad_historia = 'PRIVADA'
        config.save(update_fields=['visibilidad_historia'])
        self.assertNotContains(self.cliente.get(self.detalle), restringido.nombre)
        self.assertEqual(self.cliente.get(ruta).status_code, 404)
        with self.en_tenant():
            self.assertEqual(ValoracionPreoperatoria.objects.get().estudios.get().adjuntos.get(), restringido)

    def test_revocacion_y_emision_requieren_cierre_y_validacion(self):
        self.assertEqual(self.cliente.get(self.emitir).status_code, 405)
        self.assertRedirects(self.cliente.post(self.emitir), self.detalle)
        self.assertRedirects(self.cliente.post(self.valorar, self.valoracion(validada='')), self.detalle)
        r = self.cliente.post(self.editar, {'accion': 'cerrar', 'cirugia-procedimiento': 'Procedimiento sintético',
                                          'cirugia-motivo': 'Motivo', 'cirugia-caracter': 'EMERGENCIA'})
        self.assertRedirects(r, self.editar)
        config = self.tenant.configuracion
        config.preoperatorio_especialidades.clear()
        self.assertEqual(self.cliente.get(self.valorar).status_code, 403)
        self.assertEqual(self.cliente.post(self.emitir).status_code, 403)
        with self.en_tenant():
            self.assertTrue(Consulta.objects.get(pk=self.consulta.pk).editable)
            self.assertFalse(DocumentoEmitido.objects.exists())

    def test_pdf_inmutable_con_firma_y_revision_por_enmienda(self):
        colega, _ = self.colega()
        with self.en_tenant():
            perfil = self.actor.perfil
            imagen = Image.new('RGBA', (200, 80), (0, 0, 0, 0))
            ImageDraw.Draw(imagen).line([(20, 65), (55, 12), (74, 57), (117, 30), (149, 59), (183, 38)],
                                        fill=(20, 40, 160, 255), width=4)
            firma = BytesIO()
            imagen.save(firma, 'PNG')
            perfil.firma = SimpleUploadedFile('firma-sintetica.png', firma.getvalue(), content_type='image/png')
            perfil.save(update_fields=['firma'])
        estudios = [{'tipo': 'ECG', 'resultado': 'Trazado sintético'}]
        self.assertRedirects(self.cliente.post(self.valorar, self.valoracion(estudios=estudios)), self.detalle)
        self.cerrar()
        r = self.cliente.post(self.emitir)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.cliente.post(self.emitir).url, r.url)
        self.assertEqual(colega.post(self.emitir).status_code, 403)
        generico = reverse('documentos:emitir', args=[preoperatorio.CODIGO_INFORME])
        self.assertEqual(self.cliente.post(generico, {'consulta': self.consulta.pk}).status_code, 404)
        with self.en_tenant():
            original = InformePreoperatorio.objects.get()
            primera_valoracion = ValoracionPreoperatoria.objects.get()
            self.assertNotEqual(original.pdf_firmado, original.pdf_sin_firma)
            self.assertEqual(Auditoria.objects.filter(objeto_tipo='documentos.DocumentoEmitido', accion='CREAR').count(), 1)
        url = self.pdf_url(original.documento)
        firmado = self.cliente.get(url).content
        self.assertEqual(firmado, bytes(original.pdf_firmado))
        sin_firma = self.cliente.get(url, {'firma': '0'}).content
        self.assertEqual(sin_firma, bytes(original.pdf_sin_firma))
        self.assertTrue(any(pagina.images for pagina in PdfReader(BytesIO(firmado)).pages))
        self.assertFalse(any(pagina.images for pagina in PdfReader(BytesIO(sin_firma)).pages))
        config = self.tenant.configuracion
        config.medicos_ven_todos_pacientes = True
        config.nombre_mostrar = 'Nombre posterior'
        config.save(update_fields=['medicos_ven_todos_pacientes', 'nombre_mostrar'])
        self.assertEqual(colega.get(url).content, bytes(original.pdf_sin_firma))
        texto = '\n'.join(p.extract_text() for p in PdfReader(BytesIO(firmado)).pages)
        for frase in ('Procedimiento sintético', 'Trazado sintético', 'ASA IIE', 'Conclusión inicial del médico',
                      'Condición pendiente'):
            self.assertIn(frase, texto)

        datos = self.valoracion(version=primera_valoracion.pk, estudios=estudios, iniciales=1,
                                conclusion='Conclusión corregida', motivo_enmienda='Aclaración documentada')
        self.assertRedirects(self.cliente.post(self.valorar, datos), self.detalle)
        self.assertRedirects(self.cliente.post(self.valorar, datos), self.detalle)  # Reintento de enmienda.
        revision = self.cliente.post(self.emitir)
        self.assertNotEqual(revision.url, r.url)
        self.assertEqual(self.cliente.get(url).content, firmado)
        with self.en_tenant():
            nueva = InformePreoperatorio.objects.get(revision=2)
            self.assertEqual(nueva.documento.datos['reemplaza'], original.documento.numero)
            self.assertEqual(ValoracionPreoperatoria.objects.count(), 2)
            self.assertEqual(ValoracionPreoperatoria.objects.first().motivo_enmienda, 'Aclaración documentada')
        cuerpo = self.cliente.get(self.pdf_url(nueva.documento)).content
        self.assertIn('Conclusión corregida', '\n'.join(p.extract_text() for p in PdfReader(BytesIO(cuerpo)).pages))
        self.assertContains(self.cliente.get(self.detalle), 'Aclaración documentada')
        with self.en_tenant(), usando_tenant(self.tenant, self.titular):
            consultas.enmendar(self.consulta, self.motivo.pk, {'motivo': 'Anamnesis corregida'}, 'Ajuste clínico')
        self.assertNotEqual(self.cliente.post(self.emitir).url, revision.url)
        with self.en_tenant():
            self.assertEqual(InformePreoperatorio.objects.count(), 3)
        self.assertEqual(self.cliente.get(url).content, firmado)

    def test_rutas_y_documentos_entre_consultorios(self):
        self.assertRedirects(self.cliente.post(self.valorar, self.valoracion()), self.detalle)
        self.cerrar()
        self.cliente.post(self.emitir)
        with self.en_tenant():
            ruta_pdf = self.pdf_url(DocumentoEmitido.objects.get())
        otro_tenant, _ = crear_consultorio(slug='otro', usuario='otro')
        ajeno = self.entrar(otro_tenant, 'otro')
        self.assertEqual(ajeno.get(self.valorar).status_code, 404)
        self.assertEqual(ajeno.post(self.emitir).status_code, 404)
        self.assertEqual(ajeno.get(ruta_pdf).status_code, 404)


class EmisionConcurrenteTest(FlujoPreoperatorio, TransactionTestCase):
    @skipUnlessDBFeature('has_select_for_update')
    def test_emisiones_concurrentes_generan_un_solo_correlativo(self):
        self.tenant, self.titular = crear_consultorio()
        self.cliente = BaseTest.entrar(self.tenant, 'titular')
        self.configurar_evaluacion()
        self.assertRedirects(self.cliente.post(self.valorar, self.valoracion()), self.detalle)
        self.cerrar()

        def emitir():
            close_old_connections()
            try:
                with usando_tenant(self.tenant, self.titular):
                    documento, nuevo = preoperatorio.emitir_informe(self.consulta, self.actor)
                    return documento.numero, nuevo
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            trabajos = [pool.submit(emitir) for _ in range(2)]
            resultados = [trabajo.result(timeout=20) for trabajo in trabajos]
        self.assertEqual(resultados[0][0], resultados[1][0])
        self.assertEqual(sum(nuevo for _, nuevo in resultados), 1)
        with usando_tenant(self.tenant):
            self.assertEqual(InformePreoperatorio.objects.count(), 1)
