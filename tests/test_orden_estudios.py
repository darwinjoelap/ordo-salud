"""Órdenes de estudios: selección, indicaciones, PDF inmutable y ausencia de cargos."""
from io import BytesIO

from django.urls import reverse
from pypdf import PdfReader

from apps.clinica.consultas import abrir_consulta
from apps.clinica.models.consulta import EstudioCatalogo
from apps.cobros.models import Cargo
from apps.documentos.models import DocumentoEmitido
from apps.equipo.models import Membresia
from apps.pacientes.models import Paciente

from .base import BaseTest, crear_consultorio


class OrdenEstudiosTest(BaseTest):
    def setUp(self):
        super().setUp()
        self.perfil = Membresia.objects.get(usuario=self.titular).perfil
        with self.en_tenant():
            self.paciente = Paciente.objects.create(nombres='Paciente', apellidos='Sintético')
            self.consulta = abrir_consulta(paciente=self.paciente, profesional=self.perfil)
            self.hemograma = EstudioCatalogo.objects.create(nombre='Hemograma completo', categoria='LAB')
            self.ecg = EstudioCatalogo.objects.create(nombre='Electrocardiograma', categoria='ECG')
        self.url = reverse('documentos:emitir', args=['orden_estudios'])

    def test_orden_documento_pdf_con_snapshot_y_sin_cargos(self):
        form = self.cliente.get(self.url, {'consulta': self.consulta.pk})
        self.assertContains(form, 'Hemograma completo')
        self.assertContains(form, 'Agregar examen al catálogo')
        resultado = self.cliente.post(self.url, {
            'consulta': self.consulta.pk, 'examenes': [self.hemograma.pk, self.ecg.pk],
            f'indicacion_{self.hemograma.pk}': 'En ayunas',
            f'indicacion_{self.ecg.pk}': 'Antes de la cirugía',
        })
        self.assertEqual(resultado.status_code, 302)
        with self.en_tenant():
            doc = DocumentoEmitido.objects.get(tipo='orden_estudios')
            self.assertEqual(len(doc.datos['estudios']), 2)
            self.assertFalse(Cargo.objects.exists())
            self.hemograma.nombre = 'Nombre modificado'
            self.hemograma.save()
        pdf = self.cliente.get(reverse('documentos:pdf', args=[doc.pk]))
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf['Content-Type'], 'application/pdf')
        texto = '\n'.join(p.extract_text() for p in PdfReader(BytesIO(pdf.content)).pages)
        self.assertIn('Hemograma completo', texto)
        self.assertIn('En ayunas', texto)
        self.assertIn('Electrocardiograma', texto)
        self.assertNotIn('Nombre modificado', texto)

    def test_consulta_incluye_catalogo_y_orden_pdf_preseleccionada(self):
        url_editar = reverse('clinica:consulta_editar', args=[self.consulta.pk])
        nueva = self.cliente.get(
            f'/pacientes/{self.paciente.pk}/consultas/nueva/', {'independiente': '1'})
        self.assertContains(nueva, 'data-modo="consulta"')
        self.assertContains(nueva, 'Órdenes de exámenes')
        vista = self.cliente.get(url_editar)
        self.assertContains(vista, 'Hemograma completo')
        self.assertContains(vista, 'Electrocardiograma')
        self.assertContains(vista, 'data-orden-examen')
        self.assertContains(vista, 'data-orden-indicacion')
        self.assertContains(vista, 'Generar orden de exámenes en PDF')
        item = next(i for i in self.consulta.estructura if i['codigo'] == 'nucleo.ordenes')
        respuesta = self.cliente.post(url_editar, {
            f"s{item['seccion_id']}-laboratorio": '• Hemograma completo — Ayunas 8 horas',
            f"s{item['seccion_id']}-imagenes": '• Electrocardiograma — Reposo previo',
            'accion': 'guardar',
        })
        self.assertEqual(respuesta.status_code, 302)
        with self.en_tenant():
            from apps.clinica.models import RegistroSeccion
            datos = RegistroSeccion.objects.get(consulta=self.consulta, seccion_id=item['seccion_id']).datos
            self.assertIn('Hemograma completo', datos['laboratorio'])
            self.assertIn('Electrocardiograma', datos['imagenes'])
            self.assertFalse(Cargo.objects.exists())
        documento = self.cliente.get(self.url, {'consulta': self.consulta.pk})
        self.assertEqual(documento.status_code, 200)
        self.assertEqual(set(documento.context['form'].initial['examenes']),
                         {self.hemograma.pk, self.ecg.pk})
        self.assertEqual(documento.context['form'].initial[f'indicacion_{self.hemograma.pk}'],
                         'Ayunas 8 horas')
        self.assertEqual(documento.context['form'].initial[f'indicacion_{self.ecg.pk}'],
                         'Reposo previo')
        emitido = self.cliente.post(self.url, {
            'consulta': self.consulta.pk, 'examenes': [self.hemograma.pk, self.ecg.pk],
            f'indicacion_{self.hemograma.pk}': 'Ayunas 8 horas',
            f'indicacion_{self.ecg.pk}': 'Reposo previo',
        })
        self.assertEqual(emitido.status_code, 302)
        with self.en_tenant():
            orden = DocumentoEmitido.objects.get(tipo='orden_estudios')
            self.assertFalse(Cargo.objects.exists())
        pdf = self.cliente.get(reverse('documentos:pdf', args=[orden.pk]))
        self.assertEqual(pdf.status_code, 200)
        texto = '\\n'.join(p.extract_text() for p in PdfReader(BytesIO(pdf.content)).pages)
        self.assertIn('Ayunas 8 horas', texto)
        self.assertIn('Reposo previo', texto)

    def test_no_permite_orden_vacia_ni_examen_ajeno(self):
        with self.en_tenant():
            self.assertFalse(DocumentoEmitido.objects.exists())
        r = self.cliente.post(self.url, {'consulta': self.consulta.pk, 'examenes': []})
        self.assertEqual(r.status_code, 200)
        otro, _ = crear_consultorio(slug='otro-orden', usuario='otroorden')
        with self.en_tenant(otro):
            ajeno = EstudioCatalogo.objects.create(nombre='Ajeno', categoria='LAB')
        r = self.cliente.post(self.url, {'consulta': self.consulta.pk, 'examenes': [ajeno.pk]})
        self.assertEqual(r.status_code, 200)
        with self.en_tenant():
            self.assertFalse(DocumentoEmitido.objects.exists())
