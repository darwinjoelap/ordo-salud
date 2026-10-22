"""
Rehace las plantillas iniciales de una especialidad con la definición actual de su módulo:

    python manage.py refrescar_plantillas ginecologia                 # todos los consultorios con GO
    python manage.py refrescar_plantillas ginecologia --consultorio dra-ruiz

Las plantillas propias de los médicos y las consultas ya abiertas no cambian. Los cambios hechos a mano sobre las
plantillas del sistema de esa especialidad se pierden.
"""
from django.core.management.base import BaseCommand, CommandError

from apps.clinica.servicios import refrescar_plantillas_sistema
from apps.core.tenancy import usando_tenant
from apps.plataforma.models import Especialidad, Tenant


class Command(BaseCommand):
    help = 'Rehace las plantillas del sistema de una especialidad con la definición actual del módulo.'

    def add_arguments(self, parser):
        parser.add_argument('especialidad', help='Código: ginecologia, pediatria…')
        parser.add_argument('--consultorio', help='Enlace del consultorio (por defecto, todos los que la tienen).')

    def handle(self, *args, especialidad, consultorio=None, **opciones):
        esp = Especialidad.objects.filter(codigo=especialidad).first()
        if esp is None:
            raise CommandError(f'No existe la especialidad «{especialidad}».')
        tenants = Tenant.objects.filter(especialidades=esp)
        if consultorio:
            tenants = tenants.filter(slug=consultorio)
            if not tenants.exists():
                raise CommandError(f'El consultorio «{consultorio}» no existe o no tiene {esp.nombre}.')
        for tenant in tenants:
            with usando_tenant(tenant):
                n = refrescar_plantillas_sistema(esp)
            self.stdout.write(self.style.SUCCESS(f'{tenant.nombre}: {n} plantilla(s) de {esp.nombre} rehechas.'))
