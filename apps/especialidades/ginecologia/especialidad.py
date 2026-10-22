"""
Ginecología y obstetricia (Fase 14): reemplaza a la especialidad «básica» del mismo código.
Ver docs/roadmap/14_ginecologia.md.
"""
from apps.clinica import registro
from apps.clinica.registro import EspecialidadDef, PanelDef, PlantillaDef, ReporteDef

from .calculos import CALCULOS
from .documentos import DOCUMENTOS
from .secciones import CONSULTA, FICHA

# Como en Ginea, en la consulta van peso y tensión arterial; se ocultan las medidas que no usa.
# Consulta con los mismos campos y nombres que Ginea (ajustes de plantilla sobre las secciones del núcleo).
SIGNOS_GO = ('nucleo.signos_vitales', {'ajustes': {'ocultos': [
    'talla_cm', 'imc', 'superficie_corporal', 'fc', 'fr', 'temperatura', 'spo2', 'glicemia', 'perimetro_abdominal'],
    'etiquetas': {'pa_sistolica': 'Tensión arterial (sistólica)', 'pa_diastolica': 'Tensión arterial (diastólica)'}}})
EXAMEN = ('nucleo.examen_fisico', {'ajustes': {'ocultos': [
    'piel', 'cabeza_cuello', 'torax', 'cardiopulmonar', 'abdomen', 'genitales', 'extremidades', 'neurologico'],
    'etiquetas': {'general': 'Examen físico'}}})
PLAN = ('nucleo.plan', {'ajustes': {'etiquetas': {'plan': 'Tratamiento', 'indicaciones': 'Indicaciones',
                                                  'proximo_control': 'Próxima cita'}}})
ORDENES = ('nucleo.ordenes', {'ajustes': {'ocultos': ['imagenes', 'otros'],
                                          'etiquetas': {'laboratorio': 'Exámenes solicitados'}}})
FICHA_COLAPSADA = [(s.codigo, {'colapsada': True}) for s in FICHA]
# En Ginea el motivo y el diagnóstico no son obligatorios (la doctora lo pidió así): se respetan.
MOTIVO = ('nucleo.motivo', {'ajustes': {'opcionales': ['motivo'], 'etiquetas': {
    'motivo': 'Motivo / notas adicionales', 'enfermedad_actual': 'Síntomas actuales'}}})
DIAGNOSTICOS = ('nucleo.diagnosticos', {'ajustes': {'opcionales': ['diagnosticos']}})
TIPO_PRENATAL = ('go.tipo', {'ajustes': {'por_defecto': {'tipo': 'PRENATAL'}}})

# Igual que la consulta de Ginea: datos (peso, TA) · motivo y síntomas · examen físico · ecografía, colposcopia,
# imágenes · diagnóstico · tratamiento e indicaciones (+ próxima cita) · récipe · exámenes solicitados ·
# control prenatal (solo si aplica) · actualizar ficha (FUR, citología).
CONSULTA_GINEA = ['go.tipo', SIGNOS_GO, MOTIVO, EXAMEN, 'go.estudios', DIAGNOSTICOS, PLAN, 'nucleo.prescripcion',
                  ORDENES, 'go.notas', ('go.prenatal', {'colapsada': True}), ('go.actualizar', {'colapsada': True})]
PRENATAL = [TIPO_PRENATAL, SIGNOS_GO, 'go.prenatal', MOTIVO, EXAMEN, 'go.estudios', DIAGNOSTICOS, PLAN,
            'nucleo.prescripcion', ORDENES, 'go.notas', ('go.actualizar', {'colapsada': True})]
PRIMERA = ['go.tipo', SIGNOS_GO, MOTIVO, 'nucleo.antecedentes', *FICHA_COLAPSADA, EXAMEN, 'go.estudios',
           DIAGNOSTICOS, PLAN, 'nucleo.prescripcion', ORDENES, 'go.notas', ('go.prenatal', {'colapsada': True})]

PLANTILLAS = [
    PlantillaDef('Consulta ginecológica', CONSULTA_GINEA, predeterminada=True,
                 descripcion='Igual que en Ginea. La ficha ginecológica se llena en la ficha de la paciente.'),
    PlantillaDef('Control prenatal', PRENATAL,
                 descripcion='Control del embarazo primero: EG y FPP calculadas, altura uterina, FCF.'),
    PlantillaDef('Primera consulta con ficha completa', PRIMERA,
                 descripcion='Incluye toda la ficha ginecológica dentro de la consulta.'),
]


def _panel(nombre):
    def contexto(request, paciente):
        from . import paneles
        return getattr(paneles, nombre)(request, paciente)
    return contexto


registro.registrar(EspecialidadDef(
    codigo='ginecologia', nombre='Ginecología y obstetricia', modulo='apps.especialidades.ginecologia',
    icono='bi-gender-female', color='#B04A86', orden=22, secciones=[*FICHA, *CONSULTA], calculos=CALCULOS,
    plantillas=PLANTILLAS, documentos=DOCUMENTOS,
    paneles=[PanelDef('go_embarazo', 'Embarazo en curso', 'ginecologia/panel_embarazo.html', _panel('embarazo'),
                      orden=5),
             PanelDef('go_resumen', 'Resumen ginecológico', 'ginecologia/panel_resumen.html', _panel('resumen'),
                      orden=10)],
    reportes=[ReporteDef('go_reporte', 'Reporte de ginecología', 'ginecologia:reporte', icono='bi-gender-female',
                         descripcion='Prenatales, embarazos en curso, métodos, citología, VIH/VPH, antecedentes.')],
))


def _sincronizar_control(consulta, datos):
    from .servicios import sincronizar_control
    sincronizar_control(consulta, datos)


def _desde_actualizar(consulta, datos):
    from .servicios import desde_actualizar
    desde_actualizar(consulta, datos)


def _inicial_prenatal(consulta):
    from .servicios import inicial_prenatal
    return inicial_prenatal(consulta)


registro.registrar_al_guardar('go.prenatal', _sincronizar_control)
registro.registrar_al_guardar('go.actualizar', _desde_actualizar)
registro.registrar_inicial('go.prenatal', _inicial_prenatal)
