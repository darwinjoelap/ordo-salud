"""
Consulta clínica (Fase 07, ADR-010).

- Se abre con una plantilla; su estructura (secciones y campos efectivos) se CONGELA en `estructura`.
- Cada sección guarda sus datos en RegistroSeccion (JSONB). Las de ámbito PACIENTE se guardan en
  RegistroSeccionPaciente (con historial) y aparecen ya llenas en la próxima consulta.
- Signos vitales, diagnósticos y medicamentos además se copian a tablas para graficar y contar.
- BORRADOR → CERRADA (inmutable; se corrige con Enmienda) · ANULADA (con motivo, nunca se borra).
"""
from django.conf import settings
from django.db import models

from apps.core.tenancy import Auditable, TenantModel


class Cie10(models.Model):
    """Catálogo CIE-10 (global). Se amplía con `python manage.py importar_cie10 archivo.csv`."""
    codigo = models.CharField('Código', max_length=10, unique=True)
    descripcion = models.CharField('Descripción', max_length=300)
    busqueda = models.CharField(max_length=320, editable=False, db_index=True, default='')

    class Meta:
        verbose_name = 'Diagnóstico CIE-10'
        verbose_name_plural = 'Catálogo CIE-10'
        ordering = ['codigo']

    def __str__(self):
        return f'{self.codigo} {self.descripcion}'

    def save(self, *args, **kwargs):
        from apps.pacientes.models import normalizar_texto
        self.codigo = self.codigo.strip().upper()
        self.busqueda = normalizar_texto(f'{self.codigo} {self.descripcion}')
        super().save(*args, **kwargs)


class Consulta(TenantModel, Auditable):
    class Estado(models.TextChoices):
        BORRADOR = 'BORRADOR', 'En curso'
        CERRADA = 'CERRADA', 'Cerrada'
        ANULADA = 'ANULADA', 'Anulada'

    class Tipo(models.TextChoices):
        PRIMERA = 'PRIMERA', 'Primera consulta'
        CONTROL = 'CONTROL', 'Control'
        EMERGENCIA = 'EMERGENCIA', 'Emergencia'
        OTRA = 'OTRA', 'Otra'

    paciente = models.ForeignKey('pacientes.Paciente', on_delete=models.PROTECT, related_name='consultas')
    profesional = models.ForeignKey('equipo.PerfilProfesional', on_delete=models.PROTECT, related_name='consultas')
    especialidad = models.ForeignKey('plataforma.Especialidad', on_delete=models.PROTECT, related_name='+')
    plantilla = models.ForeignKey('clinica.PlantillaHistoria', on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='consultas')
    lugar = models.ForeignKey('configuracion.Lugar', on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='consultas')
    estructura = models.JSONField('Estructura congelada', default=list)
    fecha_hora = models.DateTimeField('Fecha y hora')
    tipo = models.CharField('Tipo', max_length=10, choices=Tipo.choices, default=Tipo.PRIMERA)
    estado = models.CharField('Estado', max_length=10, choices=Estado.choices, default=Estado.BORRADOR,
                              db_index=True)
    motivo = models.CharField('Motivo (resumen)', max_length=300, blank=True)
    diagnostico = models.CharField('Diagnóstico principal (resumen)', max_length=300, blank=True)
    cerrada_en = models.DateTimeField('Cerrada', null=True, blank=True)
    cerrada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='+')
    motivo_anulacion = models.CharField('Motivo de anulación', max_length=250, blank=True)

    class Meta:
        verbose_name = 'Consulta'
        verbose_name_plural = 'Consultas'
        ordering = ['-fecha_hora']
        indexes = [models.Index(fields=['tenant', 'paciente', '-fecha_hora'], name='consulta_paciente_fecha')]

    def __str__(self):
        return f'{self.paciente} · {self.fecha_hora:%d/%m/%Y}'

    @property
    def editable(self):
        return self.estado == self.Estado.BORRADOR


class RegistroSeccion(TenantModel):
    consulta = models.ForeignKey(Consulta, on_delete=models.CASCADE, related_name='registros')
    seccion = models.ForeignKey('clinica.SeccionClinica', on_delete=models.PROTECT, related_name='+')
    version_seccion = models.PositiveIntegerField('Versión de la sección', default=1)
    datos = models.JSONField('Datos', default=dict, blank=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Registro de sección'
        verbose_name_plural = 'Registros de secciones'
        constraints = [models.UniqueConstraint(fields=['consulta', 'seccion'], name='registro_seccion_unico')]

    def __str__(self):
        return f'{self.consulta} · {self.seccion}'


class RegistroSeccionPaciente(TenantModel, Auditable):
    """Secciones de ámbito PACIENTE (antecedentes de especialidad). Cada cambio crea una versión nueva."""
    paciente = models.ForeignKey('pacientes.Paciente', on_delete=models.CASCADE, related_name='registros_seccion')
    seccion = models.ForeignKey('clinica.SeccionClinica', on_delete=models.PROTECT, related_name='+')
    version_seccion = models.PositiveIntegerField('Versión de la sección', default=1)
    datos = models.JSONField('Datos', default=dict, blank=True)
    vigente = models.BooleanField('Vigente', default=True, db_index=True)
    consulta = models.ForeignKey(Consulta, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    class Meta:
        verbose_name = 'Antecedente por sección'
        verbose_name_plural = 'Antecedentes por sección'
        ordering = ['-creado_en']
        constraints = [models.UniqueConstraint(fields=['paciente', 'seccion'], condition=models.Q(vigente=True),
                                               name='registro_paciente_vigente_unico')]


class SignosVitales(TenantModel):
    consulta = models.OneToOneField(Consulta, on_delete=models.CASCADE, related_name='signos')
    paciente = models.ForeignKey('pacientes.Paciente', on_delete=models.CASCADE, related_name='signos_vitales')
    fecha = models.DateField('Fecha', db_index=True)
    peso_kg = models.DecimalField('Peso (kg)', max_digits=6, decimal_places=2, null=True, blank=True)
    talla_cm = models.DecimalField('Talla (cm)', max_digits=5, decimal_places=1, null=True, blank=True)
    imc = models.DecimalField('IMC', max_digits=5, decimal_places=1, null=True, blank=True)
    pa_sistolica = models.PositiveSmallIntegerField('PA sistólica', null=True, blank=True)
    pa_diastolica = models.PositiveSmallIntegerField('PA diastólica', null=True, blank=True)
    fc = models.PositiveSmallIntegerField('FC', null=True, blank=True)
    fr = models.PositiveSmallIntegerField('FR', null=True, blank=True)
    temperatura = models.DecimalField('Temperatura', max_digits=4, decimal_places=1, null=True, blank=True)
    spo2 = models.PositiveSmallIntegerField('SpO₂', null=True, blank=True)
    glicemia = models.PositiveSmallIntegerField('Glicemia', null=True, blank=True)
    perimetro_abdominal = models.DecimalField('Perímetro abdominal', max_digits=5, decimal_places=1, null=True,
                                              blank=True)

    class Meta:
        verbose_name = 'Signos vitales'
        verbose_name_plural = 'Signos vitales'
        ordering = ['-fecha']


class DiagnosticoConsulta(TenantModel):
    class Certeza(models.TextChoices):
        PRESUNTIVO = 'PRESUNTIVO', 'Presuntivo'
        DEFINITIVO = 'DEFINITIVO', 'Definitivo'

    consulta = models.ForeignKey(Consulta, on_delete=models.CASCADE, related_name='diagnosticos')
    paciente = models.ForeignKey('pacientes.Paciente', on_delete=models.CASCADE, related_name='diagnosticos')
    cie10 = models.ForeignKey(Cie10, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    codigo = models.CharField('Código', max_length=10, blank=True)
    descripcion = models.CharField('Diagnóstico', max_length=300)
    certeza = models.CharField('Certeza', max_length=10, choices=Certeza.choices, blank=True)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = 'Diagnóstico'
        verbose_name_plural = 'Diagnósticos'
        ordering = ['consulta', 'orden']

    def __str__(self):
        return f'{self.codigo} {self.descripcion}'.strip()


class ItemPrescripcion(TenantModel):
    consulta = models.ForeignKey(Consulta, on_delete=models.CASCADE, related_name='medicamentos')
    paciente = models.ForeignKey('pacientes.Paciente', on_delete=models.CASCADE, related_name='medicamentos')
    medicamento = models.CharField('Medicamento', max_length=200)
    dosis = models.CharField('Dosis', max_length=100, blank=True)
    frecuencia = models.CharField('Frecuencia', max_length=100, blank=True)
    duracion = models.CharField('Duración', max_length=100, blank=True)
    cantidad = models.CharField('Cantidad', max_length=60, blank=True)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = 'Medicamento indicado'
        verbose_name_plural = 'Medicamentos indicados'
        ordering = ['consulta', 'orden']

    def __str__(self):
        return self.medicamento


class Enmienda(TenantModel, Auditable):
    """Corrección de una consulta cerrada: queda el antes y el después, con motivo y autor."""
    consulta = models.ForeignKey(Consulta, on_delete=models.PROTECT, related_name='enmiendas')
    seccion = models.ForeignKey('clinica.SeccionClinica', on_delete=models.PROTECT, related_name='+')
    motivo = models.CharField('Motivo', max_length=300)
    antes = models.JSONField('Antes', default=dict)
    despues = models.JSONField('Después', default=dict)

    class Meta:
        verbose_name = 'Enmienda'
        verbose_name_plural = 'Enmiendas'
        ordering = ['-creado_en']


def _ruta_adjunto(instancia, archivo):
    return f'ordo-salud/{instancia.tenant.slug}/pacientes/{instancia.paciente_id}/{archivo}'


class Adjunto(TenantModel, Auditable):
    """Archivo del paciente (resultados, imágenes). Se sirve SOLO por la vista con permiso (ADR-017)."""
    paciente = models.ForeignKey('pacientes.Paciente', on_delete=models.CASCADE, related_name='adjuntos')
    consulta = models.ForeignKey(Consulta, on_delete=models.SET_NULL, null=True, blank=True, related_name='adjuntos')
    archivo = models.FileField('Archivo', upload_to=_ruta_adjunto)
    nombre = models.CharField('Nombre', max_length=200)
    descripcion = models.CharField('Descripción', max_length=250, blank=True)
    tipo_contenido = models.CharField(max_length=100, blank=True)
    tamano = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Adjunto'
        verbose_name_plural = 'Adjuntos'
        ordering = ['-creado_en']

    def __str__(self):
        return self.nombre
