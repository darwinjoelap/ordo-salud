"""
Secciones de ginecología y obstetricia (portadas de la ficha y la consulta de Ginea, ver docs/roadmap/14_ginecologia.md).

Ámbito PACIENTE = ficha ginecológica (se llena una vez, pasa a las consultas siguientes y guarda historial).
Ámbito CONSULTA = lo que se registra en cada consulta.
"""
from apps.clinica.registro import SeccionDef

T = 'texto_largo'
SI = {'igual': True}
CON_HISTERECTOMIA = {'campo': 'histerectomia', 'igual': True}

TIPOS_CONSULTA = [['GINECOLOGICA', 'Ginecológica'], ['PRENATAL', 'Control prenatal'],
                  ['PLANIFICACION', 'Planificación familiar'], ['SEGUIMIENTO', 'Seguimiento / resultados'],
                  ['PUERPERIO', 'Puerperio']]

# ── Ficha ginecológica (PACIENTE) — mismos campos, etiquetas y orden que la ficha clínica de Ginea ─────────────
# (Ginea `pacientes/forms.py::PacienteCompletoForm`). Los datos personales y alergias, enfermedades crónicas,
# cirugías y medicación viven en el núcleo (ficha del paciente y «Antecedentes generales»).

PERSONALES = SeccionDef('go.habitos', 'Antecedentes personales', ambito='PACIENTE', orden=21, esquema={'campos': [
    {'clave': 'tabaquismo', 'tipo': 'si_no', 'etiqueta': 'Tabaquismo', 'ancho': 3},
    {'clave': 'alcohol', 'tipo': 'si_no', 'etiqueta': 'Alcoholismo', 'ancho': 3},
    {'clave': 'transfusiones', 'tipo': 'si_no', 'etiqueta': 'Transfusiones', 'ancho': 3},
    {'clave': 'instruccion', 'tipo': 'opcion', 'etiqueta': 'Nivel de instrucción', 'ancho': 3,
     'opciones': [['PRIMARIA', 'Primaria'], ['SECUNDARIA', 'Secundaria'], ['TECNICO', 'Técnico'],
                  ['UNIVERSITARIO', 'Universitario'], ['POSTGRADO', 'Postgrado']]},
]})

FAMILIARES = SeccionDef('go.familiares', 'Antecedentes familiares', ambito='PACIENTE', orden=22, esquema={'campos': [
    {'clave': 'antecedentes', 'tipo': 'opciones', 'etiqueta': 'Antecedentes familiares',
     'opciones': [['CA_MAMA', 'Cáncer de mama'], ['CA_CUELLO', 'Cáncer de cuello uterino'],
                  ['DIABETES', 'Diabetes'], ['HTA', 'Hipertensión']]},
    {'clave': 'autoinmunes', 'tipo': T, 'etiqueta': 'Enfermedades autoinmunes', 'filas': 2, 'ancho': 6},
    {'clave': 'geneticas', 'tipo': T, 'etiqueta': 'Enfermedades genéticas', 'filas': 2, 'ancho': 6},
    {'clave': 'otros', 'tipo': T, 'etiqueta': 'Otros antecedentes familiares', 'filas': 2},
]})

GINECO = SeccionDef('go.gineco', 'Historia gineco-obstétrica', ambito='PACIENTE', orden=23, esquema={'campos': [
    {'clave': 'menarquia', 'tipo': 'numero', 'etiqueta': 'Menarquía (edad)', 'decimales': 0, 'min': 6, 'max': 25,
     'ancho': 3},
    {'clave': 'histerectomia', 'tipo': 'si_no', 'etiqueta': 'Histerectomía', 'ancho': 3},
    # Con histerectomía: tipo (la subtotal conserva el cuello → sigue la citología), ooforectomía (bilateral =
    # menopausia quirúrgica) y el ciclo menstrual queda atenuado como «No aplica» (sin borrar lo anotado).
    {'clave': 'histerectomia_tipo', 'tipo': 'opcion', 'etiqueta': 'Tipo de histerectomía', 'ancho': 3,
     'visible_si': CON_HISTERECTOMIA,
     'opciones': [['TOTAL', 'Total (sin cuello)'], ['SUBTOTAL', 'Subtotal (conserva el cuello)']]},
    {'clave': 'ooforectomia', 'tipo': 'opcion', 'etiqueta': 'Ooforectomía', 'ancho': 3, 'visible_si': CON_HISTERECTOMIA,
     'opciones': [['NO', 'No'], ['UNILATERAL', 'Unilateral'], ['BILATERAL', 'Bilateral']],
     'ayuda': 'Bilateral = menopausia quirúrgica.'},
    {'clave': 'histerectomia_fecha', 'tipo': 'texto', 'etiqueta': 'Histerectomía (año o edad)', 'ancho': 3,
     'visible_si': CON_HISTERECTOMIA},
    {'clave': 'ciclo_dias', 'tipo': 'numero', 'etiqueta': 'Duración del ciclo (días)', 'decimales': 0, 'min': 10,
     'max': 120, 'ancho': 3, 'no_aplica_si': CON_HISTERECTOMIA},
    {'clave': 'ciclo_regular', 'tipo': 'si_no', 'etiqueta': 'Ciclo regular', 'ancho': 3,
     'no_aplica_si': CON_HISTERECTOMIA},
    {'clave': 'fur', 'tipo': 'fecha', 'etiqueta': 'FUR (Fecha última regla)', 'ancho': 3,
     'no_aplica_si': CON_HISTERECTOMIA},
    {'clave': 'ciclo_caracteristicas', 'tipo': T, 'etiqueta': 'Características del sangrado menstrual', 'filas': 2,
     'no_aplica_si': CON_HISTERECTOMIA},
    {'clave': 'gestas', 'tipo': 'numero', 'etiqueta': 'Gestas', 'decimales': 0, 'min': 0, 'max': 30, 'ancho': 2},
    {'clave': 'partos', 'tipo': 'numero', 'etiqueta': 'Partos', 'decimales': 0, 'min': 0, 'max': 30, 'ancho': 2},
    {'clave': 'cesareas', 'tipo': 'numero', 'etiqueta': 'Cesáreas', 'decimales': 0, 'min': 0, 'max': 30, 'ancho': 2},
    {'clave': 'abortos', 'tipo': 'numero', 'etiqueta': 'Abortos', 'decimales': 0, 'min': 0, 'max': 30, 'ancho': 2},
    {'clave': 'formula', 'tipo': 'calculado', 'etiqueta': 'Fórmula obstétrica', 'funcion': 'go.formula', 'ancho': 4},
    {'clave': 'fecha_ultimo_parto', 'tipo': 'fecha', 'etiqueta': 'Fecha último parto', 'ancho': 4},
    {'clave': 'citologia_fecha', 'tipo': 'fecha', 'etiqueta': 'Última citología (fecha)', 'ancho': 4},
    {'clave': 'citologia_resultado', 'tipo': 'texto', 'etiqueta': 'Última citología (resultado)', 'ancho': 4,
     'ayuda': 'Ej.: NILM, ASCUS, L-SIL…'},
    {'clave': 'citologia_hace', 'tipo': 'texto', 'etiqueta': 'Última citología (tiempo aproximado)', 'ancho': 6,
     'ayuda': 'Si no recuerda la fecha exacta: «hace 2 años», «hace 6 meses»'},
    {'clave': 'vph_diagnostico', 'tipo': 'si_no', 'etiqueta': 'Diagnóstico VPH', 'ancho': 3},
    {'clave': 'vph_vacuna', 'tipo': 'si_no', 'etiqueta': 'Vacuna VPH', 'ancho': 3},
    {'clave': 'vih_resultado', 'tipo': 'opcion', 'etiqueta': 'Resultado VIH', 'ancho': 3,
     'opciones': [['NEGATIVO', 'Negativo'], ['POSITIVO', 'Positivo'], ['NO_REALIZADO', 'No realizado']]},
    {'clave': 'vih_fecha', 'tipo': 'fecha', 'etiqueta': 'VIH (fecha prueba)', 'ancho': 3},
    {'clave': 'its_previas', 'tipo': T, 'etiqueta': 'ITS previas', 'filas': 2},
    {'clave': 'inicio_vida_sexual', 'tipo': 'numero', 'etiqueta': 'Inicio vida sexual (edad)', 'decimales': 0,
     'min': 8, 'max': 60, 'ancho': 3},
    {'clave': 'num_parejas', 'tipo': 'numero', 'etiqueta': 'Número de parejas sexuales', 'decimales': 0, 'min': 0,
     'max': 200, 'ancho': 3},
    {'clave': 'dispareunia', 'tipo': 'si_no', 'etiqueta': 'Dispareunia', 'ancho': 3},
    {'clave': 'menopausia', 'tipo': 'si_no', 'etiqueta': 'Menopausia', 'ancho': 3},
    {'clave': 'menopausia_edad', 'tipo': 'numero', 'etiqueta': 'Menopausia (edad)', 'decimales': 0, 'min': 20,
     'max': 70, 'ancho': 3},
    {'clave': 'menopausia_sintomas', 'tipo': T, 'etiqueta': 'Síntomas de menopausia', 'filas': 2, 'ancho': 9},
]})

PLANIFICACION = SeccionDef('go.planificacion', 'Planificación familiar', ambito='PACIENTE', orden=24,
                           esquema={'campos': [
    {'clave': 'metodo', 'tipo': 'texto', 'etiqueta': 'Método anticonceptivo actual', 'ancho': 6},
    {'clave': 'tiempo_uso', 'tipo': 'texto', 'etiqueta': 'Tiempo de uso del método', 'ancho': 6},
    {'clave': 'metodos_anteriores', 'tipo': T, 'etiqueta': 'Métodos anticonceptivos anteriores', 'filas': 2},
    {'clave': 'deseo_embarazo', 'tipo': 'si_no', 'etiqueta': 'Deseo de embarazo', 'ancho': 3},
    {'clave': 'ligadura', 'tipo': 'si_no', 'etiqueta': 'Ligadura de trompas', 'ancho': 3},
    {'clave': 'diu_tipo', 'tipo': 'texto', 'etiqueta': 'Tipo de DIU', 'ancho': 3},
    {'clave': 'diu_fecha', 'tipo': 'fecha', 'etiqueta': 'DIU (fecha de colocación)', 'ancho': 3},
]})

OBSERVACIONES = SeccionDef('go.observaciones', 'Observaciones generales (ficha)', ambito='PACIENTE', orden=25,
                           esquema={'campos': [
    {'clave': 'observaciones', 'tipo': T, 'etiqueta': 'Observaciones generales', 'filas': 3},
]})

# ── Consulta ──────────────────────────────────────────────────────────────────

OBSERVACIONES_CONSULTA = SeccionDef('go.notas', 'Observaciones', orden=93, esquema={'campos': [
    {'clave': 'observaciones', 'tipo': T, 'etiqueta': 'Observaciones', 'filas': 2},
]})

TIPO = SeccionDef('go.tipo', 'Tipo de consulta', orden=5, esquema={'campos': [
    {'clave': 'tipo', 'tipo': 'opcion', 'etiqueta': 'Tipo de consulta', 'ancho': 8, 'opciones': TIPOS_CONSULTA,
     'por_defecto': 'GINECOLOGICA'},
]})

PRENATAL = SeccionDef('go.prenatal', 'Control prenatal', orden=35, esquema={'campos': [
    {'clave': 'fur', 'tipo': 'fecha', 'etiqueta': 'FUR', 'ancho': 3},
    {'clave': 'eco_fecha', 'tipo': 'fecha', 'etiqueta': 'Ecografía de referencia (fecha)', 'ancho': 3,
     'ayuda': 'La primera ecografía confiable; si la hay, manda sobre la FUR'},
    {'clave': 'eco_semanas', 'tipo': 'numero', 'etiqueta': 'EG en esa eco', 'unidad': 'sem', 'decimales': 0,
     'min': 4, 'max': 42, 'ancho': 3},
    {'clave': 'eco_dias', 'tipo': 'numero', 'etiqueta': '+ días', 'decimales': 0, 'min': 0, 'max': 6, 'ancho': 3},
    {'clave': 'eg', 'tipo': 'calculado', 'etiqueta': 'Edad gestacional hoy', 'funcion': 'go.eg', 'ancho': 6},
    {'clave': 'fpp', 'tipo': 'calculado', 'etiqueta': 'Fecha probable de parto', 'funcion': 'go.fpp', 'ancho': 6},
    {'clave': 'altura_uterina', 'tipo': 'numero', 'etiqueta': 'Altura uterina', 'unidad': 'cm', 'decimales': 1,
     'min': 5, 'max': 50, 'ancho': 3},
    {'clave': 'fcf', 'tipo': 'numero', 'etiqueta': 'FCF', 'unidad': 'lpm', 'decimales': 0, 'min': 60, 'max': 220,
     'ancho': 3},
    {'clave': 'presentacion', 'tipo': 'opcion', 'etiqueta': 'Presentación', 'ancho': 3,
     'opciones': [['CEFALICA', 'Cefálica'], ['PELVICA', 'Pélvica'], ['TRANSVERSA', 'Transversa'],
                  ['NO_EVALUABLE', 'No evaluable']]},
    {'clave': 'movimientos', 'tipo': 'si_no', 'etiqueta': 'Movimientos fetales', 'ancho': 3},
    {'clave': 'edemas', 'tipo': 'opcion', 'etiqueta': 'Edemas', 'ancho': 3,
     'opciones': [['NO', 'No'], ['1', '+'], ['2', '++'], ['3', '+++']]},
    {'clave': 'laboratorio', 'tipo': T, 'etiqueta': 'Laboratorio prenatal', 'filas': 2,
     'ayuda': 'Hematología, grupo y Rh, glicemia, VDRL, VIH, toxoplasmosis, orina…'},
]})

ESTUDIOS = SeccionDef('go.estudios', 'Ecografía, colposcopia e imágenes', orden=45, esquema={'campos': [
    {'clave': 'ecografia', 'tipo': T, 'etiqueta': 'Ecografía', 'filas': 2},
    {'clave': 'colposcopia', 'tipo': T, 'etiqueta': 'Colposcopia', 'filas': 2},
    {'clave': 'imagenes', 'tipo': T, 'etiqueta': 'Imágenes', 'filas': 2,
     'ayuda': 'Mamografía, ecografía mamaria, densitometría ósea…'},
    {'clave': 'laboratorio', 'tipo': T, 'etiqueta': 'Laboratorio', 'filas': 2},
]})

ACTUALIZAR = SeccionDef('go.actualizar', 'Actualizar ficha ginecológica', orden=95, esquema={'campos': [
    {'clave': 'ayuda', 'tipo': 'subtitulo', 'etiqueta': 'Si en esta consulta se registró la FUR o se hizo citología, '
                                                         'se copia a la ficha de la paciente.'},
    {'clave': 'fur', 'tipo': 'fecha', 'etiqueta': 'FUR', 'ancho': 4},
    {'clave': 'citologia_fecha', 'tipo': 'fecha', 'etiqueta': 'Fecha de la citología', 'ancho': 4},
    {'clave': 'citologia_resultado', 'tipo': 'texto', 'etiqueta': 'Resultado de la citología', 'ancho': 4,
     'ayuda': 'Ej.: NILM, ASCUS, L-SIL…'},
]})

FICHA = [PERSONALES, FAMILIARES, GINECO, PLANIFICACION, OBSERVACIONES]
CONSULTA = [TIPO, PRENATAL, ESTUDIOS, OBSERVACIONES_CONSULTA, ACTUALIZAR]
