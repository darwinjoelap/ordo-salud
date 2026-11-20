"""Alta por POST de exámenes propios del consultorio."""
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from apps.core.excepciones import ErrorDeNegocio
from apps.core.permisos import requiere
from apps.pacientes.models import Paciente
from apps.pacientes.selectors import puede_ver_paciente

from . import estudios, views_consultas
from .forms_estudios import AltaEstudioForm
from .models import Consulta


@login_required
@requiere('historia.ver')
@requiere('consultas.crear')
@require_POST
def nuevo(request):
    perfil = request.membresia.perfil_activo
    if perfil is None:
        raise PermissionDenied
    consulta_pk = request.POST.get('consulta')
    paciente_pk = request.POST.get('paciente')
    if consulta_pk and str(consulta_pk).isdigit():
        consulta = views_consultas._consulta_visible(request, consulta_pk)
        if consulta.profesional_id != perfil.pk or consulta.estado == Consulta.Estado.ANULADA:
            raise PermissionDenied
    elif not consulta_pk and paciente_pk and str(paciente_pk).isdigit():
        # Una consulta nueva todavía no existe: validar al paciente en el tenant activo.
        paciente = get_object_or_404(Paciente.objects.filter(activo=True), pk=paciente_pk)
        if (perfil.tenant_id != paciente.tenant_id
                or not perfil.activo or not puede_ver_paciente(request.membresia, paciente)):
            raise PermissionDenied
    else:
        raise Http404

    form = AltaEstudioForm(request.POST)
    if not form.is_valid():
        return JsonResponse({'errores': form.errors.get_json_data()}, status=400)
    try:
        examen = estudios.registrar_examen(form)
    except ErrorDeNegocio as error:
        return JsonResponse({'errores': {'nombre': [{'message': str(error)}]}}, status=409)
    return JsonResponse({
        'id': examen.pk, 'nombre': examen.nombre, 'categoria': examen.categoria,
        'descripcion': examen.descripcion,
    }, status=201)
