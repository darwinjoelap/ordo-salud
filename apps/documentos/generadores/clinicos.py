"""
Documentos clínicos comunes en carta vertical: informe médico, referencia, reposo y constancia de asistencia.
Textos inspirados en los de Ginea/Pediae, con género del paciente y números en letras.
"""
from datetime import date, timedelta
from xml.sax.saxutils import escape

from reportlab.lib.units import mm
from reportlab.platypus import Spacer

from apps.core.fechas import hora12
from apps.core.pdf import Paragraph

from . import antecedentes
from .base import (
    CUERPO,
    SUBTITULO,
    ciudad_de,
    construir,
    datos_paciente,
    fecha_larga,
    lineas,
    lugar_y_fecha,
    nota_confidencial,
    seccion,
    tabla_datos,
    titulo,
)

UNIDADES = ['cero', 'un', 'dos', 'tres', 'cuatro', 'cinco', 'seis', 'siete', 'ocho', 'nueve', 'diez', 'once', 'doce',
            'trece', 'catorce', 'quince', 'dieciséis', 'diecisiete', 'dieciocho', 'diecinueve', 'veinte',
            'veintiún', 'veintidós', 'veintitrés', 'veinticuatro', 'veinticinco', 'veintiséis', 'veintisiete',
            'veintiocho', 'veintinueve']
DECENAS = {3: 'treinta', 4: 'cuarenta', 5: 'cincuenta', 6: 'sesenta', 7: 'setenta', 8: 'ochenta', 9: 'noventa'}


def en_letras(n):
    """Entero 0–999 en letras (para «quince (15) días»)."""
    n = int(n)
    if n < 30:
        return UNIDADES[n]
    if n < 100:
        d, u = divmod(n, 10)
        return DECENAS[d] + (f' y {UNIDADES[u]}' if u else '')
    if n == 100:
        return 'cien'
    c, resto = divmod(n, 100)
    centenas = {1: 'ciento', 5: 'quinientos', 7: 'setecientos', 9: 'novecientos'}.get(c, f'{UNIDADES[c]}cientos')
    return centenas + (f' {en_letras(resto)}' if resto else '')


def _el_la(paciente):
    return ('la', 'a') if paciente.sexo == 'F' else ('el', 'o')


def _fecha(valor):
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor))
    except ValueError:
        return None


def _quien(doc):
    p = doc.profesional
    if p is None:
        return 'Quien suscribe'
    detalle = ', '.join(x for x in [p.especialidad_texto, p.registros_texto] if x)
    return f'Quien suscribe, <b>{p.nombre_con_titulo}</b>' + (f', {detalle}' if detalle else '')


def _identificacion(paciente):
    articulo, o = _el_la(paciente)
    texto = f'{articulo} paciente <b>{paciente.nombre_completo}</b>'
    if paciente.numero_documento:
        texto += f', titular del documento {paciente.documento}'
    if paciente.edad_texto:
        texto += f', de {paciente.edad_texto} de edad'
    return texto


def _diagnosticos(consulta):
    if consulta is None:
        return ''
    filas = [f"{d.codigo} {d.descripcion}".strip() for d in consulta.diagnosticos.all()]
    return '\n'.join(filas) or consulta.diagnostico


# ── Informe médico ────────────────────────────────────────────────────────────

def informe(doc, con_firma=True):
    from apps.clinica.consultas import lectura
    consulta = doc.consulta
    cuerpo = lugar_y_fecha(doc.fecha, ciudad_de(doc)) + titulo('Informe médico', doc.tenant, doc.numero)
    cuerpo += datos_paciente(doc.paciente)
    if doc.datos.get('dirigido_a'):
        cuerpo += [Spacer(1, 2 * mm), Paragraph(f"<b>A:</b> {doc.datos['dirigido_a']}", CUERPO)]
    if doc.datos.get('introduccion'):
        cuerpo += [Spacer(1, 2 * mm)] + lineas(doc.datos['introduccion'])
    cuerpo += tabla_datos([('Fecha de la consulta', f'{consulta.fecha_hora:%d/%m/%Y}'),
                           ('Especialidad', consulta.especialidad.nombre if consulta.especialidad_id else '')])
    omitir = set(doc.datos.get('omitir') or [])
    for item, filas in lectura(consulta):
        if item['codigo'] in omitir or item['codigo'] == 'nucleo.prescripcion':
            continue
        cuerpo += seccion(item['nombre'], doc.tenant)
        for campo, texto in filas:
            if len(filas) == 1 and campo['tipo'] in ('texto_largo', 'tabla'):
                cuerpo += lineas(texto)
            elif '\n' in texto:
                cuerpo.append(Paragraph(f"<b>{campo['etiqueta']}:</b>", CUERPO))
                cuerpo += lineas(texto)
            else:
                cuerpo.append(Paragraph(f"<b>{escape(campo['etiqueta'])}:</b> {escape(texto)}", CUERPO))
    if doc.datos.get('conclusion'):
        cuerpo += seccion('Conclusión', doc.tenant) + lineas(doc.datos['conclusion'])
    cuerpo += nota_confidencial()
    return construir(doc, cuerpo, con_firma=con_firma)


# ── Referencia ────────────────────────────────────────────────────────────────

def referencia(doc, con_firma=True):
    d = doc.datos
    cuerpo = lugar_y_fecha(doc.fecha, ciudad_de(doc)) + titulo('Informe de referencia', doc.tenant, doc.numero)
    cuerpo += datos_paciente(doc.paciente)
    cuerpo += seccion('Referencia', doc.tenant)
    cuerpo += tabla_datos([('Referido a', d.get('dirigido_a', '')), ('Prioridad', d.get('prioridad', ''))])
    if d.get('motivo'):
        cuerpo += [Paragraph('Motivo de la referencia', SUBTITULO)] + lineas(d['motivo'])
    if d.get('resumen'):
        cuerpo += seccion('Resumen clínico', doc.tenant) + lineas(d['resumen'])
    if d.get('diagnosticos'):
        cuerpo += seccion('Impresión diagnóstica', doc.tenant) + lineas(d['diagnosticos'])
    if d.get('tratamiento'):
        cuerpo += seccion('Tratamiento actual', doc.tenant) + lineas(d['tratamiento'])
    cuerpo += antecedentes.flowables(d.get('antecedentes_texto'), doc.tenant)
    cuerpo += [Spacer(1, 4 * mm), Paragraph('Agradeciendo la atención prestada, quedo a su disposición.', CUERPO)]
    cuerpo += nota_confidencial()
    return construir(doc, cuerpo, con_firma=con_firma)


def inicial_referencia(paciente, consulta):
    if consulta is None:
        return {}
    from apps.clinica.consultas import datos_guardados
    datos = datos_guardados(consulta)
    por_codigo = {i['codigo']: datos.get(i['seccion_id']) or {} for i in consulta.estructura}
    medicamentos = por_codigo.get('nucleo.prescripcion', {}).get('medicamentos') or []
    tratamiento = '\n'.join('- ' + ' '.join(x for x in [m.get('medicamento'), m.get('dosis'), m.get('frecuencia')] if x)
                            for m in medicamentos if m.get('medicamento'))
    resumen = []
    if consulta.motivo:
        resumen.append(f'Consulta por: {consulta.motivo}.')
    enfermedad = por_codigo.get('nucleo.motivo', {}).get('enfermedad_actual')
    if enfermedad:
        resumen.append(enfermedad)
    return {'diagnosticos': _diagnosticos(consulta), 'tratamiento': tratamiento, 'resumen': '\n'.join(resumen)}


# ── Reposo ────────────────────────────────────────────────────────────────────

def reposo(doc, con_firma=True):
    d, paciente = doc.datos, doc.paciente
    dias = int(d.get('dias') or 1)
    desde = _fecha(d.get('desde')) or doc.fecha
    hasta = desde + timedelta(days=dias - 1)
    dias_txt = f"{en_letras(dias)} ({dias}) día{'s' if dias != 1 else ''}"
    texto = (f'{_quien(doc)}, hace constar que {_identificacion(paciente)}, fue evaluad{_el_la(paciente)[1]} '
             f'en consulta y amerita <b>reposo médico por {dias_txt}</b>, desde el {fecha_larga(desde)} hasta el '
             f'{fecha_larga(hasta)}, ambos inclusive.')
    cuerpo = lugar_y_fecha(doc.fecha, ciudad_de(doc)) + titulo('Constancia de reposo médico', doc.tenant, doc.numero)
    cuerpo += [Spacer(1, 4 * mm), Paragraph(texto, CUERPO), Spacer(1, 3 * mm)]
    if d.get('diagnostico'):
        cuerpo += [Paragraph('<b>Diagnóstico:</b>', CUERPO)] + lineas(d['diagnostico'])
    if d.get('indicaciones'):
        cuerpo += [Spacer(1, 2 * mm), Paragraph('<b>Indicaciones:</b>', CUERPO)] + lineas(d['indicaciones'])
    cuerpo += [Spacer(1, 4 * mm), Paragraph('Constancia que se expide a petición de la parte interesada.', CUERPO)]
    return construir(doc, cuerpo, con_firma=con_firma)


def inicial_reposo(paciente, consulta):
    return {'diagnostico': _diagnosticos(consulta), 'dias': 1, 'desde': date.today().isoformat()}


# ── Constancia de asistencia ──────────────────────────────────────────────────

def constancia(doc, con_firma=True):
    d, paciente = doc.datos, doc.paciente
    fecha = _fecha(d.get('fecha_asistencia')) or doc.fecha
    especialidad = doc.profesional.especialidad.nombre.lower() if doc.profesional and \
        doc.profesional.especialidad_id else ''
    texto = f'{_quien(doc)}, hace constar que {_identificacion(paciente)}, asistió a consulta'
    if especialidad:
        texto += f' de {especialidad}'
    texto += f' el día {fecha_larga(fecha)}'
    desde, hasta = d.get('hora_desde'), d.get('hora_hasta')
    if desde and hasta:
        texto += f', entre las {hora12(_hora(desde))} y las {hora12(_hora(hasta))}'
    elif desde:
        texto += f', a las {hora12(_hora(desde))}'
    texto += '.'
    if d.get('acompanante'):
        texto += f" Acudió en compañía de <b>{d['acompanante']}</b>."
    cuerpo = lugar_y_fecha(doc.fecha, ciudad_de(doc)) + titulo('Constancia de asistencia', doc.tenant, doc.numero)
    cuerpo += [Spacer(1, 4 * mm), Paragraph(texto, CUERPO)]
    if d.get('observaciones'):
        cuerpo += [Spacer(1, 2 * mm)] + lineas(d['observaciones'])
    cuerpo += [Spacer(1, 4 * mm), Paragraph('Constancia que se expide a petición de la parte interesada.', CUERPO)]
    return construir(doc, cuerpo, con_firma=con_firma)


def _hora(valor):
    from datetime import time
    if isinstance(valor, time):
        return valor
    h, m = str(valor).split(':')[:2]
    return time(int(h), int(m))


def inicial_constancia(paciente, consulta):
    from django.utils import timezone
    inicial = {'fecha_asistencia': timezone.localdate().isoformat()}
    if consulta is not None:
        inicio = timezone.localtime(consulta.fecha_hora)
        inicial.update(fecha_asistencia=inicio.date().isoformat(), hora_desde=inicio.strftime('%H:%M'))
    if paciente.es_menor and paciente.representante_principal:
        r = paciente.representante_principal
        inicial['acompanante'] = f'{r.nombre}' + (f', {r.documento}' if r.numero_documento else '') + \
            f' ({r.get_parentesco_display().lower()})'
    return inicial
