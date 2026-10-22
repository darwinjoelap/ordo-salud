"""
Bloques de antecedentes del paciente para documentos (referencia, historia completa): antecedentes generales, la
ficha de cada especialidad del consultorio y la última medición. Se guardan como texto en el documento al emitirlo
(el PDF sale igual aunque después cambie la ficha).
"""
from apps.core.fechas import edad_texto

CAMPOS_BASE = [('alergias', 'Alergias'), ('medicacion_actual', 'Medicación actual'),
               ('enfermedades_cronicas', 'Enfermedades crónicas'), ('cirugias', 'Cirugías'),
               ('hospitalizaciones', 'Hospitalizaciones'), ('transfusiones', 'Transfusiones'),
               ('habitos', 'Hábitos'), ('antecedentes_familiares', 'Antecedentes familiares'), ('otros', 'Otros')]


def _numero(valor, decimales=1):
    return f'{valor:.{decimales}f}'.replace('.', ',') if valor is not None else ''


def bloques(paciente, tenant):
    """[{'clave', 'titulo', 'filas': [[etiqueta, texto]]}] solo con lo que tiene datos."""
    from apps.clinica.consultas import lectura_ficha
    salida = []
    base = getattr(paciente, 'antecedentes', None)
    if base is not None:
        filas = [[e, getattr(base, c).strip()] for c, e in CAMPOS_BASE if (getattr(base, c) or '').strip()]
        if filas:
            salida.append({'clave': 'base', 'titulo': 'Antecedentes generales', 'filas': filas})
    for codigo in tenant.especialidades.order_by('nombre').values_list('codigo', flat=True):
        for item, filas in lectura_ficha(paciente, codigo):
            salida.append({'clave': item['codigo'], 'titulo': item['nombre'],
                           'filas': [[c['etiqueta'], t] for c, t in filas]})
    medicion = ultima_medicion(paciente)
    if medicion:
        salida.append(medicion)
    return salida


def ultima_medicion(paciente):
    """Antropometría con percentiles (pediatría) o los últimos signos vitales."""
    filas, fecha = [], None
    mediciones = getattr(paciente, 'mediciones', None)
    m = mediciones.order_by('-fecha', '-pk').first() if mediciones is not None else None
    if m is not None:
        fecha = m.fecha
        for etiqueta, valor, unidad, decimales, p in (('Peso', m.peso_kg, 'kg', 2, m.p_peso),
                                                      ('Talla', m.talla_cm, 'cm', 1, m.p_talla),
                                                      ('Perímetro cefálico', m.pc_cm, 'cm', 1, m.p_pc)):
            if valor is not None:
                percentil = f' (P{_numero(p)})' if p is not None else ''
                filas.append([etiqueta, f'{_numero(valor, decimales)} {unidad}{percentil}'])
        if m.imc is not None:
            filas.append(['IMC', _numero(m.imc)])
        if m.estado_nutricional:
            filas.append(['Estado nutricional', m.estado_nutricional])
        if m.clasificacion_imc:
            filas.append(['Clasificación OMS', m.clasificacion_imc])
    else:
        s = paciente.signos_vitales.order_by('-fecha', '-pk').first()
        if s is not None:
            fecha = s.fecha
            for etiqueta, valor in (('Peso', f'{_numero(s.peso_kg, 2)} kg' if s.peso_kg else ''),
                                    ('Talla', f'{_numero(s.talla_cm)} cm' if s.talla_cm else ''),
                                    ('IMC', _numero(s.imc) if s.imc else ''),
                                    ('Tensión arterial', f'{s.pa_sistolica}/{s.pa_diastolica} mmHg'
                                     if s.pa_sistolica and s.pa_diastolica else ''),
                                    ('Frecuencia cardíaca', f'{s.fc} lpm' if s.fc else '')):
                if valor:
                    filas.append([etiqueta, valor])
    if not filas:
        return None
    titulo = f'Última medición ({fecha:%d/%m/%Y}'
    if paciente.fecha_nacimiento:
        titulo += f', a los {edad_texto(paciente.fecha_nacimiento, fecha)}'
    return {'clave': 'medicion', 'titulo': titulo + ')', 'filas': filas}


def opciones(paciente, tenant):
    return [(b['clave'], b['titulo']) for b in bloques(paciente, tenant)]


def elegidos(paciente, tenant, claves):
    claves = set(claves or [])
    return [b for b in bloques(paciente, tenant) if b['clave'] in claves]


def flowables(lista, tenant):
    """Bloques guardados → párrafos del PDF."""
    from xml.sax.saxutils import escape

    from reportlab.platypus import Paragraph

    from .base import CUERPO, SUBTITULO, lineas, seccion
    cuerpo = []
    if not lista:
        return cuerpo
    cuerpo += seccion('Antecedentes', tenant)
    for b in lista:
        cuerpo.append(Paragraph(escape(b['titulo']), SUBTITULO))
        for etiqueta, texto in b['filas']:
            if '\n' in texto:
                cuerpo.append(Paragraph(f'<b>{escape(etiqueta)}:</b>', CUERPO))
                cuerpo += lineas(texto)
            else:
                cuerpo.append(Paragraph(f'<b>{escape(etiqueta)}:</b> {escape(texto)}', CUERPO))
    return cuerpo
