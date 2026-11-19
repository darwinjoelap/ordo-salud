"""
Mensaje del recordatorio de cita por WhatsApp (ADR-058): plantilla editable por consultorio con marcadores.

Si la cita no tiene hora o lugar, la frase «a las {hora}» / «en {lugar}» desaparece sola (no queda «a las .»).
"""
import re
from urllib.parse import parse_qs, quote, urlparse

from django.core.exceptions import ValidationError

PLANTILLA = ('Hola {saludo}, le recordamos la cita {de_paciente}con {profesional} ({consultorio}) el {fecha} '
             'a las {hora} en {lugar}. Por favor confirme su asistencia. Gracias.')

VARIABLES = {
    'saludo': 'Primer nombre de quien recibe (el representante si el paciente es menor)',
    'paciente': 'Nombre del paciente',
    'de_paciente': '«de <nombre> » solo cuando se le escribe al representante',
    'profesional': 'Profesional con su título (Dra. …)',
    'consultorio': 'Nombre del consultorio',
    'fecha': 'Fecha de la cita (dd/mm/aaaa)',
    'hora': 'Hora de la cita',
    'lugar': 'Lugar de consulta y su dirección',
}
EJEMPLO = {'saludo': 'María', 'paciente': 'Pedro Pérez', 'de_paciente': 'de Pedro ', 'profesional': 'Dra. Ana Gómez',
           'consultorio': 'Consultorio Pediátrico', 'fecha': '10/11/2026', 'hora': '3:00 p. m.',
           'lugar': 'Torre Médica (piso 2)'}
MARCADOR = re.compile(r'\{(\w+)\}')


def desconocidos(plantilla):
    return sorted({m for m in MARCADOR.findall(plantilla or '') if m not in VARIABLES})


def validar(plantilla):
    malos = desconocidos(plantilla)
    if malos:
        raise ValidationError('Marcador desconocido: ' + ', '.join('{' + m + '}' for m in malos)
                              + '. Usa: ' + ' '.join('{' + v + '}' for v in VARIABLES))


def armar(plantilla, valores):
    """Texto final: quita «a las {hora}» / «en {lugar}» si faltan y reemplaza los marcadores."""
    texto = (plantilla or '').strip() or PLANTILLA
    for clave, frase in (('hora', r'\s*a\s+las\s*\{hora\}'), ('lugar', r'\s*en\s*\{lugar\}')):
        if not valores.get(clave):
            texto = re.sub(frase, '', texto, flags=re.IGNORECASE)
    texto = MARCADOR.sub(lambda m: str(valores.get(m.group(1), '')) if m.group(1) in VARIABLES else m.group(0), texto)
    return re.sub(r'[ \t]{2,}', ' ', texto).strip()


def numero_whatsapp(telefono):
    """Normaliza números venezolanos con 0 inicial e internacionales con código de país."""
    numero = re.sub(r'[ ().-]', '', telefono or '')
    if re.fullmatch(r'0[1-9][0-9]{9}', numero):
        return '58' + numero[1:]
    numero = numero.removeprefix('+')
    if numero.startswith('58') and len(numero) != 12:
        return ''
    return numero if re.fullmatch(r'[1-9][0-9]{9,14}', numero) else ''


def enlace(numero, texto):
    return f'https://wa.me/{numero}?text={quote(texto, safe="")}' if numero else None


def intent_business(url):
    """Prepara un intent de Android con el enlace HTTPS como alternativa."""
    u = urlparse(url)
    telefono = u.path.removeprefix('/')
    if u.scheme != 'https' or u.netloc != 'wa.me' or not re.fullmatch(r'[1-9][0-9]{9,14}', telefono):
        return url
    texto = parse_qs(u.query).get('text', [''])[0]
    return (f'intent://send/?phone={telefono}&text={quote(texto, safe="")}#Intent;scheme=whatsapp;'
            f'package=com.whatsapp.w4b;S.browser_fallback_url={quote(url, safe="")};end')
