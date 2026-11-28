"""
Secciones de pediatría (portadas de la ficha y la consulta de Pediae, ver docs/roadmap/13_pediatria.md §1).

Ámbito PACIENTE = ficha pediátrica (se llena una vez y pasa a las consultas siguientes, con historial).
Ámbito CONSULTA = lo que se registra en cada consulta.
"""
from apps.clinica.registro import SeccionDef

T = 'texto_largo'
SI = {'igual': True}

# ── Ficha pediátrica (PACIENTE) ───────────────────────────────────────────────

PERINATALES = SeccionDef('ped.perinatales', 'Antecedentes prenatales, perinatales y neonatales', ambito='PACIENTE',
                         orden=21, esquema={'campos': [
    {'clave': 'sub_embarazo', 'tipo': 'subtitulo', 'etiqueta': 'Embarazo'},
    {'clave': 'edad_materna', 'tipo': 'numero', 'etiqueta': 'Edad materna al embarazo', 'unidad': 'años',
     'decimales': 0, 'min': 10, 'max': 60, 'ancho': 3},
    {'clave': 'numero_gestacion', 'tipo': 'numero', 'etiqueta': 'N.º de gestación', 'decimales': 0, 'min': 1,
     'max': 20, 'ancho': 3, 'ayuda': '1 = primera gestación'},
    {'clave': 'control_prenatal', 'tipo': 'si_no', 'etiqueta': 'Control prenatal', 'ancho': 3},
    {'clave': 'consultas_prenatales', 'tipo': 'numero', 'etiqueta': 'N.º de consultas prenatales', 'decimales': 0,
     'min': 0, 'max': 60, 'ancho': 3, 'visible_si': {'campo': 'control_prenatal', **SI}},
    {'clave': 'complicaciones_embarazo', 'tipo': 'opciones', 'etiqueta': 'Complicaciones en el embarazo',
     'opciones': [['OLIGOAMNIOS', 'Oligoamnios'], ['PREECLAMPSIA', 'Preeclampsia'],
                  ['INFECCIONES', 'Infecciones'], ['DIABETES', 'Diabetes gestacional']]},
    {'clave': 'complicacion_otra', 'tipo': 'texto', 'etiqueta': 'Otra complicación del embarazo', 'ancho': 12},
    {'clave': 'sub_parto', 'tipo': 'subtitulo', 'etiqueta': 'Nacimiento'},
    {'clave': 'semanas_gestacion', 'tipo': 'numero', 'etiqueta': 'Edad gestacional al nacer', 'unidad': 'semanas',
     'decimales': 0, 'min': 20, 'max': 45, 'ancho': 3},
    {'clave': 'via_parto', 'tipo': 'opcion', 'etiqueta': 'Vía de parto', 'ancho': 3,
     'opciones': [['VAGINAL', 'Vaginal'], ['CESAREA', 'Cesárea']]},
    {'clave': 'indicacion_cesarea', 'tipo': 'texto', 'etiqueta': 'Indicación de la cesárea', 'ancho': 6,
     'visible_si': {'campo': 'via_parto', 'igual': 'CESAREA'}},
    {'clave': 'peso_nacer_g', 'tipo': 'numero', 'etiqueta': 'Peso al nacer', 'unidad': 'g', 'decimales': 0,
     'min': 300, 'max': 7000, 'ancho': 3},
    {'clave': 'talla_nacer_cm', 'tipo': 'numero', 'etiqueta': 'Talla al nacer', 'unidad': 'cm', 'decimales': 1,
     'min': 20, 'max': 65, 'ancho': 3},
    {'clave': 'pc_nacer_cm', 'tipo': 'numero', 'etiqueta': 'Perímetro cefálico al nacer', 'unidad': 'cm',
     'decimales': 1, 'min': 15, 'max': 45, 'ancho': 3},
    {'clave': 'apgar', 'tipo': 'texto', 'etiqueta': 'APGAR (1′ / 5′)', 'ancho': 3, 'ayuda': 'Ej.: 8/9'},
    {'clave': 'sub_neonatal', 'tipo': 'subtitulo', 'etiqueta': 'Período neonatal (primeros 28 días)'},
    {'clave': 'complicaciones_neonatales', 'tipo': 'si_no', 'etiqueta': 'Presentó complicaciones neonatales',
     'ancho': 4},
    {'clave': 'neonatales', 'tipo': 'opciones', 'etiqueta': 'Cuáles',
     'opciones': [['ICTERICIA', 'Ictericia'], ['SEPSIS', 'Sepsis'], ['DIF_RESP', 'Dificultad respiratoria'],
                  ['RETEN', 'Hospitalización / retén']],
     'visible_si': {'campo': 'complicaciones_neonatales', **SI}},
    {'clave': 'neonatal_otra', 'tipo': 'texto', 'etiqueta': 'Otra complicación neonatal', 'ancho': 12,
     'visible_si': {'campo': 'complicaciones_neonatales', **SI}},
    {'clave': 'onfalorrexis', 'tipo': 'opcion', 'etiqueta': 'Onfalorrexis (caída del cordón)', 'ancho': 4,
     'opciones': [['NORMAL', 'Normal'], ['COMPLICADA', 'Alterada / complicada']]},
    {'clave': 'prueba_talon', 'tipo': 'opcion', 'etiqueta': 'Prueba del talón', 'ancho': 4,
     'opciones': [['NORMAL', 'Sin alteraciones'], ['ALTERADA', 'Alterada / en estudio'], ['NO', 'No realizada']]},
    {'clave': 'prueba_talon_detalle', 'tipo': 'texto', 'etiqueta': 'Detalle de la prueba del talón', 'ancho': 4,
     'visible_si': {'campo': 'prueba_talon', 'igual': 'ALTERADA'}},
    {'clave': 'notas', 'tipo': T, 'etiqueta': 'Notas (embarazo, parto, neonatal)', 'filas': 2},
]})

ALIMENTACION = SeccionDef('ped.alimentacion', 'Alimentación y nutrición (antecedentes)', ambito='PACIENTE', orden=22,
                          esquema={'campos': [
    {'clave': 'lme', 'tipo': 'si_no', 'etiqueta': 'Lactancia materna exclusiva', 'ancho': 4},
    {'clave': 'lme_meses', 'tipo': 'numero', 'etiqueta': 'LME hasta', 'unidad': 'meses', 'decimales': 0,
     'min': 0, 'max': 36, 'ancho': 4, 'visible_si': {'campo': 'lme', **SI}},
    {'clave': 'formula', 'tipo': 'si_no', 'etiqueta': 'Fórmulas o leches especiales', 'ancho': 4},
    {'clave': 'formula_nombre', 'tipo': 'texto', 'etiqueta': 'Fórmula empleada', 'ancho': 6,
     'visible_si': {'campo': 'formula', **SI}},
    {'clave': 'formula_causa', 'tipo': 'opcion', 'etiqueta': 'Causa', 'ancho': 6,
     'opciones': [['EVACUACIONES', 'Dificultad en evacuaciones'], ['ESTIMULACION', 'Necesidad de estimulación'],
                  ['ALERGIA', 'Alergia'], ['OTRA', 'Otra']],
     'visible_si': {'campo': 'formula', **SI}},
    {'clave': 'ablactacion_meses', 'tipo': 'numero', 'etiqueta': 'Inicio de la alimentación complementaria',
     'unidad': 'meses', 'decimales': 0, 'min': 0, 'max': 36, 'ancho': 4},
    {'clave': 'alimentacion_actual', 'tipo': 'opcion', 'etiqueta': 'Alimentación actual', 'ancho': 4,
     'opciones': [['COMPLETA', 'Completa y variada acorde a la edad'], ['SELECTIVA', 'Selectiva / restringida']]},
    {'clave': 'alimentacion_detalle', 'tipo': 'texto', 'etiqueta': 'Detalle de la dieta selectiva', 'ancho': 4,
     'visible_si': {'campo': 'alimentacion_actual', 'igual': 'SELECTIVA'}},
    {'clave': 'notas', 'tipo': T, 'etiqueta': 'Notas de alimentación', 'filas': 1},
]})

DESARROLLO_HITOS = SeccionDef('ped.desarrollo_hitos', 'Desarrollo psicomotor e hitos madurativos', ambito='PACIENTE',
                              orden=23, esquema={'campos': [
    {'clave': 'neuromotor_adecuado', 'tipo': 'si_no', 'etiqueta': 'Desarrollo neuromotor acorde a la edad', 'ancho': 6},
    {'clave': 'areas_afectadas', 'tipo': 'opciones', 'etiqueta': 'Áreas afectadas',
     'opciones': [['MOTOR_GRUESO', 'Motor grueso'], ['MOTOR_FINO', 'Motor fino'], ['LENGUAJE', 'Lenguaje'],
                  ['SOCIAL', 'Social-afectivo']],
     'visible_si': {'campo': 'neuromotor_adecuado', 'igual': False}},
    {'clave': 'esfinter_vesical', 'tipo': 'si_no', 'etiqueta': 'Control vesical logrado', 'ancho': 3},
    {'clave': 'esfinter_vesical_edad', 'tipo': 'texto', 'etiqueta': 'Edad (vesical)', 'ancho': 3,
     'visible_si': {'campo': 'esfinter_vesical', **SI}},
    {'clave': 'esfinter_anal', 'tipo': 'si_no', 'etiqueta': 'Control anal logrado', 'ancho': 3},
    {'clave': 'esfinter_anal_edad', 'tipo': 'texto', 'etiqueta': 'Edad (anal)', 'ancho': 3,
     'visible_si': {'campo': 'esfinter_anal', **SI}},
    {'clave': 'notas', 'tipo': T, 'etiqueta': 'Hitos (sostén cefálico, sedestación, marcha, lenguaje…)', 'filas': 2},
]})

PATOLOGICOS = SeccionDef('ped.patologicos', 'Antecedentes patológicos pediátricos', ambito='PACIENTE', orden=24,
                         version=2, esquema={'campos': [
    {'clave': 'traumatismos', 'tipo': 'si_no', 'etiqueta': 'Traumatismos / accidentes', 'ancho': 4},
    {'clave': 'traumatismos_detalle', 'tipo': 'texto', 'etiqueta': 'Detalle', 'ancho': 8,
     'visible_si': {'campo': 'traumatismos', **SI}},
    {'clave': 'exantematicas', 'tipo': 'si_no', 'etiqueta': 'Enfermedades exantemáticas', 'ancho': 4},
    {'clave': 'exantematicas_detalle', 'tipo': 'texto', 'etiqueta': 'Cuáles (varicela, sarampión, rubéola…)',
     'ancho': 8, 'visible_si': {'campo': 'exantematicas', **SI}},
    {'clave': 'otros', 'tipo': T, 'etiqueta': 'Otros', 'filas': 2},
]})

FAMILIARES = SeccionDef('ped.familiares', 'Antecedentes familiares', ambito='PACIENTE', orden=26, esquema={'campos': [
    {'clave': 'antecedentes', 'tipo': 'opciones', 'etiqueta': 'Antecedentes en la familia',
     'opciones': [['DIABETES', 'Diabetes'], ['HTA', 'Hipertensión'], ['CARDIOPATIAS', 'Cardiopatías'],
                  ['EPILEPSIA', 'Epilepsia'], ['ASMA_ATOPIA', 'Asma / atopía'], ['ONCOLOGICO', 'Oncológicos']]},
    {'clave': 'oncologico_rama', 'tipo': 'opcion', 'etiqueta': 'Rama (oncológicos)', 'ancho': 4,
     'opciones': [['MATERNA', 'Materna'], ['PATERNA', 'Paterna'], ['AMBAS', 'Ambas']],
     'visible_si': {'campo': 'antecedentes', 'igual': 'ONCOLOGICO'}},
    {'clave': 'autoinmunes', 'tipo': 'texto', 'etiqueta': 'Enfermedades autoinmunes', 'ancho': 6},
    {'clave': 'geneticas', 'tipo': 'texto', 'etiqueta': 'Enfermedades genéticas', 'ancho': 6},
    {'clave': 'otros', 'tipo': T, 'etiqueta': 'Otros antecedentes familiares', 'filas': 1},
]})

ENTORNO = SeccionDef('ped.entorno', 'Familia, hábitos y entorno', ambito='PACIENTE', orden=27, esquema={'campos': [
    {'clave': 'sub_padres', 'tipo': 'subtitulo', 'etiqueta': 'Padres'},
    {'clave': 'edad_madre', 'tipo': 'numero', 'etiqueta': 'Edad de la madre', 'unidad': 'años', 'decimales': 0,
     'min': 10, 'max': 90, 'ancho': 3},
    {'clave': 'ocupacion_madre', 'tipo': 'texto', 'etiqueta': 'Ocupación de la madre', 'ancho': 3},
    {'clave': 'edad_padre', 'tipo': 'numero', 'etiqueta': 'Edad del padre', 'unidad': 'años', 'decimales': 0,
     'min': 10, 'max': 99, 'ancho': 3},
    {'clave': 'ocupacion_padre', 'tipo': 'texto', 'etiqueta': 'Ocupación del padre', 'ancho': 3},
    {'clave': 'sub_habitos', 'tipo': 'subtitulo', 'etiqueta': 'Hábitos psicobiológicos'},
    {'clave': 'patron_sueno', 'tipo': 'opcion', 'etiqueta': 'Sueño', 'ancho': 4,
     'opciones': [['TRANQUILO', 'Tranquilo y reparador'], ['ALTERADO', 'Alterado / trastorno del sueño']]},
    {'clave': 'patron_evacuacion', 'tipo': 'opcion', 'etiqueta': 'Evacuación', 'ancho': 4,
     'opciones': [['NORMAL', 'Normal / continente'], ['ESTRENIMIENTO', 'Estreñimiento'], ['ENCOPRESIS', 'Encopresis']]},
    {'clave': 'patron_miccion', 'tipo': 'opcion', 'etiqueta': 'Micción', 'ancho': 4,
     'opciones': [['NORMAL', 'Normal / continente'], ['ENURESIS_DIURNA', 'Enuresis diurna'],
                  ['ENURESIS_NOCTURNA', 'Enuresis nocturna']]},
    {'clave': 'sub_entorno', 'tipo': 'subtitulo', 'etiqueta': 'Entorno socio-ambiental'},
    {'clave': 'tabaquismo_pasivo', 'tipo': 'si_no', 'etiqueta': 'Exposición a humo de tabaco', 'ancho': 4},
    {'clave': 'agua', 'tipo': 'opcion', 'etiqueta': 'Agua de consumo', 'ancho': 4,
     'opciones': [['HERVIDA', 'Hervida'], ['FILTRADA', 'Filtrada'], ['EMBOTELLADA', 'Embotellada'],
                  ['TUBERIA', 'Directa de tubería']]},
    {'clave': 'mascotas', 'tipo': 'si_no', 'etiqueta': 'Mascotas en el hogar', 'ancho': 4},
    {'clave': 'mascotas_tipo', 'tipo': 'texto', 'etiqueta': 'Tipo de mascotas', 'ancho': 4,
     'visible_si': {'campo': 'mascotas', **SI}},
    {'clave': 'guarderia', 'tipo': 'si_no', 'etiqueta': 'Asiste a guardería / escuela', 'ancho': 4},
]})

# ── Consulta ─────────────────────────────────────────────────────────────────

TIPOS_CONSULTA = [['CONTROL_SANO', 'Control sano'], ['ENFERMEDAD', 'Consulta por enfermedad'],
                  ['SEGUIMIENTO', 'Seguimiento']]
TIPO = SeccionDef('ped.tipo', 'Tipo de consulta', orden=5, esquema={'campos': [
    {'clave': 'tipo', 'tipo': 'opcion', 'etiqueta': 'Tipo de consulta', 'ancho': 6, 'opciones': TIPOS_CONSULTA,
     'por_defecto': 'CONTROL_SANO'},
]})

ANTROPOMETRIA = SeccionDef('ped.antropometria', 'Antropometría y crecimiento (OMS)', orden=41, esquema={'campos': [
    {'clave': 'peso_kg', 'tipo': 'numero', 'etiqueta': 'Peso', 'unidad': 'kg', 'min': 0.3, 'max': 200,
     'decimales': 3, 'ancho': 3},
    {'clave': 'talla_cm', 'tipo': 'numero', 'etiqueta': 'Talla / longitud', 'unidad': 'cm', 'min': 20, 'max': 230,
     'decimales': 1, 'ancho': 3, 'ayuda': 'Acostado hasta los 2 años; de pie desde los 2 años.'},
    {'clave': 'pc_cm', 'tipo': 'numero', 'etiqueta': 'Perímetro cefálico', 'unidad': 'cm', 'min': 15, 'max': 70,
     'decimales': 1, 'ancho': 3},
    {'clave': 'imc', 'tipo': 'calculado', 'etiqueta': 'IMC', 'unidad': 'kg/m²', 'funcion': 'ped.imc', 'ancho': 3},
    {'clave': 'percentil_peso', 'tipo': 'calculado', 'etiqueta': 'Percentil peso/edad', 'funcion': 'ped.p_peso',
     'ancho': 3},
    {'clave': 'percentil_talla', 'tipo': 'calculado', 'etiqueta': 'Percentil talla/edad', 'funcion': 'ped.p_talla',
     'ancho': 3},
    {'clave': 'percentil_pc', 'tipo': 'calculado', 'etiqueta': 'Percentil PC/edad', 'funcion': 'ped.p_pc', 'ancho': 3},
    {'clave': 'percentil_imc', 'tipo': 'calculado', 'etiqueta': 'Percentil IMC/edad', 'funcion': 'ped.p_imc',
     'ancho': 3},
    {'clave': 'estado_nutricional', 'tipo': 'calculado', 'etiqueta': 'Estado nutricional (peso/edad)',
     'funcion': 'ped.estado_nutricional', 'ancho': 4},
    {'clave': 'clasificacion_imc', 'tipo': 'calculado', 'etiqueta': 'Clasificación OMS (IMC/edad)',
     'funcion': 'ped.clasificacion_imc', 'ancho': 4},
    {'clave': 'clasificacion_talla', 'tipo': 'calculado', 'etiqueta': 'Talla para la edad',
     'funcion': 'ped.clasificacion_talla', 'ancho': 4},
]})

HABITOS = SeccionDef('ped.habitos', 'Hábitos: alimentación, sueño y eliminación', orden=42, esquema={'campos': [
    {'clave': 'sub_alimentacion', 'tipo': 'subtitulo', 'etiqueta': 'Alimentación'},
    {'clave': 'tipo_alimentacion', 'tipo': 'opcion', 'etiqueta': 'Tipo', 'ancho': 6,
     'opciones': [['LME', 'Lactancia materna exclusiva'], ['MIXTA', 'Lactancia mixta'],
                  ['FORMULA', 'Fórmula exclusiva'], ['COMPLEMENTARIA', 'Complementaria + lactancia'],
                  ['FAMILIAR', 'Dieta familiar']]},
    {'clave': 'apetito', 'tipo': 'opcion', 'etiqueta': 'Apetito', 'ancho': 3,
     'opciones': [['BUENO', 'Bueno'], ['REGULAR', 'Regular'], ['MALO', 'Malo / hiporexia']]},
    {'clave': 'comidas_dia', 'tipo': 'numero', 'etiqueta': 'Comidas al día', 'decimales': 0, 'min': 0, 'max': 15,
     'ancho': 3},
    {'clave': 'notas_alimentacion', 'tipo': 'texto', 'etiqueta': 'Notas (rechazos, alergias, hábitos)', 'ancho': 12},
    {'clave': 'sub_sueno', 'tipo': 'subtitulo', 'etiqueta': 'Sueño'},
    {'clave': 'horas_sueno', 'tipo': 'numero', 'etiqueta': 'Horas de sueño nocturno', 'decimales': 0, 'min': 0,
     'max': 24, 'ancho': 4},
    {'clave': 'siestas', 'tipo': 'numero', 'etiqueta': 'Siestas al día', 'decimales': 0, 'min': 0, 'max': 10,
     'ancho': 4},
    {'clave': 'duracion_siesta', 'tipo': 'numero', 'etiqueta': 'Duración de la siesta', 'unidad': 'min',
     'decimales': 0, 'min': 0, 'max': 600, 'ancho': 4},
    {'clave': 'notas_sueno', 'tipo': 'texto', 'etiqueta': 'Notas (ronquidos, despertares, colecho)', 'ancho': 12},
    {'clave': 'sub_eliminacion', 'tipo': 'subtitulo', 'etiqueta': 'Eliminación'},
    {'clave': 'deposiciones', 'tipo': 'opcion', 'etiqueta': 'Deposiciones', 'ancho': 4,
     'opciones': [['VARIAS_DIA', 'Varias al día'], ['UNA_DIA', 'Una al día'], ['CADA_2_3', 'Cada 2–3 días'],
                  ['ESTRENIMIENTO', 'Estreñimiento (> 3 días)']]},
    {'clave': 'consistencia', 'tipo': 'opcion', 'etiqueta': 'Consistencia', 'ancho': 4,
     'opciones': [['NORMAL', 'Normal / pastosa'], ['BLANDA', 'Blanda / semilíquida'], ['LIQUIDA', 'Líquida'],
                  ['DURA', 'Dura / caprinas']]},
    {'clave': 'control_esfinteres', 'tipo': 'si_no', 'etiqueta': 'Control de esfínteres', 'ancho': 4},
    {'clave': 'notas_eliminacion', 'tipo': 'texto', 'etiqueta': 'Notas (disuria, enuresis, encopresis)', 'ancho': 12},
]})

DESARROLLO = SeccionDef('ped.desarrollo', 'Desarrollo psicomotor', orden=43, esquema={'campos': [
    {'clave': 'acorde', 'tipo': 'si_no', 'etiqueta': 'Acorde a la edad', 'ancho': 4},
    {'clave': 'desarrollo', 'tipo': T, 'etiqueta': 'Evaluación del desarrollo', 'filas': 2},
]})

VACUNAS_PENDIENTES = SeccionDef('ped.vacunas_pendientes', 'Vacunas pendientes', orden=95, esquema={'campos': [
    {'clave': 'notas', 'tipo': T, 'etiqueta': 'Anotaciones', 'filas': 3},
]})

FICHA = [PERINATALES, ALIMENTACION, DESARROLLO_HITOS, PATOLOGICOS, FAMILIARES, ENTORNO]
CONSULTA = [TIPO, ANTROPOMETRIA, HABITOS, DESARROLLO, VACUNAS_PENDIENTES]
