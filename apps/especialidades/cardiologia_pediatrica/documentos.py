"""
«Informe médico» de cardiología pediátrica con el formato del modelo de la Dra. Sierra: ciudad y fecha a la derecha,
línea de datos del paciente, título subrayado, bloques ENFERMEDAD ACTUAL · ANTECEDENTES PERSONALES · EXAMEN FÍSICO ·
EKG · ECOCARDIOGRAMA TRANSTORÁCICO · COMENTARIO, imágenes del eco y notas de evolución al pie.
"""
from io import BytesIO
from xml.sax.saxutils import escape

from django import forms
from django.utils import timezone
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image, KeepTogether, Spacer, Table, TableStyle

from apps.core.pdf import ESTILOS, Paragraph, archivo_bytes
from apps.documentos.forms import DocumentoForm
from apps.documentos.generadores.base import ciudad_de, construir
from apps.documentos.registro import DocumentoDef

from . import informe

TEXTO = ParagraphStyle('cp_texto', parent=ESTILOS['Normal'], fontName='Times-Roman', fontSize=11, leading=14.5,
                       alignment=TA_JUSTIFY, spaceAfter=5)
NEGRITA = ParagraphStyle('cp_negrita', parent=TEXTO, fontName='Times-Bold')
FECHA = ParagraphStyle('cp_fecha', parent=TEXTO, fontName='Times-Bold', alignment=TA_RIGHT, spaceAfter=8)
TITULO = ParagraphStyle('cp_titulo', parent=TEXTO, fontName='Times-BoldItalic', alignment=TA_CENTER, fontSize=11.5,
                        spaceBefore=6, spaceAfter=10)

ESPECIALIDAD = 'cardiologia_pediatrica'


class InformeForm(DocumentoForm):
    incluir_imagenes = forms.BooleanField(label='Incluir las imágenes adjuntas de la consulta', required=False,
                                          initial=True)
    incluir_notas = forms.BooleanField(label='Incluir las notas de evolución', required=False, initial=True)

    def datos(self):
        salida = super().datos()
        salida['incluir_imagenes'] = bool(self.cleaned_data.get('incluir_imagenes'))
        salida['incluir_notas'] = bool(self.cleaned_data.get('incluir_notas'))
        return salida


def _bloque(etiqueta, texto, negrita=False):
    if not (texto or '').strip():
        return []
    cuerpo = escape(texto.strip())
    if negrita:
        cuerpo = f'<b>{cuerpo}</b>'
    return [Paragraph(f'<u><b>{etiqueta}:</b></u> {cuerpo}', TEXTO)]


def datos_informe(consulta):
    """Todo lo que el informe necesita, leído de la consulta y de la ficha del paciente."""
    from apps.clinica.consultas import contexto_calculo, datos_ficha, datos_guardados, items_ficha
    guardados = datos_guardados(consulta)
    por_codigo = {i['codigo']: guardados.get(i['seccion_id']) or {} for i in consulta.estructura}
    ficha = datos_ficha(consulta.paciente, items_ficha(ESPECIALIDAD))
    antecedentes = next(iter(ficha.values()), {}) or por_codigo.get('cp.antecedentes') or {}
    signos = por_codigo.get('nucleo.signos_vitales') or {}
    sc = signos.get('superficie_corporal') or contexto_calculo(consulta).get('sc')
    motivo = por_codigo.get('nucleo.motivo') or {}
    examen = por_codigo.get('nucleo.examen_fisico') or {}
    plan = por_codigo.get('nucleo.plan') or {}
    return {
        'enfermedad_actual': motivo.get('enfermedad_actual') or motivo.get('motivo', ''),
        'antecedentes': informe.antecedentes(antecedentes),
        'examen_linea': informe.examen_linea(signos, sc),
        'examen': ' '.join(t.strip() for t in (examen.get('general'), examen.get('cardiopulmonar')) if t),
        'ekg': informe.ekg_linea(por_codigo.get('cp.ekg')),
        'eco': informe.eco(por_codigo.get('cp.eco'), sc),
        'comentario': plan.get('plan', ''),
    }


def _encabezado(doc, consulta):
    p = consulta.paciente
    fecha = timezone.localtime(consulta.fecha_hora).date()
    ciudad = ciudad_de(doc)
    partes = [f'NOMBRE: {p.nombre_completo.upper()}']
    edad = informe.edad_informe(p.fecha_nacimiento, fecha)
    if edad:
        partes.append(f'EDAD: {edad}')
    if p.fecha_nacimiento:
        partes.append(f'FN: {p.fecha_nacimiento:%d/%m/%Y}')
    if p.telefono_contacto:
        partes.append(f'TLF: {p.telefono_contacto}')
    rep = p.representante_principal if p.es_menor else None
    if rep is not None:
        partes.append(f'{rep.get_parentesco_display().upper()}: {rep.nombre.upper()}')
        if rep.numero_documento:
            partes.append(f'CI: {rep.documento}')
    if p.ciudad:
        partes.append(p.ciudad.upper())
    return [Paragraph(escape(f'{ciudad} {fecha:%d/%m/%Y}'.strip()), FECHA),
            Paragraph(f"<b>{escape('. '.join(partes))}.</b>", TEXTO),
            Paragraph('<u>INFORME MÉDICO</u>', TITULO)]


def _imagenes(consulta):
    adjuntos = [a for a in consulta.adjuntos.all() if (a.tipo_contenido or '').startswith('image/')
                or a.nombre.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
    celdas = []
    for a in adjuntos:
        datos = archivo_bytes(a.archivo)
        if not datos:
            continue
        img = Image(BytesIO(datos))
        ancho = 82 * mm
        img.drawHeight = img.imageHeight * ancho / img.imageWidth
        img.drawWidth = ancho
        if img.drawHeight > 70 * mm:
            img.drawWidth = img.drawWidth * 70 * mm / img.drawHeight
            img.drawHeight = 70 * mm
        celdas.append(img)
    if not celdas:
        return []
    filas = [celdas[i:i + 2] + [''] * (2 - len(celdas[i:i + 2])) for i in range(0, len(celdas), 2)]
    tabla = Table(filas, colWidths=[93 * mm, 93 * mm])
    tabla.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                               ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
    return [Spacer(1, 4 * mm), tabla]


def generar(doc, con_firma=True):
    consulta = doc.consulta
    d = datos_informe(consulta)
    cuerpo = _encabezado(doc, consulta)
    cuerpo += _bloque('ENFERMEDAD ACTUAL', d['enfermedad_actual'])
    cuerpo += _bloque('ANTECEDENTES PERSONALES', d['antecedentes'])
    if d['examen_linea'] or d['examen']:
        cuerpo.append(Paragraph(f"<u><b>EXAMEN FÍSICO:</b></u> <b>{escape(d['examen_linea'])}</b>", TEXTO))
        if d['examen']:
            cuerpo.append(Paragraph(escape(d['examen']), TEXTO))
    cuerpo += _bloque('EKG', d['ekg'])
    cuerpo += _bloque('ECOCARDIOGRAMA TRANSTORÁCICO', d['eco'])
    cuerpo += _bloque('COMENTARIO', d['comentario'], negrita=True)
    if doc.datos.get('incluir_imagenes', True):
        cuerpo += _imagenes(consulta)
    if doc.datos.get('incluir_notas', True):
        for n in consulta.notas_evolucion.all():
            cuerpo.append(KeepTogether([Spacer(1, 3 * mm),
                                        Paragraph(f'<b>{n.fecha:%d/%m/%Y} {escape(n.texto)}</b>', TEXTO)]))
    return construir(doc, cuerpo, con_firma=con_firma, titulo_pdf=f'Informe médico · {consulta.paciente}')


def inicial(paciente, consulta):
    return {'incluir_imagenes': True, 'incluir_notas': True}


DOCUMENTOS = [
    DocumentoDef('cp_informe', 'Informe médico (cardiología)', prefijo='ICP', generar=generar, formulario=InformeForm,
                 inicial=inicial, requiere_consulta=True, icono='bi-heart-pulse', orden=5, especialidad=ESPECIALIDAD,
                 descripcion='Con el formato de la doctora: antecedentes, examen, EKG, eco, comentario e imágenes.'),
]
