"""Puntuación sin acceso a datos clínicos ni efectos de escritura."""
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Resultado:
    estado: str
    motivo: str = ''
    puntos: dict | None = None
    total: int | Decimal | None = None
    clase: str = ''
    interpretacion: str = ''
    derivados: tuple = ()


def _si(datos, nombre, puntos):
    return puntos if datos[nombre] == 'si' else 0


def _total(puntos, cortes, interpretaciones):
    total = sum(puntos.values())
    indice = sum(total > corte for corte in cortes)
    clase = ('I', 'II', 'III', 'IV')[indice]
    return Resultado('evaluado', puntos=puntos, total=total, clase=clase, interpretacion=interpretaciones[indice])


def _pendiente(motivo):
    return Resultado('regla_pendiente', motivo)


def goldman(d):
    if d['edad'] <= 40:
        return Resultado('no_aplica', 'La cohorte original incluyó mayores de 40 años.')
    if d['infarto'] == 'limite':
        return _pendiente('Infarto a seis meses exactos. La frontera temporal requiere revisión clínica.')
    puntos = {
        'edad': 5 if d['edad'] > 70 else 0,
        'infarto': 10 if d['infarto'] == 'reciente' else 0,
        's3_yugular': _si(d, 's3_yugular', 11),
        'estenosis': _si(d, 'estenosis', 3),
        'ritmo': _si(d, 'ritmo', 7),
        'ectopia': 7 if d['ectopia'] > 5 else 0,
        'estado_general': _si(d, 'estado_general', 3),
        'tipo_cirugia': _si(d, 'tipo_cirugia', 3),
        'emergencia': _si(d, 'emergencia', 4),
    }
    cortes = (5, 12, 25)
    interpretacion = 'Estrato histórico de complicaciones cardíacas graves o mortales. Sin probabilidad individual.'
    return _total(puntos, cortes, (interpretacion,) * 4)


def detsky(d):
    if d['edad'] < 18:
        return Resultado('no_aplica', 'El uso pediátrico está fuera del ámbito definido.')
    if d['edad'] == 70:
        return _pendiente('Edad exacta de 70 años. La descripción original y la tabla posterior discrepan.')
    if d['infarto'] == 'limite' or d['edema'] == 'limite':
        return _pendiente('Evento en la frontera temporal. El límite requiere revisión clínica.')
    puntos = {
        'edad': 5 if d['edad'] > 70 else 0,
        'infarto': {'no': 0, 'reciente': 10, 'remoto': 5}[d['infarto']],
        'angina_ccs': {'no': 0, 'III': 10, 'IV': 20}[d['angina_ccs']],
        'inestable': _si(d, 'inestable', 10),
        'edema': {'no': 0, 'reciente': 10, 'remoto': 5}[d['edema']],
        'estenosis': _si(d, 'estenosis', 20),
        'ritmo': _si(d, 'ritmo', 5),
        'ectopia_o_tv_fv': _si(d, 'ectopia_o_tv_fv', 5),
        'estado_general': _si(d, 'estado_general', 5),
        'emergencia': _si(d, 'emergencia', 10),
    }
    total = sum(puntos.values())
    clase = 'I' if total <= 15 else 'II' if total <= 30 else 'III'
    return Resultado('evaluado', puntos=puntos, total=total, clase=clase,
                     interpretacion='Estrato histórico. La probabilidad posprueba requiere calibración local.')


def ariscat(d):
    edad = d['edad']
    if edad < 18:
        return Resultado('no_aplica', 'La cohorte original excluyó menores de 18 años.')
    if d['modo_spo2'] != 'aire_supino':
        return Resultado('datos_insuficientes', 'Se requiere SpO₂ en aire ambiente y decúbito supino.')
    duracion = d['duracion']
    puntos = {
        'edad': 0 if edad <= 50 else 3 if edad <= 80 else 16,
        'spo2': 0 if d['spo2'] >= 96 else 8 if d['spo2'] >= 91 else 24,
        'infeccion': _si(d, 'infeccion', 17),
        'hb': 11 if d['hb'] <= 10 else 0,
        'incision': {'periferica': 0, 'superior': 15, 'intratoracica': 24}[d['incision']],
        'duracion': 0 if duracion <= 120 else 16 if duracion <= 180 else 23,
        'emergencia': _si(d, 'emergencia', 8),
    }
    total = sum(puntos.values())
    clase = 'Bajo' if total < 26 else 'Intermedio' if total < 45 else 'Alto'
    return Resultado('evaluado', puntos=puntos, total=total, clase=clase,
                     interpretacion='Estrato de complicaciones pulmonares posoperatorias intrahospitalarias.')


def rcri(d):
    if d['edad'] < 50:
        return Resultado('no_aplica', 'La cohorte de Lee 1999 incluyó pacientes de 50 años o más.')
    puntos = {k: _si(d, k, 1) for k in ('tipo_cirugia', 'isquemica', 'falla_cardiaca', 'cerebrovascular', 'insulina')}
    puntos['creatinina'] = int(d['creatinina'] > Decimal('2.0'))
    return _total(puntos, (0, 1, 2), tuple(
        f'Complicaciones cardíacas mayores intrahospitalarias en la cohorte de validación de Lee: {tasa}.'
        for tasa in ('0,4 %', '0,9 %', '6,6 %', '11,0 %')
    ))


CAPRINI_UN_PUNTO = (
    'cirugia_previa', 'varices', 'edema_piernas', 'eii', 'infarto_reciente', 'falla_cardiaca',
    'infeccion_grave', 'hormonas', 'embarazo_puerperio', 'antecedente_obstetrico', 'tabaco', 'insulina',
    'quimioterapia', 'transfusion',
)
CAPRINI_CINCO_PUNTOS = ('fractura', 'trauma_grave', 'lesion_medular', 'ictus')


def caprini(d):
    """Reglas verificadas de la edición 2013, fuera de las rutas clínicas hasta resolver derechos."""
    adicionales = ('edad', 'imc', 'duracion', 'artroplastias', 'movilidad', 'enfermedades_pulmonares',
                   'canceres', 'inmovilizacion', 'acceso_central', 'episodios_venosos', 'historia_familiar',
                   'marcadores', 'vih', 'aplica_reproductivo')
    if any(d.get(k) in (None, '') for k in CAPRINI_UN_PUNTO + CAPRINI_CINCO_PUNTOS + adicionales):
        return Resultado('datos_insuficientes', 'Revisa los factores incompletos del modelo.')
    if 'discordante' in d.values():
        return Resultado('contradiccion', 'Aclara los factores discordantes.')
    if d['edad'] < 18:
        return Resultado('no_aplica', 'El alcance previsto es quirúrgico adulto.')
    if (d['embarazo_puerperio'] == 'si') and d['aplica_reproductivo'] != 'si':
        return Resultado('contradiccion', 'Confirma los datos reproductivos.')
    if d['aplica_reproductivo'] == 'no' and any(d[k] == 'si' for k in ('hormonas', 'antecedente_obstetrico')):
        return Resultado('contradiccion', 'Los factores reproductivos no son coherentes.')
    if d['vih'] == 'si':
        return _pendiente('El tratamiento de VIH difiere entre el formulario y la guía de trombofilia.')
    if d['fractura'] == d['trauma_grave'] == 'si':
        return _pendiente('Fractura y trauma grave requieren adjudicar el posible doble conteo.')
    artroplastia = d['artroplastias']
    duracion = d['duracion']
    if not artroplastia and duracion == 45:
        return _pendiente('El formulario publicado deja sin asignar 45 minutos exactos.')
    edad, imc = d['edad'], d['imc']
    puntos = {k: _si(d, k, 1) for k in CAPRINI_UN_PUNTO}
    puntos.update({k: _si(d, k, 5) for k in CAPRINI_CINCO_PUNTOS})
    puntos.update({
        'edad': 0 if edad <= 40 else 1 if edad <= 60 else 2 if edad <= 74 else 3,
        'imc': int(imc > 25) + int(imc > 40),
        'duracion': 0 if artroplastia else 1 if duracion < 45 else 2 + int(duracion > 120),
        'artroplastias': 5 * artroplastia,
        'movilidad': {'sin_restriccion': 0, 'menos_72': 1, 'desde_72': 2}[d['movilidad']],
        'enfermedades_pulmonares': d['enfermedades_pulmonares'],
        'canceres': 2 * d['canceres'],
        'inmovilizacion': _si(d, 'inmovilizacion', 2),
        'acceso_central': _si(d, 'acceso_central', 2),
        'episodios_venosos': 3 * d['episodios_venosos'],
        'historia_familiar': _si(d, 'historia_familiar', 3),
        'marcadores': 3 * d['marcadores'],
        'vih': 0,
    })
    return Resultado('evaluado', puntos=puntos, total=sum(puntos.values()), clase='Sin categoría universal',
                     interpretacion='Riesgo tromboembólico. La categoría depende de la población quirúrgica.')


PESOS_DASI = tuple(map(Decimal, ('2.75', '1.75', '2.75', '5.50', '8', '2.70', '3.50', '8', '4.50', '5.25', '6', '7.50')))


def dasi(respuestas):
    """Verifica la fórmula con vectores numerados, sin contenido de los ítems protegidos."""
    if len(respuestas) != len(PESOS_DASI) or any(type(r) is not bool for r in respuestas):
        return Resultado('datos_insuficientes', 'Se requieren doce respuestas explícitas.')
    puntos = {str(i): peso if respuesta else Decimal(0)
              for i, (respuesta, peso) in enumerate(zip(respuestas, PESOS_DASI), 1)}
    total = sum(puntos.values())
    vo2 = Decimal('0.43') * total + Decimal('9.6')
    precision = Decimal('0.01')
    return Resultado(
        'evaluado', puntos=puntos, total=total,
        clase='≤34 puntos' if total <= 34 else '>34 puntos',
        interpretacion='Capacidad funcional autorreportada. El umbral perioperatorio depende de la población.',
        derivados=(('VO₂ pico estimado (mL/kg/min)', str(vo2.quantize(precision))),
                   ('METS estimados por DASI', str((vo2 / Decimal('3.5')).quantize(precision)))),
    )
