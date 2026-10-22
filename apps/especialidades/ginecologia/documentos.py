"""
Documentos de ginecología y obstetricia (nuevos respecto a Ginea): constancia de embarazo y carnet de control
prenatal, con el diseño de Ordo Salud (encabezado del médico, logo tenue y firma/sello fijos al pie).
"""
from datetime import timedelta

from django import forms
from django.utils import timezone
from reportlab.lib.units import mm
from reportlab.platypus import Spacer, Table, TableStyle

from apps.core.pdf import ESTILO_CELDA, Paragraph
from apps.documentos.forms import DocumentoForm, _area
from apps.documentos.generadores.base import (
    CUERPO,
    CUERPO_ITEM,
    FONDO,
    LINEA,
    construir,
    datos_paciente,
    fecha_larga,
    lineas,
    lugar_y_fecha,
    seccion,
    tabla_datos,
    titulo,
)
from apps.documentos.generadores.clinicos import _quien, ciudad_de
from apps.documentos.registro import DocumentoDef

from . import obstetricia as ob
from .models import ControlPrenatal
from .paneles import _fila
from .servicios import control_actual, ficha


def _cierre(doc):
    ciudad = ciudad_de(doc)
    lugar = f'en la ciudad de {ciudad}, ' if ciudad else ''
    return Paragraph(f'Se expide la presente a petición de la parte interesada, {lugar}{fecha_larga(doc.fecha)}.',
                     CUERPO)


# ── Constancia de embarazo ────────────────────────────────────────────────────

class EmbarazoForm(DocumentoForm):
    edad_gestacional = forms.CharField(label='Edad gestacional', max_length=40,
                                       help_text='Calculada a hoy desde el último control; puedes corregirla.')
    metodo = forms.ChoiceField(label='Calculada por', choices=[('FUR', 'Fecha de última regla'),
                                                               ('ECO', 'Ecografía')])
    fpp = forms.DateField(label='Fecha probable de parto', widget=forms.DateInput(attrs={'type': 'date'}))
    evolucion = forms.CharField(label='Evolución', widget=_area(2))
    observaciones = forms.CharField(label='Observaciones (opcional)', required=False, widget=_area(2))


def inicial_embarazo(paciente, consulta):
    c = control_actual(paciente)
    if c is None:
        return {'evolucion': 'Embarazo de evolución satisfactoria a la fecha.'}
    return {'edad_gestacional': ob.texto_eg(c.eg_dias_en(timezone.localdate())).replace('sem', 'semanas')
            .replace(' d', ' días'), 'metodo': c.metodo_eg or 'FUR', 'fpp': c.fpp,
            'evolucion': 'Embarazo de evolución satisfactoria a la fecha.'}


def constancia_embarazo(doc, con_firma=True):
    d, paciente = doc.datos, doc.paciente
    cuerpo = lugar_y_fecha(doc.fecha, ciudad_de(doc)) + titulo('Constancia de embarazo', doc.tenant, doc.numero)
    ident = f', titular de la cédula {paciente.documento}' if paciente.numero_documento else ''
    fpp = ob.a_fecha(d.get('fpp'))
    por = 'fecha de última regla' if d.get('metodo') != 'ECO' else 'ecografía'
    cuerpo.append(Paragraph(
        f'{_quien(doc)}, hace constar que la paciente <b>{paciente.nombre_completo}</b>{ident}, de '
        f'{paciente.edad_texto}, se encuentra cursando un embarazo de <b>{d.get("edad_gestacional", "")}</b> de '
        f'gestación calculado por {por}, con fecha probable de parto el <b>{fpp:%d/%m/%Y}</b>.' if fpp else '', CUERPO))
    cuerpo += [Spacer(1, 2 * mm), Paragraph(f'<b>Evolución:</b> {d.get("evolucion", "")}', CUERPO)]
    if d.get('observaciones'):
        cuerpo += [Paragraph('<b>Observaciones:</b>', CUERPO)] + lineas(d['observaciones'])
    cuerpo += [Spacer(1, 4 * mm), _cierre(doc)]
    return construir(doc, cuerpo, con_firma=con_firma)


# ── Carnet de control prenatal ────────────────────────────────────────────────

def carnet_prenatal(doc, con_firma=True):
    paciente = doc.paciente
    actual = control_actual(paciente) or ControlPrenatal.objects.filter(paciente=paciente).order_by('-fecha').first()
    cuerpo = lugar_y_fecha(doc.fecha, ciudad_de(doc)) + titulo('Control prenatal', doc.tenant, doc.numero)
    cuerpo += datos_paciente(paciente)
    gineco = ficha(paciente, 'go.gineco')
    if actual is None:
        cuerpo.append(Paragraph('La paciente no tiene controles prenatales registrados.', CUERPO))
        return construir(doc, cuerpo, con_firma=con_firma)
    datos = [('Fórmula obstétrica', ob.formula(gineco) or '—'),
             ('Grupo sanguíneo', paciente.get_grupo_sanguineo_display() or '—'),
             ('FUR', f'{actual.fur:%d/%m/%Y}' if actual.fur else '—'),
             ('Ecografía de referencia', (f'{actual.eco_fecha:%d/%m/%Y} · {actual.eco_semanas} sem'
                                          + (f' {actual.eco_dias} d' if actual.eco_dias else ''))
              if actual.eco_fecha else '—'),
             ('FPP', f'{actual.fpp:%d/%m/%Y}' if actual.fpp else '—'),
             ('EG a la fecha', ob.texto_eg(actual.eg_dias_en(doc.fecha)) or '—')]
    cuerpo += seccion('Embarazo actual', doc.tenant) + tabla_datos(datos, columnas=3)
    desde = actual.fpp - timedelta(days=ob.POSTERMINO) if actual.fpp else None
    controles = ControlPrenatal.objects.filter(paciente=paciente).order_by('fecha')
    if desde:
        controles = controles.filter(fecha__gte=desde, fecha__lte=actual.fpp + timedelta(days=14))
    filas = [[Paragraph(f'<b>{t}</b>', ESTILO_CELDA) for t in
              ('Fecha', 'EG', 'Peso (kg)', 'TA', 'AU (cm)', 'FCF', 'Presentación', 'Edemas')]]
    for f in (_fila(c) for c in controles):
        c = f['c']
        filas.append([Paragraph(x, ESTILO_CELDA) for x in (
            f'{c.fecha:%d/%m/%Y}', c.eg_texto or '—', f'{f["peso"]:g}' if f['peso'] else '—',
            (f'<b>{f["pa"]}</b>' if f['alerta_pa'] else f['pa']) or '—',
            f'{c.altura_uterina:g}' if c.altura_uterina else '—', str(c.fcf or '—'),
            c.get_presentacion_display() or '—', c.get_edemas_display() or '—')])
    t = Table(filas, colWidths=[22 * mm, 20 * mm, 20 * mm, 20 * mm, 18 * mm, 16 * mm, 28 * mm, 18 * mm],
              repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), FONDO), ('GRID', (0, 0), (-1, -1), 0.3, LINEA),
                           ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]))
    cuerpo += seccion('Controles', doc.tenant) + [t]
    cuerpo += [Spacer(1, 2 * mm), Paragraph('EG = edad gestacional · TA = tensión arterial · AU = altura uterina · '
                                            'FCF = frecuencia cardíaca fetal. TA en negrita: ≥ 140/90.', CUERPO_ITEM)]
    return construir(doc, cuerpo, con_firma=con_firma)


DOCUMENTOS = [
    DocumentoDef('go_embarazo', 'Constancia de embarazo', prefijo='CEM', generar=constancia_embarazo,
                 formulario=EmbarazoForm, inicial=inicial_embarazo, icono='bi-heart', orden=60,
                 especialidad='ginecologia'),
    DocumentoDef('go_carnet', 'Carnet de control prenatal', prefijo='CPN', generar=carnet_prenatal,
                 icono='bi-journal-medical', orden=61, especialidad='ginecologia'),
]
