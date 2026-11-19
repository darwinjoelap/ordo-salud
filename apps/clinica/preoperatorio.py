"""Campos quirúrgicos y secciones clínicas de la evaluación preoperatoria."""
from django import forms

from apps.core.forms import FormBase

from .models.consulta import EvaluacionPreoperatoria


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
