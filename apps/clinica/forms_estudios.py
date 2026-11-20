"""Alta controlada de un examen al catálogo del consultorio."""
from django import forms

from apps.core.forms import FormBase

from .models.consulta import EstudioCatalogo


class AltaEstudioForm(FormBase, forms.ModelForm):
    class Meta:
        model = EstudioCatalogo
        fields = ('nombre', 'categoria', 'descripcion')
        widgets = {'descripcion': forms.Textarea(attrs={'rows': 2})}

    def clean_nombre(self):
        nombre = ' '.join((self.cleaned_data.get('nombre') or '').split())
        if len(nombre) < 3:
            raise forms.ValidationError('El examen debe tener al menos tres caracteres.')
        return nombre
