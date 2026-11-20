"""Resultados preoperatorios seleccionados del catálogo y trazabilidad por revisión."""
from datetime import date

from apps.clinica.models.consulta import EstudioCatalogo, EstudioPreoperatorio, ValoracionPreoperatoria

from .base import BaseTest, crear_consultorio
from .test_evaluacion_preoperatoria_etapa2 import FlujoPreoperatorio


class CatalogoEnPreoperatorioTest(FlujoPreoperatorio, BaseTest):
    def setUp(self):
        super().setUp()
        self.configurar_evaluacion()
        with self.en_tenant():
            self.examen = EstudioCatalogo.objects.create(nombre='Perfil metabólico', categoria='LAB')

    def test_catalogo_se_muestra_compacto_con_campos_inicialmente_ocultos(self):
        respuesta = self.cliente.get(self.valorar)
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'border-bottom py-1')
        self.assertContains(respuesta, 'data-fila-estudio')
        self.assertContains(respuesta, 'data-detalles-estudio hidden')
        self.assertContains(respuesta, '/static/js/estudios.js')
        self.assertContains(respuesta, 'Perfil metabólico')

    def test_seleccion_registra_resultado_y_conserva_version_original(self):
        formulario = self.cliente.get(self.valorar)
        self.assertContains(formulario, 'Perfil metabólico')
        self.assertContains(formulario, 'Agregar examen al catálogo')
        datos = self.valoracion(estudios=[{
            'catalogo': self.examen.pk, 'nombre': self.examen.nombre, 'tipo': 'LAB',
            'control_seleccion': 'on', 'seleccionado': 'on',
            'fecha': '2026-10-12', 'resultado': 'Hallazgo sintético',
            'unidad': 'mg/dL', 'observaciones': 'Revisado por internista',
        }])
        self.assertEqual(self.cliente.post(self.valorar, datos).status_code, 302)
        with self.en_tenant():
            primera = ValoracionPreoperatoria.objects.get()
            estudio = primera.estudios.get()
            self.assertEqual((estudio.catalogo_id, estudio.nombre),
                             (self.examen.pk, 'Perfil metabólico'))
            self.assertEqual(estudio.unidad, 'mg/dL')
            self.assertEqual(estudio.get_tipo_display(), 'Perfil metabólico (mg/dL)')
            self.examen.nombre = 'Examen renombrado'
            self.examen.save()
            self.assertEqual(primera.estudios.get().nombre, 'Perfil metabólico')

    def test_sin_seleccion_no_crea_estudios_y_puede_dejar_pendiente(self):
        datos = self.valoracion(estudios=[{
            'catalogo': self.examen.pk, 'tipo': 'LAB',
            'control_seleccion': 'on',
        }])
        self.assertEqual(self.cliente.post(self.valorar, datos).status_code, 302)
        with self.en_tenant():
            self.assertFalse(EstudioPreoperatorio.objects.exists())
            valoracion = ValoracionPreoperatoria.objects.get()
        datos = self.valoracion(version=valoracion.pk, estudios=[{
            'catalogo': self.examen.pk, 'tipo': 'LAB',
            'control_seleccion': 'on', 'seleccionado': 'on',
            'observaciones': 'Resultado pendiente',
        }])
        self.assertEqual(self.cliente.post(self.valorar, datos).status_code, 302)
        with self.en_tenant():
            pendiente = ValoracionPreoperatoria.objects.first().estudios.get()
            self.assertEqual(pendiente.resultado, '')
            self.assertEqual(pendiente.observaciones, 'Resultado pendiente')

    def test_catalogo_ajeno_no_puede_inyectarse_en_valoracion(self):
        otro, _ = crear_consultorio(slug='otro-preop-catalogo', usuario='otropreop')
        with self.en_tenant(otro):
            ajeno = EstudioCatalogo.objects.create(nombre='Examen de otra clínica', categoria='LAB')
        datos = self.valoracion(estudios=[{
            'catalogo': ajeno.pk, 'tipo': 'LAB', 'control_seleccion': 'on',
            'seleccionado': 'on', 'resultado': 'Valor inventado',
        }])
        r = self.cliente.post(self.valorar, datos)
        self.assertEqual(r.status_code, 200)
        self.assertIn('catalogo', r.context['estudios'].forms[0].errors)
        with self.en_tenant():
            self.assertFalse(ValoracionPreoperatoria.objects.exists())
