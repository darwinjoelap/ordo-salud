"""
Secciones de cardiología pediátrica, tomadas del modelo de informe de la Dra. Lyna Sierra
(docs/roadmap/15_cardiologia_pediatrica.md).

Ámbito PACIENTE = ficha (antecedentes, se llenan una vez). Ámbito CONSULTA = EKG y ecocardiograma de cada consulta.
El informe arma la prosa con estos campos (informe.py), igual que la doctora la redacta en Word.
"""
from apps.clinica.registro import SeccionDef

T = 'texto_largo'
DEFECTO = {'campo': 'tia', 'igual': 'DEFECTO'}

GRADOS = [['NO', 'Competente'], ['LEVE', 'Leve'], ['MODERADA', 'Moderada'], ['SEVERA', 'Severa']]
SHUNT = [['ID', 'I-D'], ['DI', 'D-I'], ['BI', 'Bidireccional']]
DILATACION = [['NO', 'No dilatado'], ['LEVE', 'Levemente dilatado'], ['MODERADO', 'Moderadamente dilatado'],
              ['SEVERO', 'Severamente dilatado']]


def _mm(clave, etiqueta, ancho=2, decimales=1):
    return {'clave': clave, 'tipo': 'numero', 'etiqueta': etiqueta, 'unidad': 'mm', 'decimales': decimales,
            'min': 0, 'max': 120, 'ancho': ancho}


def _vel(clave, etiqueta='Vmáx', ancho=2):
    return {'clave': clave, 'tipo': 'numero', 'etiqueta': etiqueta, 'unidad': 'm/s', 'decimales': 2, 'min': 0,
            'max': 8, 'ancho': ancho}


def _z(clave):
    return {'clave': clave, 'tipo': 'numero', 'etiqueta': 'Z-score', 'decimales': 2, 'min': -20, 'max': 20,
            'ancho': 2}


def _gp(clave, de):
    return {'clave': clave, 'tipo': 'calculado', 'etiqueta': 'Gp (4v²)', 'unidad': 'mmHg', 'decimales': 1,
            'funcion': f'cp.gradiente:{de}', 'ancho': 2}


def _gp_manual(clave):
    return {'clave': clave, 'tipo': 'numero', 'etiqueta': 'Gp medido', 'unidad': 'mmHg', 'decimales': 1, 'min': 0,
            'max': 250, 'ancho': 2, 'ayuda': 'Si el equipo da el gradiente, se usa este y no el calculado.'}


def _grado(clave, etiqueta='Regurgitación'):
    return {'clave': clave, 'tipo': 'opcion', 'etiqueta': etiqueta, 'opciones': GRADOS, 'ancho': 2}


# ── Ficha: antecedentes personales (perinatales y patológicos) ──────────────────────────────────────────────────
ANTECEDENTES = SeccionDef('cp.antecedentes', 'Antecedentes personales', ambito='PACIENTE', orden=21,
                          descripcion='Se llenan una vez; el informe arma el párrafo «Producto de madre de…».',
                          esquema={'campos': [
    {'clave': 'sub_perinatales', 'tipo': 'subtitulo', 'etiqueta': 'Perinatales'},
    {'clave': 'edad_madre', 'tipo': 'numero', 'etiqueta': 'Edad de la madre', 'unidad': 'años', 'decimales': 0,
     'min': 10, 'max': 60, 'ancho': 2},
    {'clave': 'gestas', 'tipo': 'numero', 'etiqueta': 'Gestas (con este)', 'decimales': 0, 'min': 1, 'max': 20,
     'ancho': 2, 'ayuda': 'Sale en romanos: 5 → VG.'},
    {'clave': 'gestas_detalle', 'tipo': 'texto', 'etiqueta': 'Detalle de gestas', 'ancho': 4,
     'ayuda': 'Ej.: I Mortinato · II Abortos'},
    {'clave': 'embarazo', 'tipo': 'opcion', 'etiqueta': 'Embarazo', 'ancho': 2, 'por_defecto': 'SIMPLE',
     'opciones': [['SIMPLE', 'Simple'], ['GEMELAR', 'Gemelar'], ['MULTIPLE', 'Múltiple']]},
    {'clave': 'termino', 'tipo': 'opcion', 'etiqueta': 'Edad gestacional', 'ancho': 2, 'por_defecto': 'TERMINO',
     'opciones': [['TERMINO', 'A término'], ['PRETERMINO', 'Pretérmino'], ['POSTERMINO', 'Postérmino']]},
    {'clave': 'semanas', 'tipo': 'numero', 'etiqueta': 'Semanas', 'decimales': 0, 'min': 20, 'max': 45, 'ancho': 2},
    {'clave': 'dias', 'tipo': 'numero', 'etiqueta': '+ días', 'decimales': 0, 'min': 0, 'max': 6, 'ancho': 2},
    {'clave': 'complicaciones', 'tipo': 'texto', 'etiqueta': 'Complicado con', 'ancho': 8,
     'ayuda': 'Vacío = no complicado. Ej.: Pre-Eclampsia desde las 11 semanas · ITU primer trimestre'},
    {'clave': 'via_parto', 'tipo': 'opcion', 'etiqueta': 'Vía de nacimiento', 'ancho': 4,
     'opciones': [['EUTOCICO', 'Parto eutócico'], ['DISTOCICO', 'Parto distócico'],
                  ['INSTRUMENTAL', 'Parto instrumental'], ['CESAREA', 'Cesárea segmentaria']]},
    {'clave': 'via_detalle', 'tipo': 'texto', 'etiqueta': 'Detalle del nacimiento', 'ancho': 8,
     'ayuda': 'Ej.: por sufrimiento fetal agudo, se practicó esterilización quirúrgica · practican maniobra de Kristeller'},
    {'clave': 'respiro_lloro', 'tipo': 'si_no', 'etiqueta': 'Respiró y lloró espontáneamente', 'ancho': 4,
     'por_defecto': True},
    {'clave': 'pan', 'tipo': 'numero', 'etiqueta': 'PAN (peso al nacer)', 'unidad': 'g', 'decimales': 0, 'min': 300,
     'max': 7000, 'ancho': 2},
    {'clave': 'tan', 'tipo': 'numero', 'etiqueta': 'TAN (talla al nacer)', 'unidad': 'cm', 'decimales': 1,
     'min': 20, 'max': 65, 'ancho': 2},
    {'clave': 'egreso', 'tipo': T, 'etiqueta': 'Egreso / ingreso neonatal', 'filas': 2,
     'ayuda': 'Ej.: Egresó con la madre a las 24 horas · Ingresó a UCIN con Dx: 1) RNAT/AEG, 2) …'},
    {'clave': 'sub_patologicos', 'tipo': 'subtitulo', 'etiqueta': 'Patológicos'},
    {'clave': 'alergias', 'tipo': 'texto', 'etiqueta': 'Alergias', 'ancho': 4, 'ayuda': 'Vacío = niega.'},
    {'clave': 'asma', 'tipo': 'si_no', 'etiqueta': 'Asma bronquial', 'ancho': 2},
    {'clave': 'eruptivas', 'tipo': 'texto', 'etiqueta': 'Eruptivas', 'ancho': 3, 'ayuda': 'Vacío = niega.'},
    {'clave': 'hospitalizaciones', 'tipo': 'texto', 'etiqueta': 'Ingresos hospitalarios', 'ancho': 3,
     'ayuda': 'Vacío = niega.'},
    {'clave': 'intervenciones', 'tipo': T, 'etiqueta': 'Intervenciones quirúrgicas (I/Q)', 'filas': 3,
     'ayuda': 'Vacío = niega. Ej.: 03/03/2026: corrección completa (infundibulotomía + parche transanular)…'},
    {'clave': 'otros', 'tipo': T, 'etiqueta': 'Otros antecedentes / diagnósticos previos', 'filas': 2},
    {'clave': 'inmunizaciones', 'tipo': 'opcion', 'etiqueta': 'Esquema de inmunizaciones', 'ancho': 4,
     'opciones': [['COMPLETO', 'Completo'], ['INCOMPLETO', 'Incompleto']]},
    {'clave': 'inmunizaciones_documentado', 'tipo': 'si_no', 'etiqueta': 'Documentado (trae carnet)', 'ancho': 4},
    {'clave': 'texto_informe', 'tipo': 'calculado', 'etiqueta': 'Así sale en el informe', 'funcion': 'cp.antecedentes',
     'filas': 5, 'ancho': 12},
]})

# ── Consulta: EKG ──────────────────────────────────────────────────────────────────────────────────────────────────
RITMOS = [['RS', 'Ritmo sinusal (RS)'], ['RU', 'Ritmo de la unión (RU)'], ['FA', 'Fibrilación auricular (FA)'],
          ['FLA', 'Flutter auricular'], ['TSV', 'Taquicardia supraventricular (TSV)'], ['MP', 'Marcapaso (MP)'],
          ['OTRO', 'Otro (ver trazo)']]

EKG = SeccionDef('cp.ekg', 'Electrocardiograma (EKG)', orden=44, esquema={'campos': [
    {'clave': 'ritmo', 'tipo': 'opcion', 'etiqueta': 'Ritmo', 'opciones': RITMOS, 'por_defecto': 'RS', 'ancho': 3},
    {'clave': 'fc', 'tipo': 'numero', 'etiqueta': 'FC', 'unidad': 'lpm', 'decimales': 0, 'min': 20, 'max': 330,
     'ancho': 2},
    {'clave': 'pr', 'tipo': 'numero', 'etiqueta': 'PR', 'unidad': 's', 'decimales': 2, 'min': 0, 'max': 1, 'ancho': 2},
    {'clave': 'qrs', 'tipo': 'numero', 'etiqueta': 'QRS', 'unidad': 's', 'decimales': 2, 'min': 0, 'max': 1,
     'ancho': 2},
    {'clave': 'qt', 'tipo': 'numero', 'etiqueta': 'QT', 'unidad': 's', 'decimales': 2, 'min': 0, 'max': 1, 'ancho': 2},
    {'clave': 'qtc', 'tipo': 'calculado', 'etiqueta': 'QTc (Bazett)', 'unidad': 's', 'decimales': 2,
     'funcion': 'cp.qtc', 'ancho': 2},
    {'clave': 'eje_p', 'tipo': 'numero', 'etiqueta': 'Eje de P', 'unidad': '°', 'decimales': 0, 'min': -180,
     'max': 360, 'ancho': 2},
    {'clave': 'eje_qrs', 'tipo': 'numero', 'etiqueta': 'Eje de QRS', 'unidad': '°', 'decimales': 0, 'min': -180,
     'max': 360, 'ancho': 2},
    {'clave': 'trazo', 'tipo': T, 'etiqueta': 'Trazo', 'filas': 2,
     'ayuda': 'Ej.: HVD, variabilidad sinusal respiratoria.'},
    {'clave': 'linea', 'tipo': 'calculado', 'etiqueta': 'Así sale en el informe', 'funcion': 'cp.ekg_linea',
     'ancho': 12},
]})

# ── Consulta: ecocardiograma transtorácico (todo estructurado) ────────────────────────────────────────────────────
ECO = SeccionDef('cp.eco', 'Ecocardiograma transtorácico', orden=46,
                 descripcion='Un campo por medida; el informe arma la prosa. Lo normal viene marcado.',
                 esquema={'campos': [
    {'clave': 'sub_situs', 'tipo': 'subtitulo', 'etiqueta': 'Situs, retornos y conexiones'},
    {'clave': 'situs', 'tipo': 'opcion', 'etiqueta': 'Situs', 'por_defecto': 'SOLITUS', 'ancho': 3,
     'opciones': [['SOLITUS', 'Situs solitus'], ['INVERSUS', 'Situs inversus'], ['AMBIGUO', 'Situs ambiguo']]},
    {'clave': 'apex', 'tipo': 'opcion', 'etiqueta': 'Ápex', 'por_defecto': 'LEVO', 'ancho': 3,
     'opciones': [['LEVO', 'Levocardia'], ['DEXTRO', 'Dextrocardia'], ['MESO', 'Mesocardia']]},
    {'clave': 'rvs', 'tipo': 'opcion', 'etiqueta': 'Retornos venosos sistémicos', 'por_defecto': 'NORMALES',
     'ancho': 3, 'opciones': [['NORMALES', 'Normales'], ['ANOMALOS', 'Anómalos']]},
    {'clave': 'rvs_detalle', 'tipo': 'texto', 'etiqueta': 'Detalle', 'ancho': 3,
     'visible_si': {'campo': 'rvs', 'igual': 'ANOMALOS'}},
    _mm('vci', 'VCI'),
    {'clave': 'vci_colapso', 'tipo': 'opcion', 'etiqueta': 'Colapso inspiratorio', 'ancho': 3,
     'opciones': [['MAYOR', '> 50 %'], ['MENOR', '< 50 %']]},
    {'clave': 'rvp', 'tipo': 'opcion', 'etiqueta': 'Retornos venosos pulmonares', 'por_defecto': 'NORMALES',
     'ancho': 3, 'opciones': [['NORMALES', 'Normales'], ['ANOMALOS', 'Anómalos']]},
    {'clave': 'rvp_detalle', 'tipo': 'texto', 'etiqueta': 'Detalle', 'ancho': 4,
     'visible_si': {'campo': 'rvp', 'igual': 'ANOMALOS'}},
    {'clave': 'conexion_av', 'tipo': 'opcion', 'etiqueta': 'Conexión AV', 'por_defecto': 'CONCORDANTE', 'ancho': 3,
     'opciones': [['CONCORDANTE', 'Concordante'], ['DISCORDANTE', 'Discordante'], ['UNIVENTRICULAR', 'Univentricular'],
                  ['AUSENTE', 'Ausente (atresia)']]},
    {'clave': 'conexion_va', 'tipo': 'opcion', 'etiqueta': 'Conexión VA', 'por_defecto': 'CONCORDANTE', 'ancho': 3,
     'opciones': [['CONCORDANTE', 'Concordante'], ['DISCORDANTE', 'Discordante'], ['DSVD', 'Doble salida del VD'],
                  ['UNICA', 'Salida única']]},

    {'clave': 'sub_tia', 'tipo': 'subtitulo', 'etiqueta': 'Tabique interatrial'},
    {'clave': 'tia', 'tipo': 'opcion', 'etiqueta': 'Tabique interatrial', 'por_defecto': 'INTACTO', 'ancho': 3,
     'opciones': [['INTACTO', 'Intacto'], ['FOP', 'Foramen oval permeable'], ['DEFECTO', 'Defecto (CIA)']]},
    {'clave': 'cia_tipo', 'tipo': 'opcion', 'etiqueta': 'Tipo de defecto', 'ancho': 3, 'visible_si': DEFECTO,
     'opciones': [['OS', 'Ostium secundum'], ['OP', 'Ostium primum'], ['SV', 'Seno venoso'],
                  ['SC', 'Seno coronario']]},
    {**_mm('cia_mm1', 'Medida 1'), 'visible_si': DEFECTO},
    {**_mm('cia_mm2', 'Medida 2'), 'visible_si': DEFECTO},
    {'clave': 'cia_shunt', 'tipo': 'opcion', 'etiqueta': 'Shunt', 'opciones': SHUNT, 'ancho': 2,
     'visible_si': {'campo': 'tia', 'en': ['DEFECTO', 'FOP']}},
    {**_mm('borde_ps', 'Borde posterosuperior'), 'visible_si': DEFECTO},
    {**_mm('borde_pi', 'Borde posteroinferior'), 'visible_si': DEFECTO},
    {**_mm('borde_as', 'Borde anterosuperior'), 'visible_si': DEFECTO},
    {**_mm('borde_ai', 'Borde anteroinferior'), 'visible_si': DEFECTO},
    {'clave': 'qpqs', 'tipo': 'numero', 'etiqueta': 'Qp:Qs', 'decimales': 1, 'min': 0.1, 'max': 10, 'ancho': 2,
     'ayuda': '2.5 → «2.5:1»'},

    {'clave': 'sub_auriculas', 'tipo': 'subtitulo', 'etiqueta': 'Aurículas'},
    {'clave': 'ad_estado', 'tipo': 'opcion', 'etiqueta': 'Aurícula derecha', 'por_defecto': 'NO', 'ancho': 3,
     'opciones': [['NO', 'No dilatada'], ['DILATADA', 'Dilatada']]},
    {'clave': 'ad_area', 'tipo': 'numero', 'etiqueta': 'Área AD', 'unidad': 'cm²', 'decimales': 2, 'min': 0,
     'max': 80, 'ancho': 2},
    {'clave': 'ad_vol', 'tipo': 'numero', 'etiqueta': 'Volumen AD', 'unidad': 'ml', 'decimales': 1, 'min': 0,
     'max': 300, 'ancho': 2},
    {'clave': 'ad_vol_index', 'tipo': 'calculado', 'etiqueta': 'Vol. index AD', 'unidad': 'ml/m²', 'decimales': 1,
     'funcion': 'cp.indexado:ad_vol', 'ancho': 2},
    {'clave': 'ai_estado', 'tipo': 'opcion', 'etiqueta': 'Aurícula izquierda', 'por_defecto': 'NO', 'ancho': 3,
     'opciones': [['NO', 'No dilatada'], ['DILATADA', 'Dilatada']]},
    {'clave': 'ai_area', 'tipo': 'numero', 'etiqueta': 'Área AI', 'unidad': 'cm²', 'decimales': 2, 'min': 0,
     'max': 80, 'ancho': 2},
    {'clave': 'ai_vol', 'tipo': 'numero', 'etiqueta': 'Volumen AI', 'unidad': 'ml', 'decimales': 1, 'min': 0,
     'max': 300, 'ancho': 2},
    {'clave': 'ai_vol_index', 'tipo': 'calculado', 'etiqueta': 'Vol. index AI', 'unidad': 'ml/m²', 'decimales': 1,
     'funcion': 'cp.indexado:ai_vol', 'ancho': 2},

    {'clave': 'sub_tric', 'tipo': 'subtitulo', 'etiqueta': 'Válvula tricúspide (los Z-score se escriben a mano por ahora)'},
    _mm('tric_anillo', 'Anillo'), _z('tric_z'),
    _vel('tric_e', 'Onda E'), _vel('tric_a', 'Onda A'), _grado('tric_ir'),
    {'clave': 'tric_jets', 'tipo': 'texto', 'etiqueta': 'Jets', 'ancho': 4,
     'ayuda': 'Ej.: triple jet, 1 céntrico y 2 excéntricos, que ocupa 2/3 de la AD'},
    _vel('tric_vmax'), _gp('tric_gp', 'tric_vmax'), _gp_manual('tric_gp_medido'),

    {'clave': 'sub_mitral', 'tipo': 'subtitulo', 'etiqueta': 'Válvula mitral'},
    _mm('mit_anillo', 'Anillo'), _z('mit_z'), _vel('mit_e', 'Onda E'), _vel('mit_a', 'Onda A'), _grado('mit_ir'),
    {'clave': 'mit_detalle', 'tipo': 'texto', 'etiqueta': 'Detalle', 'ancho': 4},

    {'clave': 'sub_tiv', 'tipo': 'subtitulo', 'etiqueta': 'Tabique interventricular'},
    {'clave': 'tiv', 'tipo': 'opcion', 'etiqueta': 'Tabique interventricular', 'por_defecto': 'INTACTO', 'ancho': 3,
     'opciones': [['INTACTO', 'Intacto'], ['DEFECTO', 'Defecto (CIV)'], ['CERRADO', 'Cierre quirúrgico (parche)']]},
    {'clave': 'civ_tipo', 'tipo': 'opcion', 'etiqueta': 'Tipo de CIV', 'ancho': 3,
     'visible_si': {'campo': 'tiv', 'igual': 'DEFECTO'},
     'opciones': [['PERIMEMBRANOSA', 'Perimembranosa'], ['MUSCULAR', 'Muscular'], ['ENTRADA', 'De entrada'],
                  ['SUBARTERIAL', 'Subarterial (doblemente relacionada)']]},
    {**_mm('civ_mm', 'Tamaño'), 'visible_si': {'campo': 'tiv', 'igual': 'DEFECTO'}},
    {'clave': 'civ_shunt', 'tipo': 'opcion', 'etiqueta': 'Shunt', 'opciones': SHUNT, 'ancho': 2,
     'visible_si': {'campo': 'tiv', 'igual': 'DEFECTO'}},
    {'clave': 'tiv_movimiento', 'tipo': 'opcion', 'etiqueta': 'Movimiento septal', 'ancho': 2,
     'opciones': [['NORMAL', 'Normal'], ['PARADOJICO', 'Paradójico']]},
    {'clave': 'tiv_detalle', 'tipo': 'texto', 'etiqueta': 'Detalle', 'ancho': 4,
     'ayuda': 'Ej.: sin shunt residual. Parche normoposicionado.'},

    {'clave': 'sub_vd', 'tipo': 'subtitulo', 'etiqueta': 'Ventrículo derecho'},
    {'clave': 'vd_estado', 'tipo': 'opcion', 'etiqueta': 'Ventrículo derecho', 'opciones': DILATACION,
     'por_defecto': 'NO', 'ancho': 3},
    _mm('vd_db', 'DB'), _mm('vd_dm', 'DM'), _mm('vd_dl', 'DL'), _mm('tapse', 'TAPSE'),
    _vel('vd_s', "s'"),
    {'clave': 'vd_area_d', 'tipo': 'numero', 'etiqueta': 'Área diástole', 'unidad': 'cm²', 'decimales': 2,
     'min': 0, 'max': 80, 'ancho': 2},
    {'clave': 'vd_area_s', 'tipo': 'numero', 'etiqueta': 'Área sístole', 'unidad': 'cm²', 'decimales': 2,
     'min': 0, 'max': 80, 'ancho': 2},
    {'clave': 'caf', 'tipo': 'calculado', 'etiqueta': 'CAF', 'unidad': '%', 'decimales': 1, 'funcion': 'cp.caf',
     'ancho': 2},

    {'clave': 'sub_vi', 'tipo': 'subtitulo', 'etiqueta': 'Ventrículo izquierdo'},
    _mm('sivd', 'SIVd'), _mm('ddvi', 'DdVI'), _mm('ppd', 'PPd'), _mm('sivs', 'SIVs'), _mm('dsvi', 'DsVI'),
    _mm('pps', 'PPs'),
    {'clave': 'fa', 'tipo': 'calculado', 'etiqueta': 'FA', 'unidad': '%', 'decimales': 0, 'funcion': 'cp.fa',
     'ancho': 2},
    {'clave': 'fevi_teichholz', 'tipo': 'calculado', 'etiqueta': 'FEVI (Teichholz)', 'unidad': '%', 'decimales': 0,
     'funcion': 'cp.fevi', 'ancho': 2},
    {'clave': 'fevi', 'tipo': 'texto', 'etiqueta': 'FEVI informada', 'ancho': 2,
     'ayuda': 'Vacío = la de Teichholz. Ej.: > 60 %'},

    {'clave': 'sub_tsvd', 'tipo': 'subtitulo', 'etiqueta': 'Tracto de salida del VD y válvula pulmonar'},
    _mm('tsvd_mm', 'TSVD'), _vel('tsvd_vmax'), _gp('tsvd_gp', 'tsvd_vmax'),
    {'clave': 'tsvd_detalle', 'tipo': 'texto', 'etiqueta': 'Detalle TSVD', 'ancho': 6,
     'ayuda': 'Ej.: rodete muscular de 12 mm hacia el tracto de salida, sin gradiente obstructivo'},
    _mm('pulm_anillo', 'Anillo pulmonar'), _z('pulm_z'), _vel('pulm_vmax'), _gp('pulm_gp', 'pulm_vmax'),
    _grado('pulm_ip', 'Insuficiencia'),
    {'clave': 'pulm_detalle', 'tipo': 'texto', 'etiqueta': 'Detalle pulmonar', 'ancho': 6,
     'ayuda': 'Ej.: con aliasing · jet excéntrico · TMP: 336 ms'},
    _mm('tap_mm', 'TAP'), _z('tap_z'), _vel('tap_vmax'), _gp('tap_gp', 'tap_vmax'),
    {'clave': 'tap_detalle', 'tipo': 'texto', 'etiqueta': 'Detalle TAP', 'ancho': 4, 'ayuda': 'Ej.: hipoplásico y tortuoso'},
    _mm('rd_mm', 'Rama derecha'), _z('rd_z'), _vel('rd_vmax'), _gp('rd_gp', 'rd_vmax'),
    _mm('ri_mm', 'Rama izquierda'), _z('ri_z'), _vel('ri_vmax'), _gp('ri_gp', 'ri_vmax'),
    {'clave': 'ramas', 'tipo': 'opcion', 'etiqueta': 'Ramas pulmonares', 'ancho': 3,
     'opciones': [['CONFLUENTES', 'Confluentes'], ['NO_CONFLUENTES', 'No confluentes']]},
    {'clave': 'ductus', 'tipo': 'opcion', 'etiqueta': 'Ductus', 'por_defecto': 'NO', 'ancho': 3,
     'opciones': [['NO', 'No se capta flujo'], ['PERMEABLE', 'Permeable'], ['LIGADO', 'Ligado']]},
    {**_mm('ductus_mm', 'Ductus'), 'visible_si': {'campo': 'ductus', 'igual': 'PERMEABLE'}},
    {'clave': 'ductus_shunt', 'tipo': 'opcion', 'etiqueta': 'Shunt ductal', 'opciones': SHUNT, 'ancho': 2,
     'visible_si': {'campo': 'ductus', 'igual': 'PERMEABLE'}},

    {'clave': 'sub_aorta', 'tipo': 'subtitulo', 'etiqueta': 'Aorta'},
    {'clave': 'ao_valva', 'tipo': 'opcion', 'etiqueta': 'Válvula aórtica', 'por_defecto': 'TRIVALVA', 'ancho': 2,
     'opciones': [['TRIVALVA', 'Trivalva'], ['BIVALVA', 'Bivalva'], ['UNIVALVA', 'Univalva']]},
    _mm('ao_anillo', 'Anillo'), _z('ao_z'), _vel('ao_vmax'), _gp('ao_gp', 'ao_vmax'),
    _grado('ao_ia', 'Insuficiencia'),
    _mm('ao_sv', 'Senos de Valsalva'), _mm('ao_ust', 'Unión sinotubular'), _mm('ao_asc', 'Aorta ascendente'),
    {'clave': 'arco', 'tipo': 'opcion', 'etiqueta': 'Arco aórtico', 'por_defecto': 'IZQUIERDO', 'ancho': 2,
     'opciones': [['IZQUIERDO', 'Izquierdo'], ['DERECHO', 'Derecho']]},
    {'clave': 'arco_obstruccion', 'tipo': 'opcion', 'etiqueta': 'Obstrucción', 'por_defecto': 'NO', 'ancho': 2,
     'opciones': [['NO', 'Sin obstrucción'], ['COARTACION', 'Coartación'], ['HIPOPLASIA', 'Hipoplasia']]},
    _vel('ao_desc_vmax', 'Vmáx Ao descendente'),

    {'clave': 'sub_pericardio', 'tipo': 'subtitulo', 'etiqueta': 'Pericardio y otros'},
    {'clave': 'derrame', 'tipo': 'opcion', 'etiqueta': 'Derrame pericárdico', 'por_defecto': 'NO', 'ancho': 3,
     'opciones': [['NO', 'No'], ['LEVE', 'Leve'], ['MODERADO', 'Moderado'], ['SEVERO', 'Severo']]},
    {'clave': 'trombos', 'tipo': 'si_no', 'etiqueta': 'Trombos', 'por_defecto': False, 'ancho': 2},
    {'clave': 'vegetaciones', 'tipo': 'si_no', 'etiqueta': 'Vegetaciones', 'por_defecto': False, 'ancho': 2},
    {'clave': 'otros', 'tipo': T, 'etiqueta': 'Otros hallazgos', 'filas': 2},
    {'clave': 'texto_informe', 'tipo': 'calculado', 'etiqueta': 'Así sale en el informe', 'funcion': 'cp.eco_texto',
     'filas': 8, 'ancho': 12},
]})

FICHA = [ANTECEDENTES]
CONSULTA = [EKG, ECO]
