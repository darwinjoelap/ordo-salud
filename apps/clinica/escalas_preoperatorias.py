"""Catálogo clínico, formularios y confirmación de resultados preoperatorios."""
import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django import forms
from django.core.signing import Signer
from django.utils import timezone
from django.utils.crypto import constant_time_compare

from apps.core.forms import FormBase

from . import reglas_preoperatorias as reglas


@dataclass(frozen=True)
class Campo:
    codigo: str
    etiqueta: str
    maximo: int | None = 0
    precision: int = 0
    opciones: tuple = ()
    ayuda: str = ''
    unidad: str = ''
    minimo: int | Decimal = 0

    def formulario(self):
        datos = {'label': self.etiqueta, 'required': False, 'help_text': self.ayuda}
        if self.maximo != 0:
            datos.update(min_value=self.minimo, max_value=self.maximo)
            if self.precision:
                return forms.DecimalField(**datos, max_digits=10, decimal_places=self.precision)
            return forms.IntegerField(**datos)
        opciones = self.opciones or (('si', 'Sí'), ('no', 'No'))
        return forms.ChoiceField(**datos, choices=(('', 'Sin confirmar'), *opciones,
                                                   ('discordante', 'Datos discordantes')))

    def mostrar(self, valor):
        if self.maximo != 0:
            texto = format(valor.normalize(), 'f').replace('.', ',') if isinstance(valor, Decimal) else str(valor)
            return f'{texto} {self.unidad}'.strip()
        return dict(self.opciones or (('si', 'Sí'), ('no', 'No')))[valor]


@dataclass(frozen=True)
class Escala:
    codigo: str
    nombre: str
    version: str
    fuente: str
    poblacion: str
    regla: object = None
    campos: tuple = ()
    edad_minima: int = 0
    restriccion: str = ''


EDAD = Campo('edad', 'Edad', 130, unidad='años')
EMERGENCIA = Campo('emergencia', 'Cirugía de emergencia')
RITMO = Campo('ritmo', 'Ritmo no sinusal o extrasístoles auriculares en el último ECG preoperatorio')
ESTADO_GENERAL = Campo(
    'estado_general', 'Mal estado general según el índice',
    ayuda='PaO₂ <60 o PaCO₂ >50 mmHg, K <3 o bicarbonato <20 mEq/L, BUN >50 o creatinina >3 mg/dL, '
          'AST anormal, signos de hepatopatía crónica o encamamiento por causa no cardíaca. '
          'Confirma «No» solo cuando puedas descartar el compuesto.',
)
INFARTO = Campo('infarto', 'Infarto previo', opciones=(
    ('no', 'Sin antecedente'), ('reciente', 'Hace menos de seis meses'), ('remoto', 'Hace más de seis meses'),
    ('limite', 'Hace seis meses exactos'),
))

ESCALAS = (
    Escala(
        'goldman', 'Goldman', '1977', 'https://pubmed.ncbi.nlm.nih.gov/904659/',
        'Índice histórico en mayores de 40 años con cirugía mayor no cardíaca.',
        reglas.goldman, edad_minima=41, campos=(
            EDAD, INFARTO, Campo('s3_yugular', 'Tercer ruido cardíaco o distensión yugular'),
            Campo('estenosis', 'Estenosis aórtica significativa'), RITMO,
            Campo('ectopia', 'Máximo de extrasístoles ventriculares documentadas antes de operar',
                  None, unidad='por minuto'),
            ESTADO_GENERAL, Campo('tipo_cirugia', 'Procedimiento intraperitoneal, intratorácico o aórtico'),
            EMERGENCIA,
        ),
    ),
    Escala(
        'detsky', 'Detsky', '1986', 'https://pubmed.ncbi.nlm.nih.gov/3778043/',
        'Índice histórico en adultos remitidos a evaluación antes de cirugía no cardíaca.',
        reglas.detsky, edad_minima=18, campos=(
            EDAD, INFARTO,
            Campo('angina_ccs', 'Clase CCS de angina en las dos semanas previas', opciones=(
                ('no', 'No cumple III ni IV'), ('III', 'III'), ('IV', 'IV'),
            )),
            Campo('inestable', 'Angina inestable en los tres meses previos'),
            Campo('edema', 'Edema pulmonar alveolar', opciones=(
                ('no', 'Sin antecedente'), ('reciente', 'Hace menos de una semana, confirmado por radiografía'),
                ('remoto', 'Hace más de una semana'), ('limite', 'Hace siete días exactos'),
            )),
            Campo('estenosis', 'Sospecha clínica de estenosis aórtica crítica'), RITMO,
            Campo('ectopia_o_tv_fv', 'Más de cinco extrasístoles ventriculares por minuto, o antecedente de TV o FV'),
            ESTADO_GENERAL, EMERGENCIA,
        ),
    ),
    Escala(
        'caprini', 'Caprini', 'RAM 2013 · Cronin 2019', 'https://doi.org/10.1177/1076029619838052',
        'Riesgo tromboembólico en adultos quirúrgicos. La interpretación depende de la población.',
        restriccion='Pendiente de autorización comercial para el material protegido y de resolver límites de puntuación.',
    ),
    Escala(
        'ariscat', 'ARISCAT', 'Canet 2010 · tablas 6 y 7', 'https://pubmed.ncbi.nlm.nih.gov/21045639/',
        'Adultos hospitalizados bajo anestesia general, neuraxial o regional. Excluye embarazo y obstetricia, '
        'anestesia exclusivamente local o de nervio periférico, cirugía ambulatoria o fuera de quirófano, '
        'trasplante, intubación previa y cirugía por una complicación de un procedimiento anterior.',
        reglas.ariscat, edad_minima=18, campos=(
            EDAD, Campo('spo2', 'SpO₂ preoperatoria (%)', 100, unidad='%', minimo=1),
            Campo('modo_spo2', 'Condiciones de oximetría', opciones=(
                ('aire_supino', 'Aire ambiente y decúbito supino'),
                ('otras', 'Oxígeno suplementario u otra condición'),
            )),
            Campo('infeccion', 'Infección respiratoria aguda en el mes previo',
                  ayuda='Considera infecciones altas o bajas con fiebre y tratamiento antibiótico según Canet.'),
            Campo('hb', 'Hemoglobina preoperatoria (g/dL)', None, 2, unidad='g/dL', minimo=Decimal('0.01')),
            Campo('incision', 'Sitio de la incisión', opciones=(
                ('periferica', 'Periférica'), ('superior', 'Abdominal superior'), ('intratoracica', 'Intratorácica'),
            )),
            Campo('duracion', 'Duración quirúrgica prevista (minutos)', None, unidad='min', minimo=1),
            EMERGENCIA,
        ),
    ),
    Escala(
        'rcri', 'RCRI de Lee', 'Lee 1999', 'https://escholarship.org/content/qt845640mb/qt845640mb.pdf',
        'Pacientes estables de 50 años o más con cirugía mayor no cardíaca no urgente e ingreso previsto de dos días o más.',
        reglas.rcri, edad_minima=50, campos=(
            EDAD, Campo('tipo_cirugia', 'Procedimiento intraperitoneal, intratorácico o vascular suprainguinal'),
            Campo('isquemica', 'Cardiopatía isquémica según Lee',
                  ayuda='Infarto, prueba de esfuerzo positiva, angina isquémica actual, nitratos u ondas Q patológicas. '
                        'La revascularización aislada no cumple el criterio.'),
            Campo('falla_cardiaca', 'Insuficiencia cardíaca según Lee',
                  ayuda='Antecedente de insuficiencia, edema pulmonar o disnea paroxística nocturna. '
                        'También estertores bilaterales, S3 o redistribución vascular pulmonar documentada.'),
            Campo('cerebrovascular', 'Antecedente de ACV o AIT'),
            Campo('insulina', 'Tratamiento con insulina para diabetes antes de la cirugía'),
            Campo('creatinina', 'Creatinina sérica preoperatoria (mg/dL)', None, 3, unidad='mg/dL',
                  minimo=Decimal('0.001')),
        ),
    ),
    Escala(
        'dasi', 'DASI', 'Hlatky 1989', 'https://pubmed.ncbi.nlm.nih.gov/2782256/',
        'Capacidad funcional autorreportada. La estimación DASI tiene procedencia distinta de los METS manuales.',
        restriccion='Pendiente de autorización electrónica comercial del cuestionario y de su versión en español.',
    ),
)

POR_CODIGO = {escala.codigo: escala for escala in ESCALAS}
AMBITO = Campo('ambito', 'La población descrita corresponde a este caso')
ESTADOS = {
    'no_evaluado': 'No evaluada',
    'no_aplica': 'No aplica',
    'datos_insuficientes': 'Datos insuficientes',
    'contradiccion': 'Datos discordantes',
    'regla_pendiente': 'Regla pendiente',
    'no_disponible': 'No disponible',
}


class EscalaForm(FormBase, forms.Form):
    def __init__(self, escala, datos=None, *, inicial=None):
        super().__init__(data=datos, initial=inicial, prefix=escala.codigo)
        self.escala = escala
        self.campos_clinicos = (AMBITO, *escala.campos)
        for campo in self.campos_clinicos:
            self.fields[campo.codigo] = campo.formulario()
        self.fields['fecha'] = forms.DateField(
            label='Fecha de valoración de los factores', required=False,
            widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control'}),
        )
        # Los campos se agregan después de inicializar el formulario.
        from apps.core.forms import aplicar_bootstrap, decimales_tolerantes
        decimales_tolerantes(self)
        aplicar_bootstrap(self)

    def calcular(self):
        if self.escala.restriccion:
            return reglas.Resultado('no_disponible', self.escala.restriccion)
        if not self.is_bound:
            return reglas.Resultado('no_evaluado')
        self.is_valid()
        datos = self.cleaned_data
        ambito, edad = datos.get('ambito'), datos.get('edad')
        if ambito == 'discordante':
            return reglas.Resultado('contradiccion', 'Aclara primero la población de aplicación.')
        if ambito == 'no' or (edad is not None and edad < self.escala.edad_minima):
            return reglas.Resultado('no_aplica', self.escala.poblacion)
        discordantes = [c.etiqueta for c in self.campos_clinicos if datos.get(c.codigo) == 'discordante']
        if discordantes:
            return reglas.Resultado('contradiccion', ', '.join(discordantes))
        faltan = [str(self.fields[k].label) for k in self.fields if datos.get(k) in (None, '')]
        if self.errors or faltan:
            return reglas.Resultado('datos_insuficientes', 'Completa o corrige: ' + ', '.join(faltan))
        if datos['fecha'] > timezone.localdate():
            return reglas.Resultado('contradiccion', 'La fecha de valoración está en el futuro.')
        return self.escala.regla(datos)

    def insumos(self):
        valores = {}
        for clave, valor in self.cleaned_data.items():
            if isinstance(valor, date):
                valor = valor.isoformat()
            elif isinstance(valor, Decimal):
                valor = format(valor.normalize(), 'f')
            valores[clave] = valor
        return valores

    def desglose(self, resultado):
        return [
            {'factor': campo.etiqueta, 'valor': campo.mostrar(self.cleaned_data[campo.codigo]),
             'puntos': resultado.puntos.get(campo.codigo)}
            for campo in self.campos_clinicos
        ]


def confirmados(valoracion):
    return valoracion.datos.get('escalas_preoperatorias', {}) if valoracion else {}


def _problema_quirurgico(consulta, codigo, datos):
    caracter = consulta.preoperatorio.caracter
    if codigo == 'rcri' and caracter in ('URGENTE', 'EMERGENCIA'):
        return reglas.Resultado('no_aplica', 'Lee 1999 se desarrolló en cirugía mayor no cardíaca no urgente.')
    emergencia = datos.get('emergencia')
    if (emergencia, caracter) in (('no', 'EMERGENCIA'), ('si', 'ELECTIVA')):
        return reglas.Resultado('contradiccion', 'La emergencia indicada difiere del carácter de la cirugía prevista.')
    return None


def para_informe(consulta, valoracion):
    return [resultado for codigo, resultado in confirmados(valoracion).items()
            if _problema_quirurgico(consulta, codigo, resultado['insumos']) is None]


def para_historia(consulta, valoracion):
    resultados = []
    for codigo, resultado in confirmados(valoracion).items():
        problema = _problema_quirurgico(consulta, codigo, resultado['insumos'])
        resultados.append({**resultado, 'aviso_contexto': problema.motivo if problema else ''})
    return resultados


def _firma(consulta, usuario, version, form, resultado):
    escala = form.escala
    contenido = json.dumps({
        'version': escala.version, 'insumos': form.insumos(), 'total': str(resultado.total),
        'clase': resultado.clase, 'puntos': resultado.puntos, 'fuente': escala.fuente,
        'interpretacion': resultado.interpretacion,
    }, sort_keys=True, separators=(',', ':'))
    huella = hashlib.sha256(contenido.encode()).hexdigest()
    contexto = f'preoperatorio.escala.{consulta.tenant_id}.{consulta.pk}.{usuario.pk}.{version}.{escala.codigo}'
    return Signer(salt=contexto).sign(huella)


def tarjeta(escala, consulta, usuario, version, *, datos=None, anterior=None):
    if escala.restriccion:
        return {'escala': escala, 'estado': ESTADOS['no_disponible'], 'motivo': escala.restriccion}
    inicial = (anterior or {}).get('insumos', {'fecha': timezone.localdate()})
    form = EscalaForm(escala, datos, inicial=inicial)
    resultado = form.calcular()
    if form.is_bound:
        problema = _problema_quirurgico(consulta, escala.codigo, form.cleaned_data)
        if problema:
            resultado = problema
    salida = {'escala': escala, 'form_escala': form, 'resultado': resultado, 'anterior': anterior,
              'estado': ESTADOS.get(resultado.estado), 'motivo': resultado.motivo,
              'parametros': ','.join(form.add_prefix(campo) for campo in form.fields)}
    if resultado.estado == 'evaluado':
        salida['factores'] = form.desglose(resultado)
        salida['firma'] = _firma(consulta, usuario, version, form, resultado)
    return salida


def preparar_confirmaciones(datos, consulta, usuario, version):
    seleccionadas = {escala.codigo for escala in ESCALAS if datos.get(f'{escala.codigo}-confirmar') == '1'}
    cambios, errores = {}, {}
    for codigo in seleccionadas:
        escala = POR_CODIGO[codigo]
        vista = tarjeta(escala, consulta, usuario, version, datos=datos)
        firma = datos.get(f'{codigo}-firma', '')
        if 'firma' not in vista or not constant_time_compare(vista['firma'], firma):
            errores[codigo] = 'Recalcula y revisa el resultado antes de confirmar.'
            continue
        resultado = vista['resultado']
        fecha = timezone.localdate()
        cambios[codigo] = {
            'nombre': escala.nombre, 'version': escala.version, 'fuente': escala.fuente,
            'insumos': vista['form_escala'].insumos(), 'factores': vista['factores'],
            'puntaje': str(resultado.total), 'clase': resultado.clase, 'interpretacion': resultado.interpretacion,
            'fecha_evaluacion': vista['form_escala'].cleaned_data['fecha'].strftime('%d/%m/%Y'),
            'fecha_confirmacion': fecha.strftime('%d/%m/%Y'),
            'autor_id': usuario.pk, 'autor': usuario.nombre_visible,
        }
    return cambios, errores
