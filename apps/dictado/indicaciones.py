"""
Sugerir récipe e indicaciones con IA (ADR-060).

- La IA ELIGE medicamentos (del glosario si están: por su id) y REDACTA indicaciones; NUNCA hace la cuenta de la dosis.
- Si propone un medicamento que no está en el glosario, devuelve su FICHA de dosificación (mg/kg por dosis, concentración,
  frecuencia…) y la dosis la calcula `clinica.dosis.calcular` con el peso. La fila llega marcada «verificar» con la
  ficha a la vista (por dosis y por día) y se puede guardar en el glosario de la doctora.
- Contexto: lo escrito en la consulta (cualquier especialidad), edad, sexo, alergias, el glosario y algunas indicaciones
  anteriores de la misma profesional (su estilo). Sin nombre ni documento del paciente.
- Nada se guarda en la historia: el médico revisa y agrega lo que quiera.
"""
import json
import logging
import re
import unicodedata
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from apps.clinica.dosis import calcular
from apps.clinica.models import Medicamento

from . import proveedores
from .models import SugerenciaIA

UNIDADES_KG = {u for u, _ in Medicamento.UNIDADES_KG}
UNIDADES_RESULTADO = {u for u, _ in Medicamento.UNIDADES_RESULTADO}
MAX_CONTEXTO = 6000          # caracteres de lo escrito en la consulta
MAX_EJEMPLOS = 4

SISTEMA = """Eres el asistente de prescripción de {especialidad} en un consultorio de Venezuela. Propones el récipe y las
indicaciones de ESTA consulta para que la profesional los revise; ella decide.

Reglas:
- Basate en el diagnóstico y lo escrito en la consulta. Si no hay diagnóstico ni motivo claros, no propongas
  medicamentos y explícalo en `alertas`.
- Prefiere los medicamentos del glosario de la profesional: si usas uno, pon su `glosario_id` y nada más de dosis.
- Si un medicamento no está en el glosario, `glosario_id` = 0 y llena su ficha: presentación comercial habitual en
  Venezuela, `modo` PESO (pediatría o dosis por kg) o FIJA (adultos). En PESO: `mg_kg_min`/`mg_kg_max` son POR DOSIS
  (no por día), con `unidad_kg`, `concentracion` (cantidad de principio activo en `volumen_ml` mL, o por tableta) y
  `unidad_resultado`. En FIJA: `dosis_fija` (p. ej. «1 tableta»). Siempre `frecuencia_horas` y `duracion_dias` si
  aplica, y `dosis_max` por dosis si existe.
- NO calcules la dosis final para el peso: la calcula el sistema.
- Respeta las alergias: no propongas nada de la misma familia y avísalo en `alertas`.
- `indicaciones`: medidas generales y signos de alarma, breves, en el estilo de los ejemplos de la profesional.
- Usa solo medicamentos de uso aceptado para la edad del paciente. Ante la duda, no lo propongas.
- No incluyas nombres ni datos de identificación.
Paciente: {paciente}."""

ESQUEMA = {'type': 'object', 'required': ['medicamentos', 'indicaciones'], 'properties': {
    'medicamentos': {'type': 'array', 'items': {'type': 'object', 'required': ['glosario_id', 'nombre'], 'properties': {
        'glosario_id': {'type': 'integer'},
        'nombre': {'type': 'string'},
        'presentacion': {'type': 'string'},
        'modo': {'type': 'string', 'enum': ['PESO', 'FIJA']},
        'mg_kg_min': {'type': 'number'}, 'mg_kg_max': {'type': 'number'},
        'unidad_kg': {'type': 'string', 'enum': sorted(UNIDADES_KG)},
        'concentracion': {'type': 'number'}, 'volumen_ml': {'type': 'number'},
        'unidad_resultado': {'type': 'string', 'enum': sorted(UNIDADES_RESULTADO)},
        'dosis_max': {'type': 'number'}, 'dosis_fija': {'type': 'string'},
        'frecuencia_horas': {'type': 'integer'}, 'duracion_dias': {'type': 'integer'},
        'via': {'type': 'string'}, 'nota': {'type': 'string'}}}},
    'indicaciones': {'type': 'string'},
    'alertas': {'type': 'array', 'items': {'type': 'string'}}}}


log = logging.getLogger('apps.dictado')


class ErrorSugerencia(Exception):
    pass


def activo(tenant):
    return bool(getattr(tenant.configuracion, 'sugerencias_ia', False))


def costo(tokens_entrada, tokens_salida):
    return round(tokens_entrada / 1e6 * settings.IA_PRECIO_ENTRADA + tokens_salida / 1e6 * settings.IA_PRECIO_SALIDA, 4)


def uso_mes(tenant):
    desde = timezone.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    qs = SugerenciaIA.todos.filter(tenant=tenant, creado_en__gte=desde)
    t = qs.aggregate(e=Sum('tokens_entrada'), s=Sum('tokens_salida'))
    return {'n': qs.count(), 'costo': f"{costo(t['e'] or 0, t['s'] or 0):.2f}"}


# ── Contexto ──────────────────────────────────────────────────────────────────────────────────────────────────

def _norm(t):
    return unicodedata.normalize('NFKD', t or '').encode('ascii', 'ignore').decode().lower()


def _palabras(t):
    return set(re.findall(r'[a-z]{4,}', _norm(t)))


def contexto_paciente(paciente, peso):
    partes = [paciente.get_sexo_display().lower() if paciente.sexo else 'sexo no indicado']
    if paciente.edad_texto:
        partes.append(paciente.edad_texto)
    if peso:
        partes.append(f'{peso} kg')
    ant = getattr(paciente, 'antecedentes', None)
    alergias = (getattr(ant, 'alergias', '') or '').strip()
    partes.append(f'alergias: {alergias}' if alergias else 'sin alergias registradas')
    return ', '.join(partes)


def glosario_texto(meds):
    lineas = []
    for m in meds:
        ficha = m.presentacion or ''
        lineas.append(f'- id {m.pk}: {m.nombre}{" · " + ficha if ficha else ""}'
                      f'{" — " + " ".join(m.indicaciones.split())[:120] if m.indicaciones else ""}')
    return '\n'.join(lineas) or '(vacío)'


def ejemplos(perfil, diagnostico):
    """Récipes e indicaciones anteriores de la misma profesional, primero los de diagnóstico parecido (su estilo)."""
    from apps.clinica.models import Consulta, ItemPrescripcion
    candidatas = list(Consulta.objects.filter(profesional=perfil, estado=Consulta.Estado.CERRADA)
                      .exclude(diagnostico='').order_by('-fecha_hora').values('pk', 'diagnostico')[:60])
    objetivo = _palabras(diagnostico)
    candidatas.sort(key=lambda c: -len(objetivo & _palabras(c['diagnostico'])))
    salida = []
    for c in candidatas:
        items = list(ItemPrescripcion.objects.filter(consulta_id=c['pk']).order_by('orden')
                     .values_list('medicamento', 'dosis', 'frecuencia', 'duracion'))
        if not items:
            continue
        recipe = '; '.join(' '.join(x for x in fila if x) for fila in items)
        salida.append(f'- Diagnóstico: {c["diagnostico"][:120]} → {recipe[:300]}')
        if len(salida) >= MAX_EJEMPLOS:
            break
    return '\n'.join(salida)


# ── Resultado ─────────────────────────────────────────────────────────────────────────────────────────────────

def _dec(v):
    try:
        d = Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return d if d > 0 else None


def _ficha_medicamento(d):
    """Medicamento SIN guardar con la ficha que propuso la IA (o None si no alcanza para nada)."""
    modo = d.get('modo') if d.get('modo') in ('PESO', 'FIJA') else 'FIJA'
    m = Medicamento(nombre=(d.get('nombre') or '').strip()[:150], presentacion=(d.get('presentacion') or '')[:120],
                    modo=modo, rangos_edad=[], indicaciones='')
    if not m.nombre:
        return None
    m.unidad_kg = d.get('unidad_kg') if d.get('unidad_kg') in UNIDADES_KG else 'mg'
    m.dosis_kg_min, m.dosis_kg_max = _dec(d.get('mg_kg_min')), _dec(d.get('mg_kg_max'))
    if m.dosis_kg_min and m.dosis_kg_max and m.dosis_kg_max < m.dosis_kg_min:
        m.dosis_kg_min, m.dosis_kg_max = m.dosis_kg_max, m.dosis_kg_min
    m.concentracion_mg, m.volumen_ml = _dec(d.get('concentracion')), _dec(d.get('volumen_ml'))
    m.unidad_resultado = d.get('unidad_resultado') if d.get('unidad_resultado') in UNIDADES_RESULTADO else ''
    m.dosis_max = _dec(d.get('dosis_max'))
    m.dosis_fija = (d.get('dosis_fija') or '')[:60]
    fh, dd = d.get('frecuencia_horas'), d.get('duracion_dias')
    m.frecuencia_horas = fh if isinstance(fh, int) and 1 <= fh <= 168 else None
    m.duracion_dias = dd if isinstance(dd, int) and 1 <= dd <= 365 else None
    return m


def _f(n):
    return f'{float(n):g}'.replace('.', ',')


def ficha_texto(m):
    """«15–25 mg/kg/dosis (45–75 mg/kg/día) · 250 mg/5 mL · cada 8 h · 7 días · máx. 500 mg/dosis»."""
    partes = []
    if m.modo == 'PESO' and m.dosis_kg_min:
        rango = _f(m.dosis_kg_min) + (f'–{_f(m.dosis_kg_max)}' if m.dosis_kg_max else '')
        txt = f'{rango} {m.unidad_kg}/kg/dosis'
        if m.frecuencia_horas:
            veces = 24 / m.frecuencia_horas
            dia = _f(round(float(m.dosis_kg_min) * veces, 2)) + (
                f'–{_f(round(float(m.dosis_kg_max) * veces, 2))}' if m.dosis_kg_max else '')
            txt += f' ({dia} {m.unidad_kg}/kg/día)'
        partes.append(txt)
        if m.concentracion_mg:
            por = (f'/{_f(m.volumen_ml)} mL' if m.unidad_resultado in ('mL', 'gotas')
                   else f' por {m.unidad_resultado or "unidad"}')
            partes.append(f'{_f(m.concentracion_mg)} {m.unidad_kg}{por}')
    elif m.dosis_fija:
        partes.append(m.dosis_fija)
    if m.frecuencia_horas:
        partes.append(f'cada {m.frecuencia_horas} h')
    if m.duracion_dias:
        partes.append(f'{m.duracion_dias} días')
    if m.dosis_max:
        partes.append(f'máx. {_f(m.dosis_max)} {m.unidad_kg}/dosis')
    return ' · '.join(partes)


def _choca_con_alergias(nombre, alergias):
    palabras = {w for w in _palabras(alergias) if w not in {'alergia', 'alergico', 'alergica', 'niega', 'conocidas'}}
    return bool(palabras & _palabras(nombre))


def armar_filas(salida, glosario, peso, edad_meses, alergias):
    filas, por_id = [], {m.pk: m for m in glosario}
    for d in salida.get('medicamentos') or []:
        if not isinstance(d, dict):
            continue
        med = por_id.get(d.get('glosario_id') or 0)
        origen = 'glosario' if med else 'ia'
        if med is None:
            med = _ficha_medicamento(d)
            if med is None:
                continue
        r = calcular(med, peso_kg=peso, edad_meses=edad_meses)
        alertas = list(r['alertas'])
        if origen == 'ia':
            alertas.insert(0, {'tipo': 'warning', 'msg': 'Dosis sugerida por IA · verificar la ficha antes de indicar.'})
            if med.modo == 'PESO' and not med.dosis_kg_min:
                alertas.append({'tipo': 'warning', 'msg': 'La IA no dio dosis por kg: complétala a mano.'})
        if alergias and _choca_con_alergias(med.nombre, alergias):
            alertas.insert(0, {'tipo': 'danger',
                               'msg': f'Revisar: el paciente tiene alergias registradas ({alergias[:80]}).'})
        texto = r['texto'] if (r['calculada'] or r.get('con_indicaciones')) else ''
        if origen == 'ia' and d.get('via'):
            texto = f'{texto} vía {d["via"]}'.strip()
        filas.append({
            'origen': origen, 'medicamento': r['medicamento'], 'dosis': r['dosis'], 'dosis_mg': r['dosis_mg'],
            'frecuencia': r['frecuencia'], 'duracion': r['duracion'], 'texto': texto,
            'nota': (d.get('nota') or '')[:200], 'alertas': alertas,
            'ficha': ficha_texto(med) if origen == 'ia' else '',
            'para_glosario': _para_glosario(med) if origen == 'ia' else None})
    return filas


def _para_glosario(m):
    return {'nombre': m.nombre, 'presentacion': m.presentacion, 'modo': m.modo, 'unidad_kg': m.unidad_kg,
            'dosis_kg_min': str(m.dosis_kg_min or ''), 'dosis_kg_max': str(m.dosis_kg_max or ''),
            'concentracion_mg': str(m.concentracion_mg or ''), 'volumen_ml': str(m.volumen_ml or ''),
            'unidad_resultado': m.unidad_resultado or '', 'dosis_max': str(m.dosis_max or ''),
            'dosis_fija': m.dosis_fija or '', 'frecuencia_horas': m.frecuencia_horas or '',
            'duracion_dias': m.duracion_dias or ''}


# ── Llamada ───────────────────────────────────────────────────────────────────────────────────────────────────

def sugerir(*, paciente, perfil, campos, peso=None, glosario=()):
    """
    campos: {etiqueta: valor} con lo escrito en la consulta (lo arma la página). Devuelve
    {'filas': [...], 'indicaciones': str, 'alertas': [str], 'id': SugerenciaIA.pk}. Lanza ErrorSugerencia.
    """
    from apps.core.fechas import edad_meses as calc_edad_meses
    glosario = list(glosario)
    texto_consulta = '\n'.join(f'{k}: {v}' for k, v in campos.items() if str(v).strip())[:MAX_CONTEXTO]
    if not texto_consulta.strip():
        raise ErrorSugerencia('Escribe al menos el motivo o el diagnóstico antes de pedir una sugerencia.')
    diagnostico = ' '.join(str(v) for k, v in campos.items() if 'iagn' in k)
    edad_m = calc_edad_meses(paciente.fecha_nacimiento) if paciente.fecha_nacimiento else None
    ant = getattr(paciente, 'antecedentes', None)
    alergias = (getattr(ant, 'alergias', '') or '').strip()
    sistema = SISTEMA.format(especialidad=perfil.especialidad.nombre if perfil.especialidad_id else 'medicina',
                             paciente=contexto_paciente(paciente, peso))
    estilo = ejemplos(perfil, diagnostico)
    usuario = (f'Consulta actual:\n"""\n{texto_consulta}\n"""\n\nGlosario de la profesional:\n{glosario_texto(glosario)}'
               + (f'\n\nAsí indicó antes en casos parecidos (su estilo):\n{estilo}' if estilo else ''))
    registro = SugerenciaIA(paciente=paciente, profesional=perfil)
    try:
        salida, (t_in, t_out), modelo = _llamar(sistema, usuario)
    except proveedores.ErrorProveedor as e:
        registro.ok, registro.error = False, str(e)[:300]
        registro.save()
        raise ErrorSugerencia(str(e)) from e
    filas = armar_filas(salida, glosario, peso, edad_m, alergias)
    resultado = {'filas': filas, 'indicaciones': (salida.get('indicaciones') or '').strip()[:2000],
                 'alertas': [str(a)[:300] for a in (salida.get('alertas') or [])][:6]}
    registro.resultado, registro.modelo_ia = resultado, modelo
    registro.tokens_entrada, registro.tokens_salida = t_in, t_out
    registro.save()
    return {**resultado, 'id': registro.pk}


def _llamar(sistema, usuario):
    if proveedores.en_prueba():
        return ({'medicamentos': [], 'indicaciones': 'Modo de prueba: configura GEMINI_API_KEY para sugerencias reales.',
                 'alertas': []}, (0, 0), 'prueba')
    modelo = settings.DICTADO_MODELO_GEMINI
    cuerpo = {
        'system_instruction': {'parts': [{'text': sistema}]},
        'contents': [{'role': 'user', 'parts': [{'text': usuario}]}],
        'generation_config': {'response_mime_type': 'application/json', 'response_json_schema': ESQUEMA,
                              'temperature': 0.2,
                              'thinking_config': {'thinking_level': settings.SUGERENCIAS_RAZONAMIENTO}},
        'store': False,
    }
    try:
        r = proveedores._llamar_gemini(proveedores._url(modelo), cuerpo, ESQUEMA)
    except proveedores.ErrorProveedor as e:
        log.warning('Sugerencia IA: Gemini no respondió: %s', e)
        raise proveedores.ErrorProveedor('Gemini no respondió a tiempo. Intenta de nuevo en un momento.') from e
    if r.status_code != 200:
        log.warning('Sugerencia IA: Gemini respondió %s: %s', r.status_code, r.text[:800])
        raise proveedores.ErrorProveedor(f'Gemini no respondió bien ({r.status_code}): {r.text[:160]}')
    datos = r.json()
    try:
        salida = json.loads(proveedores._texto(datos))
    except ValueError as e:
        log.warning('Sugerencia IA: respuesta no es JSON: %s', str(datos)[:800])
        raise proveedores.ErrorProveedor('Gemini devolvió un formato inesperado.') from e
    t_in, t_out, _ = proveedores._uso(datos)
    return (salida if isinstance(salida, dict) else {}), (t_in, t_out), modelo
