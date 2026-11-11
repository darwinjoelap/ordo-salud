"""Inicio: las consultas sin cerrar se ven arriba, con enlace y, si están vencidas, qué les falta."""
from datetime import timedelta

from django.utils import timezone

from apps.clinica.consultas import abrir_consulta
from apps.clinica.models import Consulta
from apps.equipo.models import Membresia
from apps.pacientes.models import Paciente

from .base import BaseTest


class InicioEnCursoTest(BaseTest):
    def test_enlace_y_vencida(self):
        with self.en_tenant():
            p = Paciente.objects.create(nombres='Rosa', apellidos='Paz', sexo='F')
            c = abrir_consulta(paciente=p, profesional=Membresia.objects.get(usuario=self.titular).perfil)
        r = self.cliente.get('/')
        self.assertContains(r, 'id="en-curso"')
        self.assertContains(r, f'/consultas/{c.pk}/', count=2)          # tarjeta (única) + lista
        self.assertNotContains(r, 'No se puede cerrar sola')
        with self.en_tenant():
            Consulta.objects.filter(pk=c.pk).update(fecha_hora=timezone.now() - timedelta(days=3))
        r = self.cliente.get('/')
        self.assertTrue(r.context['en_curso'][0].vencida)
        if r.context['en_curso'][0].falta:
            self.assertContains(r, 'No se puede cerrar sola')
        else:
            self.assertContains(r, 'Se cerrará sola')
