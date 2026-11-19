from django import forms

from apps.configuracion.whatsapp import numero_whatsapp
from apps.core.forms import FormBase

from .models import AntecedenteBase, Paciente, Representante

FECHA = forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')


class ContactoSeguimientoForm(FormBase, forms.ModelForm):
    permiso_whatsapp = forms.ChoiceField(
        label='Recordatorios de seguimiento por WhatsApp', required=False,
        choices=[('', 'Sin autorización registrada'), ('SI', 'Autorizado para este número'), ('NO', 'No contactar')],
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        preferencia = self.instance.whatsapp_seguimiento
        self.telefono_inicial = numero_whatsapp(self.instance.telefono)
        self.initial['permiso_whatsapp'] = (
            'NO' if preferencia == 'NO' else 'SI' if preferencia and preferencia == self.telefono_inicial else ''
        )

    def clean(self):
        datos = super().clean()
        telefono = numero_whatsapp(datos.get('telefono'))
        if self.add_prefix('permiso_whatsapp') not in self.data:
            # Los formularios anteriores pueden omitir la preferencia. Un cambio de teléfono invalida el permiso.
            if telefono != self.telefono_inicial and self.instance.whatsapp_seguimiento != 'NO':
                self.instance.whatsapp_seguimiento = ''
            return datos
        permiso = datos.get('permiso_whatsapp')
        if permiso == 'SI' and (not telefono or (
                self.initial['permiso_whatsapp'] == 'SI' and telefono != self.telefono_inicial)):
            self.add_error('permiso_whatsapp',
                           'Guarda primero el teléfono válido sin autorización y luego registra el permiso.')
        elif permiso is not None:
            self.instance.whatsapp_seguimiento = telefono if permiso == 'SI' else permiso
        return datos


class PacienteForm(ContactoSeguimientoForm):
    class Meta:
        model = Paciente
        fields = ['nombres', 'apellidos', 'sexo', 'fecha_nacimiento', 'tipo_documento', 'numero_documento',
                  'telefono', 'permiso_whatsapp', 'telefono_2', 'email', 'direccion', 'ciudad', 'ocupacion', 'estado_civil',
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


class RepresentanteForm(ContactoSeguimientoForm):
    class Meta:
        model = Representante
        fields = ['nombre', 'parentesco', 'tipo_documento', 'numero_documento', 'telefono',
                  'permiso_whatsapp', 'email', 'ocupacion', 'es_principal']
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
