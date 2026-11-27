"""Fase 10: documentos PDF (récipe, informe, referencia, reposo, constancia, recibo)."""
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from pypdf import PdfReader

from apps.clinica.models import Adjunto, Consulta, SeccionClinica
from apps.cobros import servicios as cobros
from apps.core.permisos import Rol
from apps.documentos.generadores.clinicos import en_letras
from apps.documentos.models import DocumentoEmitido
from apps.equipo import servicios as equipo
from apps.equipo.models import Membresia
from apps.pacientes.models import Paciente, Representante
from apps.plataforma.models import Especialidad

from .base import BaseTest, crear_consultorio


def _png(ancho=200):
    from PIL import Image
    b = BytesIO()
    Image.new('RGBA', (ancho, 80), (20, 40, 160, 255)).save(b, 'PNG')
    return SimpleUploadedFile('firma.png', b.getvalue(), content_type='image/png')


def _texto_pdf(contenido):
    return '\n'.join(p.extract_text() for p in PdfReader(BytesIO(contenido)).pages)


class DocumentosTest(BaseTest):
    def setUp(self):
        super().setUp()
        with self.en_tenant():
            self.paciente = Paciente.objects.create(nombres='Luisa', apellidos='Mora', sexo='F',
                                                    numero_documento='9000111', fecha_nacimiento='1990-05-04')
            s = {x.codigo: x.pk for x in SeccionClinica.objects.visibles()}
        r = self.iniciar_independiente(self.paciente, {'tipo': 'PRIMERA'})
        self.assertEqual(r.status_code, 302)
        with self.en_tenant():
            self.consulta = Consulta.objects.latest('id')
        datos = {
            f"s{s['nucleo.motivo']}-motivo": 'Dolor de garganta',
            f"s{s['nucleo.diagnosticos']}-diagnosticos__0__codigo": 'J02.9',
            f"s{s['nucleo.diagnosticos']}-diagnosticos__0__descripcion": '',
            f"s{s['nucleo.prescripcion']}-medicamentos__0__medicamento": 'Ibuprofeno 400 mg tabletas',
            f"s{s['nucleo.prescripcion']}-medicamentos__0__dosis": '1 tableta',
            f"s{s['nucleo.prescripcion']}-medicamentos__0__frecuencia": 'cada 8 horas',
            f"s{s['nucleo.prescripcion']}-medicamentos__0__cantidad": '1 caja',
            f"s{s['nucleo.plan']}-indicaciones": 'Abundantes líquidos & reposo <relativo>',
            f"s{s['nucleo.ordenes']}-laboratorio": 'Hematología completa',
            'accion': 'cerrar',
        }
        r = self.cliente.post(f'/consultas/{self.consulta.pk}/editar/', datos)
        self.assertEqual(r.status_code, 302)

    def pdf(self, doc, cliente=None, **params):
        r = (cliente or self.cliente).get(f'/documentos/{doc.pk}/pdf/', params)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/pdf')
        return _texto_pdf(r.content)

    def test_recipe_dos_columnas_y_numero_unico_por_consulta(self):
        r = self.cliente.get(f'/documentos/emitir/recipe/?consulta={self.consulta.pk}')
        with self.en_tenant():
            doc = DocumentoEmitido.objects.get()
        self.assertRedirects(r, f'/documentos/{doc.pk}/pdf/', fetch_redirect_response=False)
        self.assertTrue(doc.numero.startswith('RCP-'))
        texto = self.pdf(doc)
        self.assertEqual(texto.count('Ibuprofeno 400 mg tabletas'), 2)      # Rp. e Indicaciones
        self.assertIn('cada 8 horas', texto)
        self.assertIn('Hematología completa', texto)
        self.assertIn('Abundantes líquidos & reposo <relativo>', texto)
        self.cliente.get(f'/documentos/emitir/recipe/?consulta={self.consulta.pk}')
        with self.en_tenant():
            self.assertEqual(DocumentoEmitido.objects.count(), 1)

    def test_recipe_lee_solo_las_imagenes_que_usa_en_cada_apertura(self):
        self.cliente.get(f'/documentos/emitir/recipe/?consulta={self.consulta.pk}')
        with self.en_tenant():
            doc = DocumentoEmitido.objects.get(tipo='recipe')
            perfil = Membresia.objects.get(usuario=self.titular).perfil
            perfil.logo = _png()
            perfil.membrete = _png(ancho=480)
            perfil.firma = _png(ancho=160)
            perfil.sello = _png(ancho=120)
            perfil.save()
        escenarios = [
            (False, True, True, [perfil.logo.name, perfil.firma.name, perfil.sello.name], 1),
            (False, True, False, [perfil.logo.name], 1),
            (True, False, False, [perfil.membrete.name], 0),
            (True, True, False, [perfil.membrete.name, perfil.logo.name], 0),
        ]
        for membrete, marca, firma, nombres, reutilizadas in escenarios:
            with self.subTest(membrete=membrete, marca=marca, firma=firma):
                perfil.usar_membrete_propio = membrete
                perfil.marca_agua = marca
                perfil.save(update_fields=['usar_membrete_propio', 'marca_agua'])
                with (
                    patch.object(FileSystemStorage, '_open', autospec=True, side_effect=FileSystemStorage._open) as abrir,
                    self.assertLogs('apps.core.pdf', level='INFO') as logs,
                ):
                    params = {} if firma else {'firma': '0'}
                    respuesta = self.cliente.get(f'/documentos/{doc.pk}/pdf/', params)
                self.assertEqual(respuesta.status_code, 200)
                self.assertCountEqual([llamada.args[1] for llamada in abrir.call_args_list], nombres)
                self.assertIn(f'lecturas={len(nombres)} reutilizadas={reutilizadas} fallos=0', logs.output[0])
                pagina = PdfReader(BytesIO(respuesta.content)).pages[0]
                self.assertIn('Ibuprofeno', pagina.extract_text())
                imagenes = {(i.image.width, i.image.convert('RGBA').getpixel((0, 0))[3]) for i in pagina.images}
                esperadas = {(480 if membrete else 200, 255)}
                if marca:
                    esperadas.add((200, 20))
                if firma:
                    esperadas.update({(160, 255), (120, 255)})
                self.assertEqual(imagenes, esperadas)

    def test_informe_con_secciones_y_conclusion(self):
        r = self.cliente.post('/documentos/emitir/informe/', {'consulta': self.consulta.pk, 'ciudad': 'Maracay',
                                                              'conclusion': 'Evolución favorable.'})
        self.assertEqual(r.status_code, 302)
        with self.en_tenant():
            doc = DocumentoEmitido.objects.get(tipo='informe')
        texto = self.pdf(doc)
        for esperado in ('INFORME MÉDICO', 'Maracay', 'Faringitis aguda', 'Evolución favorable.', 'Luisa Mora'):
            self.assertIn(esperado, texto)

    def test_reposo_con_dias_en_letras_y_rango(self):
        r = self.cliente.get(f'/documentos/emitir/reposo/?consulta={self.consulta.pk}')
        self.assertContains(r, 'J02.9')     # diagnóstico sugerido
        r = self.cliente.post('/documentos/emitir/reposo/', {'consulta': self.consulta.pk, 'dias': 3,
                                                             'desde': '2026-10-20', 'diagnostico': 'Faringitis'})
        with self.en_tenant():
            doc = DocumentoEmitido.objects.get(tipo='reposo')
        self.assertRedirects(r, f'/documentos/{doc.pk}/', fetch_redirect_response=False)
        texto = ' '.join(self.pdf(doc).split())
        self.assertIn('tres (3) días', texto)
        self.assertIn('desde el 20 de octubre de 2026 hasta el 22 de octubre de 2026', texto)
        self.assertIn('evaluada', texto)

    def test_constancia_de_menor_con_representante(self):
        with self.en_tenant():
            nino = Paciente.objects.create(nombres='Tomás', apellidos='Mora', sexo='M',
                                           fecha_nacimiento=timezone.localdate().replace(year=2020))
            Representante.objects.create(paciente=nino, nombre='Luisa Mora', numero_documento='9000111')
        r = self.cliente.get(f'/documentos/emitir/constancia/?paciente={nino.pk}')
        self.assertContains(r, 'Luisa Mora')
        self.cliente.post('/documentos/emitir/constancia/', {'paciente': nino.pk, 'fecha_asistencia': '2026-10-20',
                                                             'hora_desde': '08:00', 'hora_hasta': '09:30',
                                                             'acompanante': 'Luisa Mora (madre)'})
        with self.en_tenant():
            doc = DocumentoEmitido.objects.get(tipo='constancia')
        texto = ' '.join(self.pdf(doc).split())
        self.assertIn('asistió a consulta de medicina general', texto)
        self.assertIn('8:00 a. m.', texto)
        self.assertIn('Luisa Mora (madre)', texto)

    def test_referencia_sugiere_tratamiento(self):
        r = self.cliente.get(f'/documentos/emitir/referencia/?consulta={self.consulta.pk}')
        self.assertContains(r, 'Ibuprofeno 400 mg tabletas 1 tableta cada 8 horas')
        self.cliente.post('/documentos/emitir/referencia/', {'consulta': self.consulta.pk, 'dirigido_a': 'ORL',
                                                             'motivo': 'Amigdalitis a repetición'})
        with self.en_tenant():
            doc = DocumentoEmitido.objects.get(tipo='referencia')
        self.assertIn('Amigdalitis a repetición', self.pdf(doc))

    def test_firma_solo_la_pone_quien_firma(self):
        with self.en_tenant():
            perfil = Membresia.objects.get(usuario=self.titular).perfil
            perfil.firma = _png()
            perfil.sello = _png(ancho=160)
            perfil.save()
        self.cliente.post('/documentos/emitir/reposo/', {'consulta': self.consulta.pk, 'dias': 1, 'desde': '2026-10-20'})
        with self.en_tenant():
            doc = DocumentoEmitido.objects.get()
        con = self.cliente.get(f'/documentos/{doc.pk}/pdf/').content
        sin = self.cliente.get(f'/documentos/{doc.pk}/pdf/?firma=0').content
        self.assertGreater(len(con), len(sin) + 200)
        self.assertEqual({imagen.image.width for imagen in PdfReader(BytesIO(con)).pages[0].images}, {160, 200})
        # Otro médico del consultorio lo ve, con historia compartida y sin las imágenes de firma y sello.
        esp = Especialidad.objects.get(codigo='medicina_general')
        actor = Membresia.objects.get(usuario=self.titular)
        m, clave = equipo.agregar(self.tenant, actor, 'drdos', 'Luis', 'Mar', Rol.MEDICO, especialidad=esp)
        m.usuario.debe_cambiar_clave = False
        m.usuario.save()
        otro = self.entrar(self.tenant, 'drdos', clave)
        self.assertEqual(len(otro.get(f'/documentos/{doc.pk}/pdf/').content), len(sin))
        # ni puede emitir el récipe de una consulta ajena
        r = otro.get(f'/documentos/emitir/recipe/?consulta={self.consulta.pk}')
        self.assertRedirects(r, f'/consultas/{self.consulta.pk}/', fetch_redirect_response=False)

    def test_asistente_no_ve_documentos_clinicos_pero_si_recibos(self):
        self.cliente.post('/documentos/emitir/reposo/', {'consulta': self.consulta.pk, 'dias': 1, 'desde': '2026-10-20'})
        with self.en_tenant():
            doc = DocumentoEmitido.objects.get()
            cobros.crear_cargo(paciente=self.paciente, descripcion='Consulta', precio_usd=Decimal('40'))
            pago = cobros.registrar_pago(paciente=self.paciente, monto=Decimal('50'), moneda='USD', metodo='ZELLE',
                                         referencia='ABC123')
        actor = Membresia.objects.get(usuario=self.titular)
        m, clave = equipo.agregar(self.tenant, actor, 'caja', 'Ana', 'Gil', Rol.ASISTENTE)
        m.usuario.debe_cambiar_clave = False
        m.usuario.save()
        asistente = self.entrar(self.tenant, 'caja', clave)
        self.assertEqual(asistente.get(f'/documentos/{doc.pk}/pdf/').status_code, 403)
        r = asistente.get(f'/documentos/recibos/{pago.pk}/')
        with self.en_tenant():
            recibo = DocumentoEmitido.objects.get(tipo='recibo')
        self.assertRedirects(r, f'/documentos/{recibo.pk}/pdf/', fetch_redirect_response=False)
        texto = ' '.join(self.pdf(recibo, asistente).split())
        self.assertIn('$ 50,00', texto)
        self.assertIn('ABC123', texto)
        self.assertIn('Saldo a favor: $ 10,00', texto)

    def test_anular_documento(self):
        self.cliente.post('/documentos/emitir/reposo/', {'consulta': self.consulta.pk, 'dias': 1, 'desde': '2026-10-20'})
        with self.en_tenant():
            doc = DocumentoEmitido.objects.get()
        self.cliente.post(f'/documentos/{doc.pk}/anular/', {'motivo': 'Error en días'})
        doc.refresh_from_db()
        self.assertTrue(doc.anulado)
        self.assertContains(self.cliente.get(f'/pacientes/{self.paciente.pk}/'), 'text-decoration-line-through')

    def test_menu_en_consulta_y_ficha(self):
        r = self.cliente.get(f'/consultas/{self.consulta.pk}/')
        self.assertContains(r, 'Récipe e indicaciones')
        r = self.cliente.get(f'/pacientes/{self.paciente.pk}/')
        self.assertContains(r, 'Reposo médico')
        self.assertNotContains(r, 'Récipe e indicaciones')     # el récipe sale de una consulta

    def test_numeros_en_letras(self):
        self.assertEqual(en_letras(1), 'un')
        self.assertEqual(en_letras(21), 'veintiún')
        self.assertEqual(en_letras(45), 'cuarenta y cinco')
        self.assertEqual(en_letras(120), 'ciento veinte')


class InformeConAdjuntoTest(BaseTest):
    def test_informe_cardiologico_incluye_adjunto_y_reutiliza_logo(self):
        tenant, titular = crear_consultorio('Cardiología de prueba', 'prueba-cardio', especialidad='cardiologia_pediatrica')
        cliente = self.entrar(tenant, 'titular')
        with self.en_tenant(tenant):
            paciente = Paciente.objects.create(nombres='Paciente', apellidos='Sintético', sexo='F')
            perfil = Membresia.objects.get(usuario=titular).perfil
            perfil.logo = _png()
            perfil.save(update_fields=['logo'])
        r = self.iniciar_independiente(paciente, {'tipo': 'PRIMERA'}, cliente=cliente)
        self.assertEqual(r.status_code, 302)
        with self.en_tenant(tenant):
            consulta = Consulta.objects.get()
            adjunto = Adjunto.objects.create(paciente=paciente, consulta=consulta, nombre='estudio.png',
                                            archivo=_png(ancho=320), tipo_contenido='image/png')
        r = cliente.post('/documentos/emitir/cp_informe/',
                         {'consulta': consulta.pk, 'incluir_imagenes': 'on', 'incluir_notas': 'on'})
        self.assertEqual(r.status_code, 302)
        with self.en_tenant(tenant):
            doc = DocumentoEmitido.objects.get(tipo='cp_informe')
        with (
            patch.object(FileSystemStorage, '_open', autospec=True, side_effect=FileSystemStorage._open) as abrir,
            self.assertLogs('apps.core.pdf', level='INFO') as logs,
        ):
            r = cliente.get(f'/documentos/{doc.pk}/pdf/')
        self.assertEqual(r.status_code, 200)
        self.assertCountEqual([llamada.args[1] for llamada in abrir.call_args_list],
                              [perfil.logo.name, adjunto.archivo.name])
        self.assertIn('lecturas=2 reutilizadas=1 fallos=0', logs.output[0])
        paginas = PdfReader(BytesIO(r.content)).pages
        self.assertTrue(any(imagen.image.width == 320 for pagina in paginas for imagen in pagina.images))
