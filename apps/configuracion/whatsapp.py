"""
Mensaje del recordatorio de cita por WhatsApp (ADR-058): plantilla editable por consultorio con marcadores.

Si la cita no tiene hora o lugar, la frase «a las {hora}» / «en {lugar}» desaparece sola (no queda «a las .»).
"""
import re

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
