"""Informe preoperatorio con el formato clínico común y bytes congelados al emitir."""
from xml.sax.saxutils import escape

from django.utils import timezone
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm

from apps.clinica.preoperatorio import CODIGO_INFORME, ESTADOS_METS

from .base import CUERPO, construir, lineas, lugar_y_fecha, nota_confidencial, seccion, tabla_datos, titulo


TEXTO = ParagraphStyle('preoperatorio_texto', parent=CUERPO, fontSize=10, leading=12)


def generar(doc, con_firma=True):
    informe = doc.informe_preoperatorio
    return bytes(informe.pdf_firmado if con_firma else informe.pdf_sin_firma)


def _campo(cuerpo, etiqueta, valor):
    if valor:
        cuerpo.extend(lineas(f'{etiqueta}: {valor}', estilo=TEXTO))


def _datos(pares):
    return tabla_datos([(etiqueta, escape(str(valor))) for etiqueta, valor in pares if valor])


def _seccion(titulo_seccion, tenant):
    elementos = seccion(titulo_seccion, tenant)
    elementos[0].height = 1.5 * mm
    elementos[-1].height = 1 * mm
    for elemento in elementos:
        elemento.keepWithNext = True
    return elementos


def renderizar(doc, evaluacion, valoracion, lectura, *, con_firma):
    tenant = doc.tenant
    consulta = doc.consulta
    datos = valoracion.datos
    revision = doc.datos['revision']
    cuerpo = titulo('Informe de evaluación preoperatoria', tenant, doc.numero)
    paciente = doc.paciente
    cuerpo += lugar_y_fecha(doc.fecha) + _datos([
        ('Paciente', paciente.nombre_completo), ('Documento', paciente.documento),
        ('Nacimiento', paciente.fecha_nacimiento.strftime('%d/%m/%Y') if paciente.fecha_nacimiento else ''),
        ('Sexo', paciente.get_sexo_display() if paciente.sexo else ''),
        ('Revisión', revision), ('Evaluación', timezone.localtime(consulta.fecha_hora).strftime('%d/%m/%Y')),
        ('Reemplaza a', doc.datos.get('reemplaza')),
    ])
    if valoracion.creado_por:
        _campo(cuerpo, 'Conclusión validada por',
               f'{valoracion.creado_por.nombre_visible} el {timezone.localtime(valoracion.creado_en):%d/%m/%Y}')

    cuerpo += _seccion('Cirugía prevista', tenant)
    _campo(cuerpo, 'Procedimiento', evaluacion.procedimiento)
    _campo(cuerpo, 'Diagnóstico o motivo', evaluacion.motivo)
    cuerpo += _datos([
        ('Carácter', evaluacion.get_caracter_display()),
        ('Fecha prevista', evaluacion.fecha_prevista.strftime('%d/%m/%Y') if evaluacion.fecha_prevista else ''),
        ('Cirujano', evaluacion.cirujano), ('Centro quirúrgico', evaluacion.centro),
        ('Anestesia', evaluacion.anestesia),
    ])

    cuerpo += _seccion('Valoración clínica', tenant)
    for item, filas in lectura:
        _campo(cuerpo, item['nombre'], '; '.join(f"{campo['etiqueta']}: {texto}" for campo, texto in filas))

    cuerpo += _seccion('Estudios complementarios', tenant)
    estudios = list(valoracion.estudios.all())
    if not estudios:
        cuerpo += lineas('Sin estudios consignados.')
    for estudio in estudios:
        fecha = f' · {estudio.fecha:%d/%m/%Y}' if estudio.fecha else ''
        _campo(cuerpo, f'{estudio.get_tipo_display()}{fecha}', estudio.resultado)
        _campo(cuerpo, 'Observaciones', estudio.observaciones)

    cuerpo += _seccion('ASA-PS y capacidad funcional', tenant)
    clase = f"ASA {datos['asa']}{'E' if datos.get('asa_emergencia') else ''}" if datos.get('asa') else 'No evaluada'
    estado_mets = dict(ESTADOS_METS).get(datos.get('mets_estado'), '')
    if datos.get('mets'):
        estado_mets += f" · {datos['mets'].replace('.', ',')} METS"
    fecha_mets = ''
    if datos.get('mets_fecha'):
        ano, mes, dia = datos['mets_fecha'].split('-')
        fecha_mets = f'{dia}/{mes}/{ano}'
    cuerpo += _datos([
        ('ASA-PS', clase), ('Cap. funcional', estado_mets),
        ('Método', datos.get('mets_metodo')), ('Fecha funcional', fecha_mets),
    ])
    if datos.get('asa'):
        cuerpo += lineas('Valoración clínica del profesional. Clasificación definitiva por anestesiología.',
                         estilo=TEXTO)
    _campo(cuerpo, 'Justificación ASA-PS', datos.get('asa_justificacion'))
    _campo(cuerpo, 'Observaciones de ASA-PS', datos.get('asa_observaciones'))
    _campo(cuerpo, 'Observaciones de capacidad funcional', datos.get('mets_observaciones'))

    cuerpo += _seccion('Conclusiones y recomendaciones', tenant)
    for clave, etiqueta in (
        ('riesgos', 'Hallazgos y riesgos'), ('recomendaciones', 'Recomendaciones'),
        ('pendientes', 'Estudios e interconsultas pendientes'), ('optimizacion', 'Optimización pendiente'),
        ('equipo_quirurgico', 'Cirugía y anestesiología'), ('conclusion', 'Conclusión clínica'),
    ):
        _campo(cuerpo, etiqueta, datos.get(clave))
    cuerpo += nota_confidencial()
    return construir(doc, cuerpo, con_firma=con_firma, titulo_pdf='Informe de evaluación preoperatoria')
