"""
Proveedores externos del dictado (ADR-045, ADR-046).

- `gemini` (predeterminado, disponible en Venezuela), en dos pasos (ADR-052):
  1. transcribir: solo el audio, sin datos del paciente ni del formulario; si no hay voz responde [SIN VOZ];
  2. ordenar: el TEXTO transcrito → campos del formulario (JSON con el esquema de la plantilla).
  Así el modelo no tiene de dónde inventar un caso cuando el audio viene en silencio. Sin guardar la conversación
  (store=false); si el audio es grande se sube con la Files API y se borra apenas termina.
- `openai_claude` (alternativa, apagada): OpenAI transcribe y Claude ordena. Solo para operar desde un país admitido.

Sin clave (o con DICTADO_MODO='prueba') funciona en modo de prueba, sin salir a internet.
"""
import base64
import contextlib
import json
import time
from dataclasses import dataclass

import requests
from django.conf import settings

URL_GEMINI = 'https://generativelanguage.googleapis.com'
URL_OPENAI = 'https://api.openai.com/v1/audio/transcriptions'
URL_CLAUDE = 'https://api.anthropic.com/v1/messages'
MAX_INLINE = 10 * 1024 * 1024           # más grande: Files API
TEXTO_PRUEBA = ('Modo de prueba: no hay clave del proveedor de IA configurada, así que no se procesó el audio. '
                'Configura GEMINI_API_KEY para usar el dictado real.')

class ErrorProveedor(Exception):
    pass


@dataclass
class Resultado:
    transcripcion: str
    entrada: dict
    tokens_entrada: int = 0
    tokens_salida: int = 0
    modelo_transcripcion: str = ''
    modelo_ia: str = ''
    segundos_audio: int | None = None


def proveedor():
    return getattr(settings, 'DICTADO_PROVEEDOR', 'gemini') or 'gemini'


def en_prueba():
    if getattr(settings, 'DICTADO_MODO', '') == 'prueba':
        return True
    if proveedor() == 'openai_claude':
        return not (getattr(settings, 'OPENAI_API_KEY', '') and getattr(settings, 'ANTHROPIC_API_KEY', ''))
    return not getattr(settings, 'GEMINI_API_KEY', '')


def procesar_audio(audio, tipo, vocabulario, sistema, herramienta):
    """Audio → Resultado (transcripción + campos ordenados)."""
    if en_prueba():
        return Resultado(TEXTO_PRUEBA, {'secciones': {}, 'no_ubicado': TEXTO_PRUEBA}, modelo_transcripcion='prueba',
                         modelo_ia='prueba')
    if proveedor() == 'openai_claude':
        texto, modelo_t = transcribir(audio, 'dictado', tipo, vocabulario)
        entrada, t_in, t_out, modelo_ia = ordenar(texto, sistema, herramienta)
        return Resultado(texto, entrada, t_in, t_out, modelo_t, modelo_ia)
    return gemini(audio, tipo, vocabulario, sistema, herramienta)


# ── Gemini ────────────────────────────────────────────────────────────────────────────────────────────────────

def _cabeceras():
    return {'x-goog-api-key': settings.GEMINI_API_KEY}


def _subir_archivo(audio, tipo):
    """Files API (subida reanudable en dos pasos). Devuelve (uri, nombre)."""
    inicio = requests.post(f'{URL_GEMINI}/upload/v1beta/files', headers={
        **_cabeceras(), 'X-Goog-Upload-Protocol': 'resumable', 'X-Goog-Upload-Command': 'start',
        'X-Goog-Upload-Header-Content-Length': str(len(audio)), 'X-Goog-Upload-Header-Content-Type': tipo,
        'Content-Type': 'application/json'}, data=json.dumps({'file': {'display_name': 'dictado'}}), timeout=60)
    url = inicio.headers.get('x-goog-upload-url')
    if inicio.status_code != 200 or not url:
        raise ErrorProveedor(f'No se pudo subir el audio a Gemini ({inicio.status_code}).')
    subida = requests.post(url, headers={'X-Goog-Upload-Offset': '0', 'X-Goog-Upload-Command': 'upload, finalize',
                                         'Content-Length': str(len(audio))}, data=audio, timeout=300)
    if subida.status_code != 200:
        raise ErrorProveedor(f'No se pudo subir el audio a Gemini ({subida.status_code}).')
    archivo = subida.json().get('file') or {}
    nombre = archivo.get('name', '')
    for _ in range(30):                                   # el audio suele quedar listo en segundos
        if archivo.get('state', 'ACTIVE') == 'ACTIVE':
            break
        time.sleep(2)
        archivo = requests.get(f'{URL_GEMINI}/v1beta/{nombre}', headers=_cabeceras(), timeout=30).json()
    return archivo.get('uri'), nombre


def _borrar_archivo(nombre):
    if nombre:
        with contextlib.suppress(requests.RequestException):     # si falla, Google lo borra solo a las 48 h
            requests.delete(f'{URL_GEMINI}/v1beta/{nombre}', headers=_cabeceras(), timeout=30)


def _sin_additional(esquema):
    """Para el modo `response_schema` (subconjunto OpenAPI): quita lo que no admite."""
    if isinstance(esquema, dict):
        return {k: _sin_additional(v) for k, v in esquema.items() if k != 'additionalProperties'}
    if isinstance(esquema, list):
        return [_sin_additional(v) for v in esquema]
    return esquema


SIN_VOZ = '[SIN VOZ]'
TRANSCRIPTOR = (
    'Eres un transcriptor médico. Escribe en español, palabra por palabra, SOLO lo que realmente se oye en el audio, '
    'con puntuación. Escribe los números con cifras (10.4, 99/60). No resumas, no corrijas el contenido, no agregues '
    f'nada. Si el audio está en silencio, es solo ruido o no se entiende ninguna frase, responde exactamente {SIN_VOZ}.')


def _parte_audio(audio, tipo):
    """(parte para la petición, nombre del archivo subido o '')."""
    if len(audio) > MAX_INLINE:
        uri, nombre = _subir_archivo(audio, tipo)
        return {'file_data': {'mime_type': tipo, 'file_uri': uri}}, nombre
    return {'inline_data': {'mime_type': tipo, 'data': base64.b64encode(audio).decode()}}, ''


def _texto(datos):
    candidatos = datos.get('candidates') or []
    if not candidatos:
        motivo = (datos.get('promptFeedback') or {}).get('blockReason', 'sin respuesta')
        raise ErrorProveedor(f'Gemini no devolvió resultado ({motivo}).')
    partes = (candidatos[0].get('content') or {}).get('parts') or []
    return ''.join(p.get('text', '') for p in partes if not p.get('thought'))


def _uso(datos):
    uso = datos.get('usageMetadata') or {}
    audio_tokens = sum(d.get('tokenCount', 0) for d in uso.get('promptTokensDetails') or []
                       if d.get('modality') == 'AUDIO')
    return (uso.get('promptTokenCount', 0), uso.get('candidatesTokenCount', 0) + uso.get('thoughtsTokenCount', 0),
            audio_tokens)


def _url(modelo):
    return f'{URL_GEMINI}/v1beta/models/{modelo}:generateContent'


def transcribir_gemini(audio, tipo, vocabulario):
    """Paso 1: solo el audio, sin datos del paciente ni del formulario (nada de dónde inventar)."""
    modelo = settings.DICTADO_MODELO_GEMINI
    parte, nombre_archivo = _parte_audio(audio, tipo)
    try:
        cuerpo = {
            'system_instruction': {'parts': [{'text': f'{TRANSCRIPTOR}\nTérminos que pueden aparecer: {vocabulario}'}]},
            'contents': [{'role': 'user', 'parts': [parte, {'text': 'Transcribe este audio.'}]}],
            'generation_config': {'temperature': 0, 'thinking_config': {'thinking_level': 'minimal'}},
            'store': False,
        }
        r = _llamar_gemini(_url(modelo), cuerpo, None)
        if r.status_code != 200:
            raise ErrorProveedor(f'Gemini no respondió bien ({r.status_code}): {r.text[:150]}')
        datos = r.json()
        texto = _texto(datos).strip()
        if not texto or SIN_VOZ in texto:
            raise ErrorProveedor('No se entendió voz en la grabación. Revisa el micrófono o sube una nota de voz '
                                 'del teléfono.')
        return texto, _uso(datos), modelo
    finally:
        _borrar_archivo(nombre_archivo)


REGLAS_LISTA = """
Cómo responder:
- Recorre el texto de principio a fin y crea un elemento en `datos` por CADA dato clínico mencionado.
- `campo` es el identificador exacto del catálogo; `valor` es lo dictado para ese campo.
- Opciones: el código (lo que va antes del «=»). Sí/No: «si» o «no» («niega» = «no»). Números: solo la cifra en la
  unidad del campo. Fechas: AAAA-MM-DD.
- Un dato que no tenga campo en el catálogo va completo en `no_ubicado`."""


def catalogo(herramienta):
    """El esquema anidado de la plantilla → (líneas «sección.campo — descripción», identificadores, tipos)."""
    secciones = herramienta['input_schema']['properties']['secciones']['properties']
    lineas, ids, tipos = [], [], {}
    for codigo, seccion in secciones.items():
        lineas.append(f"\n## {seccion.get('description', codigo)}")
        for clave, prop in seccion['properties'].items():
            ident = f'{codigo}.{clave}'
            tipo = prop.get('type')
            if tipo == 'array' and (prop.get('items') or {}).get('type') == 'object':
                tipo = 'tabla'
            nombre = {'number': 'número', 'boolean': 'si/no', 'tabla': 'lista: un elemento por fila',
                      'array': 'varias opciones separadas por coma'}.get(tipo, 'texto')
            if prop.get('enum'):
                nombre = 'opción'
            lineas.append(f"- {ident} ({nombre}): {prop.get('description', '')}")
            ids.append(ident)
            tipos[ident] = (tipo, prop)
    return '\n'.join(lineas), ids, tipos


def a_secciones(datos, tipos):
    """La lista [{campo, valor}] → {'secciones': {codigo: {clave: valor}}} (lo que valida servicios.validar)."""
    secciones = {}
    for d in datos or []:
        if not isinstance(d, dict) or d.get('campo') not in tipos:
            continue
        valor = d.get('valor')
        if valor in (None, ''):
            continue
        codigo, clave = d['campo'].rsplit('.', 1)
        tipo, prop = tipos[d['campo']]
        actual = secciones.setdefault(codigo, {})
        if tipo == 'tabla':
            subcampos = list((prop.get('items') or {}).get('properties') or {})
            destino = 'descripcion' if 'descripcion' in subcampos else (subcampos[0] if subcampos else 'texto')
            actual.setdefault(clave, []).append({destino: str(valor)})
        elif tipo == 'array':
            actual[clave] = [x.strip() for x in str(valor).split(',') if x.strip()]
        elif tipo == 'string' and not prop.get('enum') and clave in actual:
            actual[clave] = f'{actual[clave]} {valor}'.strip()        # dos frases para el mismo texto: se juntan
        else:
            actual[clave] = valor
    return secciones


def ordenar_gemini(texto, sistema, herramienta):
    """
    Paso 2: el texto (no el audio) → campos. En vez del formulario anidado (≈150 campos opcionales, con el que el
    modelo llenaba el primero y cortaba), se le da un catálogo y devuelve una LISTA plana de {campo, valor}.
    """
    modelo = settings.DICTADO_MODELO_GEMINI
    lineas, ids, tipos = catalogo(herramienta)
    esquema = {'type': 'object', 'required': ['datos'], 'properties': {
        'datos': {'type': 'array', 'items': {'type': 'object', 'required': ['campo', 'valor'], 'properties': {
            'campo': {'type': 'string', 'enum': ids}, 'valor': {'type': 'string'}}}},
        'no_ubicado': {'type': 'string'}}}
    cuerpo = {
        'system_instruction': {'parts': [{'text': f'{sistema}\n{REGLAS_LISTA}\n\nCatálogo de campos:{lineas}'}]},
        'contents': [{'role': 'user', 'parts': [{'text': f'Texto dictado:\n"""\n{texto}\n"""'}]}],
        'generation_config': {'response_mime_type': 'application/json', 'response_json_schema': esquema,
                              'temperature': 0.1,
                              # Ubicar datos dictados no necesita razonar mucho: es lo que más alarga la espera.
                              'thinking_config': {'thinking_level': settings.DICTADO_RAZONAMIENTO}},
        'store': False,
    }
    r = _llamar_gemini(_url(modelo), cuerpo, esquema)
    if r.status_code != 200:
        raise ErrorProveedor(f'Gemini no respondió bien ({r.status_code}): {r.text[:150]}')
    datos = r.json()
    try:
        salida = json.loads(_texto(datos))
    except ValueError as e:
        raise ErrorProveedor('Gemini devolvió un formato inesperado.') from e
    if not isinstance(salida, dict):
        salida = {}
    entrada = {'secciones': a_secciones(salida.get('datos'), tipos), 'no_ubicado': salida.get('no_ubicado') or ''}
    return entrada, _uso(datos), modelo


def gemini(audio, tipo, vocabulario, sistema, herramienta):
    texto, (t_in1, t_out1, audio_tokens), modelo = transcribir_gemini(audio, tipo, vocabulario)
    entrada, (t_in2, t_out2, _), _ = ordenar_gemini(texto, sistema, herramienta)
    return Resultado(
        transcripcion=texto, entrada=entrada if isinstance(entrada, dict) else {},
        tokens_entrada=t_in1 + t_in2, tokens_salida=t_out1 + t_out2,
        modelo_transcripcion=modelo, modelo_ia=modelo,
        segundos_audio=round(audio_tokens / 32) if audio_tokens else None)     # 32 tokens por segundo de audio


TIMEOUT_GEMINI = 90          # segundos por intento
REINTENTABLES = (429, 500, 502, 503, 504)


def _llamar_gemini(url, cuerpo, esquema, timeout=None, intentos=2):
    """
    POST con dos intentos (si Google no responde a tiempo o está saturado) y dos ajustes automáticos si la versión
    del modelo no admite algo: `response_json_schema` → esquema OpenAPI; `thinking_config` → sin él.
    """
    cabeceras = {**_cabeceras(), 'Content-Type': 'application/json'}
    ultimo = None
    for intento in range(intentos):
        try:
            r = requests.post(url, headers=cabeceras, data=json.dumps(cuerpo), timeout=timeout or TIMEOUT_GEMINI)
        except (requests.Timeout, requests.ConnectionError) as e:
            ultimo = e
            time.sleep(2)
            continue
        except requests.RequestException as e:
            raise ErrorProveedor(f'No se pudo conectar con Gemini ({e.__class__.__name__}).') from e
        if r.status_code == 400:
            texto = r.text.lower()
            config = cuerpo['generation_config']
            if 'thinking' in texto and 'thinking_config' in config:
                config.pop('thinking_config')
                return _llamar_gemini(url, cuerpo, esquema, timeout, intentos)
            if 'schema' in texto and 'response_json_schema' in config:
                config.pop('response_json_schema')
                config['response_schema'] = _sin_additional(esquema)
                return _llamar_gemini(url, cuerpo, esquema, timeout, intentos)
        if r.status_code in REINTENTABLES and intento < intentos - 1:
            time.sleep(3)
            continue
        return r
    raise ErrorProveedor(f'Gemini no respondió a tiempo ({ultimo.__class__.__name__}). Toca «Enviar ahora» para '
                         'reintentar; la grabación quedó guardada.') from ultimo


# ── OpenAI + Claude (alternativa; no disponible desde Venezuela) ───────────────────────────────────────────────

def transcribir(audio, nombre, tipo, vocabulario=''):
    modelo = settings.DICTADO_MODELO_TRANSCRIPCION
    try:
        r = requests.post(URL_OPENAI, headers={'Authorization': f'Bearer {settings.OPENAI_API_KEY}'},
                          files={'file': (f'{nombre}.mp3' if tipo == 'audio/mp3' else nombre, audio, tipo)},
                          data={'model': modelo, 'language': 'es', 'response_format': 'json',
                                'prompt': vocabulario[:900]}, timeout=150)
    except requests.RequestException as e:
        raise ErrorProveedor(f'No se pudo conectar con el servicio de transcripción ({e.__class__.__name__}).') from e
    if r.status_code != 200:
        raise ErrorProveedor(f'La transcripción falló ({r.status_code}): {r.text[:150]}')
    return (r.json().get('text') or '').strip(), modelo


def ordenar(transcripcion, sistema, herramienta):
    modelo = settings.DICTADO_MODELO_IA
    cuerpo = {'model': modelo, 'max_tokens': 8000, 'system': sistema, 'tools': [herramienta],
              'tool_choice': {'type': 'tool', 'name': herramienta['name']},
              'messages': [{'role': 'user', 'content': f'Dictado de la consulta:\n\n{transcripcion}'}]}
    try:
        r = requests.post(URL_CLAUDE, headers={'x-api-key': settings.ANTHROPIC_API_KEY,
                                               'anthropic-version': '2023-06-01', 'content-type': 'application/json'},
                          data=json.dumps(cuerpo), timeout=150)
    except requests.RequestException as e:
        raise ErrorProveedor(f'No se pudo conectar con la IA ({e.__class__.__name__}).') from e
    if r.status_code != 200:
        raise ErrorProveedor(f'La IA no respondió bien ({r.status_code}): {r.text[:150]}')
    datos = r.json()
    entrada = next((b.get('input') for b in datos.get('content', []) if b.get('type') == 'tool_use'), None)
    if entrada is None:
        raise ErrorProveedor('La IA no devolvió los campos.')
    uso = datos.get('usage') or {}
    return entrada, uso.get('input_tokens', 0), uso.get('output_tokens', 0), modelo
