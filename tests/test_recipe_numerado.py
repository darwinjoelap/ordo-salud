"""ADR-063: récipe numerado como Pediae — cada medicamento con su indicación, mismo número a ambos lados del PDF."""
import io

from pypdf import PdfReader

from apps.clinica import consultas as srv
from apps.clinica.consultas import abrir_consulta
from apps.clinica.models import ItemPrescripcion
from apps.documentos import servicios as documentos
from apps.equipo.models import Membresia
from apps.pacientes.models import Paciente

from .base import BaseTest


class RecipeNumeradoTest(BaseTest):
    def test_indicacion_por_medicamento_en_el_pdf(self):
        from apps.documentos.generadores import recipe
        with self.en_tenant():
            p = Paciente.objects.create(nombres='Rosa', apellidos='Paz', sexo='F')
            perfil = Membresia.objects.get(usuario=self.titular).perfil
            c = abrir_consulta(paciente=p, profesional=perfil)
            item = next(i for i in c.estructura if i['codigo'] == 'nucleo.prescripcion')
            srv.guardar_secciones(c, {item['seccion_id']: {'medicamentos': [
                {'medicamento': 'Apiret 180 mg/5 mL', 'dosis': '5 mL', 'indicacion': 'Dar 5 mL cada 6 h solo si fiebre'},
                {'medicamento': 'Amoxicilina 250 mg/5 mL', 'dosis': '4,8 mL', 'frecuencia': 'cada 8 horas'}],
                'observaciones': 'Abundante líquido'}})
            items = list(ItemPrescripcion.objects.filter(consulta=c).values_list('orden', 'indicacion'))
            doc = documentos.documento_de_consulta('recipe', c)
            pdf = recipe.generar(doc)
        self.assertEqual(items, [(0, 'Dar 5 mL cada 6 h solo si fiebre'), (1, '')])
        datos = pdf if isinstance(pdf, bytes) else pdf.getvalue()
        texto = ' '.join(pg.extract_text() for pg in PdfReader(io.BytesIO(datos)).pages)
        self.assertIn('1. Apiret', texto)
        self.assertIn('Dar 5 mL cada 6 h solo si fiebre', texto)
        self.assertIn('2. Amoxicilina', texto)
        self.assertIn('4,8 mL, cada 8 horas', texto)        # sin indicación: dosis y frecuencia
        self.assertIn('Abundante líquido', texto)
