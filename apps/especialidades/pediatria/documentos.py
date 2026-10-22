"""
Documentos de pediatría (textos de Pediae `pacientes/constancias_pdf.py`, con el diseño de Ordo Salud: encabezado del
médico, logo tenue y firma/sello fijos al pie). Mejoras: el diagnóstico nutricional y el estado de vacunas salen de
los datos reales (en Pediae la constancia de niño sano decía «Eutrófico» siempre) y la médica puede corregirlos.
"""
from django import forms
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Spacer, Table, TableStyle

from apps.core.pdf import ESTILO_CELDA, Paragraph
from apps.documentos.forms import DocumentoForm, _area
from apps.documentos.generadores.base import (
    ANCHO,
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
from apps.documentos.generadores.clinicos import _el_la, _quien, ciudad_de, en_letras
from apps.documentos.registro import DocumentoDef

from . import curvas, vacunas
from .models import MedicionCrecimiento

EXAMEN_NINO_SANO = ('Paciente en excelentes condiciones generales, activo, reactivo, con un desarrollo psicomotor '
                    'adecuado para su edad cronológica. Sistema cardiopulmonar, abdominal y neurológico normales.')


def _ultima_medicion(paciente):
    return MedicionCrecimiento.objects.filter(paciente=paciente).order_by('-fecha', '-pk').first()


def _nino(paciente):
    return 'la niña' if paciente.sexo == 'F' else 'el niño'


def _cierre(doc):
    ciudad = ciudad_de(doc)
    lugar = f'en la ciudad de {ciudad}, ' if ciudad else ''
    return Paragraph(f'Se expide la presente a petición de la parte interesada, {lugar}{fecha_larga(doc.fecha)}.',
                     CUERPO)


# ── Constancia de niño sano ───────────────────────────────────────────────────

class NinoSanoForm(DocumentoForm):
    examen = forms.CharField(label='Examen físico', widget=_area(3))
    diagnostico_nutricional = forms.CharField(label='Diagnóstico nutricional', max_length=200)
    vacunas = forms.ChoiceField(label='Inmunizaciones', choices=[
        ('COMPLETO', 'Esquema completo y al día'), ('PENDIENTE', 'Presenta dosis pendientes'),
        ('', 'No mencionar')], required=False)
    conclusion = forms.CharField(label='Conclusión', widget=_area(2))


def inicial_nino_sano(paciente, consulta):
    m = _ultima_medicion(paciente)
    if m and m.estado_nutricional:
        nutricional = f'{m.estado_nutricional.split(" (")[0]}. Peso y talla evaluados con las curvas de la OMS.'
    else:
        nutricional = 'Normopeso (eutrófico), con crecimiento armónico para su edad y sexo.'
    return {'examen': EXAMEN_NINO_SANO, 'diagnostico_nutricional': nutricional,
            'vacunas': 'COMPLETO' if vacunas.resumen(paciente)['al_dia'] else 'PENDIENTE',
            'conclusion': f'Se concluye que {_nino(paciente)} se encuentra clínicamente SANO, sin evidencia de '
                          'patologías agudas o crónicas al momento de la evaluación.'}


def nino_sano(doc, con_firma=True):
    d, paciente = doc.datos, doc.paciente
    m = _ultima_medicion(paciente)
    cuerpo = lugar_y_fecha(doc.fecha, ciudad_de(doc)) + titulo('Constancia de niño sano', doc.tenant, doc.numero)
    articulo, o = _el_la(paciente)
    nacimiento = f' (fecha de nacimiento: {paciente.fecha_nacimiento:%d/%m/%Y})' if paciente.fecha_nacimiento else ''
    cuerpo.append(Paragraph(
        f'{_quien(doc)}, hace constar que {articulo} paciente <b>{paciente.nombre_completo}</b>, de '
        f'{paciente.edad_texto}{nacimiento}, fue evaluad{o} clínicamente en el marco de la consulta de control de '
        'niño sano, obteniéndose los siguientes datos antropométricos:', CUERPO))
    if m:
        datos = [('Peso', f'{m.peso_kg:g} kg' + (f' (P{m.p_peso:g})' if m.p_peso is not None else '')
                  if m.peso_kg else ''),
                 ('Talla', f'{m.talla_cm:g} cm' + (f' (P{m.p_talla:g})' if m.p_talla is not None else '')
                  if m.talla_cm else ''),
                 ('Medido el', f'{m.fecha:%d/%m/%Y}')]
        cuerpo += [Spacer(1, 2 * mm)] + tabla_datos(datos, columnas=3)
    cuerpo += [Spacer(1, 3 * mm), Paragraph('<b>Evaluación y diagnóstico:</b>', CUERPO),
               Paragraph(f"<b>1. Examen físico:</b> {d.get('examen', '')}", CUERPO_ITEM),
               Paragraph(f"<b>2. Diagnóstico nutricional:</b> {d.get('diagnostico_nutricional', '')}", CUERPO_ITEM)]
    if d.get('vacunas'):
        estado = ('se encuentra <b>completo y al día</b>' if d['vacunas'] == 'COMPLETO'
                  else 'presenta <b>dosis pendientes</b>')
        cuerpo.append(Paragraph('<b>3. Inmunizaciones:</b> Posterior a la revisión de la tarjeta de vacunación, se '
                                f'constata que el esquema de inmunizaciones {estado} para su edad.', CUERPO_ITEM))
    cuerpo += [Spacer(1, 3 * mm), Paragraph('<b>Conclusión:</b>', CUERPO)] + lineas(d.get('conclusion', ''))
    cuerpo += [Spacer(1, 4 * mm), _cierre(doc)]
    return construir(doc, cuerpo, con_firma=con_firma)


# ── Lactancia ─────────────────────────────────────────────────────────────────

class LactanciaForm(DocumentoForm):
    meses = forms.IntegerField(label='Meses de lactancia materna exclusiva', min_value=1, max_value=36)


def inicial_lactancia(paciente, consulta):
    from apps.clinica.models import RegistroSeccionPaciente
    ficha = RegistroSeccionPaciente.objects.filter(paciente=paciente, seccion__codigo='ped.alimentacion',
                                                   vigente=True).first()
    return {'meses': (ficha.datos.get('lme_meses') if ficha else None) or 6}


def lactancia(doc, con_firma=True):
    paciente, meses = doc.paciente, int(doc.datos.get('meses') or 6)
    nino = _nino(paciente)
    nacio = f', quien nació el {paciente.fecha_nacimiento:%d/%m/%Y},' if paciente.fecha_nacimiento else ''
    cuerpo = lugar_y_fecha(doc.fecha, ciudad_de(doc)) + titulo('Certificado de lactancia materna exclusiva',
                                                                doc.tenant, doc.numero)
    cuerpo += [Paragraph(
        f'Por medio de la presente se certifica con orgullo que {nino} <b>{paciente.nombre_completo}</b>{nacio} ha '
        f'recibido <b>lactancia materna exclusiva</b> durante sus primeros <b>{en_letras(meses)} ({meses}) meses</b> '
        'de vida, de acuerdo con las recomendaciones de la Organización Mundial de la Salud (OMS) y UNICEF.', CUERPO),
        Spacer(1, 3 * mm),
        Paragraph('La lactancia materna exclusiva es uno de los actos más significativos en el desarrollo y la '
                  'protección de la salud de un niño o niña: aporta todos los nutrientes necesarios, anticuerpos y el '
                  'vínculo afectivo esencial para su crecimiento integral.', CUERPO),
        Spacer(1, 3 * mm),
        Paragraph('En reconocimiento a este logro compartido, se otorga el presente certificado como testimonio del '
                  f'compromiso y la dedicación hacia la salud y el bienestar de {nino} '
                  f'<b>{paciente.nombre_completo}</b>.', CUERPO),
        Spacer(1, 4 * mm), _cierre(doc)]
    return construir(doc, cuerpo, con_firma=con_firma)


class LactanciaTrabajoForm(DocumentoForm):
    nombre_madre = forms.CharField(label='Nombre de la madre', max_length=150, required=False)
    cedula_madre = forms.CharField(label='Cédula de la madre', max_length=20, required=False)
    texto = forms.CharField(label='Indicación', widget=_area(3))


def inicial_lactancia_trabajo(paciente, consulta):
    madre = next((r for r in paciente.representantes.all() if r.parentesco == 'MADRE'), None)
    return {'nombre_madre': madre.nombre if madre else '', 'cedula_madre': madre.documento if madre and
            madre.numero_documento else '',
            'texto': 'Paciente quien actualmente recibe lactancia materna + alimentación complementaria, por lo que '
                     'se indica dar continuidad a la misma, agradeciendo de antemano la colaboración para su '
                     'cumplimiento.'}


def lactancia_trabajo(doc, con_firma=True):
    d, paciente = doc.datos, doc.paciente
    m = _ultima_medicion(paciente)
    cuerpo = lugar_y_fecha(doc.fecha, ciudad_de(doc)) + titulo('Constancia de lactancia materna', doc.tenant,
                                                                doc.numero)
    cuerpo += tabla_datos([('Paciente', f'<b>{paciente.nombre_completo}</b>'), ('Edad', paciente.edad_texto),
                           ('Peso', f'{m.peso_kg:g} kg' if m and m.peso_kg else ''),
                           ('Talla', f'{m.talla_cm:g} cm' if m and m.talla_cm else '')])
    cuerpo += [Spacer(1, 5 * mm)] + lineas(d.get('texto', '')) + [Spacer(1, 5 * mm)]
    ciudad = ciudad_de(doc)
    lugar = f', {ciudad}' if ciudad else ''
    if d.get('nombre_madre'):
        ci = f", C.I. <b>{d['cedula_madre']}</b>" if d.get('cedula_madre') else ''
        cuerpo.append(Paragraph(f"Constancia que se expide a petición de su madre <b>{d['nombre_madre']}</b>{ci}"
                                f'{lugar}, {fecha_larga(doc.fecha)}.', CUERPO))
    else:
        cuerpo.append(_cierre(doc))
    return construir(doc, cuerpo, con_firma=con_firma)


# ── Esquema de vacunación ─────────────────────────────────────────────────────

def esquema_vacunas(doc, con_firma=True):
    paciente = doc.paciente
    cuerpo = lugar_y_fecha(doc.fecha, ciudad_de(doc)) + titulo('Esquema de vacunación', doc.tenant, doc.numero)
    cuerpo += datos_paciente(paciente)
    for grupo in vacunas.por_grupos(vacunas.esquema(paciente)):
        filas = [[Paragraph(f'<b>{t}</b>', ESTILO_CELDA) for t in ('Vacuna', 'Dosis', 'Edad', 'Estado', 'Fecha',
                                                                    'Lote')]]
        for f in grupo['vacunas']:
            v = f['vacuna']
            aplicaciones = f['historial'] if v.anual else ([f['aplicada']] if f['aplicada'] else [])
            fechas = ', '.join(a.fecha.strftime('%d/%m/%Y') if a.fecha else 'sin fecha' for a in aplicaciones)
            lotes = ', '.join(a.lote for a in aplicaciones if a.lote)
            filas.append([Paragraph(v.nombre, ESTILO_CELDA), Paragraph(str(v.dosis), ESTILO_CELDA),
                          Paragraph(v.edad_texto, ESTILO_CELDA), Paragraph(f['texto'], ESTILO_CELDA),
                          Paragraph(fechas or '—', ESTILO_CELDA), Paragraph(lotes or '—', ESTILO_CELDA)])
        t = Table(filas, colWidths=[52 * mm, 14 * mm, 24 * mm, 26 * mm, 38 * mm, 32 * mm], repeatRows=1)
        t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), FONDO), ('GRID', (0, 0), (-1, -1), 0.3, LINEA),
                               ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('TOPPADDING', (0, 0), (-1, -1), 2),
                               ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]))
        cuerpo.append(KeepTogether(seccion(grupo['nombre'], doc.tenant) + [t]))
    pesq = [p for p in vacunas.pesquisas(paciente) if p['realizada']]
    if pesq:
        cuerpo += seccion('Pesquisas', doc.tenant)
        cuerpo += tabla_datos([(p['pesquisa'].nombre, (f"{p['realizada'].fecha:%d/%m/%Y} " if p['realizada'].fecha
                                                       else '') + p['realizada'].resultado) for p in pesq])
    return construir(doc, cuerpo, con_firma=con_firma)


# ── Curvas de crecimiento ─────────────────────────────────────────────────────

class CurvasForm(DocumentoForm):
    indicadores = forms.MultipleChoiceField(
        label='Curvas', widget=forms.CheckboxSelectMultiple, initial=['peso', 'talla', 'pc'],
        choices=[(k, v['titulo']) for k, v in curvas.INDICADORES.items()])


def inicial_curvas(paciente, consulta):
    return {'indicadores': ['peso', 'talla', 'pc'] if (paciente.edad_anios or 0) < 5 else ['peso', 'talla', 'imc']}


def datos_nacimiento(paciente):
    from apps.clinica.models import RegistroSeccionPaciente
    r = RegistroSeccionPaciente.objects.filter(paciente=paciente, seccion__codigo='ped.perinatales',
                                               vigente=True).first()
    return r.datos if r else {}


def curvas_pdf(doc, con_firma=True):
    paciente = doc.paciente
    mediciones = list(MedicionCrecimiento.objects.filter(paciente=paciente).order_by('fecha'))
    nacimiento = datos_nacimiento(paciente)
    cuerpo = lugar_y_fecha(doc.fecha, ciudad_de(doc)) + titulo('Curvas de crecimiento (OMS)', doc.tenant,
                                                                doc.numero)
    cuerpo += datos_paciente(paciente)
    if not paciente.sexo:
        cuerpo.append(Paragraph('Falta el sexo del paciente: sin él no se pueden dibujar las curvas.', CUERPO))
    for ind in doc.datos.get('indicadores') or ['peso', 'talla']:
        puntos = curvas.puntos_del_paciente(paciente, ind, mediciones, nacimiento)
        g = curvas.geometria(ind, paciente.sexo, puntos) if paciente.sexo else None
        if g is None:
            continue
        cuerpo.append(KeepTogether(seccion(g['titulo'], doc.tenant) + [curvas.dibujo_pdf(g, escala=ANCHO / 760)]))
    if mediciones:
        filas = [[Paragraph(f'<b>{t}</b>', ESTILO_CELDA) for t in
                  ('Fecha', 'Edad', 'Peso (kg)', 'Talla (cm)', 'PC (cm)', 'IMC', 'Estado nutricional')]]
        for m in mediciones:
            meses = float(m.edad_meses or 0)
            edad = f'{int(meses // 12)}a {int(meses % 12)}m' if meses >= 24 else f'{meses:.1f} m'
            filas.append([Paragraph(x, ESTILO_CELDA) for x in (
                m.fecha.strftime('%d/%m/%Y'), edad, _con_p(m.peso_kg, m.p_peso), _con_p(m.talla_cm, m.p_talla),
                _con_p(m.pc_cm, m.p_pc), _con_p(m.imc, m.p_imc), m.estado_nutricional or '—')])
        t = Table(filas, colWidths=[22 * mm, 18 * mm, 26 * mm, 26 * mm, 24 * mm, 24 * mm, 46 * mm], repeatRows=1)
        t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), FONDO), ('GRID', (0, 0), (-1, -1), 0.3, LINEA),
                               ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]))
        cuerpo += seccion('Mediciones', doc.tenant) + [t]
    cuerpo += [Spacer(1, 2 * mm), Paragraph('Patrones de crecimiento infantil OMS (2006) y referencia OMS 2007 '
                                            '(5–19 años). P = percentil.', CUERPO_ITEM)]
    return construir(doc, cuerpo, con_firma=con_firma)


def _con_p(valor, p):
    if valor is None:
        return '—'
    return f'{valor:g}' + (f' (P{p:g})' if p is not None else '')


DOCUMENTOS = [
    DocumentoDef('ped_nino_sano', 'Constancia de niño sano', prefijo='CNS', generar=nino_sano,
                 formulario=NinoSanoForm, inicial=inicial_nino_sano, icono='bi-emoji-smile', orden=60,
                 especialidad='pediatria'),
    DocumentoDef('ped_lactancia', 'Certificado de lactancia materna', prefijo='CLM', generar=lactancia,
                 formulario=LactanciaForm, inicial=inicial_lactancia, icono='bi-award', orden=61,
                 especialidad='pediatria'),
    DocumentoDef('ped_lactancia_trabajo', 'Constancia de lactancia (trabajo)', prefijo='CLT',
                 generar=lactancia_trabajo, formulario=LactanciaTrabajoForm, inicial=inicial_lactancia_trabajo,
                 icono='bi-briefcase', orden=62, especialidad='pediatria'),
    DocumentoDef('ped_vacunas', 'Esquema de vacunación', prefijo='VAC', generar=esquema_vacunas,
                 icono='bi-shield-plus', orden=63, especialidad='pediatria'),
    DocumentoDef('ped_curvas', 'Curvas de crecimiento', prefijo='CRV', generar=curvas_pdf, formulario=CurvasForm,
                 inicial=inicial_curvas, icono='bi-graph-up', orden=64, especialidad='pediatria'),
]

