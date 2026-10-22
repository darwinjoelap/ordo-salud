"""
Normaliza el audio antes de enviarlo: cualquier formato (grabación del navegador, nota de voz del teléfono .m4a,
.mp3, .ogg, .wav…) → MP3 mono 16 kHz 32 kbps (≈ 0,24 MB por minuto) y su duración exacta en segundos (para cobrar
los minutos). Usa el ffmpeg que trae `imageio-ffmpeg` (funciona igual en Windows y en Railway). Si no está, se envía
el archivo tal cual y la duración la da el navegador. Los archivos temporales se borran al terminar.
"""
import os
import re
import subprocess
import tempfile

TIPOS = {'.webm': 'audio/webm', '.m4a': 'audio/m4a', '.mp4': 'audio/m4a', '.mp3': 'audio/mp3', '.ogg': 'audio/ogg',
         '.opus': 'audio/ogg', '.oga': 'audio/ogg', '.wav': 'audio/wav', '.aac': 'audio/aac', '.flac': 'audio/flac',
         '.aiff': 'audio/aiff', '.amr': 'audio/amr', '.3gp': 'audio/3gpp'}
DURACION = re.compile(r'time=(\d+):(\d+):(\d+(?:\.\d+)?)')


def tipo_de(nombre, tipo=''):
    extension = os.path.splitext(nombre or '')[1].lower()
    return TIPOS.get(extension) or (tipo.split(';')[0] if tipo else 'audio/webm')


def _ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001 - sin ffmpeg se envía el original
        return None


def convertir(datos, nombre, tipo=''):
    """(bytes, tipo MIME, segundos o None)."""
    ejecutable = _ffmpeg()
    if not ejecutable:
        return datos, tipo_de(nombre, tipo), None
    extension = os.path.splitext(nombre or '')[1].lower() or '.webm'
    with tempfile.TemporaryDirectory(prefix='dictado_') as carpeta:
        entrada, salida = os.path.join(carpeta, 'entrada' + extension), os.path.join(carpeta, 'salida.mp3')
        with open(entrada, 'wb') as f:
            f.write(datos)
        try:
            proceso = subprocess.run([ejecutable, '-hide_banner', '-nostdin', '-y', '-i', entrada, '-vn', '-ac', '1',
                                      '-ar', '16000', '-b:a', '32k', salida], capture_output=True, timeout=300)
        except (OSError, subprocess.TimeoutExpired):
            return datos, tipo_de(nombre, tipo), None
        if proceso.returncode != 0 or not os.path.exists(salida):
            return datos, tipo_de(nombre, tipo), None
        marcas = DURACION.findall(proceso.stderr.decode('utf-8', 'ignore'))
        segundos = None
        if marcas:
            h, m, s = marcas[-1]
            segundos = int(int(h) * 3600 + int(m) * 60 + float(s))
        with open(salida, 'rb') as f:
            return f.read(), 'audio/mp3', segundos
