"""
Récipe e indicaciones (de Ginea): carta horizontal en dos columnas simétricas —izquierda «Rp.» (lo que se
entrega en farmacia), derecha «Indicaciones» (cómo tomarlo + indicaciones + exámenes)— para cortar por la mitad.
La firma y el sello van fijos al pie de cada columna (canvas), así nunca quedan solos en otra página.
"""
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import BaseDocTemplate, Frame, HRFlowable, PageTemplate, Spacer, Table, TableStyle

from apps.core.pdf import ESTILOS, Paragraph, banner_de, dibujar_firma, dibujar_marca_agua, logo_de, marca_agua_de

from .base import GRIS, LINEA, color_tenant

ANCHO_PAG, ALTO_PAG = landscape(letter)
MARGEN = 12 * mm
SEPARACION = 9 * mm
COLUMNA = (ANCHO_PAG - 2 * MARGEN - SEPARACION) / 2
ALTO_FIRMA = 30 * mm

NOMBRE = ParagraphStyle('r_nombre', parent=ESTILOS['Normal'], fontName='Helvetica-Bold', fontSize=12.5, leading=15)
DATO = ParagraphStyle('r_dato', parent=ESTILOS['Normal'], fontSize=8, leading=10, textColor=GRIS)
FECHA = ParagraphStyle('r_fecha', parent=DATO, alignment=TA_RIGHT, fontSize=8.5)
PACIENTE = ParagraphStyle('r_paciente', parent=ESTILOS['Normal'], fontName='Helvetica-Bold', fontSize=10, leading=13)
ETIQUETA = ParagraphStyle('r_etiqueta', parent=ESTILOS['Normal'], fontName='Helvetica-Bold', fontSize=12, leading=16)
SUB = ParagraphStyle('r_sub', parent=ESTILOS['Normal'], fontName='Helvetica-Bold', fontSize=9.5, leading=13,
                     spaceBefore=4)
TEXTO = ParagraphStyle('r_texto', parent=ESTILOS['Normal'], fontSize=10, leading=13.5)
ITEM = ParagraphStyle('r_item', parent=TEXTO, leftIndent=4 * mm)
DETALLE = ParagraphStyle('r_detalle', parent=TEXTO, leftIndent=4 * mm, fontSize=9, textColor=colors.HexColor('#374151'))


def _bytes(archivo):
    if not archivo:
        return None
    try:
        archivo.open('rb')
        datos = archivo.read()
        archivo.close()
        ImageReader(BytesIO(datos)).getSize()
        return datos
    except Exception:  # noqa: BLE001  una imagen dañada nunca impide el récipe
        return None


def _texto(texto):
    salida = []
    for linea in (texto or '').strip().split('\n'):
        linea = linea.strip()
        if linea:
            salida.append(Paragraph(linea, ITEM if linea[0] in '-·•' else TEXTO))
    return salida


def _cabecera(doc, membrete, logo=None):
    tenant, profesional, paciente = doc.tenant, doc.profesional, doc.paciente
    config = tenant.configuracion
    salida = []
    if membrete:
        from reportlab.platypus import Image
        lector = ImageReader(BytesIO(membrete))
        ancho, alto = lector.getSize()
        escala = min(COLUMNA / ancho, 24 * mm / alto)
        salida.append(Image(BytesIO(membrete), width=ancho * escala, height=alto * escala))
    else:
        # Estilo Pediae: logo + nombre grande + especialidad, credenciales y registros
        info = [Paragraph(profesional.nombre_con_titulo if profesional else config.nombre_display,
                          ParagraphStyle('n', parent=NOMBRE, textColor=color_tenant(tenant)))]
        telefono = (profesional.telefono_consulta if profesional else '') or config.telefono
        for linea in [profesional.especialidad_texto if profesional else '',
                      profesional.credenciales if profesional else '',
                      profesional.registros_texto if profesional else '',
                      config.nombre_display if profesional else '',
                      ' · '.join(x for x in [telefono, config.email] if x)]:
            if linea:
                info.append(Paragraph(linea, DATO))
        if logo:
            from reportlab.platypus import Image
            lado = 18 * mm
            ancho, alto = ImageReader(BytesIO(logo)).getSize()
            escala = min(lado / ancho, lado / alto)
            t = Table([[Image(BytesIO(logo), width=ancho * escala, height=alto * escala), info]],
                      colWidths=[lado + 3 * mm, COLUMNA - lado - 3 * mm])
            t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                                   ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
            salida.append(t)
        else:
            salida += info
    lugar = doc.consulta.lugar if doc.consulta_id and doc.consulta.lugar_id else None
    if lugar and (lugar.direccion or lugar.nombre):
        salida.append(Paragraph(lugar.direccion or lugar.nombre, DATO))
    salida += [Spacer(1, 2 * mm), HRFlowable(width=COLUMNA, thickness=0.6, color=LINEA), Spacer(1, 2 * mm),
               Paragraph(f'{doc.fecha:%d/%m/%Y}', FECHA), Paragraph(paciente.nombre_completo, PACIENTE)]
    detalle = [paciente.documento if paciente.numero_documento else '', paciente.edad_texto or '']
    if any(detalle):
        salida.append(Paragraph(' · '.join(x for x in detalle if x), DATO))
    return salida + [Spacer(1, 4 * mm)]


def contenido(consulta):
    """Datos del récipe a partir de las secciones de la consulta (prescripción, plan, órdenes)."""
    from apps.clinica.consultas import datos_guardados
    datos = datos_guardados(consulta)
    por_codigo = {i['codigo']: datos.get(i['seccion_id']) or {} for i in consulta.estructura}
    medicamentos = [m for m in por_codigo.get('nucleo.prescripcion', {}).get('medicamentos') or []
                    if (m.get('medicamento') or '').strip()]
    plan = por_codigo.get('nucleo.plan', {})
    ordenes = por_codigo.get('nucleo.ordenes', {})
    return {
        'medicamentos': medicamentos,
        'indicaciones_generales': por_codigo.get('nucleo.prescripcion', {}).get('observaciones', ''),
        'indicaciones': plan.get('indicaciones', ''),
        'proximo_control': plan.get('proximo_control', ''),
        'laboratorio': ordenes.get('laboratorio', ''),
        'imagenes': ordenes.get('imagenes', ''),
        'otros': ordenes.get('otros', ''),
    }


def generar(doc, con_firma=True):
    profesional = doc.profesional
    datos = contenido(doc.consulta)
    membrete = _bytes(banner_de(doc.tenant, profesional))
    logo = _bytes(logo_de(doc.tenant, profesional))
    marca = marca_agua_de(doc.tenant, profesional)
    firma = _bytes(profesional.firma) if con_firma and profesional else None
    sello = _bytes(profesional.sello) if con_firma and profesional else None

    izquierda = _cabecera(doc, membrete, logo) + [Paragraph('Rp.', ETIQUETA), Spacer(1, 2 * mm)]
    derecha = _cabecera(doc, membrete, logo) + [Paragraph('Indicaciones', ETIQUETA), Spacer(1, 2 * mm)]
    for n, m in enumerate(datos['medicamentos'], 1):
        cantidad = f" — {m['cantidad']}" if m.get('cantidad') else ''
        izquierda.append(Paragraph(f"{n}. {m['medicamento']}{cantidad}", TEXTO))
        izquierda.append(Spacer(1, 2 * mm))
        como = ', '.join(x for x in [m.get('dosis'), m.get('frecuencia'), m.get('duracion')] if x)
        derecha.append(Paragraph(f"{n}. <b>{m['medicamento']}</b>", TEXTO))
        if como:
            derecha.append(Paragraph(como, DETALLE))
        derecha.append(Spacer(1, 1.5 * mm))
    if not datos['medicamentos']:
        izquierda.append(Paragraph('—', TEXTO))
    for etiqueta, clave in [('', 'indicaciones_generales'), ('Indicaciones generales', 'indicaciones'),
                            ('Exámenes de laboratorio', 'laboratorio'), ('Estudios de imagen', 'imagenes'),
                            ('Otros', 'otros')]:
        if datos[clave]:
            if etiqueta:
                derecha.append(Paragraph(etiqueta, SUB))
            derecha += _texto(datos[clave])
    if datos['proximo_control']:
        from datetime import date
        try:
            control = date.fromisoformat(datos['proximo_control']).strftime('%d/%m/%Y')
        except ValueError:
            control = datos['proximo_control']
        derecha += [Paragraph('Próximo control', SUB), Paragraph(control, TEXTO)]

    def pie(canvas, documento):
        canvas.saveState()
        centros = (MARGEN + COLUMNA / 2, MARGEN + COLUMNA + SEPARACION + COLUMNA / 2)
        for cx in centros:      # logo tenue de fondo en cada mitad (como Pediae)
            dibujar_marca_agua(canvas, marca, cx, MARGEN + ALTO_FIRMA + (ALTO_PAG - 2 * MARGEN - ALTO_FIRMA) * 0.4,
                               62 * mm)
            dibujar_firma(canvas, profesional, cx, MARGEN, firma=firma, sello=sello, ancho_linea=54 * mm)
        corte = MARGEN + COLUMNA + SEPARACION / 2
        canvas.setStrokeColor(LINEA)
        canvas.setDash(2, 3)
        canvas.line(corte, MARGEN, corte, ALTO_PAG - MARGEN)
        canvas.setDash()
        canvas.setFont('Helvetica', 6.5)
        canvas.setFillColor(GRIS)
        canvas.drawRightString(ANCHO_PAG - MARGEN, MARGEN - 7 * mm, f'{doc.numero} · Ordo Salud')
        canvas.restoreState()

    tabla = Table([[izquierda, '', derecha]], colWidths=[COLUMNA, SEPARACION, COLUMNA])
    tabla.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'),
                               ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                               ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0)]))
    buffer = BytesIO()
    marco = Frame(MARGEN, MARGEN + ALTO_FIRMA, ANCHO_PAG - 2 * MARGEN, ALTO_PAG - 2 * MARGEN - ALTO_FIRMA,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    pdf = BaseDocTemplate(buffer, pagesize=(ANCHO_PAG, ALTO_PAG), title=f'Récipe {doc.numero}',
                          pageTemplates=[PageTemplate(id='recipe', frames=[marco], onPage=pie)])
    # Si el récipe es muy largo, la tabla se parte por filas: se arma por bloques para que sí pueda partirse.
    try:
        pdf.build([tabla])
    except Exception:  # noqa: BLE001  LayoutError: una sola fila más alta que la hoja
        buffer = BytesIO()
        pdf = BaseDocTemplate(buffer, pagesize=(ANCHO_PAG, ALTO_PAG), title=f'Récipe {doc.numero}',
                              pageTemplates=[PageTemplate(id='recipe', frames=[
                                  Frame(MARGEN, MARGEN + ALTO_FIRMA, COLUMNA, ALTO_PAG - 2 * MARGEN - ALTO_FIRMA,
                                        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0),
                                  Frame(MARGEN + COLUMNA + SEPARACION, MARGEN + ALTO_FIRMA, COLUMNA,
                                        ALTO_PAG - 2 * MARGEN - ALTO_FIRMA,
                                        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)], onPage=pie)])
        from reportlab.platypus import FrameBreak
        pdf.build(izquierda + [FrameBreak()] + derecha)
    return buffer.getvalue()
