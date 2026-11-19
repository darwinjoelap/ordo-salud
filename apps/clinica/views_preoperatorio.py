"""Edición, enmiendas y emisión de la valoración preoperatoria."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.core import auditoria
from apps.core.excepciones import ErrorDeNegocio
from apps.core.permisos import requiere

from . import preoperatorio, views_consultas
from .models import Consulta


def _evaluacion_visible(request, pk):
    consulta = views_consultas._consulta_visible(request, pk)
    evaluacion = getattr(consulta, 'preoperatorio', None)
    if evaluacion is None:
        raise Http404
    return consulta, evaluacion


@login_required
@requiere('historia.ver')
@require_http_methods(['GET', 'POST'])
@transaction.atomic
def valorar(request, pk):
    consulta, evaluacion = _evaluacion_visible(request, pk)
    if not preoperatorio.puede_valorar(request.membresia, consulta):
        raise PermissionDenied
    actual = preoperatorio.valoracion_actual(evaluacion)
    enmienda = consulta.estado == Consulta.Estado.CERRADA
    adjuntos = preoperatorio.adjuntos_visibles(consulta, request.membresia)
    datos = request.POST if request.method == 'POST' else None
    inicial = {**(actual.datos if actual else {'mets_estado': 'NO_EVALUADO'}),
               'version': actual.pk if actual else 0, 'validada': False}
    form = preoperatorio.ValoracionForm(datos, initial=inicial, enmienda=enmienda)
    estudios = preoperatorio.EstudiosFormSet(
        datos, initial=preoperatorio.datos_estudios(actual), prefix='estudios', form_kwargs={'adjuntos': adjuntos},
    )
    if request.method == 'POST':
        valoracion_valida = form.is_valid()
        if estudios.is_valid() and valoracion_valida:
            try:
                version, nueva = preoperatorio.guardar_valoracion(
                    consulta, request.membresia, form, estudios.cleaned_data,
                )
            except ErrorDeNegocio as error:
                form.add_error(None, str(error))
            else:
                if nueva:
                    auditoria.registrar(request, 'ENMENDAR' if enmienda else 'EDITAR', version,
                                        paciente_id=consulta.paciente_id, detalle='Valoración preoperatoria')
                messages.success(request, 'Valoración preoperatoria guardada.')
                redireccion = 'clinica:consulta'
                if request.POST.get('continuar') == 'estudios':
                    redireccion = 'clinica:preoperatorio_valorar'
                return redirect(redireccion, pk=pk)
    else:
        auditoria.registrar(request, 'VER', consulta, paciente_id=consulta.paciente_id,
                            detalle='Valoración preoperatoria')
    return render(request, 'clinica/preoperatorio_form.html', {
        'titulo': 'Valoración preoperatoria', 'consulta': consulta, 'form': form, 'estudios': estudios,
        'enmienda': enmienda,
    })


@login_required
@requiere('historia.ver')
@require_GET
def adjunto_estudio(request, pk, adjunto_pk):
    consulta, evaluacion = _evaluacion_visible(request, pk)
    actual = preoperatorio.valoracion_actual(evaluacion)
    if actual is None or not actual.estudios.filter(adjuntos__pk=adjunto_pk).exists():
        raise Http404
    adjunto = get_object_or_404(preoperatorio.adjuntos_visibles(consulta, request.membresia), pk=adjunto_pk)
    return views_consultas.adjunto(request, adjunto.pk)


@login_required
@requiere('historia.ver')
@require_POST
@transaction.atomic
def emitir(request, pk):
    consulta, _ = _evaluacion_visible(request, pk)
    try:
        doc, nuevo = preoperatorio.emitir_informe(consulta, request.membresia)
    except ErrorDeNegocio as error:
        messages.warning(request, str(error))
        return redirect('clinica:consulta', pk=pk)
    if nuevo:
        auditoria.registrar(request, 'CREAR', doc, paciente_id=consulta.paciente_id, detalle=doc.numero)
    return redirect('documentos:documento', pk=doc.pk)
