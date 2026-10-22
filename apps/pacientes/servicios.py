"""Reglas de pacientes: duplicados, menores con representante y antecedentes base."""
from django.db import transaction

from apps.core.excepciones import ErrorDeNegocio

from .models import AntecedenteBase, Paciente, Representante, normalizar_documento, normalizar_texto


class PacienteDuplicado(ErrorDeNegocio):
    def __init__(self, paciente):
        self.paciente = paciente
        super().__init__(f'Este paciente ya está registrado: {paciente.nombre_completo} ({paciente.documento}).')


def buscar_duplicado(*, tipo_documento, numero_documento, nombres, apellidos, fecha_nacimiento, excluir_pk=None):
    """
    Con documento: mismo tipo y número (normalizado). Sin documento: mismo nombre completo y misma fecha de
    nacimiento (dos hermanos sin cédula con el mismo representante sí se pueden registrar).
    """
    qs = Paciente.objects.exclude(pk=excluir_pk) if excluir_pk else Paciente.objects.all()
    if numero_documento and tipo_documento != Paciente.TipoDocumento.NINGUNO:
        return qs.filter(documento_normalizado=f'{tipo_documento}{normalizar_documento(numero_documento)}').first()
    if fecha_nacimiento:
        nombre = normalizar_texto(f'{nombres} {apellidos}')
        return qs.filter(busqueda__startswith=nombre, fecha_nacimiento=fecha_nacimiento).first()
    return None


def aviso_representante(paciente, representante):
    """
    Como en Pediae, ni la cédula ni el representante son obligatorios (en consulta se registra rápido y se completa
    después). Solo se avisa cuando un menor sin documento queda sin representante identificable.
    """
    sin_documento = not paciente.numero_documento or paciente.tipo_documento == Paciente.TipoDocumento.NINGUNO
    if paciente.es_menor and sin_documento:
        if representante is None or not representante.nombre.strip():
            return 'Menor sin documento y sin representante: conviene registrarlo para los recordatorios y documentos.'
        if not representante.numero_documento.strip():
            return 'Falta la cédula del representante (sale en constancias y documentos).'
    return None


@transaction.atomic
def crear_paciente(*, paciente: Paciente, representante: Representante | None = None,
                   alergias: str = '') -> Paciente:
    """`paciente` y `representante` llegan sin guardar (desde los formularios)."""
    duplicado = buscar_duplicado(tipo_documento=paciente.tipo_documento, numero_documento=paciente.numero_documento,
                                 nombres=paciente.nombres, apellidos=paciente.apellidos,
                                 fecha_nacimiento=paciente.fecha_nacimiento)
    if duplicado:
        raise PacienteDuplicado(duplicado)
    paciente.save()
    paciente.aviso = aviso_representante(paciente, representante)
    if representante is not None and representante.nombre.strip():
        representante.paciente = paciente
        representante.es_principal = True
        representante.save()
    AntecedenteBase.objects.create(paciente=paciente, alergias=alergias.strip())
    return paciente


@transaction.atomic
def actualizar_paciente(*, paciente: Paciente) -> Paciente:
    duplicado = buscar_duplicado(tipo_documento=paciente.tipo_documento, numero_documento=paciente.numero_documento,
                                 nombres=paciente.nombres, apellidos=paciente.apellidos,
                                 fecha_nacimiento=paciente.fecha_nacimiento, excluir_pk=paciente.pk)
    if duplicado:
        raise PacienteDuplicado(duplicado)
    paciente.save()
    paciente.aviso = aviso_representante(paciente, paciente.representante_principal)
    return paciente


@transaction.atomic
def guardar_representante(*, paciente: Paciente, representante: Representante) -> Representante:
    representante.paciente = paciente
    if representante.es_principal:
        paciente.representantes.exclude(pk=representante.pk).update(es_principal=False)
    elif not paciente.representantes.exclude(pk=representante.pk).filter(es_principal=True).exists():
        representante.es_principal = True        # siempre hay uno principal
    representante.save()
    return representante


@transaction.atomic
def eliminar_representante(*, representante: Representante) -> None:
    paciente = representante.paciente
    otros = paciente.representantes.exclude(pk=representante.pk)
    era_principal = representante.es_principal
    representante.delete()
    if era_principal and otros.exists():
        primero = otros.first()
        primero.es_principal = True
        primero.save(update_fields=['es_principal', 'actualizado_en'])


def antecedentes_de(paciente: Paciente) -> AntecedenteBase:
    antecedentes, _ = AntecedenteBase.objects.get_or_create(paciente=paciente)
    return antecedentes


ESPECIALIDADES_FEMENINAS = {'ginecologia'}


def sexo_por_defecto(request):
    """«F» en consultorios de ginecología (la médica que registra es de GO, o es la única especialidad); si no, ''."""
    membresia = getattr(request, 'membresia', None)
    perfil = getattr(membresia, 'perfil_activo', None) if membresia else None
    if perfil is not None and perfil.especialidad_id:
        return 'F' if perfil.especialidad.codigo in ESPECIALIDADES_FEMENINAS else ''
    tenant = getattr(request, 'tenant', None)
    codigos = set(tenant.especialidades.values_list('codigo', flat=True)) if tenant else set()
    return 'F' if codigos and codigos <= ESPECIALIDADES_FEMENINAS else ''
