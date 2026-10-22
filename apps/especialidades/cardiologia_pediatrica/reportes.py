"""
Reporte de cardiología pediátrica: cardiopatías y hallazgos del eco, FEVI, ritmo del EKG, enfermedades más frecuentes
y edades. Mismos filtros y alcance que «Reportes». Solo conteos.
"""
from collections import Counter

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render

from apps.reportes import exportar
from apps.reportes import selectors as rs

from . import informe
from .secciones import RITMOS

GRUPOS_EDAD = [('Menor de 1 año', 0, 1), ('1 a 5 años', 1, 6), ('6 a 11 años', 6, 12), ('12 a 17 años', 12, 18),
               ('18 años o más', 18, 200)]
TITULO = 'Reporte de cardiología pediátrica'


def datos_reporte(f):
    from apps.clinica.models import RegistroSeccion
    consultas = rs.consultas_de(f).select_related('paciente')
    ids = list(consultas.values_list('pk', flat=True))
    pacientes = {c.paciente_id: c.paciente for c in consultas}
    ecos = list(RegistroSeccion.objects.filter(consulta_id__in=ids, seccion__codigo='cp.eco')
                .select_related('consulta').order_by('consulta__fecha_hora'))
    ekgs = list(RegistroSeccion.objects.filter(consulta_id__in=ids, seccion__codigo='cp.ekg'))
    ultimo_eco = {}
    for r in ecos:                                   # el último eco de cada paciente en el período
        ultimo_eco[r.consulta.paciente_id] = r.datos
    hallazgos, fevi = Counter(), Counter()
    for datos in ultimo_eco.values():
        hallazgos.update({h.split(' · ')[0] for h in informe.hallazgos(datos)})
        valor = informe.fevi(datos)
        if valor is not None:
            fevi['< 40 %' if valor < 40 else '40 a 54 %' if valor < 55 else '55 % o más'] += 1
    ritmos = Counter(r.datos.get('ritmo') for r in ekgs if r.datos.get('ritmo'))
    nombres_ritmo = dict(RITMOS)
    edades = Counter()
    for p in pacientes.values():
        if p.edad_anios is not None:
            edades[next(e for e, a, b in GRUPOS_EDAD if a <= p.edad_anios < b)] += 1
    sin_hallazgos = sum(1 for datos in ultimo_eco.values() if not informe.hallazgos(datos))
    return {
        'consultas': len(ids), 'pacientes': len(pacientes), 'ecos': len(ecos), 'ekgs': len(ekgs),
        'con_cardiopatia': len(ultimo_eco) - sin_hallazgos, 'sin_hallazgos': sin_hallazgos,
        'hallazgos': rs._barras(hallazgos.most_common(15)),
        'fevi': rs._barras([(k, fevi.get(k, 0)) for k in ('55 % o más', '40 a 54 %', '< 40 %')]),
        'ritmos': rs._barras([(nombres_ritmo.get(k, k), v) for k, v in ritmos.most_common()]),
        'edades': rs._barras([(e, edades.get(e, 0)) for e, _, _ in GRUPOS_EDAD]),
        'morbilidad': rs.morbilidad_de(consultas),
    }


def _exportable(d):
    kpis = [('Consultas', d['consultas']), ('Pacientes', d['pacientes']), ('Ecocardiogramas', d['ecos']),
            ('EKG', d['ekgs']), ('Pacientes con hallazgos', d['con_cardiopatia'])]
    bloques = [('Enfermedades y hallazgos', [('Enfermedades más frecuentes', d['morbilidad']),
                                            ('Hallazgos del ecocardiograma', d['hallazgos'])]),
               ('Función y ritmo', [('FEVI (Teichholz)', d['fevi']), ('Ritmo en el EKG', d['ritmos'])]),
               ('Pacientes', [('Grupos de edad', d['edades'])])]
    return kpis, bloques, ()


@login_required
def tablero(request):
    if not rs.puede_ver_reportes(request):
        raise PermissionDenied
    f = rs.filtros_de(request)
    datos = datos_reporte(f)
    formato = request.GET.get('formato')
    if formato in ('pdf', 'excel'):
        return exportar.responder_especialidad(request, f, formato, 'reporte_cardiologia', TITULO, *_exportable(datos),
                                               nota='Hallazgos = último eco de cada paciente en el período.')
    return render(request, 'cardiologia_pediatrica/reporte.html', {
        'titulo': TITULO, 'filtros': f, **datos, 'rangos': rs.rangos_rapidos(),
        'pestanas': rs.pestanas(request, 'cp_reporte'),
        'query_sin_formato': rs.query_sin(request), 'query_sin_dx': rs.query_sin(request, 'diagnostico')})
