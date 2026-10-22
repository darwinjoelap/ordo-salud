"""Dictado de la consulta con IA: subir el audio y consultar el resultado (ADR-045)."""
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from apps.clinica.consultas import congelar_estructura, puede_editar
from apps.clinica.models import Consulta, PlantillaHistoria
from apps.core import auditoria
from apps.core.permisos import requiere
from apps.pacientes.models import Paciente

from . import servicios
from .models import SesionDictado


def _error(mensaje, estado=400):
    return JsonResponse({'error': mensaje}, status=estado)


@login_required
@requiere('consultas.crear')
@require_POST
def subir(request):
    perfil = request.membresia.perfil_activo
    if perfil is None:
        return _error('Solo un profesional puede dictar.', 403)
    audio = request.FILES.get('audio')
    try:
        segundos = min(int(float(request.POST.get('segundos') or 0)), servicios.MAX_SEGUNDOS)
    except ValueError:
        segundos = 0
    if audio is None or audio.size == 0:
        return _error('No llegó el audio.')
    if audio.size > servicios.MAX_BYTES:
        return _error('La grabación es muy larga (máximo 25 MB). Divide el dictado en dos partes.')
    if request.POST.get('consentimiento') != '1':
        return _error('Falta marcar que el paciente o su representante autorizó la grabación.')
    ok, motivo = servicios.puede_dictar(request.tenant, segundos)
    if not ok:
        return _error(motivo, 403)
    consulta = plantilla = None
    if (request.POST.get('consulta') or '').isdigit():
        consulta = get_object_or_404(Consulta.objects.select_related('paciente', 'especialidad'),
                                     pk=request.POST['consulta'])
        if not puede_editar(request.membresia, consulta):
            return _error('No puedes editar esta consulta.', 403)
        paciente, estructura, especialidad = consulta.paciente, consulta.estructura, consulta.especialidad
    else:
        paciente = get_object_or_404(Paciente.objects.all(), pk=request.POST.get('paciente') or 0)
        plantilla = get_object_or_404(PlantillaHistoria.objects.select_related('especialidad'),
                                      pk=request.POST.get('plantilla') or 0)
        estructura, especialidad = congelar_estructura(plantilla), plantilla.especialidad
    sesion = SesionDictado.objects.create(paciente=paciente, profesional=perfil, consulta=consulta,
                                         plantilla=plantilla, segundos=segundos, consentimiento=True)
    auditoria.registrar(request, 'CREAR', sesion, paciente_id=paciente.pk,
                        detalle=f'Dictado con IA ({round(segundos / 60, 1)} min)')
    servicios.lanzar(sesion.pk, audio.read(), audio.name or 'dictado.webm', audio.content_type, estructura,
                     especialidad.codigo if especialidad else '', especialidad.nombre if especialidad else '')
    return JsonResponse({'id': sesion.pk, 'estado': SesionDictado.objects.get(pk=sesion.pk).estado})


@login_required
@requiere('consultas.crear')
@require_GET
def estado(request, pk):
    sesion = get_object_or_404(SesionDictado.objects.all(), pk=pk)
    if request.membresia.perfil_activo is None or sesion.profesional_id != request.membresia.perfil_activo.pk:
        raise Http404
    datos = {'id': sesion.pk, 'estado': sesion.estado}
    if sesion.estado == SesionDictado.Estado.LISTO:
        datos.update({'resultado': sesion.resultado, 'no_ubicado': sesion.no_ubicado,
                      'transcripcion': sesion.transcripcion, 'prueba': sesion.modelo_ia == 'prueba'})
    elif sesion.estado == SesionDictado.Estado.ERROR:
        datos['error'] = sesion.error
    return JsonResponse(datos)


def vincular(request, consulta):
    """Al guardar la consulta, la sesión de dictado del formulario queda asociada (trazabilidad)."""
    pk = request.POST.get('dictado') or ''
    perfil = request.membresia.perfil_activo
    if pk.isdigit() and perfil is not None:
        SesionDictado.objects.filter(pk=pk, paciente_id=consulta.paciente_id, profesional=perfil,
                                     consulta__isnull=True).update(consulta=consulta)
