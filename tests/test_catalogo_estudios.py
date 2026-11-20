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

    def test_alta_desde_consulta_nueva_con_paciente_autorizado(self):
        respuesta = self.cliente.post(self.url, {
            'paciente': self.paciente.pk, 'nombre': 'Proteína C reactiva', 'categoria': 'LAB',
        })
        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(respuesta.json()['nombre'], 'Proteína C reactiva')
        with self.en_tenant():
            self.assertEqual(EstudioCatalogo.objects.count(), 1)

    def test_no_alta_con_paciente_ajeno_o_inactivo(self):
        otro, _ = crear_consultorio(slug='otro-alta-consulta', usuario='otroalta')
        with self.en_tenant(otro):
            ajeno = Paciente.objects.create(nombres='Paciente', apellidos='De Otro Tenant')
        respuesta = self.cliente.post(self.url, {
            'paciente': ajeno.pk, 'nombre': 'Examen ajeno', 'categoria': 'LAB',
        })
        self.assertIn(respuesta.status_code, (403, 404))
        with self.en_tenant():
            self.paciente.activo = False
            self.paciente.save()
        respuesta = self.cliente.post(self.url, {
            'paciente': self.paciente.pk, 'nombre': 'Examen inactivo', 'categoria': 'LAB',
        })
        self.assertIn(respuesta.status_code, (403, 404))
        with self.en_tenant():
            self.assertFalse(EstudioCatalogo.objects.exists())

    def test_aviso_global_de_actualizacion_desaparece_definitivamente(self):
        respuesta = self.cliente.get(f'/pacientes/{self.paciente.pk}/')
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, 'os-transicion-pwa')
        self.assertNotContains(respuesta, 'Actualización de Ordo Salud')
        self.assertContains(respuesta, 'js/pwa.js')

    def test_nunca_crea_cargos_al_registrar_examen(self):
        from apps.cobros.models import Cargo

        self.assertEqual(self.alta(nombre='Creatinina').status_code, 201)
        with self.en_tenant():
            self.assertFalse(Cargo.objects.exists())
