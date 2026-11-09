from django import forms
from django.contrib.auth.validators import UnicodeUsernameValidator

from apps.core.forms import FormBase
from apps.equipo.models import PerfilProfesional

from .models import Especialidad, Plan, Tenant


class _TenantBase(FormBase, forms.Form):
    nombre = forms.CharField(label='Nombre del consultorio o clínica', max_length=150)
    slug = forms.CharField(label='Enlace', max_length=40,
                           help_text='Queda como https://<dominio>/<enlace>/ — minúsculas, números y guiones.')
    plan = forms.ModelChoiceField(label='Plan', queryset=Plan.objects.filter(activo=True), required=False)
    activo_hasta = forms.DateField(label='Pagado / activo hasta', required=False,
                                   widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
                                   help_text='Vacío = sin vencimiento.')
    especialidades = forms.ModelMultipleChoiceField(label='Especialidades habilitadas', required=False,
                                                    queryset=Especialidad.objects.filter(activa=True),
                                                    widget=forms.CheckboxSelectMultiple)
    notas = forms.CharField(label='Notas internas', required=False, widget=forms.Textarea(attrs={'rows': 2}))

    def __init__(self, *args, tenant=None, **kwargs):
        self.tenant = tenant
        super().__init__(*args, **kwargs)

    def clean_slug(self):
        from .servicios import validar_enlace
        return validar_enlace(self.cleaned_data['slug'], excluir_pk=self.tenant.pk if self.tenant else None)


class NuevoTenantForm(_TenantBase):
    usuario_titular = forms.CharField(label='Usuario del Titular', max_length=60,
                                      validators=[UnicodeUsernameValidator()])
    nombre_titular = forms.CharField(label='Nombre del Titular', max_length=150)
    apellido_titular = forms.CharField(label='Apellido del Titular', max_length=150)
    email_titular = forms.EmailField(label='Correo del Titular (opcional)', required=False)
    titular_es_profesional = forms.BooleanField(label='El Titular atiende pacientes', required=False, initial=True)
    especialidad_titular = forms.ModelChoiceField(label='Especialidad del Titular', required=False,
                                                  queryset=Especialidad.objects.filter(activa=True))
    titulo_titular = forms.ChoiceField(label='Título', choices=PerfilProfesional.Titulo.choices, initial='Dra.',
                                       required=False)

    def clean(self):
        datos = super().clean()
        if datos.get('titular_es_profesional') and not datos.get('especialidad_titular'):
            self.add_error('especialidad_titular', 'Indica la especialidad del Titular.')
        return datos


class EditarTenantForm(_TenantBase):
    estado = forms.ChoiceField(label='Estado', choices=Tenant.Estado.choices)
    limite_usuarios = forms.IntegerField(label='Límite de usuarios', required=False, min_value=1,
                                         help_text='Vacío = el del plan.')
    limite_profesionales = forms.IntegerField(label='Límite de profesionales', required=False, min_value=1,
                                              help_text='Vacío = el del plan.')
    dias_gracia = forms.IntegerField(label='Días de gracia', required=False, min_value=0, max_value=60,
                                     help_text='Vacío = los del plan.')
    dictado_activo = forms.BooleanField(label='Dictado por voz activo', required=False)
    sugerencias_ia = forms.BooleanField(label='Sugerir indicaciones con IA', required=False,
                                        help_text='Récipe e indicaciones sugeridos; dosis fuera del glosario.')

    def clean_especialidades(self):
        nuevas = set(self.cleaned_data['especialidades'])
        if self.tenant is not None:
            from apps.equipo.models import PerfilProfesional
            en_uso = set(Especialidad.objects.filter(
                pk__in=PerfilProfesional.todos.filter(tenant=self.tenant, activo=True)
                .values_list('especialidad_id', flat=True)))
            faltan = en_uso - nuevas
            if faltan:
                raise forms.ValidationError('No se puede quitar una especialidad que usan sus profesionales: '
                                            + ', '.join(str(e) for e in faltan))
        return list(nuevas)


class RenovarForm(FormBase, forms.Form):
    meses = forms.TypedChoiceField(label='Período', coerce=int, initial=1,
                                   choices=[(1, '1 mes'), (3, '3 meses'), (6, '6 meses'), (12, '12 meses (anual)')])
    plan = forms.ModelChoiceField(label='Plan', queryset=Plan.objects.filter(activo=True), required=False)
    monto_usd = forms.DecimalField(label='Monto cobrado (USD)', max_digits=9, decimal_places=2, initial=0)
    referencia = forms.CharField(label='Referencia de pago', max_length=100, required=False)
    notas = forms.CharField(label='Notas', max_length=200, required=False)


class PlanForm(FormBase, forms.ModelForm):
    class Meta:
        model = Plan
        fields = ['nombre', 'descripcion', 'precio_usd', 'precio_anual_usd', 'max_profesionales', 'max_usuarios',
                  'dias_gracia', 'incluye_dictado', 'minutos_dictado_mes', 'precio_minuto_extra_usd',
                  'tope_minutos_extra', 'activo']
