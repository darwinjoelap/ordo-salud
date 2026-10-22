"""
Secciones del núcleo: comunes a toda especialidad. Se registran en ClinicaConfig.ready().

Fase 07: las secciones nucleo.signos_vitales, nucleo.diagnosticos y nucleo.prescripcion además se copian a
tablas (SignosVitales, DiagnosticoConsulta, ItemPrescripcion) para graficar y contar.
"""
from decimal import Decimal

from .registro import PlantillaDef, SeccionDef, registrar_nucleo


def imc(datos, contexto):
    peso, talla = datos.get('peso_kg'), datos.get('talla_cm')
    if not peso or not talla:
        return None
    metros = Decimal(str(talla)) / 100
    return float((Decimal(str(peso)) / (metros * metros)).quantize(Decimal('0.1')))


def superficie_corporal(datos, contexto):
    """Mosteller: √(talla cm × peso kg / 3600)."""
    peso, talla = datos.get('peso_kg'), datos.get('talla_cm')
    if not peso or not talla:
        return None
    return round((float(peso) * float(talla) / 3600) ** 0.5, 2)


T = 'texto_largo'

SECCIONES = [
    SeccionDef('nucleo.motivo', 'Motivo de consulta y enfermedad actual', orden=10, esquema={'campos': [
        {'clave': 'motivo', 'tipo': T, 'etiqueta': 'Motivo de consulta', 'filas': 2, 'requerido': True},
        {'clave': 'enfermedad_actual', 'tipo': T, 'etiqueta': 'Enfermedad actual', 'filas': 4},
    ]}),
    SeccionDef('nucleo.antecedentes', 'Antecedentes generales', ambito='PACIENTE', orden=20,
               descripcion='Alergias, medicación, enfermedades crónicas, cirugías… (ficha del paciente).',
               esquema={'campos': [
                   {'clave': 'alergias', 'tipo': T, 'etiqueta': 'Alergias', 'filas': 1, 'ancho': 6},
                   {'clave': 'medicacion_actual', 'tipo': T, 'etiqueta': 'Medicación actual', 'filas': 1, 'ancho': 6},
                   {'clave': 'enfermedades_cronicas', 'tipo': T, 'etiqueta': 'Enfermedades crónicas', 'filas': 1,
                    'ancho': 6},
                   {'clave': 'cirugias', 'tipo': T, 'etiqueta': 'Cirugías', 'filas': 1, 'ancho': 6},
                   {'clave': 'hospitalizaciones', 'tipo': T, 'etiqueta': 'Hospitalizaciones', 'filas': 1, 'ancho': 6},
                   {'clave': 'transfusiones', 'tipo': T, 'etiqueta': 'Transfusiones', 'filas': 1, 'ancho': 6},
                   {'clave': 'habitos', 'tipo': T, 'etiqueta': 'Hábitos', 'filas': 1, 'ancho': 6},
                   {'clave': 'antecedentes_familiares', 'tipo': T, 'etiqueta': 'Antecedentes familiares',
                    'filas': 1, 'ancho': 6},
                   {'clave': 'otros', 'tipo': T, 'etiqueta': 'Otros', 'filas': 1},
               ]}),
    SeccionDef('nucleo.signos_vitales', 'Signos vitales y medidas', orden=30, esquema={'campos': [
        {'clave': 'peso_kg', 'tipo': 'numero', 'etiqueta': 'Peso', 'unidad': 'kg', 'min': 0.3, 'max': 400,
         'decimales': 2, 'ancho': 3},
        {'clave': 'talla_cm', 'tipo': 'numero', 'etiqueta': 'Talla', 'unidad': 'cm', 'min': 20, 'max': 250,
         'decimales': 1, 'ancho': 3},
        {'clave': 'imc', 'tipo': 'calculado', 'etiqueta': 'IMC', 'unidad': 'kg/m²', 'funcion': 'nucleo.imc',
         'decimales': 1, 'ancho': 3},
        {'clave': 'superficie_corporal', 'tipo': 'calculado', 'etiqueta': 'Superficie corporal', 'unidad': 'm²',
         'funcion': 'nucleo.superficie_corporal', 'decimales': 2, 'ancho': 3},
        {'clave': 'pa_sistolica', 'tipo': 'numero', 'etiqueta': 'PA sistólica', 'unidad': 'mmHg', 'min': 40,
         'max': 300, 'decimales': 0, 'ancho': 3},
        {'clave': 'pa_diastolica', 'tipo': 'numero', 'etiqueta': 'PA diastólica', 'unidad': 'mmHg', 'min': 20,
         'max': 200, 'decimales': 0, 'ancho': 3},
        {'clave': 'fc', 'tipo': 'numero', 'etiqueta': 'Frec. cardíaca', 'unidad': 'lpm', 'min': 20, 'max': 300,
         'decimales': 0, 'ancho': 3},
        {'clave': 'fr', 'tipo': 'numero', 'etiqueta': 'Frec. respiratoria', 'unidad': 'rpm', 'min': 4, 'max': 120,
         'decimales': 0, 'ancho': 3},
        {'clave': 'temperatura', 'tipo': 'numero', 'etiqueta': 'Temperatura', 'unidad': '°C', 'min': 30, 'max': 45,
         'decimales': 1, 'ancho': 3},
        {'clave': 'spo2', 'tipo': 'numero', 'etiqueta': 'SpO₂', 'unidad': '%', 'min': 40, 'max': 100,
         'decimales': 0, 'ancho': 3},
        {'clave': 'glicemia', 'tipo': 'numero', 'etiqueta': 'Glicemia capilar', 'unidad': 'mg/dL', 'min': 10,
         'max': 1500, 'decimales': 0, 'ancho': 3},
        {'clave': 'perimetro_abdominal', 'tipo': 'numero', 'etiqueta': 'Perímetro abdominal', 'unidad': 'cm',
         'min': 20, 'max': 250, 'decimales': 1, 'ancho': 3},
    ]}),
    SeccionDef('nucleo.examen_fisico', 'Examen físico', orden=40, esquema={'campos': [
        {'clave': 'general', 'tipo': T, 'etiqueta': 'Aspecto general', 'filas': 2},
        {'clave': 'piel', 'tipo': T, 'etiqueta': 'Piel y faneras', 'filas': 1, 'ancho': 6},
        {'clave': 'cabeza_cuello', 'tipo': T, 'etiqueta': 'Cabeza y cuello', 'filas': 1, 'ancho': 6},
        {'clave': 'torax', 'tipo': T, 'etiqueta': 'Tórax', 'filas': 1, 'ancho': 6},
        {'clave': 'cardiopulmonar', 'tipo': T, 'etiqueta': 'Cardiopulmonar', 'filas': 1, 'ancho': 6},
        {'clave': 'abdomen', 'tipo': T, 'etiqueta': 'Abdomen', 'filas': 1, 'ancho': 6},
        {'clave': 'genitales', 'tipo': T, 'etiqueta': 'Genitales', 'filas': 1, 'ancho': 6},
        {'clave': 'extremidades', 'tipo': T, 'etiqueta': 'Extremidades', 'filas': 1, 'ancho': 6},
        {'clave': 'neurologico', 'tipo': T, 'etiqueta': 'Neurológico', 'filas': 1, 'ancho': 6},
    ]}),
    SeccionDef('nucleo.paraclinicos', 'Resultados de exámenes (paraclínicos)', orden=50, esquema={'campos': [
        {'clave': 'laboratorio', 'tipo': T, 'etiqueta': 'Laboratorio', 'filas': 2},
        {'clave': 'imagenes', 'tipo': T, 'etiqueta': 'Imágenes y otros estudios', 'filas': 2},
    ]}),
    SeccionDef('nucleo.diagnosticos', 'Diagnósticos', orden=60, esquema={'campos': [
        {'clave': 'diagnosticos', 'tipo': 'tabla', 'etiqueta': 'Diagnósticos', 'requerido': True, 'filas': 2,
         'subcampos': [
             {'clave': 'codigo', 'tipo': 'texto', 'etiqueta': 'Código', 'ancho': 2},
             {'clave': 'descripcion', 'tipo': 'texto', 'etiqueta': 'Diagnóstico', 'ancho': 7},
             {'clave': 'certeza', 'tipo': 'opcion', 'etiqueta': 'Certeza', 'ancho': 3,
              'opciones': [['PRESUNTIVO', 'Presuntivo'], ['DEFINITIVO', 'Definitivo']]},
         ]},
    ]}),
    SeccionDef('nucleo.plan', 'Plan e indicaciones', orden=70, esquema={'campos': [
        {'clave': 'plan', 'tipo': T, 'etiqueta': 'Plan / tratamiento', 'filas': 3},
        {'clave': 'indicaciones', 'tipo': T, 'etiqueta': 'Indicaciones al paciente', 'filas': 3},
        {'clave': 'proximo_control', 'tipo': 'fecha', 'etiqueta': 'Próximo control', 'ancho': 4},
    ]}),
    SeccionDef('nucleo.prescripcion', 'Récipe (prescripción)', orden=80, esquema={'campos': [
        {'clave': 'medicamentos', 'tipo': 'tabla', 'etiqueta': 'Medicamentos', 'filas': 3, 'subcampos': [
            {'clave': 'medicamento', 'tipo': 'texto', 'etiqueta': 'Medicamento y presentación', 'ancho': 4},
            {'clave': 'dosis', 'tipo': 'texto', 'etiqueta': 'Dosis', 'ancho': 2},
            {'clave': 'frecuencia', 'tipo': 'texto', 'etiqueta': 'Frecuencia', 'ancho': 2},
            {'clave': 'duracion', 'tipo': 'texto', 'etiqueta': 'Duración', 'ancho': 2},
            {'clave': 'cantidad', 'tipo': 'texto', 'etiqueta': 'Cantidad', 'ancho': 2},
        ]},
        {'clave': 'observaciones', 'tipo': T, 'etiqueta': 'Indicaciones del récipe', 'filas': 2},
    ]}),
    SeccionDef('nucleo.ordenes', 'Órdenes de exámenes', orden=90, esquema={'campos': [
        {'clave': 'laboratorio', 'tipo': T, 'etiqueta': 'Laboratorio', 'filas': 2, 'ancho': 6},
        {'clave': 'imagenes', 'tipo': T, 'etiqueta': 'Imágenes', 'filas': 2, 'ancho': 6},
        {'clave': 'otros', 'tipo': T, 'etiqueta': 'Otros estudios / interconsultas', 'filas': 2},
    ]}),
]

PLANTILLAS = [
    PlantillaDef('Consulta', ['nucleo.motivo', 'nucleo.antecedentes', 'nucleo.signos_vitales',
                              'nucleo.examen_fisico', 'nucleo.paraclinicos', 'nucleo.diagnosticos', 'nucleo.plan',
                              'nucleo.prescripcion', 'nucleo.ordenes'], predeterminada=True),
]


def registrar():
    registrar_nucleo(SECCIONES, calculos={'nucleo.imc': imc, 'nucleo.superficie_corporal': superficie_corporal},
                     plantillas=PLANTILLAS)
