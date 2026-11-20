"""Catálogo de estudios: aislamiento por consultorio y altas explícitas."""
from django.urls import reverse

from apps.clinica.consultas import abrir_consulta
from apps.clinica.models import Consulta
from apps.clinica.models.consulta import EstudioCatalogo
from apps.equipo.models import Membresia
from apps.pacientes.models import Paciente

from .base import BaseTest, crear_consultorio


class CatalogoEstudiosTest(BaseTest):
    def setUp(self):
        super().setUp()
        self.perfil = Membresia.objects.get(usuario=self.titular).perfil
        with self.en_tenant():
            self.paciente = Paciente.objects.create(nombres='Paciente', apellidos='Sintético')
            self.consulta = abrir_consulta(paciente=self.paciente, profesional=self.perfil)
        self.url = reverse('clinica:estudio_catalogo_nuevo')

    def alta(self, **cambios):
        return self.cliente.post(self.url, {
            'consulta': self.consulta.pk,
            'nombre': 'Hemograma completo', 'categoria': 'LAB', **cambios,
        })

    def test_alta_permitida_y_duplicado_normalizado(self):
        self.assertEqual(self.cliente.get(self.url).status_code, 405)
        respuesta = self.alta()
        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(respuesta.json()['nombre'], 'Hemograma completo')
        self.assertEqual(self.alta(nombre='  HEMÓGRAMA   COMPLETO ').status_code, 409)
        with self.en_tenant():
            self.assertEqual(EstudioCatalogo.objects.count(), 1)

    def test_validacion_de_campos_y_aislamiento_entre_consultorios(self):
        self.assertEqual(self.alta(categoria='FALSO').status_code, 400)
        self.assertEqual(self.alta(nombre='X').status_code, 400)
        otro, usuario = crear_consultorio(slug='otro-catalogo', usuario='otrocat')
        otro_cliente = self.entrar(otro, 'otrocat')
        self.assertIn(otro_cliente.post(self.url, {
            'consulta': self.consulta.pk, 'nombre': 'Examen ajeno', 'categoria': 'LAB',
        }).status_code, (403, 404))
        with self.en_tenant():
            self.assertFalse(EstudioCatalogo.objects.exists())

    def test_nunca_crea_cargos_al_registrar_examen(self):
        from apps.cobros.models import Cargo

        self.assertEqual(self.alta(nombre='Creatinina').status_code, 201)
        with self.en_tenant():
            self.assertFalse(Cargo.objects.exists())
