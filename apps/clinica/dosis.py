"""
Calculadora de dosis del glosario (portada de Pediae `Medicamento.calcular_dosis`).

Modos: por peso (rango mín/máx por kg con nivel mínimo · estándar = punto medio · máximo; unidades de masa con
concentración → mL, tabletas o gotas; unidades directas mL/kg, gotas/kg…), dosis fija y por rango de edad.
Redondeo: tabletas a ½, mL a 0,1, gotas/sobres/puffs a entero. Tope absoluto por dosis y alertas de edad y peso.

Diferencias con Pediae: el tope absoluto también limita las unidades directas cuando hay concentración; la dosis por
edad admite cualquier cantidad de rangos; nunca devuelve «nan» ni divide por cero.
"""
UNIDADES_PLURAL = {'tableta': 'tableta(s)', 'sobre': 'sobre(s)', 'puff': 'puff(s)', 'aplicacion': 'aplicación(es)'}


def _num(v):
    if v in (None, ''):
        return None
    return float(v) if not isinstance(v, float) else v


def _redondear(cantidad, unidad):
    if unidad == 'tableta':
        return round(cantidad * 2) / 2
    if unidad == 'mL':
        return round(cantidad, 1)
    if unidad in ('gotas', 'sobre', 'puff', 'aplicacion'):
        return round(cantidad)
    return round(cantidad, 1)


def _fmt(n):
    if n is None:
        return ''
    if float(n).is_integer():
        return str(int(n))
    return f'{n:g}'.replace('.', ',')


def _edad_txt(meses):
    a, m = divmod(int(meses), 12)
    if not a:
        return f'{m} meses'
    return f'{a} año{"s" if a > 1 else ""}' + (f' y {m} meses' if m else '')


def calcular(med, *, peso_kg=None, edad_meses=None, nivel='estandar'):
    """
    Devuelve {'dosis': texto para la tabla (p. ej. «5,5 mL»), 'dosis_mg': «165 mg» o '', 'frecuencia', 'duracion',
    'texto': plantilla de indicaciones resuelta, 'alertas': [{'tipo', 'msg'}], 'calculada': bool}.
    """
    peso = _num(peso_kg)
    alertas = []
    frecuencia = f'cada {med.frecuencia_horas} horas' if med.frecuencia_horas else ''
    duracion = (f'por {med.duracion_dias} día{"s" if med.duracion_dias != 1 else ""}' if med.duracion_dias else '')
    dosis_txt, dosis_mg_txt, calculada = '', '', False

    if edad_meses is not None:
        if med.edad_min_meses and edad_meses < med.edad_min_meses:
            alertas.append({'tipo': 'danger', 'msg': f'Contraindicado en menores de {_edad_txt(med.edad_min_meses)}.'})
        if med.edad_max_meses and edad_meses > med.edad_max_meses:
            alertas.append({'tipo': 'warning', 'msg': 'Paciente fuera del rango de edad: verificar dosis de adulto.'})
    if peso is not None and med.peso_min_kg and peso < float(med.peso_min_kg):
        alertas.append({'tipo': 'warning',
                        'msg': f'Peso por debajo del mínimo recomendado ({_fmt(float(med.peso_min_kg))} kg).'})

    if med.modo == 'FIJA':
        dosis_txt, calculada = med.dosis_fija, bool(med.dosis_fija)
    elif med.modo == 'EDAD':
        rango = None
        for r in med.rangos_edad or []:
            minimo, maximo = r.get('min'), r.get('max')
            if edad_meses is None or ((minimo is None or edad_meses >= minimo) and
                                      (maximo is None or edad_meses <= maximo)):
                rango = r
                break
        if rango and rango.get('dosis'):
            dosis_txt, calculada = rango['dosis'], True
        else:
            alertas.append({'tipo': 'warning', 'msg': 'No hay dosis definida para esta edad.'})
    else:   # PESO
        d_min, d_max = _num(med.dosis_kg_min), _num(med.dosis_kg_max)
        if d_min is None:
            if not med.indicaciones:     # con plantilla de indicaciones es un medicamento «de texto» (como en Pediae)
                alertas.append({'tipo': 'info', 'msg': 'Este medicamento no tiene dosis por kg cargada.'})
        elif peso is None or peso <= 0:
            alertas.append({'tipo': 'info', 'msg': 'Indica el peso para calcular la dosis.'})
        else:
            factor = d_min
            if d_max:
                factor = {'minimo': d_min, 'maximo': d_max}.get(nivel, (d_min + d_max) / 2)
            bruto = factor * peso
            unidad_kg = med.unidad_kg
            if unidad_kg in med.DIRECTAS:
                cantidad = _redondear(bruto, unidad_kg)
                dosis_txt = f'{_fmt(cantidad)} {UNIDADES_PLURAL.get(unidad_kg, unidad_kg)}'
                calculada = True
            else:
                masa = bruto
                tope = _num(med.dosis_max)
                if tope and masa > tope:
                    masa = tope
                    alertas.append({'tipo': 'info', 'msg': f'Dosis ajustada al tope de {_fmt(tope)} {unidad_kg} por dosis.'})
                dosis_mg_txt = f'{_fmt(round(masa, 1))} {unidad_kg}'
                conc, vol, unidad = _num(med.concentracion_mg), _num(med.volumen_ml), med.unidad_resultado
                if not conc or not unidad:
                    dosis_txt = dosis_mg_txt
                    if not conc:
                        alertas.append({'tipo': 'warning', 'msg': 'Falta la concentración: la dosis queda en '
                                                                  f'{unidad_kg}.'})
                    calculada = True
                else:
                    if unidad in ('mL', 'gotas'):
                        cantidad = masa / conc * (vol or 1)
                    elif unidad in ('tableta', 'sobre'):
                        cantidad = masa / conc
                    else:
                        cantidad = masa
                    cantidad = _redondear(cantidad, unidad)
                    dosis_txt = f'{_fmt(cantidad)} {UNIDADES_PLURAL.get(unidad, unidad)}'
                    calculada = True

    reemplazos = {'{{NOMBRE}}': med.nombre, '{{PRESENTACION}}': med.presentacion or '', '{{DOSIS}}': dosis_txt,
                  '{{DOSIS_MG}}': dosis_mg_txt, '{{FRECUENCIA}}': frecuencia, '{{DURACION}}': duracion,
                  '{{PESO}}': f'{_fmt(peso)} kg' if peso else ''}
    texto = med.indicaciones or ' '.join(x for x in (dosis_txt, frecuencia, duracion) if x)
    for k, v in reemplazos.items():
        texto = texto.replace(k, v)
    return {'medicamento': str(med), 'dosis': dosis_txt, 'dosis_mg': dosis_mg_txt, 'frecuencia': frecuencia,
            'duracion': duracion, 'texto': ' '.join(texto.split()), 'alertas': alertas, 'calculada': calculada,
            'rango': bool(med.dosis_kg_min and med.dosis_kg_max), 'con_indicaciones': bool(med.indicaciones)}

