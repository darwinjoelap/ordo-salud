from django import forms

from apps.core.forms import FormBase

FECHA = forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')
HORA = forms.TimeInput(attrs={'type': 'time'}, format='%H:%M')


def _area(filas=3):
    return forms.Textarea(attrs={'rows': filas})


class DocumentoForm(FormBase, forms.Form):
    """Base: todo documento puede llevar ciudad (para «Ciudad, fecha»). Recibe el paciente y la petición."""
    ciudad = forms.CharField(label='Ciudad', max_length=80, required=False)

    def __init__(self, *args, paciente=None, request=None, **kwargs):
        self.paciente, self.request = paciente, request
        super().__init__(*args, **kwargs)

    def datos(self):
        salida = {}
        for k, v in self.cleaned_data.items():
            if v in (None, ''):
                continue
            salida[k] = v.isoformat() if hasattr(v, 'isoformat') else v
        return salida


class InformeForm(DocumentoForm):
    dirigido_a = forms.CharField(label='Dirigido a (opcional)', max_length=150, required=False)
    introduccion = forms.CharField(label='Introducción (opcional)', required=False, widget=_area(2))
    conclusion = forms.CharField(label='Conclusión (opcional)', required=False, widget=_area(3))


class ReferenciaForm(DocumentoForm):
    dirigido_a = forms.CharField(label='Referido a (especialidad, médico o institución)', max_length=150)
    prioridad = forms.ChoiceField(label='Prioridad', required=False,
                                  choices=[('', '—'), ('Electiva', 'Electiva'), ('Prioritaria', 'Prioritaria'),
                                           ('Urgente', 'Urgente')])
    motivo = forms.CharField(label='Motivo de la referencia', widget=_area(3))
    resumen = forms.CharField(label='Resumen clínico', required=False, widget=_area(4))
    diagnosticos = forms.CharField(label='Impresión diagnóstica', required=False, widget=_area(2))
    tratamiento = forms.CharField(label='Tratamiento actual', required=False, widget=_area(2))
    antecedentes = forms.MultipleChoiceField(
        label='Antecedentes que se incluyen', required=False, widget=forms.CheckboxSelectMultiple,
        help_text='Marca solo lo que le sirve al colega que recibe la referencia.')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .generadores import antecedentes
        opciones = antecedentes.opciones(self.paciente, self.request.tenant) if self.paciente and self.request else []
        self.fields['antecedentes'].choices = opciones
        if not opciones:
            del self.fields['antecedentes']
        elif not self.is_bound:
            self.initial.setdefault('antecedentes', [c for c, _ in opciones])

    def datos(self):
        salida = super().datos()
        claves = salida.pop('antecedentes', [])
        if claves:
            from .generadores import antecedentes
            salida['antecedentes_texto'] = antecedentes.elegidos(self.paciente, self.request.tenant, claves)
        return salida


class ReposoForm(DocumentoForm):
    dias = forms.IntegerField(label='Días de reposo', min_value=1, max_value=365)
    desde = forms.DateField(label='Desde', widget=FECHA)
    diagnostico = forms.CharField(label='Diagnóstico', required=False, widget=_area(2))
    indicaciones = forms.CharField(label='Indicaciones (opcional)', required=False, widget=_area(2))


class ConstanciaForm(DocumentoForm):
    fecha_asistencia = forms.DateField(label='Fecha de la consulta', widget=FECHA)
    hora_desde = forms.TimeField(label='Desde', required=False, widget=HORA)
    hora_hasta = forms.TimeField(label='Hasta', required=False, widget=HORA)
    acompanante = forms.CharField(label='Acompañante (opcional)', max_length=150, required=False)
    observaciones = forms.CharField(label='Observaciones (opcional)', required=False, widget=_area(2))

    def clean(self):
        d = super().clean()
        if d.get('hora_desde') and d.get('hora_hasta') and d['hora_hasta'] <= d['hora_desde']:
            self.add_error('hora_hasta', 'Debe ser posterior a la hora de inicio.')
        return d


class AnularForm(forms.Form):
    motivo = forms.CharField(label='Motivo', max_length=200, min_length=3)


class HistoriaForm(DocumentoForm):
    """Historia clínica completa: datos, antecedentes, fichas y todas las consultas que el profesional puede ver."""
    desde = forms.DateField(label='Consultas desde (opcional)', required=False, widget=FECHA)
    hasta = forms.DateField(label='Hasta (opcional)', required=False, widget=FECHA)
    incluir_antecedentes = forms.BooleanField(label='Incluir antecedentes y fichas', required=False, initial=True)

    def datos(self):
        from django.utils import timezone

        from apps.clinica.selectors import consultas_visibles

        from .generadores import antecedentes
        salida = super().datos()
        desde, hasta = self.cleaned_data.get('desde'), self.cleaned_data.get('hasta')
        consultas = [c for c in consultas_visibles(self.request, self.paciente) if c.estado != 'ANULADA'
                     and (not desde or timezone.localtime(c.fecha_hora).date() >= desde)
                     and (not hasta or timezone.localtime(c.fecha_hora).date() <= hasta)]
        salida['consultas'] = [c.pk for c in sorted(consultas, key=lambda c: c.fecha_hora)]
        if self.cleaned_data.get('incluir_antecedentes'):
            salida['antecedentes_texto'] = antecedentes.bloques(self.paciente, self.request.tenant)
        salida.pop('incluir_antecedentes', None)
        return salida
