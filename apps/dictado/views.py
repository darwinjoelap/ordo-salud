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
        return _error('La grabación es muy pesada (máximo 120 MB). Divídela en dos partes.')
    if not (audio.content_type or '').startswith(('audio/', 'video/')) and not (audio.name or '').lower().endswith(
            ('.m4a', '.mp3', '.ogg', '.opus', '.wav', '.aac', '.flac', '.webm', '.amr', '.3gp', '.mp4')):
        return _error('El archivo no parece una grabación de audio.')
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
    origen = SesionDictado.Origen.ARCHIVO if request.POST.get('origen') == 'archivo' else SesionDictado.Origen.GRABACION
    sesion = SesionDictado.objects.create(paciente=paciente, profesional=perfil, consulta=consulta,
                                         plantilla=plantilla, segundos=segundos, consentimiento=True, origen=origen)
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


# ── Sugerir indicaciones (ADR-060) ────────────────────────────────────────────────────────────────────────────

def _json(request):
    import json
    try:
        datos = json.loads(request.body or b'{}')
    except ValueError:
        return None
    return datos if isinstance(datos, dict) else None


@login_required
@requiere('consultas.crear')
@require_POST
def sugerir(request, paciente_pk):
    """POST JSON {campos: {etiqueta: valor}, peso} → récipe e indicaciones sugeridos (nada se guarda en la historia)."""
    from apps.clinica.views_medicamentos import visibles
    from apps.pacientes.selectors import puede_ver_paciente

    from . import indicaciones
    perfil = request.membresia.perfil_activo
    if perfil is None or not indicaciones.activo(request.tenant):
        return _error('La sugerencia con IA no está activa en este consultorio.', 403)
    paciente = get_object_or_404(Paciente.objects.select_related('antecedentes'), pk=paciente_pk)
    if not puede_ver_paciente(request.membresia, paciente):
        return _error('Sin acceso a este paciente.', 403)
    datos = _json(request)
    if datos is None:
        return _error('Datos inválidos.')
    campos = {str(k)[:80]: str(v)[:2000] for k, v in (datos.get('campos') or {}).items()
              if isinstance(k, str) and v not in (None, '')}
    try:
        peso = float(str(datos.get('peso') or '').replace(',', '.')) or None
    except ValueError:
        peso = None
    try:
        r = indicaciones.sugerir(paciente=paciente, perfil=perfil, campos=campos, peso=peso,
                                 glosario=visibles(request).filter(activo=True).order_by('nombre'))
    except indicaciones.ErrorSugerencia as e:
        return _error(str(e), 502 if 'Gemini' in str(e) else 400)
    auditoria.registrar(request, 'CREAR', paciente, paciente_id=paciente.pk,
                        detalle=f'Sugerencia de indicaciones con IA n.º {r["id"]}')
    return JsonResponse(r)


@login_required
@requiere('consultas.crear')
@require_POST
def guardar_en_glosario(request):
    """POST JSON con la ficha que propuso la IA (ya revisada) → Medicamento propio del profesional."""
    from decimal import Decimal, InvalidOperation

    from apps.clinica.models import Medicamento
    perfil = request.membresia.perfil_activo
    d = _json(request)
    if perfil is None or d is None or not (d.get('nombre') or '').strip():
        return _error('Datos inválidos.')

    def dec(campo):
        try:
            v = Decimal(str(d.get(campo) or '').replace(',', '.'))
        except InvalidOperation:
            return None
        return v if v > 0 else None

    def entero(campo):
        try:
            v = int(d.get(campo) or 0)
        except (TypeError, ValueError):
            return None
        return v or None
    unidades_kg = {u for u, _ in Medicamento.UNIDADES_KG}
    unidades = {u for u, _ in Medicamento.UNIDADES_RESULTADO}
    med = Medicamento.objects.create(
        profesional=perfil, nombre=d['nombre'].strip()[:150], presentacion=(d.get('presentacion') or '')[:120],
        modo=d.get('modo') if d.get('modo') in ('PESO', 'FIJA') else 'FIJA',
        unidad_kg=d.get('unidad_kg') if d.get('unidad_kg') in unidades_kg else 'mg',
        dosis_kg_min=dec('dosis_kg_min'), dosis_kg_max=dec('dosis_kg_max'), concentracion_mg=dec('concentracion_mg'),
        volumen_ml=dec('volumen_ml'), unidad_resultado=d.get('unidad_resultado') if d.get('unidad_resultado') in unidades
        else '', dosis_max=dec('dosis_max'), dosis_fija=(d.get('dosis_fija') or '')[:60],
        frecuencia_horas=entero('frecuencia_horas'), duracion_dias=entero('duracion_dias'), rangos_edad=[],
        indicaciones='', activo=True)
    auditoria.registrar(request, 'CREAR', med, detalle='Glosario: ficha sugerida por IA y aceptada')
    return JsonResponse({'id': med.pk, 'nombre': str(med)})
