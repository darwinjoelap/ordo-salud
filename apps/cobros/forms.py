from django import forms

from apps.core.forms import FormBase, validar_unico_en_tenant

from .models import Servicio


class ServicioForm(FormBase, forms.ModelForm):
    class Meta:
        model = Servicio
        fields = ['nombre', 'descripcion', 'especialidad', 'precio_usd', 'costo_usd', 'activo']

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['especialidad'].queryset = tenant.especialidades.all()
        self.fields['especialidad'].empty_label = 'Cualquier especialidad'

    def clean_nombre(self):
        return validar_unico_en_tenant(self, 'nombre', 'Ya hay un servicio con ese nombre.')


from apps.core.forms import DecimalTolerante  # noqa: E402

from .models import Pago  # noqa: E402


class CargoForm(FormBase, forms.Form):
    servicio = forms.ModelChoiceField(label='Servicio', queryset=Servicio.objects.none(), required=False,
                                      empty_label='Otro concepto')
    descripcion = forms.CharField(label='Concepto', max_length=200, required=False)
    precio_usd = DecimalTolerante(label='Precio (USD)', max_digits=10, decimal_places=2, required=False)
    descuento_usd = DecimalTolerante(label='Descuento (USD)', max_digits=10, decimal_places=2, required=False)
    exonerado = forms.BooleanField(label='Exonerado (no se cobra)', required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['servicio'].queryset = Servicio.objects.filter(activo=True)

    def clean(self):
        d = super().clean()
        if not d.get('servicio') and not d.get('descripcion'):
            self.add_error('descripcion', 'Elige un servicio o escribe el concepto.')
        if d.get('precio_usd') is None:
            if d.get('servicio'):
                d['precio_usd'] = d['servicio'].precio_usd
            else:
                self.add_error('precio_usd', 'Indica el precio.')
        return d


class PagoForm(FormBase, forms.Form):
    monto = DecimalTolerante(label='Monto', max_digits=14, decimal_places=2)
    moneda = forms.ChoiceField(label='Moneda', choices=Pago.Moneda.choices)
    metodo = forms.ChoiceField(label='Método', choices=Pago.Metodo.choices)
    referencia = forms.CharField(label='Referencia', max_length=60, required=False)
    notas = forms.CharField(label='Notas', max_length=200, required=False)


class CobroRapidoForm(PagoForm):
    notas = None
    confirmacion = forms.CharField(widget=forms.HiddenInput, max_length=1500)
    recibido = forms.BooleanField(label='Confirmo que recibí este pago')
