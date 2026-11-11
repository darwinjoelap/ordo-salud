from django import forms

from apps.core.forms import FormBase

from .models import AntecedenteBase, Paciente, Representante

FECHA = forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')


class PacienteForm(FormBase, forms.ModelForm):
    class Meta:
        model = Paciente
        fields = ['nombres', 'apellidos', 'sexo', 'fecha_nacimiento', 'tipo_documento', 'numero_documento',
                  'telefono', 'telefono_2', 'email', 'direccion', 'ciudad', 'ocupacion', 'estado_civil',
                  'nivel_instruccion', 'grupo_sanguineo', 'seguro', 'contacto_emergencia', 'referido_por', 'observaciones']
        widgets = {'fecha_nacimiento': FECHA, 'observaciones': forms.Textarea(attrs={'rows': 2}),
                   'telefono': forms.TextInput(attrs={'inputmode': 'tel'}),
                   'telefono_2': forms.TextInput(attrs={'inputmode': 'tel'}),
                   'numero_documento': forms.TextInput(attrs={'inputmode': 'numeric', 'autocomplete': 'off'})}

    def clean(self):
        datos = super().clean()
        numero = (datos.get('numero_documento') or '').strip()
        if not numero:                      # la cédula no es obligatoria (como en Pediae): sin número = sin documento
            datos['tipo_documento'] = Paciente.TipoDocumento.NINGUNO
            self.instance.tipo_documento = Paciente.TipoDocumento.NINGUNO
        if datos.get('tipo_documento') == Paciente.TipoDocumento.NINGUNO:
            datos['numero_documento'] = ''
        from django.utils import timezone
        fn = datos.get('fecha_nacimiento')
        if fn and fn > timezone.localdate():
            self.add_error('fecha_nacimiento', 'La fecha de nacimiento no puede ser futura.')
        return datos


class RepresentanteForm(FormBase, forms.ModelForm):
    class Meta:
        model = Representante
        fields = ['nombre', 'parentesco', 'tipo_documento', 'numero_documento', 'telefono', 'email', 'ocupacion',
                  'es_principal']
        widgets = {'telefono': forms.TextInput(attrs={'inputmode': 'tel'})}

    def __init__(self, *args, opcional=False, **kwargs):
        super().__init__(*args, **kwargs)
        if opcional:
            for campo in self.fields.values():
                campo.required = False


class AntecedenteBaseForm(FormBase, forms.ModelForm):
    class Meta:
        model = AntecedenteBase
        fields = ['alergias', 'medicacion_actual', 'enfermedades_cronicas', 'cirugias', 'hospitalizaciones',
                  'transfusiones', 'habitos', 'antecedentes_familiares', 'otros']
        widgets = {c: forms.Textarea(attrs={'rows': 2}) for c in fields}
