"""
Superficie corporal (SC). La fórmula la elige cada consultorio (Configuración → Historia clínica).

- Mosteller: √(talla × peso / 3600). La de siempre en adultos.
- Haycock: 0.024265 × peso^0.5378 × talla^0.3964. La que usan PHN/Lopez 2017, ParameterZ y PedZ para los Z-score
  pediátricos; por eso es la de cardiología pediátrica.
- DuBois: 0.007184 × peso^0.425 × talla^0.725.
"""
MOSTELLER, HAYCOCK, DUBOIS = 'MOSTELLER', 'HAYCOCK', 'DUBOIS'
FORMULAS = [(MOSTELLER, 'Mosteller'), (HAYCOCK, 'Haycock (Z-score pediátricos, PHN)'), (DUBOIS, 'DuBois')]


def calcular(peso_kg, talla_cm, formula=MOSTELLER):
    try:
        peso, talla = float(peso_kg), float(talla_cm)
    except (TypeError, ValueError):
        return None
    if peso <= 0 or talla <= 0:
        return None
    if formula == HAYCOCK:
        sc = 0.024265 * peso ** 0.5378 * talla ** 0.3964
    elif formula == DUBOIS:
        sc = 0.007184 * peso ** 0.425 * talla ** 0.725
    else:
        sc = (peso * talla / 3600) ** 0.5
    return round(sc, 2)


def formula_actual():
    """La del consultorio en curso (Mosteller si no hay tenant o configuración)."""
    from apps.core.tenancy import tenant_actual
    tenant = tenant_actual()
    if tenant is None:
        return MOSTELLER
    from apps.configuracion.models import ConfiguracionTenant
    formula = ConfiguracionTenant.objects.filter(tenant=tenant).values_list('formula_sc', flat=True).first()
    return formula or MOSTELLER
