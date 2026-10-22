#!/usr/bin/env python
"""Utilidad de línea de comandos de Django para Ordo Salud."""
import os
import sys


def main():
    # Local: settings de desarrollo. Railway define DJANGO_SETTINGS_MODULE=config.settings.prod
    # Tests: settings propios (contraseñas rápidas, media temporal)
    por_defecto = 'config.settings.test' if len(sys.argv) > 1 and sys.argv[1] == 'test' else 'config.settings.dev'
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', por_defecto)
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            'No se pudo importar Django. ¿Activaste el venv? '
            '(.\\venv\\Scripts\\Activate.ps1)'
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
