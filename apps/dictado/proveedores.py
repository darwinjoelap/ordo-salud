"""
Proveedores externos del dictado (ADR-045):
- Transcripción: OpenAI `gpt-4o-transcribe` (audio → texto, español, con vocabulario de la especialidad).
- Ordenar en la historia: Claude (`claude-sonnet-5-5`) con una herramienta cuyo esquema son los campos de la plantilla.

Sin claves (o con DICTADO_MODO='prueba') funciona en modo de prueba, sin salir a internet: la transcripción es un
texto fijo y nada se ubica (todo queda en «no ubicado»). Los tests reemplazan estas funciones.
"""
import json

import requests
from django.conf import settings

URL_OPENAI = 'https://api.openai.com/v1/audio/transcriptions'
URL_CLAUDE = 'https://api.anthropic.com/v1/messages'
TEXTO_PRUEBA = ('Modo de prueba: no hay claves de OpenAI y Anthropic configuradas, así que no se transcribió el audio. '
                'Configura OPENAI_API_KEY y ANTHROPIC_API_KEY para usar el dictado real.')


class ErrorProveedor(Exception):
    pass


def en_prueba():
    return (getattr(settings, 'DICTADO_MODO', '') == 'prueba' or not getattr(settings, 'OPENAI_API_KEY', '')
            or not getattr(settings, 'ANTHROPIC_API_KEY', ''))


def transcribir(audio, nombre, tipo, vocabulario=''):
    """Bytes de audio → (texto, modelo)."""
    modelo = settings.DICTADO_MODELO_TRANSCRIPCION
    if en_prueba():
        return TEXTO_PRUEBA, 'prueba'
    try:
        r = requests.post(URL_OPENAI, headers={'Authorization': f'Bearer {settings.OPENAI_API_KEY}'},
                          files={'file': (nombre, audio, tipo or 'audio/webm')},
                          data={'model': modelo, 'language': 'es', 'response_format': 'json',
                                'prompt': vocabulario[:900]}, timeout=150)
    except requests.RequestException as e:
        raise ErrorProveedor(f'No se pudo conectar con el servicio de transcripción ({e.__class__.__name__}).') from e
    if r.status_code != 200:
        raise ErrorProveedor(f'La transcripción falló ({r.status_code}): {r.text[:150]}')
    return (r.json().get('text') or '').strip(), modelo


def ordenar(transcripcion, sistema, herramienta):
    """Texto → (entrada de la herramienta como dict, tokens de entrada, tokens de salida, modelo)."""
    modelo = settings.DICTADO_MODELO_IA
    if en_prueba():
        return {'secciones': {}, 'no_ubicado': transcripcion}, 0, 0, 'prueba'
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
