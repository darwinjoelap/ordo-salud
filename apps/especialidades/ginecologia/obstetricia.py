"""
Cálculos obstétricos (sin dependencias, nunca fallan): edad gestacional (EG) por FUR o por ecografía, fecha probable
de parto (regla de Naegele: FUR + 280 días), trimestre y fórmula obstétrica.

Regla: si hay ecografía con EG, manda la ecografía (la FUR puede ser incierta); si no, la FUR.
"""
from datetime import date, timedelta

DURACION = 280                  # días (40 semanas)
POSTERMINO = 42 * 7             # más allá de 42 semanas ya no se considera embarazo en curso


def a_fecha(valor):
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor)) if valor else None
    except ValueError:
        return None


def _entero(valor):
    try:
        return int(valor) if valor not in (None, '') else None
    except (TypeError, ValueError):
        return None


def eg_dias(datos, fecha):
    """(dias, metodo) a la `fecha` dada. metodo = 'ECO' | 'FUR'. (None, '') si no hay con qué calcular."""
    fecha = a_fecha(fecha)
    if fecha is None:
        return None, ''
    eco = a_fecha(datos.get('eco_fecha'))
    semanas = _entero(datos.get('eco_semanas'))
    if eco and semanas is not None:
        dias = semanas * 7 + (_entero(datos.get('eco_dias')) or 0) + (fecha - eco).days
        if 0 <= dias <= POSTERMINO:
            return dias, 'ECO'
    fur = a_fecha(datos.get('fur'))
    if fur:
        dias = (fecha - fur).days
        if 0 <= dias <= POSTERMINO:
            return dias, 'FUR'
    return None, ''


def fpp(datos):
    """Fecha probable de parto (por ecografía si la hay, si no por FUR)."""
    eco = a_fecha(datos.get('eco_fecha'))
    semanas = _entero(datos.get('eco_semanas'))
    if eco and semanas is not None:
        return eco + timedelta(days=DURACION - (semanas * 7 + (_entero(datos.get('eco_dias')) or 0)))
    fur = a_fecha(datos.get('fur'))
    return fur + timedelta(days=DURACION) if fur else None


def texto_eg(dias):
    if dias is None:
        return ''
    s, d = divmod(int(dias), 7)
    return f'{s} sem' + (f' {d} d' if d else '')


def trimestre(dias):
    if dias is None:
        return None
    return 1 if dias < 14 * 7 else (2 if dias < 28 * 7 else 3)


def formula(datos):
    """'G3 P1 C1 A1' (E = ectópicos solo si hay). '' si no hay gestas cargadas."""
    g = _entero(datos.get('gestas'))
    if g is None:
        return ''
    p, c, a, e = (_entero(datos.get(k)) or 0 for k in ('partos', 'cesareas', 'abortos', 'ectopicos'))
    texto = f'G{g} P{p} C{c} A{a}' + (f' E{e}' if e else '')
    return texto


def formula_incongruente(datos):
    """True si partos + cesáreas + abortos + ectópicos superan las gestas (error de carga)."""
    g = _entero(datos.get('gestas'))
    if g is None:
        return False
    return sum(_entero(datos.get(k)) or 0 for k in ('partos', 'cesareas', 'abortos', 'ectopicos')) > g
