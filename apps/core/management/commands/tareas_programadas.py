"""
Tareas periódicas de Ordo Salud. En Railway: servicio Cron con este comando (railway.cron.json).
  python manage.py tareas_programadas              → todo
  python manage.py tareas_programadas --solo tasa
"""
from datetime import timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'Tasa BCV, cierre de consultas vencidas y limpiezas (para el cron de Railway).'

    def add_arguments(self, parser):
        parser.add_argument('--solo', choices=['tasa', 'limpieza', 'consultas'])

    def handle(self, *args, solo=None, **opciones):
        if solo in (None, 'tasa'):
            call_command('actualizar_tasa_bcv', stdout=self.stdout, stderr=self.stderr)
        if solo in (None, 'limpieza'):
            from django.contrib.sessions.models import Session
            n, _ = Session.objects.filter(expire_date__lt=timezone.now() - timedelta(days=1)).delete()
            self.stdout.write(f'Sesiones vencidas eliminadas: {n}')
            from apps.offline.middleware import limpiar_viejas
            self.stdout.write(f'Envíos sin conexión antiguos eliminados: {limpiar_viejas()}')
        if solo in (None, 'consultas'):
            from apps.clinica.consultas import cerrar_vencidas
            self.stdout.write(f'Consultas cerradas automáticamente: {cerrar_vencidas()}')
