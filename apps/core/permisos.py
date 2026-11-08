"""
Permisos por rol. Una sola tabla: rol → acciones (ADR-005).

- El rol vive en la membresía (TITULAR, ADMIN, MEDICO, ASISTENTE).
- Lo clínico depende de ser PROFESIONAL (tener perfil profesional activo), no del rol:
  un médico dueño de su consultorio es TITULAR y profesional a la vez.

Uso en vistas:     @requiere('pacientes.gestionar')
Uso en plantillas: {% if 'pacientes.gestionar' in permisos %}
"""
from functools import wraps

from django.core.exceptions import PermissionDenied
from django.db import models


class Rol(models.TextChoices):
    TITULAR = 'TITULAR', 'Titular'
    ADMIN = 'ADMIN', 'Administrador'
    MEDICO = 'MEDICO', 'Médico'
    ASISTENTE = 'ASISTENTE', 'Asistente'


TODOS = {Rol.TITULAR, Rol.ADMIN, Rol.MEDICO, Rol.ASISTENTE}
GESTION = {Rol.TITULAR, Rol.ADMIN}
PROFESIONAL = 'PROFESIONAL'          # pseudo-rol: membresía con perfil profesional activo

PERMISOS = {
    # Consultorio y equipo
    'tenant.configurar': GESTION,
    'usuarios.gestionar': GESTION,
    'tasa.cargar': GESTION,
    'servicios.gestionar': GESTION,
    # Pacientes (ficha base, sin contenido clínico)
    'pacientes.ver': TODOS,
    'pacientes.gestionar': TODOS,
    # Agenda
    'agenda.ver': TODOS,
    'agenda.gestionar': TODOS,
    # Clínico: solo profesionales
    'historia.ver': {PROFESIONAL},
    'consultas.crear': {PROFESIONAL},
    'plantillas.propias': {PROFESIONAL},
    'plantillas.clinica': GESTION,       # plantillas compartidas y secciones personalizadas del tenant
    # Cobros y reportes
    'cobros.gestionar': GESTION | {Rol.ASISTENTE},
    'reportes.ver': GESTION,
    'reportes.propios': {PROFESIONAL},
}


# Lo que exige un perfil profesional propio (firma la consulta o el reporte): el soporte no lo tiene
SOLO_CON_PERFIL = {'consultas.crear', 'plantillas.propias', 'reportes.propios'}


def es_soporte(membresia):
    """Superusuario de Ordo Salud dentro de un consultorio (membresía virtual, ADR-057)."""
    return bool(getattr(membresia, 'soporte', False))


def permisos_de(membresia):
    """Conjunto de códigos que tiene una membresía (o vacío si no hay)."""
    if membresia is None:
        return set()
    if es_soporte(membresia):             # control total, incluidas las historias (ADR-057)
        return set(PERMISOS) - SOLO_CON_PERFIL
    claves = {membresia.rol}
    if getattr(membresia, 'es_profesional', False):
        claves.add(PROFESIONAL)
    return {codigo for codigo, roles in PERMISOS.items() if claves & roles}


def tiene_permiso(request, codigo):
    if codigo not in PERMISOS:
        raise ValueError(f'Permiso desconocido: {codigo}')
    return codigo in permisos_de(getattr(request, 'membresia', None))


def requiere(codigo):
    """Decorador: 403 si la membresía activa no tiene el permiso."""
    if codigo not in PERMISOS:
        raise ValueError(f'Permiso desconocido: {codigo}')

    def decorador(vista):
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            if not tiene_permiso(request, codigo):
                raise PermissionDenied
            return vista(request, *args, **kwargs)
        return envoltura
    return decorador
