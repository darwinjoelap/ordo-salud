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
