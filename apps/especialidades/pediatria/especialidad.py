"""
Pediatría (Fase 13, ADR-034): reemplaza a la especialidad «básica» del mismo código.
Ver docs/roadmap/13_pediatria.md.
"""
from apps.clinica import registro
from apps.clinica.registro import EspecialidadDef, ExtraProcedimientoDef, PanelDef, PlantillaDef, ReporteDef

from .calculos import CALCULOS
from .documentos import DOCUMENTOS
from .secciones import CONSULTA, FICHA

# En pediatría peso y talla van en «Antropometría» (con percentiles): se ocultan de los signos vitales del núcleo.
SIGNOS_PEDIATRICOS = ('nucleo.signos_vitales', {'ajustes': {'ocultos': [
    'peso_kg', 'talla_cm', 'imc', 'superficie_corporal', 'glicemia', 'perimetro_abdominal']}})
FICHA_COLAPSADA = [(s.codigo, {'colapsada': True}) for s in FICHA]

# Igual que la consulta de Pediae: tipo · antropometría · signos · motivo y enfermedad actual · examen físico ·
# desarrollo · diagnóstico · tratamiento e indicaciones (+ próxima cita) · récipe · paraclínicos · hábitos.
CONSULTA_PEDIAE = ['ped.tipo', 'ped.antropometria', SIGNOS_PEDIATRICOS, 'nucleo.motivo', 'nucleo.examen_fisico',
                   'ped.desarrollo', ('nucleo.diagnosticos', {'obligatoria': True}), 'nucleo.plan',
                   'nucleo.prescripcion', 'nucleo.ordenes', 'ped.habitos']
PRIMERA = ['ped.tipo', 'nucleo.motivo', 'nucleo.antecedentes', *FICHA_COLAPSADA, 'ped.antropometria',
           SIGNOS_PEDIATRICOS, 'nucleo.examen_fisico', 'ped.desarrollo', 'nucleo.paraclinicos',
           ('nucleo.diagnosticos', {'obligatoria': True}), 'nucleo.plan', 'nucleo.prescripcion', 'nucleo.ordenes',
           'ped.habitos']
CONTROL_SANO = ['ped.tipo', 'ped.antropometria', SIGNOS_PEDIATRICOS, 'nucleo.motivo', 'ped.habitos',
                'ped.desarrollo', 'nucleo.examen_fisico', ('nucleo.diagnosticos', {'obligatoria': True}),
                'nucleo.plan', 'nucleo.prescripcion']

PLANTILLAS = [
    PlantillaDef('Consulta pediátrica', CONSULTA_PEDIAE, predeterminada=True,
                 descripcion='Igual que en Pediae. La ficha pediátrica se llena en la ficha del paciente.'),
    PlantillaDef('Primera consulta con ficha completa', PRIMERA,
                 descripcion='Incluye toda la ficha pediátrica dentro de la consulta.'),
    PlantillaDef('Control de niño sano', CONTROL_SANO, descripcion='Crecimiento, hábitos y desarrollo primero.'),
]



def _extra(nombre):
    def funcion(*args):
        from . import vacunas
        return getattr(vacunas, nombre)(*args)
    return funcion


def _panel(nombre):
    def contexto(request, paciente):
        from . import paneles
        return getattr(paneles, nombre)(request, paciente)
    return contexto


registro.registrar(EspecialidadDef(
    codigo='pediatria', nombre='Pediatría', modulo='apps.especialidades.pediatria', icono='bi-balloon-heart',
    color='#2AACA8', orden=21, secciones=[*FICHA, *CONSULTA], calculos=CALCULOS, plantillas=PLANTILLAS,
    documentos=DOCUMENTOS,
    paneles=[PanelDef('ped_crecimiento', 'Crecimiento', 'pediatria/panel_crecimiento.html', _panel('crecimiento'),
                      orden=10),
             PanelDef('ped_vacunas', 'Vacunas y pesquisas', 'pediatria/panel_vacunas.html',
                      _panel('vacunas_pesquisas'), orden=20)],
    reportes=[ReporteDef('ped_reporte', 'Reporte pediátrico', 'pediatria:reporte', icono='bi-balloon-heart',
                         descripcion='Estado nutricional, edades, vacunas, lactancia, antecedentes y pesquisas.')],
    paginas_paciente=['pediatria:vacunas'],
    extras_procedimiento=[ExtraProcedimientoDef('ped_vacunas', 'pediatria/_procedimiento_vacunas.html',
                                                _extra('contexto_procedimiento'), _extra('guardar_procedimiento'))],
))


def _sincronizar_medicion(consulta, datos):
    from .servicios import sincronizar_medicion
    sincronizar_medicion(consulta, datos)


registro.registrar_al_guardar('ped.antropometria', _sincronizar_medicion)
