"""Emisión de documentos: número correlativo + registro. El PDF se genera al abrirlo."""
from django.db import transaction
from django.utils import timezone

from apps.core.excepciones import ErrorDeNegocio
from apps.core.pdf import medir_pdf
from apps.core.secuencias import siguiente_numero

from .models import DocumentoEmitido
from .registro import documento


@transaction.atomic
def emitir(codigo, *, paciente, profesional=None, consulta=None, datos=None, fecha=None):
    definicion = documento(codigo)
    if definicion is None:
        raise ErrorDeNegocio('Documento desconocido.')
    if definicion.requiere_consulta and consulta is None:
        raise ErrorDeNegocio(f'«{definicion.nombre}» se emite desde una consulta.')
    if consulta is not None and consulta.estado == 'ANULADA':
        raise ErrorDeNegocio('La consulta está anulada.')
    if definicion.especialidad and (profesional is None or profesional.especialidad.codigo != definicion.especialidad):
        raise ErrorDeNegocio(f'«{definicion.nombre}» es propio de otra especialidad.')
    return DocumentoEmitido.objects.create(
        tipo=codigo, numero=siguiente_numero(definicion.prefijo), paciente=paciente, consulta=consulta,
        profesional=profesional, fecha=fecha or timezone.localdate(), datos=datos or {})


def documento_de_consulta(codigo, consulta):
    """Récipe/informe sin formulario: uno por consulta (se reutiliza el número al reimprimir)."""
    existente = DocumentoEmitido.objects.filter(tipo=codigo, consulta=consulta, anulado=False).first()
    return existente or emitir(codigo, paciente=consulta.paciente, profesional=consulta.profesional,
                               consulta=consulta, fecha=timezone.localtime(consulta.fecha_hora).date())


def recibo_de_pago(pago):
    existente = DocumentoEmitido.objects.filter(tipo='recibo', datos__pago=pago.pk).first()
    return existente or emitir('recibo', paciente=pago.paciente, datos={'pago': pago.pk}, fecha=pago.fecha)


def anular(doc, motivo):
    if doc.anulado:
        raise ErrorDeNegocio('El documento ya está anulado.')
    doc.anulado = True
    doc.motivo_anulacion = motivo[:200]
    doc.save(update_fields=['anulado', 'motivo_anulacion', 'actualizado_en'])


def pdf(doc, con_firma=True):
    with medir_pdf(doc.tipo):
        return doc.definicion.generar(doc, con_firma=con_firma)
