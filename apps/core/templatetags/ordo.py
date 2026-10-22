"""Filtros comunes. Están en `builtins`: no hace falta {% load ordo %}."""
from decimal import Decimal, InvalidOperation

from django import template

from apps.core import fechas

register = template.Library()


def _formato_ve(numero, decimales=2):
    entero, dec = f'{abs(numero):,.{decimales}f}'.split('.')
    return f"{'-' if numero < 0 else ''}{entero.replace(',', '.')},{dec}"


@register.filter
def usd(valor):
    """1234.5 → '$ 1.234,50'."""
    try:
        numero = Decimal(valor or 0).quantize(Decimal('0.01'))
    except (InvalidOperation, TypeError, ValueError):
        return valor
    texto = _formato_ve(numero)
    return f'-$ {texto[1:]}' if texto.startswith('-') else f'$ {texto}'


@register.filter
def bs(valor_usd, tasa=1):
    """Monto en USD convertido con la tasa: '{{ precio|bs:tasa.bs_por_usd }}' → 'Bs 1.234,50'.
    Sin tasa formatea un monto que ya está en bolívares: '{{ pago.monto|bs }}'."""
    try:
        numero = (Decimal(valor_usd or 0) * Decimal(tasa)).quantize(Decimal('0.01'))
    except (InvalidOperation, TypeError, ValueError):
        return ''
    return f'Bs {_formato_ve(numero)}'


@register.filter
def numero_ve(valor, decimales=2):
    try:
        return _formato_ve(Decimal(valor), int(decimales))
    except (InvalidOperation, TypeError, ValueError):
        return valor


@register.filter
def hora12(valor):
    return fechas.hora12(valor)


@register.filter
def edad(fecha_nacimiento, referencia=None):
    return fechas.edad_texto(fecha_nacimiento, referencia)


@register.filter
def miles(valor):
    try:
        return f'{int(valor):,}'.replace(',', '.')
    except (TypeError, ValueError):
        return valor


@register.simple_tag
def url_pagina(querystring, numero):
    return f'?{querystring}&page={numero}' if querystring else f'?page={numero}'


@register.filter
def obtener(diccionario, clave):
    """{{ dic|obtener:clave }} — acceso a diccionarios con clave variable."""
    try:
        return diccionario.get(clave)
    except AttributeError:
        return None
