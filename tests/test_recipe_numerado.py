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


class RecipePesoTallaTest(BaseTest):
    """Como Pediae: en menores de 18 el récipe lleva peso y talla de la consulta junto a la edad."""

    def _pdf(self, nacimiento):
        from apps.documentos.generadores import recipe
        with self.en_tenant():
            p = Paciente.objects.create(nombres='Tomás', apellidos='Paz', sexo='M', fecha_nacimiento=nacimiento)
            perfil = Membresia.objects.get(usuario=self.titular).perfil
            c = abrir_consulta(paciente=p, profesional=perfil)
            vitales = next(i for i in c.estructura
                           if any(x['clave'] == 'peso_kg' for x in i.get('campos', [])) or i['codigo'] == 'nucleo.vitales')
            rx = next(i for i in c.estructura if i['codigo'] == 'nucleo.prescripcion')
            srv.guardar_secciones(c, {vitales['seccion_id']: {'peso_kg': '12.50', 'talla_cm': '88'},
                                      rx['seccion_id']: {'medicamentos': [{'medicamento': 'Apiret'}]}})
            pdf = recipe.generar(documentos.documento_de_consulta('recipe', c))
        datos = pdf if isinstance(pdf, bytes) else pdf.getvalue()
        return ' '.join(pg.extract_text() for pg in PdfReader(io.BytesIO(datos)).pages)

    def test_nino_lleva_peso_y_talla(self):
        from datetime import date
        texto = self._pdf(date(date.today().year - 4, 1, 15))
        self.assertIn('Peso: 12,5 kg', texto)
        self.assertIn('Talla: 88 cm', texto)

    def test_adulto_no(self):
        from datetime import date
        self.assertNotIn('Peso:', self._pdf(date(1980, 5, 1)))
