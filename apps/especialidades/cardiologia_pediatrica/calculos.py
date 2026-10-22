"""Campos calculados de cardiología pediátrica (nunca fallan: sin datos devuelven None)."""
from . import informe

GRADIENTES = ['tric_vmax', 'tsvd_vmax', 'pulm_vmax', 'tap_vmax', 'rd_vmax', 'ri_vmax', 'ao_vmax']


def _gradiente(vmax):
    def calcular(datos, contexto):
        return informe.gradiente(datos.get(vmax))
    return calcular


def _indexado(volumen):
    def calcular(datos, contexto):
        sc = contexto.get('sc')
        if not datos.get(volumen) or not sc:
            return None
        return round(float(datos[volumen]) / float(sc), 1)
    return calcular


def antecedentes(datos, contexto):
    return informe.antecedentes(datos) or None


def qtc(datos, contexto):
    return informe.qtc(datos)


def ekg_linea(datos, contexto):
    return informe.ekg_linea(datos) or None


def caf(datos, contexto):
    return informe.caf(datos)


def fa(datos, contexto):
    return informe.fa(datos)


def fevi(datos, contexto):
    return informe.fevi(datos)


def eco_texto(datos, contexto):
    return informe.eco(datos, contexto.get('sc')) or None


CALCULOS = {
    'cp.antecedentes': antecedentes, 'cp.qtc': qtc, 'cp.ekg_linea': ekg_linea, 'cp.caf': caf, 'cp.fa': fa,
    'cp.fevi': fevi, 'cp.eco_texto': eco_texto,
    **{f'cp.gradiente:{v}': _gradiente(v) for v in GRADIENTES},
    **{f'cp.indexado:{v}': _indexado(v) for v in ('ad_vol', 'ai_vol')},
}
