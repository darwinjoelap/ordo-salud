"""Campos quirúrgicos y secciones clínicas de la evaluación preoperatoria."""
from decimal import Decimal

from django import forms
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.core.excepciones import ErrorDeNegocio
from apps.core.forms import FormBase
from apps.core.permisos import puede_usar_preoperatorio

from .models.consulta import (
    Adjunto, Consulta, EstudioPreoperatorio, EvaluacionPreoperatoria, InformePreoperatorio, ValoracionPreoperatoria,
)


SECCIONES = ('nucleo.motivo', 'nucleo.antecedentes', 'nucleo.signos_vitales', 'nucleo.examen_fisico')


class CirugiaForm(FormBase, forms.ModelForm):
    class Meta:
        model = EvaluacionPreoperatoria
        fields = ('procedimiento', 'motivo', 'caracter', 'fecha_prevista', 'cirujano', 'centro', 'anestesia')
        widgets = {
            'fecha_prevista': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'motivo': forms.Textarea(attrs={'rows': 2}),
        }


def faltantes(evaluacion):
    return [evaluacion._meta.get_field(campo).verbose_name for campo in ('procedimiento', 'motivo', 'caracter')
            if not getattr(evaluacion, campo)]


CODIGO_INFORME = 'informe_preoperatorio'
ESTADOS_METS = [('NO_EVALUADO', 'No evaluado'), ('INSUFICIENTES', 'Datos insuficientes'), ('REGISTRADO', 'Registrado')]
CLASES_ASA = [(clase, f'ASA {clase}') for clase in ('I', 'II', 'III', 'IV', 'V', 'VI')]


def _fecha():
    return forms.DateField(required=False, widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}))


def _texto(etiqueta, *, requerido=False, max_length=3000):
    return forms.CharField(label=etiqueta, required=requerido, max_length=max_length,
                           widget=forms.Textarea(attrs={'rows': 2}))


class ValoracionForm(FormBase, forms.Form):
    version = forms.IntegerField(min_value=0, widget=forms.HiddenInput)
    motivo_enmienda = forms.CharField(label='Motivo de la enmienda', max_length=300, required=False)
    asa = forms.ChoiceField(label='Clase ASA-PS', choices=[('', 'No evaluada')] + CLASES_ASA, required=False)
    asa_emergencia = forms.BooleanField(label='Sufijo E (emergencia)', required=False)
    asa_justificacion = _texto('Justificación de ASA-PS')
    asa_observaciones = _texto('Observaciones de ASA-PS')
    mets_estado = forms.ChoiceField(label='Estado de la valoración funcional', choices=ESTADOS_METS)
    mets = forms.DecimalField(label='Capacidad funcional (METS)', min_value=Decimal('0.01'), max_digits=6,
                              decimal_places=2, required=False)
    mets_metodo = forms.CharField(label='Método de estimación o medición', max_length=200, required=False)
    mets_fecha = _fecha()
    mets_observaciones = _texto('Observaciones de capacidad funcional')
    riesgos = _texto('Resumen de hallazgos y riesgos')
    recomendaciones = _texto('Recomendaciones preoperatorias')
    pendientes = _texto('Estudios e interconsultas pendientes')
    optimizacion = _texto('Condiciones pendientes de optimización')
    equipo_quirurgico = _texto('Observaciones para cirugía y anestesiología')
    conclusion = _texto('Conclusión clínica')
    validada = forms.BooleanField(label='He revisado y valido esta conclusión clínica', required=False)

    def __init__(self, *args, enmienda=False, **kwargs):
        super().__init__(*args, **kwargs)
        if enmienda:
            self.fields['motivo_enmienda'].required = True
            self.fields['motivo_enmienda'].min_length = 5
            self.fields['validada'].required = True
        else:
            del self.fields['motivo_enmienda']

    def clean(self):
        datos = super().clean()
        if datos.get('asa') and not datos.get('asa_justificacion'):
            self.add_error('asa_justificacion', 'Documenta la justificación de la clase seleccionada.')
        if datos.get('asa_emergencia') and not datos.get('asa'):
            self.add_error('asa_emergencia', 'Selecciona una clase ASA-PS para usar el sufijo E.')
        if datos.get('mets_estado') == 'REGISTRADO':
            for campo in ('mets', 'mets_metodo', 'mets_fecha'):
                if datos.get(campo) is None or datos[campo] == '':
                    if campo not in self.errors:
                        self.add_error(campo, 'Completa este dato para registrar la capacidad funcional.')
        elif datos.get('mets') is not None:
            self.add_error('mets', 'Selecciona «Registrado» si vas a consignar un valor en METS.')
        if datos.get('validada') and not datos.get('conclusion'):
            self.add_error('conclusion', 'Escribe la conclusión clínica antes de validarla.')
        return datos

    def datos_clinicos(self):
        datos = {k: v for k, v in self.cleaned_data.items() if k not in ('version', 'motivo_enmienda')}
        datos['mets'] = str(datos['mets']) if datos['mets'] is not None else ''
        datos['mets_fecha'] = datos['mets_fecha'].isoformat() if datos['mets_fecha'] else ''
        return datos


class EstudioForm(FormBase, forms.Form):
    tipo = forms.ChoiceField(label='Tipo', choices=[('', 'Selecciona un tipo')] + EstudioPreoperatorio.Tipo.choices)
    fecha = _fecha()
    resultado = _texto('Resultado o hallazgo', requerido=True)
    observaciones = _texto('Observaciones', max_length=2000)
    adjuntos = forms.ModelMultipleChoiceField(label='Adjuntos existentes', queryset=Adjunto.objects.none(),
                                             required=False)

    def __init__(self, *args, adjuntos, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['adjuntos'].queryset = adjuntos


EstudiosFormSet = forms.formset_factory(EstudioForm, extra=1, can_delete=True, validate_max=True)


def adjuntos_visibles(consulta, membresia):
    from .consultas import puede_ver
    from apps.pacientes.selectors import puede_ver_paciente

    if not puede_ver_paciente(membresia, consulta.paciente):
        return Adjunto.objects.none()
    candidatos = Adjunto.objects.filter(paciente_id=consulta.paciente_id, tenant_id=consulta.tenant_id)
    ids = [a.pk for a in candidatos.select_related('consulta__tenant__configuracion', 'consulta__preoperatorio')
           if a.consulta_id is None or (a.consulta.tenant_id == consulta.tenant_id
                                      and a.consulta.paciente_id == consulta.paciente_id
                                      and puede_ver(membresia, a.consulta))]
    return candidatos.filter(pk__in=ids)


def puede_valorar(membresia, consulta):
    return (consulta.estado in (Consulta.Estado.BORRADOR, Consulta.Estado.CERRADA)
            and puede_usar_preoperatorio(membresia)
            and membresia.perfil_activo.pk == consulta.profesional_id)


def valoracion_actual(evaluacion):
    return evaluacion.valoraciones.first()


def datos_estudios(valoracion):
    if valoracion is None:
        return []
    return [{'tipo': e.tipo, 'fecha': e.fecha, 'resultado': e.resultado, 'observaciones': e.observaciones,
             'adjuntos': sorted(a.pk for a in e.adjuntos.all())}
            for e in valoracion.estudios.prefetch_related('adjuntos').all()]


@transaction.atomic
def guardar_valoracion(consulta, membresia, form, estudios):
    from .consultas import _bloquear_consulta

    consulta = _bloquear_consulta(consulta)
    if not puede_valorar(membresia, consulta):
        raise PermissionDenied
    evaluacion = consulta.preoperatorio
    actual = valoracion_actual(evaluacion)
    datos = form.datos_clinicos()
    motivo = form.cleaned_data.get('motivo_enmienda', '')
    if consulta.estado == Consulta.Estado.CERRADA and (not datos['validada'] or len(motivo) < 5):
        raise ErrorDeNegocio('Para corregir una consulta cerrada indica el motivo y valida la conclusión.')
    visibles = adjuntos_visibles(consulta, membresia)
    ids_permitidos = set(visibles.values_list('pk', flat=True))
    filas = [{**fila, 'adjuntos': sorted(a.pk for a in fila['adjuntos'])}
             for fila in estudios if fila and not fila['DELETE']]
    for fila in filas:
        fila.pop('DELETE')
        if not ids_permitidos.issuperset(fila['adjuntos']):
            raise PermissionDenied
    if actual and actual.datos == datos and datos_estudios(actual) == filas:
        return actual, False
    if (actual.pk if actual else 0) != form.cleaned_data['version']:
        raise ErrorDeNegocio('La valoración cambió. Abre la versión actual antes de volver a guardar.')
    version = ValoracionPreoperatoria.objects.create(evaluacion=evaluacion, datos=datos,
                                                     motivo_enmienda=motivo, creado_por=membresia.usuario)
    for fila in filas:
        ids = fila.pop('adjuntos')
        estudio = EstudioPreoperatorio.objects.create(valoracion=version, **fila)
        estudio.adjuntos.set(ids)
    return version, True


@transaction.atomic
def emitir_informe(consulta, membresia):
    from apps.documentos import servicios as documentos
    from apps.documentos.generadores import preoperatorio as pdf
    from .consultas import _bloquear_consulta, lectura

    consulta = _bloquear_consulta(consulta)
    if not puede_valorar(membresia, consulta):
        raise PermissionDenied
    if consulta.estado != Consulta.Estado.CERRADA:
        raise ErrorDeNegocio('Cierra la consulta antes de emitir el informe.')
    evaluacion = consulta.preoperatorio
    valoracion = valoracion_actual(evaluacion)
    if not valoracion or not valoracion.datos.get('validada'):
        raise ErrorDeNegocio('Valida la conclusión clínica antes de emitir el informe.')
    enmienda = consulta.enmiendas.aggregate(ultima=Max('pk'))['ultima']
    fuente = f'{valoracion.pk}:{enmienda or 0}'
    informes = evaluacion.informes.select_related('documento').defer('pdf_firmado', 'pdf_sin_firma')
    existente = informes.filter(fuente=fuente).first()
    if existente:
        return existente.documento, False
    previa = informes.first()
    revision = previa.revision + 1 if previa else 1
    doc = documentos.emitir(
        CODIGO_INFORME, paciente=consulta.paciente, profesional=consulta.profesional, consulta=consulta,
        datos={'revision': revision, 'valoracion': valoracion.pk, 'ultima_enmienda': enmienda,
               'reemplaza': previa.documento.numero if previa else ''},
    )
    secciones = lectura(consulta)
    InformePreoperatorio.objects.create(
        evaluacion=evaluacion, documento=doc, fuente=fuente, revision=revision,
        pdf_sin_firma=pdf.renderizar(doc, evaluacion, valoracion, secciones, con_firma=False),
        pdf_firmado=pdf.renderizar(doc, evaluacion, valoracion, secciones, con_firma=True),
    )
    return doc, True
