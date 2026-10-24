from django import forms

from apps.core.forms import FormBase, validar_unico_en_tenant
from apps.core.imagenes import validar_imagen

from .models import ConfiguracionTenant, Lugar

GRUPOS = {
    'identidad': ('Identidad', ['nombre_mostrar', 'rif', 'logo', 'color_primario']),
    'contacto': ('Contacto', ['direccion', 'telefono', 'email', 'whatsapp', 'mensaje_whatsapp']),
    'documentos': ('Documentos', ['membrete', 'pie_documentos']),
    'historia': ('Historia clínica', ['visibilidad_historia', 'medicos_ven_todos_pacientes', 'horas_edicion_consulta',
                                         'formula_sc']),
    'agenda': ('Agenda', ['hora_inicio_agenda', 'hora_fin_agenda', 'duracion_cita_min']),
}


class ConfiguracionForm(FormBase, forms.ModelForm):
    quitar_logo = forms.BooleanField(label='Quitar logo actual', required=False)
    quitar_membrete = forms.BooleanField(label='Quitar membrete actual', required=False)

    class Meta:
        model = ConfiguracionTenant
        fields = [c for _, campos in GRUPOS.values() for c in campos]
        widgets = {
            'direccion': forms.Textarea(attrs={'rows': 2}),
            'mensaje_whatsapp': forms.Textarea(attrs={'rows': 2}),
            'color_primario': forms.TextInput(attrs={'type': 'color', 'class': 'form-control form-control-color'}),
            'logo': forms.FileInput(attrs={'accept': 'image/png,image/jpeg'}),
            'membrete': forms.FileInput(attrs={'accept': 'image/png,image/jpeg'}),
            'hora_inicio_agenda': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'hora_fin_agenda': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
        }

    def grupos(self):
        return [(clave, titulo, [self[c] for c in campos]) for clave, (titulo, campos) in GRUPOS.items()]

    def _imagen(self, campo, etiqueta):
        archivo = self.cleaned_data.get(campo)
        if archivo and hasattr(archivo, 'content_type'):
            validar_imagen(archivo, etiqueta)
        return archivo

    def clean_logo(self):
        return self._imagen('logo', 'El logo')

    def clean_membrete(self):
        return self._imagen('membrete', 'El membrete')

    def clean_rif(self):
        return self.cleaned_data['rif'].strip().upper()

    def clean(self):
        datos = super().clean()
        ini, fin = datos.get('hora_inicio_agenda'), datos.get('hora_fin_agenda')
        if ini and fin and fin <= ini:
            self.add_error('hora_fin_agenda', 'El fin de la jornada debe ser posterior al inicio.')
        return datos

    def save(self, commit=True):
        config = super().save(commit=False)
        for campo in ('logo', 'membrete'):
            if self.cleaned_data.get(f'quitar_{campo}') and not self.files.get(campo):
                archivo = getattr(config, campo)
                if archivo:
                    archivo.delete(save=False)
        if commit:
            config.save()
        return config


class LugarForm(FormBase, forms.ModelForm):
    class Meta:
        model = Lugar
        fields = ['nombre', 'ciudad', 'direccion', 'telefono', 'orden', 'activo']

    def clean_nombre(self):
        return validar_unico_en_tenant(self, 'nombre', 'Ya hay un lugar con ese nombre.')
