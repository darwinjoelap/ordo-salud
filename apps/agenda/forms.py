from django import forms
from django.db.models import Q

from apps.cobros.models import Servicio
from apps.core.forms import FormBase, validar_unico_en_tenant
from apps.equipo.models import PerfilProfesional
from apps.pacientes.models import Paciente

from . import servicios_previstos as previstos
from .models import Bloqueo, Cita, HorarioAtencion, TipoCita

FECHA = forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')
HORA = forms.TimeInput(attrs={'type': 'time', 'step': 300}, format='%H:%M')


def profesionales_activos():
    return (PerfilProfesional.objects.filter(activo=True, membresia__activa=True)
            .select_related('membresia__usuario', 'especialidad'))


class ProfesionalChoice(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f'{obj.nombre_con_titulo} · {obj.especialidad}'


class CitaForm(FormBase, forms.ModelForm):
    paciente = forms.ModelChoiceField(queryset=Paciente.objects.none(), widget=forms.HiddenInput,
                                      error_messages={'required': 'Elige el paciente.'})
    profesional = ProfesionalChoice(label='Profesional', queryset=PerfilProfesional.objects.none())
    servicios = forms.ModelMultipleChoiceField(queryset=Servicio.objects.none(), required=False)
    servicios_presentes = forms.BooleanField(required=False, widget=forms.HiddenInput, initial=True)
    version_cita = forms.DateTimeField(required=False, widget=forms.HiddenInput)
    sobrecupo = forms.BooleanField(label='Sobrecupo (agendar aunque ya haya otra cita a esa hora)', required=False)

    class Meta:
        model = Cita
        fields = ['paciente', 'profesional', 'tipo', 'lugar', 'fecha', 'hora_inicio', 'motivo', 'notas']
        widgets = {'fecha': FECHA, 'hora_inicio': HORA, 'notas': forms.Textarea(attrs={'rows': 2})}
        labels = {'tipo': 'Tipo de cita', 'hora_inicio': 'Hora (vacía = tentativa)'}

    def __init__(self, *args, solo=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['paciente'].queryset = Paciente.objects.filter(activo=True)
        # solo: el médico que solo ve su agenda (ADR-064) agenda únicamente para sí
        self.fields['profesional'].queryset = profesionales_activos().filter(pk=solo.pk) if solo else profesionales_activos()
        self.fields['tipo'].queryset = TipoCita.objects.filter(Q(activo=True) | Q(pk=self.instance.tipo_id))
        self.plan_bloqueado = self.instance.pk and previstos.plan_bloqueado(self.instance)
        self.plan_explicito = self.instance.servicios_explicitos
        if self.instance.pk:
            self.initial['version_cita'] = self.instance.actualizado_en.isoformat()
        lineas = previstos.lineas_de(self.instance) if self.instance.pk else []
        self.lineas_actuales = {linea.servicio_id: linea for linea in lineas}
        self.fields['servicios'].queryset = Servicio.objects.filter(Q(activo=True) | Q(pk__in=self.lineas_actuales))
        self.initial['servicios'] = list(self.lineas_actuales)
        self.especialidades_profesionales = dict(self.fields['profesional'].queryset.values_list('pk', 'especialidad_id'))
        self.predeterminados_tipo = {
            tipo.pk: [tipo.servicio_id, tipo.especialidad_id]
            for tipo in self.fields['tipo'].queryset if tipo.servicio_id
        }
        self.fields['lugar'].queryset = self.fields['lugar'].queryset.filter(activo=True)
        self.fields['lugar'].required = False
        self.fields['tipo'].required = False
        self.fields['tipo'].empty_label = 'Sin tipo'
        self.fields['lugar'].empty_label = 'Sin lugar'
        self.fields['hora_inicio'].help_text = ''
        if self.fields['profesional'].queryset.count() == 1:
            unico = self.fields['profesional'].queryset.first()
            self.fields['profesional'].initial = unico
            if not self.initial.get('profesional'):      # el campo va oculto: nunca puede quedar vacío
                self.initial['profesional'] = unico.pk
            self.solo_un_profesional = True
        else:
            self.solo_un_profesional = False


    def opciones_servicios(self):
        seleccion = {str(pk) for pk in self['servicios'].value() or ()}
        especialidades = self.especialidades_profesionales.values()
        opciones = self.fields['servicios'].queryset.filter(
            Q(especialidad__isnull=True) | Q(especialidad_id__in=especialidades) | Q(pk__in=self.lineas_actuales))
        for servicio in opciones:
            linea = self.lineas_actuales.get(servicio.pk)
            yield {'servicio': servicio, 'marcado': str(servicio.pk) in seleccion,
                   'nombre': linea.nombre if linea else servicio.nombre,
                   'precio': linea.precio_usd if linea else servicio.precio_usd}

    def ids_servicios(self):
        if self.cleaned_data['servicios_presentes'] or self.cleaned_data['servicios']:
            return [servicio.pk for servicio in self.cleaned_data['servicios']]
        return None


class HorarioForm(FormBase, forms.ModelForm):
    dias = forms.MultipleChoiceField(label='Días', choices=HorarioAtencion.Dia.choices,
                                     widget=forms.CheckboxSelectMultiple)

    class Meta:
        model = HorarioAtencion
        fields = ['lugar', 'hora_inicio', 'hora_fin', 'duracion_turno_min']
        widgets = {'hora_inicio': HORA, 'hora_fin': HORA}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['lugar'].required = False

    def clean(self):
        datos = super().clean()
        if datos.get('hora_inicio') and datos.get('hora_fin') and datos['hora_fin'] <= datos['hora_inicio']:
            self.add_error('hora_fin', 'Debe ser posterior al inicio.')
        return datos


class TipoCitaForm(FormBase, forms.ModelForm):
    class Meta:
        model = TipoCita
        fields = ['nombre', 'duracion_min', 'color', 'especialidad', 'tipo_consulta', 'servicio', 'plantilla',
                  'activo']
        widgets = {'color': forms.TextInput(attrs={'type': 'color', 'class': 'form-control form-control-color'})}

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant is not None:
            self.fields['especialidad'].queryset = tenant.especialidades.all()
        self.fields['plantilla'].queryset = self.fields['plantilla'].queryset.filter(profesional__isnull=True,
                                                                                    activa=True)

    def clean_nombre(self):
        return validar_unico_en_tenant(self, 'nombre', 'Ya hay un tipo de cita con ese nombre.')


class BloqueoForm(FormBase, forms.ModelForm):
    profesional = ProfesionalChoice(label='Profesional', queryset=PerfilProfesional.objects.none(), required=False,
                                    empty_label='Todo el consultorio')

    class Meta:
        model = Bloqueo
        fields = ['profesional', 'desde', 'hasta', 'motivo']
        widgets = {'desde': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
                   'hasta': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M')}

    def __init__(self, *args, solo=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['profesional'].queryset = profesionales_activos()
        if solo:            # el médico que solo ve su agenda bloquea solo la suya (no todo el consultorio)
            self.fields['profesional'].queryset = profesionales_activos().filter(pk=solo.pk)
            self.fields['profesional'].required = True
            self.fields['profesional'].empty_label = None
            self.initial.setdefault('profesional', solo.pk)

    def clean(self):
        datos = super().clean()
        if datos.get('desde') and datos.get('hasta') and datos['hasta'] <= datos['desde']:
            self.add_error('hasta', 'Debe ser posterior al inicio.')
        return datos


class MensajeInactividadForm(FormBase, forms.Form):
    mensaje = forms.CharField(label='Mensaje', max_length=1000, widget=forms.Textarea(attrs={'rows': 4}))
