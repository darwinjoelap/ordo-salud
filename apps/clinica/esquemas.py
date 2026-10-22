"""
Esquema de campos de una sección clínica: contrato ÚNICO para formulario, validación, PDF, reportes y dictado
(ADR-007, docs/01_MODELO_DATOS.md §6).

    {"campos": [{"clave": "peso", "tipo": "numero", "etiqueta": "Peso", "unidad": "kg", "min": 0.3,
                 "max": 300, "decimales": 2, "requerido": true, "ancho": 3}, ...]}

Atributos comunes: clave, tipo, etiqueta, ancho (1–12, por defecto según el tipo), requerido, ayuda,
por_defecto, visible_si {"campo": clave, "igual": valor | "en": [valores] | "distinto": valor}.
"""
import re
from datetime import date, time
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from apps.core.numeros import numero as leer_numero

TIPOS = {
    'texto': 'Texto corto',
    'texto_largo': 'Texto largo',
    'numero': 'Número',
    'fecha': 'Fecha',
    'hora': 'Hora',
    'si_no': 'Sí / No',
    'opcion': 'Una opción de una lista',
    'opciones': 'Varias opciones de una lista',
    'escala': 'Escala (p. ej. 0 a 10)',
    'tabla': 'Tabla (filas repetibles)',
    'subtitulo': 'Subtítulo (solo texto)',
    'calculado': 'Calculado (solo módulos)',
}
TIPOS_PERSONALIZABLES = [t for t in TIPOS if t != 'calculado']
TIPOS_SIN_DATO = {'subtitulo'}
ANCHO_POR_DEFECTO = {'texto_largo': 12, 'tabla': 12, 'subtitulo': 12, 'opciones': 12, 'escala': 6, 'texto': 6}
CLAVE_VALIDA = re.compile(r'^[a-z][a-z0-9_]{0,39}$')


class ErrorEsquema(ValueError):
    pass


def ancho(campo):
    try:
        n = int(campo.get('ancho') or ANCHO_POR_DEFECTO.get(campo['tipo'], 4))
    except (TypeError, ValueError):
        n = 4
    return min(max(n, 1), 12)


def opciones_de(campo):
    """[[valor, texto], ...] aunque el esquema traiga una lista simple de textos."""
    salida = []
    for op in campo.get('opciones') or []:
        if isinstance(op, (list, tuple)) and len(op) == 2:
            salida.append([str(op[0]), str(op[1])])
        else:
            salida.append([str(op), str(op)])
    return salida


def validar_esquema(esquema, permitir_calculado=True):
    """Lista de errores (vacía si el esquema es válido)."""
    errores = []
    if not isinstance(esquema, dict) or not isinstance(esquema.get('campos'), list):
        return ['El esquema debe ser un objeto con la lista "campos".']
    claves = set()
    for i, campo in enumerate(esquema['campos'], 1):
        donde = f'Campo {i}'
        if not isinstance(campo, dict):
            errores.append(f'{donde}: debe ser un objeto.')
            continue
        clave, tipo = campo.get('clave', ''), campo.get('tipo')
        donde = f'Campo {i} ({clave or "sin clave"})'
        if not CLAVE_VALIDA.match(str(clave)):
            errores.append(f'{donde}: clave inválida (minúsculas, números y _; empieza con letra).')
        elif clave in claves:
            errores.append(f'{donde}: clave repetida.')
        claves.add(clave)
        if tipo not in TIPOS:
            errores.append(f'{donde}: tipo desconocido "{tipo}".')
            continue
        if tipo == 'calculado' and not permitir_calculado:
            errores.append(f'{donde}: los campos calculados solo existen en módulos de especialidad.')
        if not campo.get('etiqueta') and tipo != 'calculado':
            errores.append(f'{donde}: falta la etiqueta.')
        if tipo in ('opcion', 'opciones') and not opciones_de(campo):
            errores.append(f'{donde}: indica al menos una opción.')
        if tipo == 'escala':
            try:
                if int(campo.get('min', 0)) >= int(campo.get('max', 10)):
                    errores.append(f'{donde}: el mínimo de la escala debe ser menor que el máximo.')
            except (TypeError, ValueError):
                errores.append(f'{donde}: mínimo y máximo de la escala deben ser enteros.')
        if tipo == 'tabla':
            subs = campo.get('subcampos') or []
            if not subs:
                errores.append(f'{donde}: una tabla necesita columnas (subcampos).')
            for sub in subs:
                if not CLAVE_VALIDA.match(str(sub.get('clave', ''))) or sub.get('tipo', 'texto') not in (
                        'texto', 'numero', 'fecha', 'opcion'):
                    errores.append(f'{donde}: columna inválida {sub.get("clave")!r}.')
        if tipo == 'calculado' and not campo.get('funcion'):
            errores.append(f'{donde}: un campo calculado necesita "funcion".')
    for campo in esquema['campos']:
        cond = campo.get('visible_si') if isinstance(campo, dict) else None
        if cond and cond.get('campo') not in claves:
            errores.append(f'Campo {campo.get("clave")}: visible_si apunta a un campo que no existe.')
    return errores


def asegurar_valido(esquema, permitir_calculado=True):
    errores = validar_esquema(esquema, permitir_calculado)
    if errores:
        raise ErrorEsquema('; '.join(errores))
    return esquema


def campos_efectivos(esquema, ajustes=None):
    """Campos del esquema aplicando los ajustes de la plantilla (ocultos, etiquetas, por defecto, requeridos, opcionales)."""
    ajustes = ajustes or {}
    ocultos = set(ajustes.get('ocultos') or [])
    etiquetas = ajustes.get('etiquetas') or {}
    por_defecto = ajustes.get('por_defecto') or {}
    requeridos = set(ajustes.get('requeridos') or [])
    opcionales = set(ajustes.get('opcionales') or [])     # la plantilla puede volver opcional un campo obligatorio
    salida = []
    for campo in esquema.get('campos', []):
        if campo['clave'] in ocultos and not campo.get('requerido'):
            continue
        c = dict(campo)
        if campo['clave'] in etiquetas and etiquetas[campo['clave']]:
            c['etiqueta'] = etiquetas[campo['clave']]
        if campo['clave'] in por_defecto:
            c['por_defecto'] = por_defecto[campo['clave']]
        if campo['clave'] in requeridos:
            c['requerido'] = True
        if campo['clave'] in opcionales:
            c['requerido'] = False
        salida.append(c)
    return salida


def _visible(campo, datos):
    cond = campo.get('visible_si')
    if not cond:
        return True
    valor = datos.get(cond.get('campo'))
    if 'igual' in cond:
        return valor == cond['igual'] or (isinstance(valor, list) and cond['igual'] in valor)
    if 'en' in cond:
        return valor in cond['en']
    if 'distinto' in cond:
        return valor != cond['distinto']
    return bool(valor)


def _numero(valor, campo, errores, etiqueta):
    if valor in (None, ''):
        return None
    if isinstance(valor, (int, float, Decimal)):
        d = Decimal(str(valor))
    else:
        d = leer_numero(str(valor))
        if d is None:
            errores[campo['clave']] = f'{etiqueta}: escribe un número.'
            return None
    if campo.get('min') is not None and d < Decimal(str(campo['min'])):
        errores[campo['clave']] = f'{etiqueta}: el mínimo es {campo["min"]}.'
    if campo.get('max') is not None and d > Decimal(str(campo['max'])):
        errores[campo['clave']] = f'{etiqueta}: el máximo es {campo["max"]}.'
    decimales = int(campo.get('decimales', 2))
    d = d.quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP)
    return int(d) if decimales == 0 else float(d)


def normalizar_valor(campo, valor, errores):
    """Convierte un valor crudo (formulario, JSON offline o dictado) al tipo del campo, apto para JSON."""
    tipo = campo['tipo']
    etiqueta = campo.get('etiqueta') or campo['clave']
    if tipo in ('texto', 'texto_largo'):
        texto = '' if valor is None else str(valor).strip()
        return texto or None
    if tipo == 'numero':
        return _numero(valor, campo, errores, etiqueta)
    if tipo == 'fecha':
        if valor in (None, ''):
            return None
        if isinstance(valor, date):
            return valor.isoformat()
        try:
            return date.fromisoformat(str(valor)).isoformat()
        except ValueError:
            errores[campo['clave']] = f'{etiqueta}: fecha inválida.'
            return None
    if tipo == 'hora':
        if valor in (None, ''):
            return None
        if isinstance(valor, time):
            return valor.strftime('%H:%M')
        try:
            return time.fromisoformat(str(valor)).strftime('%H:%M')
        except ValueError:
            errores[campo['clave']] = f'{etiqueta}: hora inválida.'
            return None
    if tipo == 'si_no':
        if valor in (None, ''):
            return None
        if isinstance(valor, bool):
            return valor
        return str(valor).lower() in ('si', 'sí', 'true', '1', 'on')
    if tipo == 'opcion':
        if valor in (None, ''):
            return None
        validos = {v for v, _ in opciones_de(campo)}
        if str(valor) not in validos:
            errores[campo['clave']] = f'{etiqueta}: opción no válida.'
            return None
        return str(valor)
    if tipo == 'opciones':
        lista = valor if isinstance(valor, (list, tuple)) else ([valor] if valor not in (None, '') else [])
        validos = {v for v, _ in opciones_de(campo)}
        malos = [x for x in lista if str(x) not in validos]
        if malos:
            errores[campo['clave']] = f'{etiqueta}: opción no válida ({", ".join(map(str, malos))}).'
        return [str(x) for x in lista if str(x) in validos] or None
    if tipo == 'escala':
        if valor in (None, ''):
            return None
        try:
            n = int(valor)
        except (TypeError, ValueError):
            errores[campo['clave']] = f'{etiqueta}: valor no válido.'
            return None
        if not int(campo.get('min', 0)) <= n <= int(campo.get('max', 10)):
            errores[campo['clave']] = f'{etiqueta}: fuera de la escala.'
            return None
        return n
    if tipo == 'tabla':
        filas = valor if isinstance(valor, list) else []
        salida = []
        for fila in filas:
            if not isinstance(fila, dict):
                continue
            limpia = {}
            for sub in campo.get('subcampos', []):
                sub_err = {}
                v = normalizar_valor({**sub, 'tipo': sub.get('tipo', 'texto')}, fila.get(sub['clave']), sub_err)
                if sub_err:
                    errores[campo['clave']] = f'{etiqueta}: {next(iter(sub_err.values()))}'
                if v not in (None, '', []):
                    limpia[sub['clave']] = v
            if limpia:
                salida.append(limpia)
        return salida or None
    return None


def validar_datos(campos, datos, contexto=None, exigir_requeridos=True):
    """
    campos: lista de `campos_efectivos(...)`. datos: dict crudo.
    Devuelve (limpios, errores). Los campos ocultos por `visible_si` se descartan; los calculados se recalculan.
    """
    from .registro import calcular
    errores, limpios = {}, {}
    for campo in campos:
        if campo['tipo'] in TIPOS_SIN_DATO or campo['tipo'] == 'calculado':
            continue
        valor = normalizar_valor(campo, datos.get(campo['clave']), errores)
        if valor is not None:
            limpios[campo['clave']] = valor
    for campo in campos:      # visible_si se evalúa con los datos ya normalizados
        if campo['clave'] in limpios and not _visible(campo, limpios):
            limpios.pop(campo['clave'])
        elif exigir_requeridos and campo.get('requerido') and campo['tipo'] not in TIPOS_SIN_DATO | {'calculado'} \
                and campo['clave'] not in limpios and _visible(campo, limpios) and campo['clave'] not in errores:
            errores[campo['clave']] = f'{campo.get("etiqueta") or campo["clave"]}: es obligatorio.'
    for campo in campos:
        if campo['tipo'] == 'calculado':
            valor = calcular(campo['funcion'], limpios, contexto or {})
            if valor is not None:
                limpios[campo['clave']] = valor
    return limpios, errores


def requeridos_vacios(campos, datos):
    """Etiquetas de los campos obligatorios (y visibles) sin valor."""
    datos = datos or {}
    return [c.get('etiqueta') or c['clave'] for c in campos
            if c.get('requerido') and c['tipo'] not in TIPOS_SIN_DATO | {'calculado'}
            and datos.get(c['clave']) in (None, '', [], {}) and _visible(c, datos)]


def texto_valor(campo, valor):
    """Valor legible para pantalla y PDF."""
    if valor in (None, '', []):
        return ''
    tipo = campo['tipo']
    unidad = f' {campo["unidad"]}' if campo.get('unidad') else ''
    if tipo == 'si_no':
        return 'Sí' if valor else 'No'
    if tipo == 'opcion':
        return dict(opciones_de(campo)).get(str(valor), str(valor))
    if tipo == 'opciones':
        mapa = dict(opciones_de(campo))
        return ', '.join(mapa.get(str(v), str(v)) for v in valor)
    if tipo == 'fecha':
        try:
            return date.fromisoformat(valor).strftime('%d/%m/%Y')
        except (TypeError, ValueError):
            return str(valor)
    if tipo == 'hora':
        from apps.core.fechas import hora12
        try:
            return hora12(time.fromisoformat(valor))
        except (TypeError, ValueError):
            return str(valor)
    if tipo in ('numero', 'calculado') and isinstance(valor, (int, float)):
        texto = f'{valor:,.{int(campo.get("decimales", 2))}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
        if ',' in texto:
            texto = texto.rstrip('0').rstrip(',')
        return f'{texto}{unidad}'
    if tipo == 'escala':
        return f'{valor} / {campo.get("max", 10)}'
    if tipo == 'tabla':
        return '\n'.join(' · '.join(str(f.get(s['clave'], '')) for s in campo.get('subcampos', [])
                                    if f.get(s['clave']) not in (None, '')) for f in valor)
    return f'{valor}{unidad}'


def slug_clave(texto, usadas):
    """'Presión arterial (mmHg)' → 'presion_arterial_mmhg' (única entre `usadas`)."""
    import unicodedata
    base = unicodedata.normalize('NFKD', texto or '').encode('ascii', 'ignore').decode().lower()
    base = re.sub(r'[^a-z0-9]+', '_', base).strip('_')[:36] or 'campo'
    if not base[0].isalpha():
        base = f'c_{base}'[:36]
    clave, n = base, 2
    while clave in usadas:
        clave, n = f'{base}_{n}', n + 1
    return clave


def numero_seguro(valor):
    try:
        return Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        return None
