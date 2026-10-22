"""Historia clínica completa (PDF): datos, antecedentes y fichas, cada consulta con todas sus secciones,
procedimientos y vacunas aplicadas. Las consultas se fijan al emitir (solo las que el profesional podía ver)."""
from xml.sax.saxutils import escape

from django.utils import timezone
from reportlab.lib.units import mm
from reportlab.platypus import CondPageBreak, Spacer

from apps.core.pdf import Paragraph

from . import antecedentes
from .base import CUERPO, SUBTITULO, construir, datos_paciente, lineas, lugar_y_fecha, seccion, tabla_datos, titulo


def _consulta(c, tenant):
    from apps.clinica.consultas import lectura
    cuerpo = [CondPageBreak(40 * mm)]
    cabecera = (f'{timezone.localtime(c.fecha_hora):%d/%m/%Y} · {c.get_tipo_display()} · {c.profesional}'
                + (f' · {c.especialidad.nombre}' if c.especialidad_id else ''))
    cuerpo += seccion(f'Consulta del {cabecera}', tenant)
    filas_total = lectura(c)
    if not filas_total:
        cuerpo.append(Paragraph('Sin datos registrados.', CUERPO))
    for item, filas in filas_total:
        cuerpo += [CondPageBreak(18 * mm), Paragraph(escape(item['nombre']), SUBTITULO)]
        for campo, texto in filas:
            if '\n' in texto or (len(filas) == 1 and campo['tipo'] in ('texto_largo', 'tabla')):
                if len(filas) > 1:
                    cuerpo.append(Paragraph(f"<b>{escape(campo['etiqueta'])}:</b>", CUERPO))
                cuerpo += lineas(texto)
            else:
                cuerpo.append(Paragraph(f"<b>{escape(campo['etiqueta'])}:</b> {escape(texto)}", CUERPO))
    for n in c.notas_evolucion.all():
        cuerpo.append(Paragraph(f'<b>Evolución {n.fecha:%d/%m/%Y}:</b> {escape(n.texto)}', CUERPO))
    if c.estado == 'BORRADOR':
        cuerpo.append(Paragraph('<i>Consulta en curso (sin cerrar) al emitir este documento.</i>', CUERPO))
    return cuerpo


def generar(doc, con_firma=True):
    from apps.clinica.models import Consulta, Procedimiento
    d, paciente, tenant = doc.datos, doc.paciente, doc.tenant
    cuerpo = lugar_y_fecha(doc.fecha, d.get('ciudad', '')) + titulo('Historia clínica', tenant, doc.numero)
    cuerpo += datos_paciente(paciente)
    ids = d.get('consultas') or []
    consultas = {c.pk: c for c in Consulta.objects.filter(pk__in=ids).select_related(
        'profesional__membresia__usuario', 'especialidad')}
    ordenadas = [consultas[i] for i in ids if i in consultas]
    periodo = ''
    if ordenadas:
        primera, ultima = (timezone.localtime(ordenadas[0].fecha_hora), timezone.localtime(ordenadas[-1].fecha_hora))
        periodo = f'{primera:%d/%m/%Y} al {ultima:%d/%m/%Y}'
    cuerpo += tabla_datos([('Consultas incluidas', str(len(ordenadas))), ('Período', periodo or '—')])
    cuerpo += antecedentes.flowables(d.get('antecedentes_texto'), tenant)

    vacunas = getattr(paciente, 'vacunas_aplicadas', None)
    if vacunas is not None and d.get('antecedentes_texto') is not None:
        aplicadas = list(vacunas.select_related('vacuna').order_by('vacuna__edad_meses', 'vacuna__orden', 'fecha'))
        if aplicadas:
            cuerpo += seccion('Vacunas aplicadas', tenant)
            texto = '; '.join(f'{a.vacuna.nombre} (dosis {a.vacuna.dosis}' + (f', {a.fecha:%d/%m/%Y}' if a.fecha else '')
                              + ')' for a in aplicadas)
            cuerpo.append(Paragraph(escape(texto), CUERPO))

    for c in ordenadas:
        cuerpo += _consulta(c, tenant)

    procs = Procedimiento.objects.filter(paciente=paciente, anulado=False).order_by('fecha')
    if ordenadas:
        procs = procs.filter(fecha__range=(timezone.localtime(ordenadas[0].fecha_hora).date(),
                                           timezone.localtime(ordenadas[-1].fecha_hora).date()))
    procs = list(procs)
    if procs:
        cuerpo += [CondPageBreak(30 * mm)] + seccion('Procedimientos', tenant)
        for p in procs:
            cuerpo.append(Paragraph(f'<b>{p.fecha:%d/%m/%Y}:</b> {escape(p.descripcion)}'
                                    + (f' — {escape(p.notas)}' if p.notas else ''), CUERPO))
    cuerpo += [Spacer(1, 4 * mm)]
    return construir(doc, cuerpo, con_firma=con_firma, titulo_pdf=f'Historia clínica · {paciente.nombre_completo}')
