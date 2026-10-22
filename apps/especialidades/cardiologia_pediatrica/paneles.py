"""Panel de cardiología pediátrica en la ficha del paciente: último EKG y eco, hallazgos y próximo control."""
from django.urls import reverse
from django.utils import timezone

from . import informe

ESPECIALIDAD = 'cardiologia_pediatrica'


def resumen(request, paciente):
    from apps.clinica.models import Consulta, RegistroSeccion
    from apps.documentos.registro import documento
    registros = (RegistroSeccion.objects.filter(consulta__paciente=paciente, seccion__codigo__in=['cp.eco', 'cp.ekg'])
                 .exclude(consulta__estado=Consulta.Estado.ANULADA).select_related('consulta', 'seccion')
                 .order_by('-consulta__fecha_hora'))
    ultimo = {}
    for r in registros:
        ultimo.setdefault(r.seccion.codigo, r)
    if not ultimo:
        return {'vacio': True}
    eco, ekg = ultimo.get('cp.eco'), ultimo.get('cp.ekg')
    consulta = (eco or ekg).consulta
    puede_informe = (request.membresia.perfil_activo is not None and documento('cp_informe') is not None
                     and consulta.profesional_id == request.membresia.perfil_activo.pk)
    return {
        'consulta': consulta, 'fecha': timezone.localtime(consulta.fecha_hora).date(),
        'ekg': informe.ekg_linea(ekg.datos) if ekg else '',
        'hallazgos': informe.hallazgos(eco.datos) if eco else [],
        'fevi': (eco.datos.get('fevi') or (f"{informe.fevi(eco.datos)} %" if informe.fevi(eco.datos) is not None
                                           else '')) if eco else '',
        'tapse': informe.num(eco.datos.get('tapse'), 1) if eco else '',
        'informe_url': (f"{reverse('documentos:emitir', args=['cp_informe'])}?consulta={consulta.pk}"
                        if puede_informe else ''),
    }
