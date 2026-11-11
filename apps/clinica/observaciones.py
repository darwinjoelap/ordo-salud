"""
Observación importante (ADR-065). Cada consulta puede dejar una nota para el médico:
- sin fijar: se recuerda SOLO en la consulta siguiente del paciente;
- fija: se recuerda en todas las consultas (y en la ficha) hasta que un médico la suelte.
La ven los médicos (todos, o solo quien la escribió, según la configuración); asistentes y administración no.
"""
from apps.core.permisos import es_soporte

from .models import Consulta

MAX = 1000


def puede_ver(membresia):
    return membresia is not None and (membresia.perfil_activo is not None or es_soporte(membresia))


def _base(membresia, paciente):
    qs = (Consulta.objects.filter(paciente=paciente).exclude(estado=Consulta.Estado.ANULADA)
          .select_related('profesional__membresia__usuario'))
    if membresia.tenant.configuracion.observaciones_visibles == 'AUTOR' and not es_soporte(membresia):
        qs = qs.filter(profesional=membresia.perfil_activo)
    return qs


def para(membresia, paciente, consulta=None):
    """
    {'fijas': [...], 'anterior': Consulta | None} que debe ver este médico. `consulta`: la que tiene abierta
    (nueva sin guardar o en edición); sin ella (ficha del paciente), la última consulta.
    """
    if not puede_ver(membresia):
        return {'fijas': [], 'anterior': None}
    qs = _base(membresia, paciente)
    if consulta is not None and consulta.pk:
        qs = qs.exclude(pk=consulta.pk)
        previas = qs.filter(fecha_hora__lt=consulta.fecha_hora)
    else:
        previas = qs
    anterior = previas.order_by('-fecha_hora').first()
    if anterior is not None and (anterior.observacion_fija or not anterior.observacion_importante.strip()):
        anterior = None                 # la fija ya sale en su lista
    fijas = list(qs.filter(observacion_fija=True).exclude(observacion_importante='').order_by('-fecha_hora'))
    return {'fijas': fijas, 'anterior': anterior}


def guardar(consulta, datos):
    """Desde el POST del formulario de la consulta."""
    texto = (datos.get('observacion_importante') or '').strip()[:MAX]
    fija = bool(texto) and datos.get('observacion_fija') in ('on', '1', 'true')
    if (texto, fija) != (consulta.observacion_importante, consulta.observacion_fija):
        Consulta.objects.filter(pk=consulta.pk).update(observacion_importante=texto, observacion_fija=fija)
        consulta.observacion_importante, consulta.observacion_fija = texto, fija


def soltable(membresia, paciente, pk):
    """La consulta con observación fija que este médico puede soltar, o None."""
    if not puede_ver(membresia):
        return None
    return _base(membresia, paciente).filter(pk=pk, observacion_fija=True).first()
