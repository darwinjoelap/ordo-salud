"""
Proveedores externos del dictado (ADR-045, ADR-046).

- `gemini` (predeterminado, disponible en Venezuela): una sola llamada a Gemini Flash con el audio; devuelve la
  transcripción y los campos ordenados (JSON con el esquema de la plantilla). Sin guardar la conversación (store=false);
  si el audio es grande se sube con la Files API y se borra apenas termina.
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
INSTRUCCION = ('Escucha el dictado de la consulta. Devuelve en `transcripcion` lo que se dijo, palabra por palabra '
               '(con puntuación), y en `secciones` cada dato en su campo. Lo que no encaje va en `no_ubicado`.')


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


def esquema_gemini(herramienta):
    esquema = json.loads(json.dumps(herramienta['input_schema']))
    esquema['properties'] = {'transcripcion': {'type': 'string', 'description': 'Lo dictado, palabra por palabra.'},
                             **esquema['properties']}
    esquema['required'] = ['transcripcion', 'secciones']
    return esquema


def gemini(audio, tipo, vocabulario, sistema, herramienta):
    modelo = settings.DICTADO_MODELO_GEMINI
    nombre_archivo = ''
    try:
        if len(audio) > MAX_INLINE:
            uri, nombre_archivo = _subir_archivo(audio, tipo)
            parte_audio = {'file_data': {'mime_type': tipo, 'file_uri': uri}}
        else:
            parte_audio = {'inline_data': {'mime_type': tipo, 'data': base64.b64encode(audio).decode()}}
        esquema = esquema_gemini(herramienta)
        cuerpo = {
            'system_instruction': {'parts': [{'text': f'{sistema}\nVocabulario frecuente: {vocabulario}'}]},
            'contents': [{'role': 'user', 'parts': [parte_audio, {'text': INSTRUCCION}]}],
            'generation_config': {'response_mime_type': 'application/json', 'response_json_schema': esquema,
                                  'temperature': 0.1},
            'store': False,
        }
        url = f'{URL_GEMINI}/v1beta/models/{modelo}:generateContent'
        try:
            r = requests.post(url, headers={**_cabeceras(), 'Content-Type': 'application/json'},
                              data=json.dumps(cuerpo), timeout=170)
            if r.status_code == 400 and 'schema' in r.text.lower():
                # Versión de la API sin `response_json_schema`: se usa el esquema OpenAPI (sin additionalProperties).
                cuerpo['generation_config'].pop('response_json_schema')
                cuerpo['generation_config']['response_schema'] = _sin_additional(esquema)
                r = requests.post(url, headers={**_cabeceras(), 'Content-Type': 'application/json'},
                                  data=json.dumps(cuerpo), timeout=170)
        except requests.RequestException as e:
            raise ErrorProveedor(f'No se pudo conectar con Gemini ({e.__class__.__name__}).') from e
        if r.status_code != 200:
            raise ErrorProveedor(f'Gemini no respondió bien ({r.status_code}): {r.text[:150]}')
        return leer_respuesta(r.json(), modelo)
    finally:
        _borrar_archivo(nombre_archivo)


def leer_respuesta(datos, modelo):
    candidatos = datos.get('candidates') or []
    if not candidatos:
        motivo = (datos.get('promptFeedback') or {}).get('blockReason', 'sin respuesta')
        raise ErrorProveedor(f'Gemini no devolvió resultado ({motivo}).')
    partes = (candidatos[0].get('content') or {}).get('parts') or []
    texto = ''.join(p.get('text', '') for p in partes if not p.get('thought'))
    try:
        entrada = json.loads(texto)
    except ValueError as e:
        raise ErrorProveedor('Gemini devolvió un formato inesperado.') from e
    uso = datos.get('usageMetadata') or {}
    audio_tokens = sum(d.get('tokenCount', 0) for d in uso.get('promptTokensDetails') or []
                       if d.get('modality') == 'AUDIO')
    return Resultado(
        transcripcion=(entrada.pop('transcripcion', '') or '').strip(), entrada=entrada,
        tokens_entrada=uso.get('promptTokenCount', 0),
        tokens_salida=uso.get('candidatesTokenCount', 0) + uso.get('thoughtsTokenCount', 0),
        modelo_transcripcion=modelo, modelo_ia=modelo,
        segundos_audio=round(audio_tokens / 32) if audio_tokens else None)     # 32 tokens por segundo de audio


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
