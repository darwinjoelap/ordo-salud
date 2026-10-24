"""
Z-score del ecocardiograma con las tablas del Pediatric Heart Network (Lopez L et al., Circ Cardiovasc Imaging
2017;10:e006979, tabla 2). Es la referencia que la Dra. Sierra usa ahora en ParameterZ (study=lopez2017).

Modelo único (sin edad, sexo ni raza): Z = (medida / SC^α − media) / DE, con medida en cm y SC por Haycock.
Si la doctora escribe un Z a mano (otra calculadora), ese manda en el informe.
"""
from apps.clinica.superficie import HAYCOCK
from apps.clinica.superficie import calcular as calcular_sc

# campo del eco (mm) → (código PHN, α, media, DE)
TABLA = {
    'tric_anillo': ('TVLAT', 0.50, 2.36, 0.29),
    'mit_anillo': ('MVLAT', 0.50, 2.23, 0.22),
    'pulm_anillo': ('PVSAX', 0.50, 1.91, 0.24),
    'tap_mm': ('MPA', 0.50, 1.82, 0.24),
    'rd_mm': ('RPA', 0.50, 1.07, 0.18),
    'ri_mm': ('LPA', 0.50, 1.10, 0.18),
    'ao_anillo': ('ANN', 0.50, 1.48, 0.14),
    'ao_sv': ('ROOT', 0.50, 2.06, 0.18),
    'ao_ust': ('STJ', 0.50, 1.69, 0.16),
    'ao_asc': ('AAO', 0.50, 1.79, 0.18),
    'ddvi': ('LVEDD', 0.45, 3.89, 0.33),
    'ppd': ('LVPWT', 0.40, 0.57, 0.09),
    'sivd': ('LVST', 0.40, 0.58, 0.09),
}
REFERENCIA = 'PHN (Lopez 2017)'


def z(campo, medida_mm, sc):
    """Z-score de una medida en mm; None si falta la medida, la SC o la tabla."""
    fila = TABLA.get(campo)
    try:
        medida, sc = float(medida_mm), float(sc)
    except (TypeError, ValueError):
        return None
    if not fila or medida <= 0 or sc <= 0:
        return None
    _, alfa, media, de = fila
    return round((medida / 10 / sc ** alfa - media) / de, 2)


def sc_haycock(peso_kg, talla_cm):
    return calcular_sc(peso_kg, talla_cm, HAYCOCK)
