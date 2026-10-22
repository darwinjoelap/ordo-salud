"""
Cardiología pediátrica (Fase 15), con el modelo de informe de la Dra. Lyna Sierra.
Ver docs/roadmap/15_cardiologia_pediatrica.md.
"""
from apps.clinica import registro
from apps.clinica.registro import EspecialidadDef, PanelDef, PlantillaDef, ReporteDef

from .calculos import CALCULOS
from .documentos import DOCUMENTOS
from .secciones import CONSULTA, FICHA

# Ajustes de las secciones del núcleo para que la consulta tenga el orden y los nombres de su informe.
MOTIVO = ('nucleo.motivo', {'ajustes': {'opcionales': ['motivo'], 'etiquetas': {
    'motivo': 'Motivo de consulta (resumen)', 'enfermedad_actual': 'Enfermedad actual'}}})
SIGNOS = ('nucleo.signos_vitales', {'ajustes': {
    'ocultos': ['imc', 'fr', 'temperatura', 'glicemia', 'perimetro_abdominal'],
    'etiquetas': {'spo2': 'Sat O₂', 'pa_sistolica': 'TA sistólica', 'pa_diastolica': 'TA diastólica',
                  'fc': 'FC', 'superficie_corporal': 'SC'}}})
EXAMEN = ('nucleo.examen_fisico', {'ajustes': {
    'ocultos': ['piel', 'cabeza_cuello', 'torax', 'abdomen', 'genitales', 'extremidades', 'neurologico'],
    'etiquetas': {'general': 'Examen físico', 'cardiopulmonar': 'Tórax y cardiovascular'}}})
DIAGNOSTICOS = ('nucleo.diagnosticos', {'ajustes': {'opcionales': ['diagnosticos']}})
PLAN = ('nucleo.plan', {'ajustes': {'etiquetas': {
    'plan': 'Comentario (resumen, plan y revaloración)', 'indicaciones': 'Indicaciones a los padres',
    'proximo_control': 'Próximo control (se revalorará)'}}})
ORDENES = ('nucleo.ordenes', {'ajustes': {'etiquetas': {'otros': 'Holter, MAPA, interconsultas y otros'}}})

# Mismo orden que su informe: enfermedad actual · (antecedentes) · examen · EKG · eco · comentario.
CONSULTA_CP = [MOTIVO, 'cp.antecedentes', SIGNOS, EXAMEN, 'cp.ekg', 'cp.eco', DIAGNOSTICOS, PLAN,
               'nucleo.prescripcion', ORDENES]
PRIMERA = [MOTIVO, 'cp.antecedentes', SIGNOS, EXAMEN, 'cp.ekg', 'cp.eco', DIAGNOSTICOS, PLAN, 'nucleo.prescripcion',
           ORDENES]
CONTROL_SIN_ECO = [MOTIVO, 'cp.antecedentes', SIGNOS, EXAMEN, 'cp.ekg', DIAGNOSTICOS, PLAN, 'nucleo.prescripcion', ORDENES,
                   ('cp.eco', {'colapsada': True})]

PLANTILLAS = [
    PlantillaDef('Consulta de cardiología pediátrica', CONSULTA_CP, predeterminada=True,
                 descripcion='Como el informe de la doctora, con los antecedentes en la misma pantalla.'),
    PlantillaDef('Primera consulta (con antecedentes)', PRIMERA,
                 descripcion='Incluye los antecedentes personales dentro de la consulta.'),
    PlantillaDef('Control (eco opcional)', CONTROL_SIN_ECO,
                 descripcion='Para controles donde no siempre se repite el ecocardiograma.'),
]


def _panel(request, paciente):
    from . import paneles
    return paneles.resumen(request, paciente)


registro.registrar(EspecialidadDef(
    codigo='cardiologia_pediatrica', nombre='Cardiología pediátrica',
    modulo='apps.especialidades.cardiologia_pediatrica', icono='bi-heart-pulse', color='#C0392B', orden=24,
    secciones=[*FICHA, *CONSULTA], calculos=CALCULOS, plantillas=PLANTILLAS, documentos=DOCUMENTOS,
    paneles=[PanelDef('cp_resumen', 'Resumen cardiológico', 'cardiologia_pediatrica/panel_resumen.html', _panel,
                      orden=5)],
    reportes=[ReporteDef('cp_reporte', 'Reporte de cardiología pediátrica', 'cardiologia_pediatrica:reporte',
                         icono='bi-heart-pulse',
                         descripcion='Cardiopatías y hallazgos del eco, FEVI, ritmo, enfermedades y edades.')],
))
