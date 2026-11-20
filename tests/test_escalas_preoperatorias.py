"""Flujo de la valoración, confirmación e inmutabilidad del informe."""
from io import BytesIO
from datetime import date

from django.utils import timezone

from django.urls import reverse
from pypdf import PdfReader

from apps.clinica.models.consulta import InformePreoperatorio, ValoracionPreoperatoria
from apps.core.tenancy import usando_tenant
from apps.pacientes.models import Paciente

from .base import BaseTest, crear_consultorio
from .test_evaluacion_preoperatoria_etapa2 import FlujoPreoperatorio
from .test_reglas_preoperatorias import factores_rcri


class EscalasPreoperatoriasTest(FlujoPreoperatorio, BaseTest):
    def setUp(self):
        super().setUp()
        self.configurar_evaluacion()
        with self.en_tenant():
            Paciente.objects.filter(pk=self.paciente.pk).update(
                fecha_nacimiento=date(timezone.localdate().year - 71, 1, 1))
            self.paciente.refresh_from_db()
            self.consulta.paciente.refresh_from_db()
            cirugia = self.consulta.preoperatorio
            cirugia.caracter = 'ELECTIVA'
            cirugia.save(update_fields=['caracter'])
        self.rcri = {f'rcri-{k}': v for k, v in factores_rcri().items()}

    def cerrar(self, caracter='ELECTIVA'):
        r = self.cliente.post(self.editar, {
            'accion': 'cerrar', 'cirugia-procedimiento': 'Procedimiento sintético',
            'cirugia-motivo': 'Motivo quirúrgico', 'cirugia-caracter': caracter,
        })
        self.assertRedirects(r, self.detalle)

    def previa(self, codigo='rcri'):
        return reverse('clinica:preoperatorio_calcular_escala', args=[self.consulta.pk, codigo])

    def firma(self, datos):
        r = self.cliente.post(self.previa(), datos, HTTP_HX_REQUEST='true')
        self.assertContains(r, 'Confirmar este resultado al guardar')
        return r.context['tarjeta']['firma']

    def test_escalas_en_formulario_y_derechos_pendientes(self):
        vista = self.cliente.get(self.valorar)
        for nombre in ('Goldman', 'Detsky', 'Caprini', 'ARISCAT', 'RCRI de Lee', 'ASA-PS', 'Capacidad funcional'):
            self.assertContains(vista, nombre)
        self.assertNotContains(vista, 'DASI')
        self.assertContains(vista, 'Pendiente de autorización')
        for codigo in ('caprini', 'dasi'):
            r = self.cliente.post(self.previa(codigo), {f'{codigo}-ambito': 'si'})
            self.assertContains(r, 'No disponible')
            self.assertNotContains(r, 'Confirmar este resultado')
        with self.en_tenant():
            self.assertFalse(ValoracionPreoperatoria.objects.exists())

    def test_edad_de_ficha_no_admite_manipulacion_del_post(self):
        vista = self.cliente.get(self.valorar)
        self.assertContains(vista, 'Edad: 71 años')
        self.assertNotContains(vista, 'name="rcri-edad" type="number"')
        datos = {**self.rcri, 'rcri-edad': '16'}
        calculada = self.cliente.post(self.previa(), datos)
        self.assertContains(calculada, '0 puntos · I')
        self.assertEqual(calculada.context['tarjeta']['form_escala'].cleaned_data['edad'], 71)

    def test_calculo_sin_javascript_no_persiste_y_conserva_borrador_de_formulario(self):
        r = self.cliente.post(self.valorar, {
            **self.valoracion(conclusion='Texto por guardar'), **self.rcri, 'calcular': 'rcri',
        })
        self.assertContains(r, 'Texto por guardar')
        self.assertContains(r, '0 puntos · I')
        self.assertContains(r, 'Confirmar este resultado')
        with self.en_tenant():
            self.assertFalse(ValoracionPreoperatoria.objects.exists())

    def test_cuatro_formularios_calculan_y_guardan_juntos(self):
        fecha = factores_rcri()['fecha']
        goldman = {'edad': 71, 'infarto': 'reciente', 's3_yugular': 'si', 'estenosis': 'no',
                   'ritmo': 'no', 'ectopia': 0, 'estado_general': 'no', 'tipo_cirugia': 'no', 'emergencia': 'no'}
        detsky = {'edad': 71, 'infarto': 'remoto', 'angina_ccs': 'IV', 'inestable': 'si', 'edema': 'no',
                  'estenosis': 'no', 'ritmo': 'no', 'ectopia_o_tv_fv': 'no', 'estado_general': 'no',
                  'emergencia': 'no'}
        ariscat = {'edad': 71, 'spo2': 94, 'modo_spo2': 'aire_supino', 'infeccion': 'no', 'hb': '12,0',
                   'incision': 'superior', 'duracion': 120, 'emergencia': 'no'}
        pruebas = {'goldman': (goldman, '26'), 'detsky': (detsky, '40'), 'ariscat': (ariscat, '26'),
                   'rcri': ({**factores_rcri(), 'edad': 71}, '0')}
        post = self.valoracion()
        for codigo, (insumos, esperado) in pruebas.items():
            datos = {f'{codigo}-{k}': v for k, v in {'ambito': 'si', 'fecha': fecha, **insumos}.items()}
            r = self.cliente.post(self.previa(codigo), datos)
            self.assertContains(r, f'{esperado} puntos')
            post.update(datos)
            post.update({f'{codigo}-firma': r.context['tarjeta']['firma'], f'{codigo}-confirmar': '1'})
        self.assertRedirects(self.cliente.post(self.valorar, post), self.detalle)
        with self.en_tenant():
            resultados = ValoracionPreoperatoria.objects.get().datos['escalas_preoperatorias']
            self.assertEqual({k: v['puntaje'] for k, v in resultados.items()},
                             {k: puntos for k, (_, puntos) in pruebas.items()})

    def test_manipulacion_o_confirmacion_sin_previa_no_guardan(self):
        firma = self.firma(self.rcri)
        for cambios in ({'rcri-firma': 'falsa'}, {'rcri-creatinina': '2.1'}, {'rcri-ambito': 'no'}):
            with self.subTest(cambios=cambios):
                r = self.cliente.post(self.valorar, {
                    **self.valoracion(), **self.rcri, 'rcri-firma': firma, 'rcri-confirmar': '1', **cambios,
                })
                self.assertContains(r, 'Recalcula y revisa')
        with self.en_tenant():
            self.assertFalse(ValoracionPreoperatoria.objects.exists())

    def test_confirmacion_historia_pdf_y_revision_inmutable(self):
        firma = self.firma(self.rcri)
        self.assertRedirects(self.cliente.post(self.valorar, {
            **self.valoracion(), **self.rcri, 'rcri-firma': firma, 'rcri-confirmar': '1',
        }), self.detalle)
        vista = self.cliente.get(self.detalle)
        self.assertContains(vista, 'RCRI de Lee')
        self.assertContains(vista, '0 puntos · I')
        with self.en_tenant():
            anterior = ValoracionPreoperatoria.objects.get()
            resultado = anterior.datos['escalas_preoperatorias']['rcri']
            self.assertEqual(resultado['version'], 'Lee 1999')
            self.assertEqual(resultado['autor_id'], self.titular.pk)
            self.assertEqual(resultado['puntaje'], '0')

        self.assertRedirects(self.cliente.post(self.valorar, self.valoracion(version=anterior.pk)), self.detalle)
        with self.en_tenant():
            self.assertEqual(ValoracionPreoperatoria.objects.count(), 1)
        self.cerrar()
        self.assertEqual(self.cliente.post(self.emitir).status_code, 302)
        with self.en_tenant():
            informe = InformePreoperatorio.objects.get()
        ruta_pdf = self.pdf_url(informe.documento)
        original = self.cliente.get(ruta_pdf).content
        texto = chr(10).join(p.extract_text() for p in PdfReader(BytesIO(original)).pages)
        self.assertIn('RCRI de Lee (Lee 1999)', texto)
        self.assertIn('0 puntos', texto)
        self.assertNotIn('Caprini', texto)

        insumos = {**self.rcri, 'rcri-creatinina': '2.1'}
        firma = self.firma(insumos)
        self.assertRedirects(self.cliente.post(self.valorar, {
            **self.valoracion(version=anterior.pk, motivo_enmienda='Laboratorio revisado'),
            **insumos, 'rcri-firma': firma, 'rcri-confirmar': '1',
        }), self.detalle)
        self.assertEqual(self.cliente.post(self.emitir).status_code, 302)
        self.assertEqual(self.cliente.get(ruta_pdf).content, original)
        with self.en_tenant():
            self.assertEqual(ValoracionPreoperatoria.objects.get(pk=anterior.pk)
                             .datos['escalas_preoperatorias']['rcri']['puntaje'], '0')
            nueva = ValoracionPreoperatoria.objects.first()
            self.assertEqual(nueva.datos['escalas_preoperatorias']['rcri']['puntaje'], '1')
            self.assertEqual(nueva.motivo_enmienda, 'Laboratorio revisado')
            self.assertEqual(InformePreoperatorio.objects.count(), 2)

    def test_cambio_a_emergencia_preserva_resultado_historico_y_lo_excluye_del_pdf(self):
        firma = self.firma(self.rcri)
        self.assertRedirects(self.cliente.post(self.valorar, {
            **self.valoracion(), **self.rcri, 'rcri-firma': firma, 'rcri-confirmar': '1',
        }), self.detalle)
        self.cerrar(caracter='EMERGENCIA')
        self.assertContains(self.cliente.get(self.detalle), 'Requiere revisión')
        self.assertContains(self.cliente.post(self.previa(), self.rcri), 'No aplica')
        self.assertEqual(self.cliente.post(self.emitir).status_code, 302)
        with self.en_tenant():
            informe = InformePreoperatorio.objects.get()
        contenido = self.cliente.get(self.pdf_url(informe.documento)).content
        texto = chr(10).join(p.extract_text() for p in PdfReader(BytesIO(contenido)).pages)
        self.assertNotIn('RCRI de Lee', texto)

    def test_previa_no_intercambiable_entre_consultas_y_permiso_en_servidor(self):
        firma = self.firma(self.rcri)
        anterior = self.paciente
        self.configurar_evaluacion_otra()
        r = self.cliente.post(self.valorar, {
            **self.valoracion(), **self.rcri, 'rcri-firma': firma, 'rcri-confirmar': '1',
        })
        self.assertContains(r, 'Recalcula y revisa')
        self.assertNotEqual(self.paciente, anterior)
        otro_tenant, _ = crear_consultorio(slug='otro', usuario='otro')
        self.assertEqual(self.entrar(otro_tenant, 'otro').post(self.previa(), self.rcri).status_code, 404)
        self.tenant.configuracion.preoperatorio_especialidades.clear()
        self.assertEqual(self.cliente.post(self.previa(), self.rcri).status_code, 403)

    def configurar_evaluacion_otra(self):
        with usando_tenant(self.tenant):
            self.paciente = Paciente.objects.create(nombres='Segundo', apellidos='Sintético')
        inicio = reverse('clinica:preoperatorio_nuevo', args=[self.paciente.pk])
        r = self.cliente.get(inicio)
        r = self.cliente.post(inicio, {
            'completa': '1', 'independiente': '1', 'intento': r.context['intento'], 'accion': 'valorar',
            'cirugia-procedimiento': 'Procedimiento sintético', 'cirugia-motivo': 'Motivo',
            'cirugia-caracter': 'ELECTIVA',
        })
        self.assertEqual(r.status_code, 302)
        self.valorar = r.url
        self.consulta = self.cliente.get(self.valorar).context['consulta']
