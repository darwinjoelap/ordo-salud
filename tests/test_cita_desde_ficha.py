"""2026-11-12: consulta hecha desde la ficha del paciente (no con «Atender») deja la cita del día atendida."""
from datetime import time
from io import StringIO

from django.core.management import call_command
from django.utils import timezone

from apps.agenda.models import Cita
from apps.clinica.consultas import abrir_consulta, crear_consulta_completa
from apps.equipo.models import Membresia
from apps.pacientes.models import Paciente

from .base import BaseTest


class CitaDesdeFichaTest(BaseTest):
    def setUp(self):
        super().setUp()
        self.perfil = Membresia.objects.get(usuario=self.titular).perfil
        with self.en_tenant():
            self.p = Paciente.objects.create(nombres='Luis', apellidos='Paz', sexo='M')
            self.cita = Cita.objects.create(paciente=self.p, profesional=self.perfil, especialidad=self.perfil.especialidad,
                                            fecha=timezone.localdate(), hora_inicio=time(9), hora_fin=time(9, 30))

    def test_consulta_completa_sin_cita_vincula_la_del_dia(self):
        with self.en_tenant():
            c = crear_consulta_completa(paciente=self.p, profesional=self.perfil, plantilla=None, tipo='PRIMERA',
                                        lugar=None, datos_por_seccion={})
            self.cita.refresh_from_db()
        self.assertEqual((self.cita.estado, self.cita.consulta_id), ('ATENDIDA', c.pk))

    def test_abrir_desde_la_ficha_tambien(self):
        r = self.cliente.post(f'/pacientes/{self.p.pk}/consultas/nueva/', {'tipo': 'PRIMERA'})
        self.assertEqual(r.status_code, 302)
        with self.en_tenant():
            self.cita.refresh_from_db()
        self.assertEqual(self.cita.estado, 'ATENDIDA')

    def test_comando_revisa_y_aplica(self):
        with self.en_tenant():
            c = abrir_consulta(paciente=self.p, profesional=self.perfil)        # como quedó en producción
        salida = StringIO()
        call_command('citas_sin_consulta', consultorio=self.tenant.slug, stdout=salida)
        self.assertIn(f'cita {self.cita.pk}', salida.getvalue())
        self.assertNotIn('Paz', salida.getvalue())                             # sin nombres
        with self.en_tenant():
            self.cita.refresh_from_db()
        self.assertEqual(self.cita.estado, 'PROGRAMADA')                       # sin --aplicar no cambia
        call_command('citas_sin_consulta', consultorio=self.tenant.slug, aplicar=True, stdout=StringIO())
        with self.en_tenant():
            self.cita.refresh_from_db()
        self.assertEqual((self.cita.estado, self.cita.consulta_id), ('ATENDIDA', c.pk))
