"""Campos calculados de ginecología (nunca fallan: sin datos devuelven None)."""
from . import obstetricia as ob


def eg(datos, contexto):
    dias, metodo = ob.eg_dias(datos, contexto.get('fecha'))
    if dias is None:
        return None
    return f'{ob.texto_eg(dias)} (por {"ecografía" if metodo == "ECO" else "FUR"})'


def fpp(datos, contexto):
    f = ob.fpp(datos)
    return f.strftime('%d/%m/%Y') if f else None


def formula(datos, contexto):
    texto = ob.formula(datos)
    if not texto:
        return None
    return texto + (' — revisar: la suma supera las gestas' if ob.formula_incongruente(datos) else '')


CALCULOS = {'go.eg': eg, 'go.fpp': fpp, 'go.formula': formula}
