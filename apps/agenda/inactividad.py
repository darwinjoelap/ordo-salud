from django.db import transaction
from django.utils.crypto import constant_time_compare, salted_hmac

from apps.configuracion import whatsapp
from apps.core import auditoria
from apps.pacientes.models import Paciente, Representante
from apps.pacientes.selectors import filtrar_propios, puede_ver_todos

from .models import RecordatorioInactividad
from .selectors import sugerencias_inactividad
from .servicios import hoy

Estado = RecordatorioInactividad.Estado


def contacto_autorizado(paciente, *, bloquear=False):
    if paciente.es_menor:
        representantes = Representante.objects.filter(paciente=paciente).order_by('-es_principal', 'pk')
        contacto = (representantes.select_for_update() if bloquear else representantes).first()
        if not contacto:
            return None, ''
    else:
        contacto = paciente
    numero = whatsapp.numero_whatsapp(contacto.telefono)
    if not numero or contacto.whatsapp_seguimiento != numero:
        return contacto, ''
    return contacto, numero


def token_contacto(*, request, paciente_id, ultima, meses, contacto, numero):
    datos = (f'{request.tenant.pk}:{request.user.pk}:{paciente_id}:{ultima}:{meses}:'
             f'{contacto._meta.model_name}:{contacto.pk}:{numero}:{contacto.actualizado_en.isoformat()}')
    return salted_hmac('agenda.recordatorio_inactividad', datos, algorithm='sha256').hexdigest()


def _pacientes(request):
    pacientes = Paciente.objects.filter(activo=True)
    return pacientes if puede_ver_todos(request.membresia) else filtrar_propios(pacientes, request.membresia)


@transaction.atomic
def validar_contacto(*, request, paciente_id, ultima, meses, token, registrar):
    paciente = _pacientes(request).select_for_update(no_key=True).filter(pk=paciente_id).first()
    if paciente is None or meses != request.tenant.configuracion.recordatorio_sin_consulta_meses:
        return ''
    if not sugerencias_inactividad(fecha=hoy(), membresia=request.membresia).filter(
            pk=paciente_id, ultima_asistencia=ultima).exists():
        return ''
    contacto, numero = contacto_autorizado(paciente, bloquear=True)
    if not numero or not constant_time_compare(token, token_contacto(
            request=request, paciente_id=paciente_id, ultima=ultima, meses=meses, contacto=contacto, numero=numero)):
        return ''
    if registrar and not registrar_decision(request=request, paciente_id=paciente_id, ultima=ultima, meses=meses,
                                           estado=Estado.INTENTO, token=token):
        return ''
    return numero


@transaction.atomic
def registrar_decision(*, request, paciente_id, ultima, meses, estado, token=''):
    paciente = _pacientes(request).select_for_update(no_key=True).filter(pk=paciente_id).first()
    if paciente is None or meses != request.tenant.configuracion.recordatorio_sin_consulta_meses:
        return False
    visible = sugerencias_inactividad(fecha=hoy(), membresia=request.membresia).filter(
        pk=paciente_id, ultima_asistencia=ultima).exists()
    decisiones = RecordatorioInactividad.objects.filter(paciente=paciente, ultima_asistencia=ultima)
    if not visible:
        return decisiones.filter(estado=estado, resuelto_por=request.user).exists()

    decision = decisiones.first()
    if estado == Estado.INTENTO or (estado == Estado.ENVIADO and decision is None):
        contacto, numero = contacto_autorizado(paciente, bloquear=True)
        if not numero or not constant_time_compare(token, token_contacto(
                request=request, paciente_id=paciente_id, ultima=ultima, meses=meses, contacto=contacto, numero=numero)):
            return False
        if decision is not None:
            return True

    if decision is None:
        decision = RecordatorioInactividad(paciente=paciente, ultima_asistencia=ultima, meses=meses,
                                           creado_por=request.user)
    decision.estado = estado
    if estado != Estado.INTENTO:
        decision.resuelto_por = request.user
    decision.save()
    auditoria.registrar(request, 'EDITAR', decision, paciente_id=paciente.pk,
                        detalle=f'Seguimiento de inactividad · WhatsApp · {decision.get_estado_display()}')
    return True
