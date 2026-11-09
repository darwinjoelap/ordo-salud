"""
Consultorio de PRUEBAS multiespecialidad con pacientes FICTICIOS (nunca datos reales).

Es una sola unidad a la que se le van agregando médicos por especialidad. Cada especialidad con «paquete» de
escenarios carga sus pacientes y situaciones para probar a fondo (hoy: pediatría).

    python manage.py consultorio_pruebas --crear --clave "Clave-larga-123"           # consultorio + administrador
    python manage.py consultorio_pruebas --medico pediatria --usuario pediatra --clave "Clave-larga-123"
    python manage.py consultorio_pruebas --escenarios pediatria                     # (re)carga los casos
    python manage.py consultorio_pruebas --borrar                                   # borra solo los pacientes [DEMO]
    python manage.py consultorio_pruebas                                            # resumen

Las fechas son relativas a hoy (las edades y las citas «de mañana» siguen teniendo sentido cada vez que se carga).
Todo paciente queda marcado [DEMO] en observaciones; --borrar elimina solo esos y todo lo suyo.
"""
import contextlib
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.datastructures import MultiValueDict

from apps.core.permisos import Rol
from apps.core.tenancy import usando_tenant
from apps.plataforma.models import Especialidad, Tenant

MARCA = '[DEMO] Paciente ficticio del consultorio de pruebas.'
D = Decimal


def hace(dias):
    return timezone.localdate() - timedelta(days=dias)


# ── Paquete de pediatría ──────────────────────────────────────────────────────────────────────────────────────
# Cada caso prueba algo concreto (columna «prueba»). Peso/talla/PC dan percentiles OMS reales.

SERVICIOS_PED = [('Consulta pediátrica', D('30')), ('Control de niño sano', D('25')), ('Nebulización', D('10')),
                 ('Lavado de oídos', D('15'))]

GLOSARIO_PED = [
    {'nombre': 'Amoxicilina', 'presentacion': 'susp. 250 mg/5 mL', 'modo': 'PESO', 'unidad_kg': 'mg',
     'dosis_kg_min': D('15'), 'dosis_kg_max': D('25'), 'concentracion_mg': D('250'), 'volumen_ml': D('5'),
     'unidad_resultado': 'mL', 'dosis_max': D('500'), 'frecuencia_horas': 8, 'duracion_dias': 7,
     'indicaciones': '{{NOMBRE}} {{PRESENTACION}}: {{DOSIS}} {{FRECUENCIA}} {{DURACION}}'},
    {'nombre': 'Acetaminofén', 'presentacion': 'jarabe 160 mg/5 mL', 'modo': 'PESO', 'unidad_kg': 'mg',
     'dosis_kg_min': D('10'), 'dosis_kg_max': D('15'), 'concentracion_mg': D('160'), 'volumen_ml': D('5'),
     'unidad_resultado': 'mL', 'dosis_max': D('500'), 'frecuencia_horas': 6,
     'indicaciones': 'Dar {{DOSIS}} {{FRECUENCIA}} solo si fiebre (>38 °C) o dolor'},
    {'nombre': 'Ibuprofeno', 'presentacion': 'susp. 100 mg/5 mL', 'modo': 'PESO', 'unidad_kg': 'mg',
     'dosis_kg_min': D('5'), 'dosis_kg_max': D('10'), 'concentracion_mg': D('100'), 'volumen_ml': D('5'),
     'unidad_resultado': 'mL', 'dosis_max': D('400'), 'frecuencia_horas': 8, 'edad_min_meses': 6,
     'indicaciones': '{{DOSIS}} {{FRECUENCIA}} con alimentos'},
    {'nombre': 'Salbutamol', 'presentacion': 'inhalador 100 mcg', 'modo': 'FIJA', 'dosis_fija': '2 puffs',
     'frecuencia_horas': 6, 'duracion_dias': 5, 'indicaciones': '{{DOSIS}} con aerocámara {{FRECUENCIA}} {{DURACION}}'},
    {'nombre': 'Cetirizina', 'presentacion': 'gotas 10 mg/mL', 'modo': 'EDAD',
     'rangos_edad': [{'min': 6, 'max': 23, 'dosis': '2,5 mg (5 gotas)'}, {'min': 24, 'max': 71, 'dosis': '5 gotas'},
                     {'min': 72, 'max': None, 'dosis': '10 gotas'}],
     'frecuencia_horas': 24, 'indicaciones': '{{DOSIS}} una vez al día en la noche'},
    # «solo texto», como varios de Pediae: sin dosis por kg (prueba que la indicación entra igual)
    {'nombre': 'Solución salina nasal', 'presentacion': 'spray', 'modo': 'PESO',
     'indicaciones': '{{NOMBRE}} 2 atomizaciones en cada fosa nasal 3 veces al día'},
]

PEDIATRIA = [
    {'prueba': 'Lactante sano: 3 controles (curva OMS), vacunas al día, LME, cita de control próxima',
     'p': {'nombres': 'Camila Andrea', 'apellidos': 'Torres Blanco', 'sexo': 'F', 'nace': 130,
           'telefono': '0414-1000001'},
     'rep': ('Daniela Blanco', 'MADRE', '0414-1000001'),
     'ficha': {'ped.perinatales': {'edad_materna': 28, 'numero_gestacion': 1, 'control_prenatal': 'si',
                                   'consultas_prenatales': 9, 'semanas_gestacion': 39, 'via_parto': 'VAGINAL',
                                   'peso_nacer_g': 3250, 'talla_nacer_cm': 50, 'pc_nacer_cm': 34.5, 'apgar': '8/9',
                                   'complicaciones_neonatales': 'no', 'prueba_talon': 'NORMAL'},
               'ped.alimentacion': {'lme': 'si'}},
     'consultas': [
         {'dias': 100, 'tipo': 'CONTROL_SANO', 'peso': 4.5, 'talla': 54.5, 'pc': 37, 'motivo': 'Control del mes',
          'dx': ['Lactante sano'], 'plan': 'LME a libre demanda. Control en 1 mes.', 'servicio': 'Control de niño sano'},
         {'dias': 70, 'tipo': 'CONTROL_SANO', 'peso': 5.4, 'talla': 58, 'pc': 38.5, 'motivo': 'Control de 2 meses',
          'dx': ['Lactante sano'], 'plan': 'Vacunas de los 2 meses hoy.', 'servicio': 'Control de niño sano'},
         {'dias': 10, 'tipo': 'CONTROL_SANO', 'peso': 6.6, 'talla': 63, 'pc': 41, 'motivo': 'Control de 4 meses',
          'dx': ['Lactante sano'], 'plan': 'Continuar LME. Vacunas de 4 meses.', 'servicio': 'Control de niño sano'}],
     'vacunas': [('BCG', 1, 128), ('Hepatitis B', 1, 128), ('Pentavalente', 1, 70), ('Polio', 1, 70),
                 ('Neumococo', 1, 70), ('Rotavirus', 1, 70), ('Pentavalente', 2, 10), ('Polio', 2, 10)],
     'pesquisas': [('Eco de cadera', 60, 'Normal (Graf I)'), ('Audiología', 120, 'Otoemisiones pasa ambos oídos')],
     'citas': [{'dias': 50, 'estado': 'PROGRAMADA', 'hora': time(9, 0), 'motivo': 'Control de 6 meses'}]},

    {'prueba': 'Desnutrición: percentil que cae en 3 controles (estado nutricional en alerta)',
     'p': {'nombres': 'Luis Miguel', 'apellidos': 'Pérez Gil', 'sexo': 'M', 'nace': 300, 'telefono': '0424-1000002'},
     'rep': ('Yelitza Gil', 'MADRE', '0424-1000002'),
     'ficha': {'ped.perinatales': {'semanas_gestacion': 36, 'via_parto': 'CESAREA', 'peso_nacer_g': 2400,
                                   'talla_nacer_cm': 46}, 'ped.alimentacion': {'lme': 'no', 'formula': 'si'}},
     'consultas': [
         {'dias': 120, 'tipo': 'CONTROL_SANO', 'peso': 6.9, 'talla': 65, 'pc': 42, 'motivo': 'Control'},
         {'dias': 60, 'tipo': 'ENFERMEDAD', 'peso': 7.0, 'talla': 67, 'pc': 43, 'temp': 37.8,
          'motivo': 'Diarrea de 5 días', 'enf': 'Evacuaciones líquidas 6 al día, sin sangre. Come poco.',
          'dx': ['Diarrea aguda sin deshidratación'], 'plan': 'SRO a libre demanda. Zinc 10 días.'},
         {'dias': 5, 'tipo': 'SEGUIMIENTO', 'peso': 7.2, 'talla': 69.5, 'pc': 44, 'motivo': 'Control de peso',
          'dx': ['Desnutrición aguda moderada'], 'plan': 'Plan de recuperación nutricional. Control en 15 días.'}],
     'citas': [{'dias': 15, 'estado': 'TENTATIVA', 'motivo': 'Control de peso'}]},

    {'prueba': 'Obesidad: IMC sobre el percentil 97 (clasificación OMS)',
     'p': {'nombres': 'Santiago', 'apellidos': 'Rivas Mora', 'sexo': 'M', 'nace': 365 * 6 + 40},
     'rep': ('Carlos Rivas', 'PADRE', '0412-1000003'),
     'consultas': [{'dias': 20, 'tipo': 'CONTROL_SANO', 'peso': 31, 'talla': 117, 'motivo': 'Control escolar',
                    'enf': 'Come entre comidas, 3 h de pantallas al día.', 'dx': ['Obesidad'],
                    'plan': 'Plan de alimentación, 1 h de actividad física diaria, menos pantallas.',
                    'ordenes': 'Perfil lipídico, glicemia, insulina basal.'}]},

    {'prueba': 'ALERGIA a penicilina + otitis: la sugerencia IA debe avisar si propone amoxicilina',
     'p': {'nombres': 'Valeria', 'apellidos': 'Suárez Peña', 'sexo': 'F', 'nace': 365 * 4 + 100},
     'rep': ('María Peña', 'MADRE', '0416-1000004'),
     'antecedentes': {'alergias': 'Penicilina (urticaria generalizada a los 2 años)'},
     'consultas': [{'dias': 0, 'abierta': True, 'tipo': 'ENFERMEDAD', 'peso': 16.5, 'talla': 103, 'temp': 38.6,
                    'motivo': 'Fiebre y dolor de oído derecho', 'enf': '2 días con fiebre de 39 °C y otalgia derecha.',
                    'examen': 'Membrana timpánica derecha abombada, eritematosa.'}]},

    {'prueba': 'Asma: medicación actual, crisis con nebulización (procedimiento cobrado)',
     'p': {'nombres': 'Diego Alejandro', 'apellidos': 'Méndez Ruiz', 'sexo': 'M', 'nace': 365 * 5 + 200},
     'rep': ('Ana Ruiz', 'MADRE', '0414-1000005'),
     'antecedentes': {'enfermedades_cronicas': 'Asma intermitente', 'medicacion_actual': 'Salbutamol a demanda'},
     'ficha': {'ped.familiares': {'antecedentes': ['ASMA_ATOPIA']}},
     'consultas': [{'dias': 30, 'tipo': 'ENFERMEDAD', 'peso': 19, 'talla': 111, 'fc': 118, 'fr': 32, 'spo2': 93,
                    'temp': 37.2, 'motivo': 'Tos y dificultad para respirar',
                    'examen': 'Sibilancias espiratorias difusas, tiraje subcostal leve.',
                    'dx': ['Crisis asmática moderada'], 'plan': 'Nebulización en consulta. Salbutamol 5 días.',
                    'receta': [('Salbutamol inhalador 100 mcg', '2 puffs', 'cada 6 horas', 'por 5 días')],
                    'procedimiento': 'Nebulización'}]},

    {'prueba': 'Recién nacido prematuro con ictericia: ficha perinatal completa, pesquisas pendientes. OJO: hoy sale '
               '«desnutrición severa» porque Ordo usa edad cronológica, no corregida (pendiente)',
     'p': {'nombres': 'Mía', 'apellidos': 'González Lara', 'sexo': 'F', 'nace': 12},
     'rep': ('Patricia Lara', 'MADRE', '0424-1000006'),
     'ficha': {'ped.perinatales': {'edad_materna': 19, 'numero_gestacion': 1, 'control_prenatal': 'si',
                                   'consultas_prenatales': 4, 'complicaciones_embarazo': ['PREECLAMPSIA'],
                                   'semanas_gestacion': 34, 'via_parto': 'CESAREA',
                                   'indicacion_cesarea': 'Preeclampsia severa', 'peso_nacer_g': 2100,
                                   'talla_nacer_cm': 44, 'pc_nacer_cm': 31, 'apgar': '7/8',
                                   'complicaciones_neonatales': 'si', 'neonatales': ['ICTERICIA']},
               'ped.alimentacion': {'lme': 'si'}},
     'consultas': [{'dias': 2, 'tipo': 'CONTROL_SANO', 'peso': 2.25, 'talla': 45, 'pc': 31.5,
                    'motivo': 'Primer control del recién nacido', 'examen': 'Ictericia hasta abdomen (Kramer 3).',
                    'dx': ['Recién nacido pretérmino', 'Ictericia neonatal'],
                    'plan': 'Bilirrubina total y fraccionada. Control en 48 h.', 'ordenes': 'Bilirrubina T y F.'}],
     'vacunas': [('BCG', 1, 11), ('Hepatitis B', 1, 11)]},

    {'prueba': 'Adolescente con cédula propia, sin representante (mayor autonomía)',
     'p': {'nombres': 'Andrés Eduardo', 'apellidos': 'Castillo Vera', 'sexo': 'M', 'nace': 365 * 15 + 30,
           'tipo_documento': 'V', 'numero_documento': '33000111', 'telefono': '0412-1000007'},
     'consultas': [{'dias': 45, 'tipo': 'CONTROL_SANO', 'peso': 55, 'talla': 168, 'motivo': 'Certificado deportivo',
                    'dx': ['Adolescente sano'], 'plan': 'Apto para actividad deportiva.'}]},

    {'prueba': 'Gemelas (mismo nacimiento y apellidos): búsqueda y no confundirlas',
     'p': {'nombres': 'Sofía', 'apellidos': 'Ramírez Ortega', 'sexo': 'F', 'nace': 365 * 2 + 10},
     'rep': ('Luisa Ortega', 'MADRE', '0414-1000008'),
     'consultas': [{'dias': 25, 'tipo': 'CONTROL_SANO', 'peso': 11.8, 'talla': 86, 'motivo': 'Control de 2 años'}]},
    {'prueba': 'Gemelas (la otra)',
     'p': {'nombres': 'Sara', 'apellidos': 'Ramírez Ortega', 'sexo': 'F', 'nace': 365 * 2 + 10},
     'rep': ('Luisa Ortega', 'MADRE', '0414-1000008'),
     'consultas': [{'dias': 25, 'tipo': 'CONTROL_SANO', 'peso': 11.2, 'talla': 85, 'motivo': 'Control de 2 años'}]},

    {'prueba': 'COBROS: deuda, pago parcial en Bs, descuento y una consulta exonerada',
     'p': {'nombres': 'Emma', 'apellidos': 'Hernández Paz', 'sexo': 'F', 'nace': 365 * 3},
     'rep': ('Rosa Paz', 'ABUELO', '0416-1000009'),
     'consultas': [
         {'dias': 40, 'tipo': 'ENFERMEDAD', 'peso': 14, 'talla': 95, 'motivo': 'Tos', 'dx': ['Rinofaringitis aguda'],
          'servicio': 'Consulta pediátrica', 'exonerado': True},
         {'dias': 8, 'tipo': 'ENFERMEDAD', 'peso': 14.2, 'talla': 95.5, 'temp': 38.2, 'motivo': 'Fiebre',
          'dx': ['Faringoamigdalitis aguda'], 'servicio': 'Consulta pediátrica', 'descuento': D('5'),
          'pago': ('BS', D('400'))}]},

    {'prueba': 'Agenda: cita de HOY, de mañana, una no asistida y una confirmada',
     'p': {'nombres': 'Tomás', 'apellidos': 'Ochoa Linares', 'sexo': 'M', 'nace': 365 + 120},
     'rep': ('Gabriela Linares', 'MADRE', '0424-1000010'),
     'consultas': [{'dias': 60, 'tipo': 'CONTROL_SANO', 'peso': 9.8, 'talla': 76, 'pc': 46, 'motivo': 'Control'}],
     'citas': [{'dias': 0, 'estado': 'CONFIRMADA', 'hora': time(10, 30), 'motivo': 'Control de 16 meses'},
               {'dias': 1, 'estado': 'PROGRAMADA', 'hora': time(8, 30), 'motivo': 'Vacunas'},
               {'dias': -20, 'estado': 'NO_ASISTIO', 'hora': time(11, 0), 'motivo': 'Control'}]},

    {'prueba': 'Datos incompletos: sin fecha de nacimiento ni teléfono (avisos, sin percentiles)',
     'p': {'nombres': 'Kevin', 'apellidos': 'Sin Datos', 'sexo': 'M'},
     'consultas': [{'dias': 3, 'tipo': 'ENFERMEDAD', 'peso': 18, 'motivo': 'Dolor abdominal',
                    'dx': ['Dolor abdominal inespecífico']}]},

    {'prueba': 'Consulta EN BORRADOR de hoy (para seguir editando, dictar o sugerir con IA)',
     'p': {'nombres': 'Isabella', 'apellidos': 'Navarro Silva', 'sexo': 'F', 'nace': 365 * 8},
     'rep': ('Elena Silva', 'MADRE', '0414-1000012'),
     'consultas': [{'dias': 0, 'abierta': True, 'tipo': 'ENFERMEDAD', 'peso': 26, 'talla': 128, 'temp': 38.9,
                    'motivo': 'Fiebre y dolor de garganta', 'enf': 'Fiebre de 39 °C desde ayer, odinofagia.',
                    'examen': 'Amígdalas hipertróficas con exudado, adenopatías cervicales dolorosas.'}]},
]

# ── Paquete de medicina interna (adultos) ─────────────────────────────────────────────────────────────────────

SERVICIOS_MI = [('Consulta de medicina interna', D('35')), ('Control de medicina interna', D('25')),
                ('Electrocardiograma', D('15'))]


def _fija(nombre, presentacion, dosis, horas, dias=None, ind=None):
    return {'nombre': nombre, 'presentacion': presentacion, 'modo': 'FIJA', 'dosis_fija': dosis,
            'frecuencia_horas': horas, 'duracion_dias': dias,
            'indicaciones': ind or '{{NOMBRE}} {{PRESENTACION}}: {{DOSIS}} {{FRECUENCIA}} {{DURACION}}'}


GLOSARIO_MI = [
    _fija('Losartán', 'tab. 50 mg', '1 tableta', 24, ind='{{NOMBRE}} 50 mg: 1 tableta diaria en la mañana. No suspender.'),
    _fija('Amlodipino', 'tab. 5 mg', '1 tableta', 24),
    _fija('Metformina', 'tab. 850 mg', '1 tableta', 12, ind='{{NOMBRE}} 850 mg: 1 tableta con desayuno y cena.'),
    _fija('Atorvastatina', 'tab. 20 mg', '1 tableta', 24, ind='{{NOMBRE}} 20 mg: 1 tableta en la noche.'),
    _fija('Omeprazol', 'cáps. 20 mg', '1 cápsula', 24, 30, '{{NOMBRE}} 20 mg: 1 cápsula en ayunas por 30 días.'),
    _fija('Levotiroxina', 'tab. 50 mcg', '1 tableta', 24,
          ind='{{NOMBRE}} 50 mcg: 1 tableta en ayunas, 30 min antes del desayuno.'),
    _fija('Acetaminofén', 'tab. 500 mg', '1 tableta', 8, 3, '{{NOMBRE}} 500 mg: 1 tableta cada 8 h si dolor o fiebre.'),
    _fija('Diclofenac', 'tab. 50 mg', '1 tableta', 12, 5, '{{NOMBRE}} 50 mg: 1 tableta cada 12 h con comida, 5 días.'),
    _fija('Salbutamol', 'inhalador 100 mcg', '2 puffs', 6, 7),
    # solo texto (sin dosis), como varios glosarios reales
    {'nombre': 'Dieta hiposódica', 'modo': 'FIJA', 'indicaciones': 'Dieta baja en sal (< 5 g/día), sin embutidos.'},
]

ADULTOS = [
    {'prueba': 'HTA no controlada: 3 controles con TA que baja al ajustar tratamiento',
     'p': {'nombres': 'José Gregorio', 'apellidos': 'Martínez Rojas', 'sexo': 'M', 'nace': 365 * 58,
           'tipo_documento': 'V', 'numero_documento': '7000001', 'telefono': '0414-2000001'},
     'antecedentes': {'enfermedades_cronicas': 'Hipertensión arterial', 'medicacion_actual': 'Losartán 50 mg/día'},
     'consultas': [
         {'dias': 90, 'peso': 88, 'talla': 172, 'ta': (168, 102), 'fc': 84, 'motivo': 'Cefalea occipital',
          'enf': 'Cefalea matutina de 2 semanas. Toma losartán irregular.', 'dx': ['Hipertensión arterial no controlada'],
          'plan': 'Adherencia, dieta hiposódica. Se agrega amlodipino 5 mg.', 'ordenes': 'Perfil renal, EKG.',
          'receta': [('Losartán tab. 50 mg', '1 tableta', 'cada 24 horas', ''),
                     ('Amlodipino tab. 5 mg', '1 tableta', 'cada 24 horas', '')]},
         {'dias': 45, 'peso': 87, 'talla': 172, 'ta': (148, 92), 'fc': 78, 'motivo': 'Control de TA',
          'dx': ['Hipertensión arterial en ajuste'], 'labs': 'Creatinina 1,0 mg/dL. K 4,2.',
          'servicio': 'Control de medicina interna'},
         {'dias': 7, 'peso': 85, 'talla': 172, 'ta': (132, 84), 'fc': 72, 'motivo': 'Control de TA',
          'dx': ['Hipertensión arterial controlada'], 'servicio': 'Control de medicina interna'}],
     'citas': [{'dias': 60, 'estado': 'PROGRAMADA', 'hora': time(8, 0), 'motivo': 'Control de TA'}]},

    {'prueba': 'Diabetes tipo 2: glicemia y HbA1c altas, metformina, mejora en el control',
     'p': {'nombres': 'Carmen Elena', 'apellidos': 'Rodríguez Paz', 'sexo': 'F', 'nace': 365 * 52,
           'tipo_documento': 'V', 'numero_documento': '9000002', 'telefono': '0424-2000002'},
     'antecedentes': {'enfermedades_cronicas': 'Diabetes mellitus tipo 2', 'antecedentes_familiares': 'Madre DM2'},
     'consultas': [
         {'dias': 120, 'peso': 82, 'talla': 160, 'cintura': 102, 'ta': (130, 80), 'glicemia': 210,
          'motivo': 'Poliuria y polidipsia', 'dx': ['Diabetes mellitus tipo 2 de reciente diagnóstico'],
          'labs': 'Glicemia 210 mg/dL, HbA1c 9,1 %.', 'plan': 'Metformina, plan de alimentación, caminar 30 min.',
          'receta': [('Metformina tab. 850 mg', '1 tableta', 'cada 12 horas', '')]},
         {'dias': 30, 'peso': 78, 'talla': 160, 'cintura': 97, 'ta': (124, 78), 'glicemia': 128,
          'motivo': 'Control de diabetes', 'dx': ['Diabetes mellitus tipo 2 en mejoría'],
          'labs': 'HbA1c 7,2 %. Perfil lipídico: LDL 142.', 'servicio': 'Control de medicina interna'}]},

    {'prueba': 'Adulto mayor polimedicado: HTA + DM2 + ERC 3 + FA anticoagulada (interacciones, ajuste renal)',
     'p': {'nombres': 'Rafael Antonio', 'apellidos': 'Quintero Salas', 'sexo': 'M', 'nace': 365 * 78,
           'tipo_documento': 'V', 'numero_documento': '3000003'},
     'rep': ('Marisol Quintero', 'OTRO', '0412-2000003'),
     'antecedentes': {'enfermedades_cronicas': 'HTA, DM2, enfermedad renal crónica estadio 3, fibrilación auricular',
                      'medicacion_actual': 'Losartán 50 mg, metformina 500 mg, apixabán 2,5 mg c/12 h, '
                                           'atorvastatina 20 mg'},
     'consultas': [{'dias': 14, 'peso': 70, 'talla': 165, 'ta': (138, 76), 'fc': 96, 'motivo': 'Control trimestral',
                    'examen_det': {'cardiopulmonar': 'Ruidos cardíacos arrítmicos, sin soplos.'},
                    'dx': ['Fibrilación auricular permanente', 'Enfermedad renal crónica estadio 3a'],
                    'labs': 'Creatinina 1,6 mg/dL, TFG 42 mL/min.', 'plan': 'Ajustar metformina a la TFG.'}]},

    {'prueba': 'ALERGIA a AINE (ibuprofeno) + lumbalgia, consulta abierta: la IA debe avisar si propone AINE',
     'p': {'nombres': 'Luisa Fernanda', 'apellidos': 'Castro Mena', 'sexo': 'F', 'nace': 365 * 41},
     'antecedentes': {'alergias': 'Ibuprofeno (angioedema)'},
     'consultas': [{'dias': 0, 'abierta': True, 'peso': 64, 'talla': 162, 'ta': (118, 76),
                    'motivo': 'Dolor lumbar', 'enf': 'Dolor lumbar mecánico de 3 días tras cargar peso, sin irradiación.',
                    'examen_det': {'extremidades': 'Lasègue negativo. Contractura paravertebral lumbar.'}}]},

    {'prueba': 'Obesidad + dislipidemia: IMC y perímetro abdominal, estatina',
     'p': {'nombres': 'Pedro Luis', 'apellidos': 'Herrera Núñez', 'sexo': 'M', 'nace': 365 * 45},
     'consultas': [{'dias': 25, 'peso': 104, 'talla': 175, 'cintura': 112, 'ta': (134, 86),
                    'motivo': 'Chequeo', 'dx': ['Obesidad grado I', 'Dislipidemia mixta'],
                    'labs': 'CT 248, LDL 168, TG 260, HDL 36 mg/dL.',
                    'plan': 'Atorvastatina 20 mg. Déficit calórico y ejercicio.',
                    'receta': [('Atorvastatina tab. 20 mg', '1 tableta', 'cada 24 horas', '')]}]},

    {'prueba': 'EPOC exfumador: SpO2 baja, salbutamol',
     'p': {'nombres': 'Ramón', 'apellidos': 'Villegas Ortiz', 'sexo': 'M', 'nace': 365 * 67},
     'antecedentes': {'enfermedades_cronicas': 'EPOC', 'habitos': 'Exfumador (40 paquetes-año)'},
     'consultas': [{'dias': 18, 'peso': 68, 'talla': 170, 'ta': (126, 74), 'fc': 92, 'fr': 22, 'spo2': 91,
                    'motivo': 'Disnea de esfuerzo', 'examen_det': {'cardiopulmonar': 'Espiración prolongada, roncus.'},
                    'dx': ['EPOC'], 'ordenes': 'Espirometría, Rx de tórax PA.'}]},

    {'prueba': 'Hipotiroidismo: TSH alta, levotiroxina',
     'p': {'nombres': 'Gabriela', 'apellidos': 'Molina Duarte', 'sexo': 'F', 'nace': 365 * 36},
     'consultas': [{'dias': 35, 'peso': 70, 'talla': 158, 'ta': (112, 72), 'motivo': 'Cansancio y aumento de peso',
                    'labs': 'TSH 9,8 mUI/L, T4L 0,7 ng/dL.', 'dx': ['Hipotiroidismo primario'],
                    'receta': [('Levotiroxina tab. 50 mcg', '1 tableta', 'cada 24 horas', '')]}]},

    {'prueba': 'Chequeo preempleo sano: revisión por sistemas sin alteraciones',
     'p': {'nombres': 'Daniel', 'apellidos': 'Peña Rivas', 'sexo': 'M', 'nace': 365 * 26},
     'consultas': [{'dias': 50, 'peso': 72, 'talla': 178, 'ta': (116, 74), 'fc': 66, 'motivo': 'Evaluación preempleo',
                    'rxs': ['GENERAL', 'CV', 'RESP', 'DIG', 'GU', 'ME', 'NEURO', 'PIEL'], 'dx': ['Adulto sano'],
                    'plan': 'Apto para el cargo.'}]},

    {'prueba': 'COBROS: deuda pendiente y pago parcial en Bs (con EKG cobrado)',
     'p': {'nombres': 'Yolanda', 'apellidos': 'Suárez Linares', 'sexo': 'F', 'nace': 365 * 63},
     'consultas': [{'dias': 12, 'peso': 66, 'talla': 155, 'ta': (142, 88), 'motivo': 'Palpitaciones',
                    'dx': ['Extrasistolia ventricular'], 'pago': ('BS', D('600')),
                    'procedimiento': 'Electrocardiograma'}]},

    {'prueba': 'Agenda: cita hoy, mañana y una tentativa',
     'p': {'nombres': 'Héctor', 'apellidos': 'Blanco Díaz', 'sexo': 'M', 'nace': 365 * 49, 'telefono': '0416-2000010'},
     'consultas': [{'dias': 75, 'peso': 80, 'talla': 170, 'ta': (128, 82), 'motivo': 'Gastritis',
                    'dx': ['Dispepsia funcional'],
                    'receta': [('Omeprazol cáps. 20 mg', '1 cápsula', 'cada 24 horas', 'por 30 días')]}],
     'citas': [{'dias': 0, 'estado': 'CONFIRMADA', 'hora': time(15, 0), 'motivo': 'Control'},
               {'dias': 1, 'estado': 'PROGRAMADA', 'hora': time(16, 0), 'motivo': 'Resultados de laboratorio'},
               {'dias': 30, 'estado': 'TENTATIVA', 'motivo': 'Control'}]},

    {'prueba': 'Consulta EN BORRADOR de hoy: fiebre y tos (dictado / sugerencia IA)',
     'p': {'nombres': 'Marta', 'apellidos': 'Ibarra Colmenares', 'sexo': 'F', 'nace': 365 * 55},
     'consultas': [{'dias': 0, 'abierta': True, 'peso': 61, 'talla': 157, 'ta': (122, 70), 'temp': 38.7, 'fc': 104,
                    'fr': 24, 'spo2': 94, 'motivo': 'Fiebre y tos productiva',
                    'enf': '4 días con fiebre, tos con expectoración amarillenta y dolor torácico al toser.',
                    'examen_det': {'cardiopulmonar': 'Crepitantes en base derecha.'}}]},
]

PAQUETES = {'pediatria': {'casos': PEDIATRIA, 'servicios': SERVICIOS_PED, 'glosario': GLOSARIO_PED,
                          'plantilla': 'Consulta pediátrica', 'usuario': ('Dra.', 'Pía', 'Pruebas')},
            'medicina_interna': {'casos': ADULTOS, 'servicios': SERVICIOS_MI, 'glosario': GLOSARIO_MI, 'adulto': True,
                                 'plantilla': 'Primera consulta', 'plantilla_control': 'Control',
                                 'usuario': ('Dr.', 'Alí', 'González')}}


class Command(BaseCommand):
    help = 'Consultorio de pruebas multiespecialidad con pacientes ficticios.'

    def add_arguments(self, parser):
        parser.add_argument('--consultorio', default='pruebas', help='Enlace (por defecto «pruebas»).')
        parser.add_argument('--crear', action='store_true', help='Crea el consultorio con un administrador.')
        parser.add_argument('--medico', metavar='ESPECIALIDAD', help='Agrega un médico de esa especialidad.')
        parser.add_argument('--usuario', help='Usuario del administrador (--crear) o del médico (--medico).')
        parser.add_argument('--clave', help='Clave al crear un usuario.')
        parser.add_argument('--escenarios', metavar='ESPECIALIDAD', help='(Re)carga los casos de esa especialidad.')
        parser.add_argument('--borrar', action='store_true', help='Borra solo los pacientes [DEMO].')

    def handle(self, consultorio, crear, medico, usuario, clave, escenarios, borrar, **op):
        tenant = Tenant.objects.filter(slug=consultorio).first()
        if crear:
            if tenant is not None:
                raise CommandError(f'«{consultorio}» ya existe.')
            tenant = self._crear(consultorio, usuario or 'admin', clave)
        if tenant is None:
            raise CommandError(f'No existe «{consultorio}». Créalo con --crear --clave …')
        with usando_tenant(tenant):
            if borrar:
                self.stdout.write(self.style.SUCCESS(f'Borrados {self._borrar()} pacientes [DEMO] y todo lo suyo.'))
                return
            if medico:
                self._medico(tenant, medico, usuario, clave)
                escenarios = escenarios or (medico if medico in PAQUETES else None)
            if escenarios:
                self._escenarios(tenant, escenarios)
            self._resumen(tenant)

    # ── Consultorio y equipo ──────────────────────────────────────────────────────────────────────────────────
    def _clave(self, clave):
        if not clave or len(clave) < 10:
            raise CommandError('Indica --clave de al menos 10 caracteres.')
        return clave

    def _crear(self, slug, usuario, clave):
        from apps.plataforma import servicios
        clave = self._clave(clave)
        tenant, titular, _ = servicios.crear_tenant({
            'nombre': 'Consultorio de pruebas Ordo Salud', 'slug': servicios.validar_enlace(slug),
            'usuario_titular': usuario, 'nombre_titular': 'Administración', 'apellido_titular': 'Pruebas',
            'titular_es_profesional': False, 'especialidades': [],
            'notas': 'Consultorio de PRUEBAS: solo pacientes ficticios ([DEMO]).'})
        titular.set_password(clave)
        titular.debe_cambiar_clave = False
        titular.save(update_fields=['password', 'debe_cambiar_clave'])
        self.stdout.write(self.style.SUCCESS(f'Consultorio «{slug}» creado. Administrador: {usuario}.'))
        return tenant

    def _medico(self, tenant, codigo, usuario, clave):
        from apps.equipo.models import Membresia
        from apps.equipo.servicios import agregar
        from apps.plataforma.servicios import habilitar_especialidades
        esp = Especialidad.objects.filter(codigo=codigo, activa=True).first()
        if esp is None:
            raise CommandError(f'Especialidad «{codigo}» no existe. Opciones: '
                               + ', '.join(Especialidad.objects.filter(activa=True).values_list('codigo', flat=True)))
        if Membresia.objects.filter(tenant=tenant, activa=True, perfil__especialidad=esp, perfil__activo=True).exists():
            self.stdout.write(f'Ya hay un médico de {esp.nombre}: se usa ese.')
            return
        if not usuario:
            raise CommandError('Indica --usuario para el médico.')
        habilitar_especialidades(tenant, [esp])
        actor = Membresia.objects.filter(tenant=tenant, rol=Rol.TITULAR).first()
        titulo, nombre, apellido = PAQUETES.get(codigo, {}).get('usuario', ('Dr.', esp.nombre.split()[0], 'Pruebas'))
        m, _ = agregar(tenant, actor, usuario, nombre, apellido, Rol.MEDICO, especialidad=esp, titulo=titulo)
        m.usuario.set_password(self._clave(clave))
        m.usuario.debe_cambiar_clave = False
        m.usuario.save(update_fields=['password', 'debe_cambiar_clave'])
        self.stdout.write(self.style.SUCCESS(f'Médico de {esp.nombre} agregado: {usuario}.'))

    def _perfil(self, tenant, codigo):
        from apps.equipo.models import Membresia
        m = (Membresia.objects.filter(tenant=tenant, activa=True, perfil__especialidad__codigo=codigo,
                                      perfil__activo=True).select_related('perfil').first())
        if m is None:
            raise CommandError(f'No hay médico de «{codigo}». Agrégalo con --medico {codigo} --usuario … --clave …')
        return m.perfil

    # ── Escenarios ────────────────────────────────────────────────────────────────────────────────────────────
    def _escenarios(self, tenant, codigo):
        from apps.clinica import registro
        paquete = PAQUETES.get(codigo)
        if paquete is None:
            raise CommandError(f'Todavía no hay escenarios de «{codigo}». Hay: {", ".join(PAQUETES)}.')
        perfil = self._perfil(tenant, codigo)
        gancho = registro._al_guardar.pop('nucleo.plan', None)      # «próximo control» no crea citas aquí
        try:
            with transaction.atomic():
                self.paquete = paquete
                self._base(tenant, perfil, paquete)
                creados = 0
                for caso in paquete['casos']:
                    from apps.pacientes.models import Paciente
                    if Paciente.objects.filter(nombres=caso['p']['nombres'], apellidos=caso['p']['apellidos'],
                                               observaciones__startswith='[DEMO]').exists():
                        continue
                    self._caso(caso, perfil, paquete)
                    creados += 1
        finally:
            if gancho:
                registro._al_guardar['nucleo.plan'] = gancho
        self.stdout.write(self.style.SUCCESS(f'{creados} casos de {codigo} cargados.'))

    def _base(self, tenant, perfil, paquete):
        from apps.clinica.models import Medicamento
        from apps.cobros.models import Servicio
        from apps.configuracion.models import Lugar
        from apps.tasas import servicios as tasas
        self.lugar = Lugar.objects.first() or Lugar.objects.create(nombre='Consultorio principal', ciudad='Barquisimeto',
                                                                   direccion='Torre de pruebas, piso 1')
        self.servicios = {}
        for nombre, precio in paquete['servicios']:
            self.servicios[nombre] = Servicio.objects.get_or_create(nombre=nombre, defaults={'precio_usd': precio})[0]
        for datos in paquete['glosario']:
            if not Medicamento.objects.filter(nombre=datos['nombre'], profesional=perfil).exists():
                Medicamento.objects.create(profesional=perfil, rangos_edad=datos.get('rangos_edad', []),
                                           **{k: v for k, v in datos.items() if k != 'rangos_edad'})
        if tasas.tasa_vigente(tenant) is None:              # pagos en Bs necesitan tasa (ficticia, solo si no hay)
            tasas.registrar_del_tenant(tenant, D('40'), None, eur=D('45'))

    def _caso(self, caso, perfil, paquete):
        from apps.clinica import consultas as srv
        from apps.clinica.models import Consulta, PlantillaHistoria
        from apps.pacientes.models import AntecedenteBase, Paciente, Representante
        datos = dict(caso['p'])
        nace = datos.pop('nace', None)
        p = Paciente.objects.create(fecha_nacimiento=hace(nace) if nace is not None else None,
                                    observaciones=f"{MARCA} Prueba: {caso['prueba']}", **datos)
        if caso.get('rep'):
            nombre, parentesco, tel = caso['rep']
            Representante.objects.create(paciente=p, nombre=nombre, parentesco=parentesco, telefono=tel,
                                         es_principal=True)
        if caso.get('antecedentes'):
            AntecedenteBase.objects.update_or_create(paciente=p, defaults=caso['antecedentes'])
        if caso.get('ficha'):
            items = {i['codigo']: i for i in srv.items_ficha(perfil.especialidad.codigo)}
            limpios = {items[c]['seccion_id']: self._limpiar(items[c], v, {'paciente': p, 'sexo': p.sexo})
                       for c, v in caso['ficha'].items() if c in items}
            srv.guardar_ficha(p, [items[c] for c in caso['ficha'] if c in items], limpios)
        def plantilla(nombre):
            return PlantillaHistoria.objects.get(nombre=nombre, profesional__isnull=True,
                                                 especialidad=perfil.especialidad)
        primera = plantilla(paquete['plantilla'])
        control = plantilla(paquete.get('plantilla_control') or paquete['plantilla'])
        for n, c in enumerate(sorted(caso.get('consultas', []), key=lambda x: -x['dias'])):
            fecha = timezone.make_aware(datetime.combine(hace(c['dias']), time(9 + n % 8, 0)))
            consulta = srv.abrir_consulta(paciente=p, profesional=perfil, plantilla=control if n else primera,
                                          lugar=self.lugar, fecha_hora=fecha,
                                          tipo=Consulta.Tipo.CONTROL if n else Consulta.Tipo.PRIMERA)
            valores = self._valores(c, adulto=paquete.get('adulto', False))
            for _ in range(2):          # 2.ª vuelta con los signos ya guardados: percentiles con fecha correcta
                contexto = srv.contexto_calculo(consulta)
                srv.guardar_secciones(consulta, {
                    i['seccion_id']: self._limpiar(i, valores[i['codigo']], contexto)
                    for i in consulta.estructura if i['codigo'] in valores and i['ambito'] != 'PACIENTE'})
            if not c.get('abierta'):
                with contextlib.suppress(Exception), transaction.atomic():
                    srv.cerrar_consulta(consulta)
                Consulta.objects.filter(pk=consulta.pk).update(estado=Consulta.Estado.CERRADA, cerrada_en=fecha)
            self._cobro(p, perfil, consulta, c)
            if c.get('procedimiento'):
                self._procedimiento(p, perfil, c, fecha.date())
        for cita in caso.get('citas', []):
            self._cita(p, perfil, cita)
        self._vacunas(p, caso.get('vacunas', []))
        self._pesquisas(p, caso.get('pesquisas', []))

    @staticmethod
    def _valores(c, adulto=False):
        dx = [{'descripcion': d} for d in c.get('dx', [])]
        signos = {'temperatura': c.get('temp'), 'fc': c.get('fc'), 'fr': c.get('fr'), 'spo2': c.get('spo2')}
        if adulto:          # adultos: peso, talla, TA y glicemia van en signos vitales (no hay antropometría OMS)
            ta = c.get('ta') or (None, None)
            signos.update({'peso_kg': c.get('peso'), 'talla_cm': c.get('talla'), 'pa_sistolica': ta[0],
                           'pa_diastolica': ta[1], 'glicemia': c.get('glicemia'),
                           'perimetro_abdominal': c.get('cintura')})
        return {
            'ped.tipo': {'tipo': c.get('tipo', 'ENFERMEDAD')},
            'ped.antropometria': {'peso_kg': c.get('peso'), 'talla_cm': c.get('talla'), 'pc_cm': c.get('pc')},
            'nucleo.signos_vitales': signos,
            'nucleo.motivo': {'motivo': c.get('motivo'), 'enfermedad_actual': c.get('enf')},
            'nucleo.examen_fisico': {'general': c.get('examen'), **(c.get('examen_det') or {})},
            'nucleo.paraclinicos': {'laboratorio': c.get('labs'), 'imagenes': c.get('imagenes')},
            'gen.revision_sistemas': {'sin_alteraciones': c.get('rxs') or []},
            'nucleo.diagnosticos': {'diagnosticos': dx},
            'nucleo.plan': {'plan': c.get('plan')},
            'nucleo.ordenes': {'laboratorio': c.get('ordenes')},
            'nucleo.prescripcion': {'medicamentos': [{'medicamento': m, 'dosis': d, 'frecuencia': f, 'duracion': du}
                                                     for m, d, f, du in c.get('receta', [])]},
        }

    def _limpiar(self, item, datos, contexto):
        from apps.clinica.formularios import FormularioSeccion
        prefijo = f"s{item['seccion_id']}"
        post = MultiValueDict()
        for k, v in datos.items():
            if v in (None, '', []):
                continue
            if isinstance(v, list) and v and isinstance(v[0], dict):
                for i, fila in enumerate(v):
                    for sub, val in fila.items():
                        post[f'{prefijo}-{k}__{i}__{sub}'] = str(val)
            elif isinstance(v, list):
                post.setlist(f'{prefijo}-{k}', [str(x) for x in v])
            else:
                post[f'{prefijo}-{k}'] = str(v)
        form = FormularioSeccion(item['campos'], post, prefix=prefijo, contexto=contexto, exigir_requeridos=False)
        if not form.is_valid():
            raise CommandError(f"{item['codigo']}: {form.errors.as_text()}")
        return form.datos_limpios

    def _cobro(self, p, perfil, consulta, c):
        from apps.cobros import servicios as cobros
        serv = self.servicios.get(c.get('servicio')) if c.get('servicio') else None
        if serv is None and c.get('abierta'):
            return
        serv = serv or self.servicios[self.paquete['servicios'][0][0]]
        cobros.crear_cargo(paciente=p, servicio=serv, descripcion=serv.nombre, precio_usd=serv.precio_usd,
                           descuento_usd=c.get('descuento') or 0, exonerado=bool(c.get('exonerado')),
                           consulta=consulta, profesional=perfil, fecha=consulta.fecha_hora.date())
        if c.get('pago'):
            moneda, monto = c['pago']
            cobros.registrar_pago(paciente=p, monto=monto, moneda=moneda, metodo='PAGO_MOVIL',
                                  fecha=consulta.fecha_hora.date(), referencia='0000 (ficticio)')
        elif not c.get('exonerado') and not c.get('pago_pendiente', c['dias'] < 2):
            cobros.registrar_pago(paciente=p, monto=serv.precio_usd - (c.get('descuento') or 0), moneda='USD',
                                  metodo='EFECTIVO', fecha=consulta.fecha_hora.date())

    def _procedimiento(self, p, perfil, c, fecha):
        from apps.clinica.models import Procedimiento
        from apps.cobros import servicios as cobros
        from apps.cobros.models import Cargo
        serv = self.servicios[c['procedimiento']]
        proc = Procedimiento.objects.create(paciente=p, profesional=perfil, fecha=fecha, descripcion=serv.nombre)
        cargo = cobros.crear_cargo(paciente=p, servicio=serv, descripcion=serv.nombre, precio_usd=serv.precio_usd,
                                   profesional=perfil, fecha=fecha)
        Cargo.objects.filter(pk=cargo.pk).update(procedimiento=proc)

    def _cita(self, p, perfil, c):
        from apps.agenda.models import Cita
        hora = c.get('hora')
        fin = (datetime.combine(hace(0), hora) + timedelta(minutes=20)).time() if hora else None
        Cita.objects.create(paciente=p, profesional=perfil, especialidad=perfil.especialidad, lugar=self.lugar,
                            fecha=hace(-c['dias']), hora_inicio=hora, hora_fin=fin, estado=c['estado'],
                            motivo=c.get('motivo', ''))

    def _vacunas(self, p, vacunas):
        from apps.especialidades.pediatria.models import Vacuna, VacunaAplicada
        for nombre, dosis, dias in vacunas:
            v = Vacuna.objects.filter(tenant__isnull=True, nombre__icontains=nombre, dosis=dosis).first()
            if v:
                VacunaAplicada.objects.create(paciente=p, vacuna=v, fecha=hace(dias), lote='LOTE-PRUEBA')

    def _pesquisas(self, p, pesquisas):
        from apps.especialidades.pediatria.models import Pesquisa, PesquisaRealizada
        for nombre, dias, resultado in pesquisas:
            x = Pesquisa.objects.filter(tenant__isnull=True, nombre=nombre).first()
            if x:
                PesquisaRealizada.objects.create(paciente=p, pesquisa=x, fecha=hace(dias), resultado=resultado)

    # ── Borrar / resumen ──────────────────────────────────────────────────────────────────────────────────────
    @staticmethod
    @transaction.atomic
    def _borrar():
        from django.apps import apps
        demo = apps.get_model('pacientes.Paciente').objects.filter(observaciones__startswith='[DEMO]')
        n = demo.count()
        for modelo in ('cobros.PagoAplicado', 'cobros.Pago', 'cobros.Cargo', 'documentos.DocumentoEmitido',
                       'agenda.Cita', 'dictado.SesionDictado', 'dictado.SugerenciaIA', 'clinica.Procedimiento'):
            with contextlib.suppress(LookupError):
                m = apps.get_model(modelo)
                campo = 'pago__paciente__in' if modelo == 'cobros.PagoAplicado' else 'paciente__in'
                getattr(m, 'todos', m.objects).filter(**{campo: demo}).delete()
        apps.get_model('clinica.Consulta').todos.filter(paciente__in=demo).delete()
        demo.delete()
        return n

    def _resumen(self, tenant):
        from apps.equipo.models import Membresia
        from apps.pacientes.models import Paciente
        self.stdout.write(f'\nConsultorio «{tenant.nombre}» ({tenant.slug})')
        for m in Membresia.objects.filter(tenant=tenant, activa=True).select_related('usuario', 'perfil__especialidad'):
            esp = m.perfil.especialidad.nombre if getattr(m, 'perfil', None) else '—'
            self.stdout.write(f'  · {m.usuario.username:20} {m.get_rol_display():14} {esp}')
        self.stdout.write(f'  Pacientes [DEMO]: {Paciente.objects.filter(observaciones__startswith="[DEMO]").count()}')
        self.stdout.write(f'  Escenarios disponibles: {", ".join(PAQUETES)}')

