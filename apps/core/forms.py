"""Utilidades comunes de formularios (de Ordo)."""
from django import forms
from django.forms.models import apply_limit_choices_to_to_formfield

from .numeros import numero
from .tenancy import TenantModel, tenant_actual


class DecimalTolerante(forms.DecimalField):
    """Acepta 12,50 · 12.50 · 1.234,50 (lo que escribe la gente en Venezuela)."""

    def to_python(self, value):
        if value in self.empty_values:
            return None
        if isinstance(value, str):
            leido = numero(value)
            if leido is None:
                raise forms.ValidationError(self.error_messages['invalid'], code='invalid')
            value = str(leido)
        return super().to_python(value)


def decimales_tolerantes(form):
    """Cambia cada DecimalField por uno tolerante con caja de texto (el navegador no borra la coma)."""
    for campo in form.fields.values():
        if isinstance(campo, forms.DecimalField) and not isinstance(campo, DecimalTolerante):
            campo.__class__ = DecimalTolerante
            attrs = {k: v for k, v in campo.widget.attrs.items() if k not in ('step', 'min', 'max', 'type')}
            attrs.update({'inputmode': 'decimal', 'autocomplete': 'off'})
            campo.widget = forms.TextInput(attrs=attrs)
            campo.widget.is_localized = False


def aplicar_bootstrap(form):
    for campo in form.fields.values():
        w = campo.widget
        if isinstance(w, (forms.CheckboxInput,)):
            w.attrs.setdefault('class', 'form-check-input')
        elif isinstance(w, (forms.CheckboxSelectMultiple, forms.RadioSelect)):
            continue
        elif isinstance(w, (forms.Select, forms.SelectMultiple)):
            w.attrs.setdefault('class', 'form-select')
        else:
            w.attrs.setdefault('class', 'form-control')


class FormBase:
    """
    Mixin OBLIGATORIO para los formularios de Ordo Salud:
      1. Rehace los querysets de campos FK hacia modelos de tenant (Django los arma al importar,
         sin tenant activo, y quedarían vacíos).
      2. Aplica las clases de Bootstrap.
      3. Los decimales aceptan coma o punto.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        decimales_tolerantes(self)
        for campo in self.fields.values():
            if isinstance(campo, forms.ModelChoiceField) and issubclass(campo.queryset.model, TenantModel):
                campo.queryset = campo.queryset.model.objects.all()
                apply_limit_choices_to_to_formfield(campo)      # respeta limit_choices_to del modelo
        aplicar_bootstrap(self)


def validar_unico_en_tenant(form, campo, mensaje):
    """
    La unicidad es por tenant (UniqueConstraint con `tenant`), pero `tenant` no está en el formulario:
    se valida aquí para mostrar un error amable en vez de un IntegrityError.
    """
    valor = form.cleaned_data.get(campo)
    if valor in (None, ''):
        return valor
    modelo = form._meta.model
    qs = modelo.objects.filter(**{f'{campo}__iexact' if isinstance(valor, str) else campo: valor})
    if form.instance.pk:
        qs = qs.exclude(pk=form.instance.pk)
    if tenant_actual() is not None and qs.exists():
        raise forms.ValidationError(mensaje)
    return valor
