"""
Cifrado simétrico para datos que hay que poder volver a leer (ADR-062: la contraseña TEMPORAL de un usuario, para
volver a compartirla mientras no la cambie). La llave sale de SECRET_KEY: si se rota, lo cifrado deja de leerse y
basta con generar una contraseña nueva. Nunca se usa para la contraseña propia del usuario (esa solo existe como hash).
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet():
    llave = hashlib.sha256(f'{settings.SECRET_KEY}:ordo-salud:clave-temporal'.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(llave))


def cifrar(texto):
    return _fernet().encrypt(texto.encode()).decode() if texto else ''


def descifrar(token):
    if not token:
        return ''
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return ''
