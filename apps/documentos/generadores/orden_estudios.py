"""Orden de exámenes: snapshot de solicitudes, sin resultados ni cargos."""
from .base import construir, datos_paciente, lineas, lugar_y_fecha, seccion, titulo


CATEGORIAS = {
    'LAB': 'Laboratorio', 'ECG': 'Electrocardiograma',
    'RX': 'Radiografía / imágenes', 'OTRO': 'Otros estudios',
}


def generar(doc, con_firma=True):
    cuerpo = lugar_y_fecha(doc.fecha, doc.datos.get('ciudad') or '')
    cuerpo += titulo('Orden de exámenes', doc.tenant, doc.numero)
    cuerpo += datos_paciente(doc.paciente)
    if doc.consulta_id:
        cuerpo += seccion('Consulta que origina la orden', doc.tenant)
        cuerpo += lineas(f'Fecha: {doc.consulta.fecha_hora:%d/%m/%Y}')
    cuerpo += seccion('Exámenes solicitados', doc.tenant)
    estudios = doc.datos.get('estudios') or []
    if not estudios:
        cuerpo += lineas('Sin exámenes seleccionados.')
    for estudio in estudios:
        nombre = estudio.get('nombre') or 'Examen'
        categoria = CATEGORIAS.get(estudio.get('categoria'), 'Estudio')
        cuerpo += lineas(f'• {nombre} ({categoria})')
        indicaciones = estudio.get('indicaciones') or ''
        if indicaciones:
            cuerpo += lineas(f'Indicaciones: {indicaciones}')
    return construir(doc, cuerpo, con_firma=con_firma)
