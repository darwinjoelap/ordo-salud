"""
Pacientes: ficha base común a todas las especialidades (ADR-009).

Los antecedentes propios de una especialidad (perinatales, gineco-obstétricos, cardiovasculares) NO van aquí:
son secciones clínicas de ámbito PACIENTE (apps.clinica).
"""
import re
import unicodedata

from django.db import models
from django.db.models import Q

from apps.core import fechas
from apps.core.tenancy import Auditable, TenantModel


def normalizar_texto(texto):
    """'José  Pérez' → 'jose perez' (para buscar sin importar acentos ni mayúsculas)."""
    sin_acentos = unicodedata.normalize('NFKD', texto or '').encode('ascii', 'ignore').decode()
    return ' '.join(sin_acentos.lower().split())


def normalizar_documento(numero):
    """'V-12.345.678' → '12345678'. Pasaportes conservan letras: 'ab 123' → 'AB123'."""
    texto = re.sub(r'[^0-9A-Za-z]', '', numero or '').upper()
    if re.fullmatch(r'[VE]\d+', texto):       # escribieron el prefijo en el número: 'V12345678'
        texto = texto[1:]
    return texto.lstrip('0') or texto


def limpiar_telefono(valor):
    """Solo dígitos y +; quita espacios, guiones y caracteres invisibles."""
    return re.sub(r'[^\d+]', '', valor or '')


class Paciente(TenantModel, Auditable):
    class Sexo(models.TextChoices):
        FEMENINO = 'F', 'Femenino'
        MASCULINO = 'M', 'Masculino'

    class TipoDocumento(models.TextChoices):
        V = 'V', 'V (venezolano)'
        E = 'E', 'E (extranjero)'
        P = 'P', 'Pasaporte'
        NINGUNO = 'N', 'Sin documento'

    class EstadoCivil(models.TextChoices):
        SOLTERO = 'SOLTERO', 'Soltero/a'
        CASADO = 'CASADO', 'Casado/a'
        UNION = 'UNION', 'Unión estable'
        DIVORCIADO = 'DIVORCIADO', 'Divorciado/a'
        VIUDO = 'VIUDO', 'Viudo/a'

    INSTRUCCION = [('PRIMARIA', 'Primaria'), ('SECUNDARIA', 'Secundaria'), ('TECNICO', 'Técnico'),
                   ('UNIVERSITARIO', 'Universitario'), ('POSTGRADO', 'Postgrado')]

    class Grupo(models.TextChoices):
        A_POS = 'A+', 'A+'
        A_NEG = 'A-', 'A-'
        B_POS = 'B+', 'B+'
        B_NEG = 'B-', 'B-'
        AB_POS = 'AB+', 'AB+'
        AB_NEG = 'AB-', 'AB-'
        O_POS = 'O+', 'O+'
        O_NEG = 'O-', 'O-'

    nombres = models.CharField('Nombres', max_length=120)
    apellidos = models.CharField('Apellidos', max_length=120)
    sexo = models.CharField('Sexo', max_length=1, choices=Sexo.choices, blank=True,
                            help_text='Opcional; hace falta para los percentiles de crecimiento.')
    fecha_nacimiento = models.DateField('Fecha de nacimiento', null=True, blank=True)
    tipo_documento = models.CharField('Tipo de documento', max_length=1, choices=TipoDocumento.choices,
                                      default=TipoDocumento.V)
    numero_documento = models.CharField('N.º de documento', max_length=20, blank=True)
    telefono = models.CharField('Teléfono', max_length=25, blank=True)
    telefono_2 = models.CharField('Otro teléfono', max_length=25, blank=True)
    email = models.EmailField('Correo', blank=True)
    direccion = models.CharField('Dirección', max_length=250, blank=True)
    ciudad = models.CharField('Ciudad', max_length=80, blank=True)
    ocupacion = models.CharField('Ocupación', max_length=100, blank=True)
    estado_civil = models.CharField('Estado civil', max_length=12, choices=EstadoCivil.choices, blank=True)
    grupo_sanguineo = models.CharField('Grupo sanguíneo', max_length=3, choices=Grupo.choices, blank=True)
    nivel_instruccion = models.CharField('Nivel de instrucción', max_length=14, choices=INSTRUCCION, blank=True)
    seguro = models.CharField('Seguro / aseguradora', max_length=100, blank=True)
    contacto_emergencia = models.CharField('Contacto de emergencia', max_length=150, blank=True)
    referido_por = models.CharField('Referido por / cómo llegó', max_length=120, blank=True)
    observaciones = models.TextField('Observaciones administrativas', blank=True)
    activo = models.BooleanField('Activo', default=True)
    # Derivados para buscar sin acentos
    busqueda = models.CharField(max_length=300, editable=False, db_index=True, default='')
    documento_normalizado = models.CharField(max_length=20, editable=False, blank=True, db_index=True)

    class Meta:
        verbose_name = 'Paciente'
        verbose_name_plural = 'Pacientes'
        ordering = ['apellidos', 'nombres']
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'documento_normalizado'],
                                    condition=~Q(documento_normalizado=''), name='paciente_documento_unico'),
        ]

    def __str__(self):
        return self.nombre_completo

    def save(self, *args, **kwargs):
        self.nombres = ' '.join(self.nombres.split())
        self.apellidos = ' '.join(self.apellidos.split())
        self.telefono = limpiar_telefono(self.telefono)
        self.telefono_2 = limpiar_telefono(self.telefono_2)
        if self.tipo_documento == self.TipoDocumento.NINGUNO:
            self.numero_documento = ''
        self.numero_documento = self.numero_documento.strip().upper()
        self.documento_normalizado = (f'{self.tipo_documento}{normalizar_documento(self.numero_documento)}'
                                      if self.numero_documento else '')
        self.busqueda = normalizar_texto(f'{self.nombres} {self.apellidos} {self.numero_documento}')
        super().save(*args, **kwargs)

    @property
    def nombre_completo(self):
        return f'{self.nombres} {self.apellidos}'.strip()

    @property
    def documento(self):
        if not self.numero_documento:
            return 'Sin documento'
        prefijo = '' if self.tipo_documento == self.TipoDocumento.P else f'{self.tipo_documento}-'
        return f'{prefijo}{self.numero_documento}'

    @property
    def edad_anios(self):
        return fechas.edad_anios(self.fecha_nacimiento)

    @property
    def edad_texto(self):
        return fechas.edad_texto(self.fecha_nacimiento)

    @property
    def es_menor(self):
        anios = self.edad_anios
        return anios is not None and anios < 18

    @property
    def representante_principal(self):
        reps = list(self.representantes.all())
        return next((r for r in reps if r.es_principal), reps[0] if reps else None)

    @property
    def telefono_contacto(self):
        """Teléfono para avisos: el del representante principal si es menor."""
        rep = self.representante_principal if self.es_menor else None
        return (rep.telefono if rep and rep.telefono else '') or self.telefono


class Representante(TenantModel, Auditable):
    class Parentesco(models.TextChoices):
        MADRE = 'MADRE', 'Madre'
        PADRE = 'PADRE', 'Padre'
        ABUELO = 'ABUELO', 'Abuela/o'
        TIO = 'TIO', 'Tía/o'
        HERMANO = 'HERMANO', 'Hermana/o'
        TUTOR = 'TUTOR', 'Tutor legal'
        CONYUGE = 'CONYUGE', 'Cónyuge'
        OTRO = 'OTRO', 'Otro'

    paciente = models.ForeignKey(Paciente, on_delete=models.CASCADE, related_name='representantes')
    nombre = models.CharField('Nombre y apellido', max_length=150)
    parentesco = models.CharField('Parentesco', max_length=10, choices=Parentesco.choices, default=Parentesco.MADRE)
    tipo_documento = models.CharField('Tipo de documento', max_length=1,
                                      choices=Paciente.TipoDocumento.choices, default=Paciente.TipoDocumento.V)
    numero_documento = models.CharField('N.º de documento', max_length=20, blank=True)
    telefono = models.CharField('Teléfono', max_length=25, blank=True)
    email = models.EmailField('Correo', blank=True)
    ocupacion = models.CharField('Ocupación', max_length=100, blank=True)
    es_principal = models.BooleanField('Representante principal', default=True)

    class Meta:
        verbose_name = 'Representante'
        verbose_name_plural = 'Representantes'
        ordering = ['-es_principal', 'nombre']

    def __str__(self):
        return f'{self.nombre} ({self.get_parentesco_display()})'

    def save(self, *args, **kwargs):
        self.telefono = limpiar_telefono(self.telefono)
        self.numero_documento = self.numero_documento.strip().upper()
        super().save(*args, **kwargs)

    @property
    def documento(self):
        if not self.numero_documento:
            return ''
        prefijo = '' if self.tipo_documento == Paciente.TipoDocumento.P else f'{self.tipo_documento}-'
        return f'{prefijo}{self.numero_documento}'


class AntecedenteBase(TenantModel, Auditable):
    """Lo común a toda especialidad. Siempre visible para todo médico del tenant (seguridad del paciente)."""
    paciente = models.OneToOneField(Paciente, on_delete=models.CASCADE, related_name='antecedentes')
    alergias = models.TextField('Alergias', blank=True,
                                help_text='Medicamentos, alimentos, látex… Vacío = no conocidas.')
    medicacion_actual = models.TextField('Medicación actual', blank=True)
    enfermedades_cronicas = models.TextField('Enfermedades crónicas', blank=True)
    cirugias = models.TextField('Cirugías', blank=True)
    hospitalizaciones = models.TextField('Hospitalizaciones', blank=True)
    transfusiones = models.TextField('Transfusiones', blank=True)
    habitos = models.TextField('Hábitos (tabaco, alcohol, otros)', blank=True)
    antecedentes_familiares = models.TextField('Antecedentes familiares', blank=True)
    otros = models.TextField('Otros', blank=True)

    class Meta:
        verbose_name = 'Antecedentes base'
        verbose_name_plural = 'Antecedentes base'

    def __str__(self):
        return f'Antecedentes — {self.paciente}'

    @property
    def tiene_alergias(self):
        texto = normalizar_texto(self.alergias)
        return bool(texto) and texto not in {'no', 'ninguna', 'niega', 'no conocidas', 'nkda', 'no refiere'}
