"""Dictado en todas las especialidades: vocabulario, reglas propias y catálogo de campos de su plantilla."""
from django.test import TestCase

from apps.clinica.consultas import congelar_estructura
from apps.clinica.models import PlantillaHistoria
from apps.dictado import proveedores, servicios
from apps.plataforma.models import Especialidad


class DictadoEspecialidadesTest(TestCase):
    def test_todas_tienen_vocabulario(self):
        faltan = [e.codigo for e in Especialidad.objects.filter(activa=True) if e.codigo not in servicios.VOCABULARIO]
        self.assertEqual(faltan, [])

    def test_reglas_propias_en_el_sistema(self):
        s = servicios.sistema_para('oftalmologia', 'Oftalmología', 'femenino, 40 años')
        self.assertIn('OD = ojo derecho', s)
        self.assertIn('Paciente: femenino, 40 años.', s)
        general = servicios.sistema_para('medicina_general', 'Medicina general', 'masculino')
        self.assertNotIn('{reglas}', general)
        self.assertIn('Paciente: masculino.', general)

    def test_catalogo_de_cada_plantilla_predeterminada(self):
        """La plantilla predeterminada de cada especialidad produce un catálogo de campos para la IA."""
        from apps.clinica.servicios import asegurar_plantillas_especialidad
        from apps.core.tenancy import usando_tenant

        from .base import crear_consultorio
        tenant, _ = crear_consultorio('Todas', 'todas')
        especialidades = list(Especialidad.objects.filter(activa=True))
        probadas = 0
        with usando_tenant(tenant):
            for esp in especialidades:
                asegurar_plantillas_especialidad(esp)
                plantilla = (PlantillaHistoria.objects.filter(especialidad=esp, profesional__isnull=True, activa=True)
                             .order_by('-es_predeterminada').first())
                with self.subTest(especialidad=esp.codigo):
                    self.assertIsNotNone(plantilla)
                    lineas, ids, _ = proveedores.catalogo(servicios.herramienta(congelar_estructura(plantilla)))
                    self.assertIn('nucleo.motivo.motivo', ids)
                    self.assertTrue(any(i.startswith('nucleo.diagnosticos.') for i in ids))
                    probadas += 1
        self.assertEqual(probadas, len(especialidades))
