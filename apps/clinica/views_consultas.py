"""Consulta clínica: abrir, llenar con la plantilla, cerrar, enmendar, anular, imprimir y adjuntos (Fase 07)."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html_join
from django.views.decorators.http import require_POST

from apps.configuracion.models import Lugar
from apps.core import auditoria
from apps.core.excepciones import ErrorDeNegocio
from apps.core.permisos import requiere
from apps.dictado.views import vincular as vincular_dictado
from apps.pacientes.models import Paciente, normalizar_texto

from . import consultas as srv
from . import registro
from .formularios import FormularioSeccion
from .models import Adjunto, Cie10, Consulta, PlantillaHistoria

MAX_ADJUNTO = 10 * 1024 * 1024


def _consulta_visible(request, pk):
    consulta = get_object_or_404(Consulta.objects.select_related(
        'paciente', 'profesional__membresia__usuario', 'especialidad', 'tenant__configuracion', 'lugar'), pk=pk)
    if not srv.puede_ver(request.membresia, consulta):
        auditoria.registrar(request, 'EXCEPCION', consulta, paciente_id=consulta.paciente_id,
                            detalle='Intento de ver una consulta sin permiso')
        raise PermissionDenied
    return consulta


def _formularios(consulta, data=None):
    guardados = srv.datos_guardados(consulta)
    contexto = srv.contexto_calculo(consulta)
    formularios = []
    for item in consulta.estructura:
        valores = guardados.get(item['seccion_id'])
        if valores is None and item['ambito'] != 'PACIENTE' and registro.inicial(item['codigo']):
            valores = registro.inicial(item['codigo'])(consulta)
        form = FormularioSeccion(item['campos'], data, initial=valores or {},
                                 prefix=f's{item["seccion_id"]}', contexto=contexto, exigir_requeridos=False)
        formularios.append((item, form))
    return formularios


def _aviso_control(request, consulta, desde):
    """Avisa si al guardar se creó o movió la cita tentativa del próximo control."""
    from apps.agenda.models import Cita
    cita = Cita.objects.filter(consulta_origen=consulta, actualizado_en__gte=desde).order_by('-actualizado_en').first()
    if cita is not None:
        messages.info(request, f'Próximo control: cita tentativa (sin hora) el {cita.fecha:%d/%m/%Y}. '
                               'La asistente le asigna la hora desde la agenda.')


def _inicio(texto):
    """Hora en que el médico abrió el formulario (la manda el navegador); se acepta si es de las últimas 72 h."""
    from datetime import datetime, timedelta

    from django.utils import timezone
    try:
        momento = datetime.fromisoformat((texto or '').replace('Z', '+00:00'))
    except ValueError:
        return None
    if timezone.is_naive(momento):
        momento = timezone.make_aware(momento)
    ahora = timezone.now()
    return momento if ahora - timedelta(hours=72) <= momento <= ahora + timedelta(minutes=10) else None


@login_required
@requiere('consultas.crear')
def nueva(request, paciente_pk):
    """
    GET: formulario completo de una consulta nueva (aún no existe; se puede llenar sin conexión).
    POST con `completa`: crea la consulta con todo lo llenado. POST sin `completa` (compatibilidad):
    abre la consulta en curso y lleva a editarla.
    """
    from apps.agenda.models import Cita
    from apps.pacientes.selectors import puede_ver_paciente
    paciente = get_object_or_404(Paciente.objects.all(), pk=paciente_pk)
    if not puede_ver_paciente(request.membresia, paciente):
        raise PermissionDenied
    perfil = request.membresia.perfil_activo
    datos = request.POST if request.method == 'POST' else request.GET
    cita = None
    if (datos.get('cita') or '').isdigit():
        cita = Cita.objects.select_related('tipo__plantilla', 'lugar').filter(
            pk=datos['cita'], paciente=paciente, profesional=perfil).first()
    plantilla = None
    if (datos.get('plantilla') or '').isdigit():
        plantilla = get_object_or_404(PlantillaHistoria.objects.filter(activa=True), pk=datos['plantilla'])
    elif cita is not None and cita.tipo_id and cita.tipo.plantilla_id and cita.tipo.plantilla.activa:
        plantilla = cita.tipo.plantilla
    lugar = Lugar.objects.filter(pk=datos.get('lugar') or 0).first() or (cita.lugar if cita else None)
    tipo = datos.get('tipo') if datos.get('tipo') in Consulta.Tipo.values else (
        cita.tipo.tipo_consulta if cita is not None and cita.tipo_id else Consulta.Tipo.PRIMERA)

    if request.method == 'POST' and not request.POST.get('completa'):
        consulta = srv.abrir_consulta(paciente=paciente, profesional=perfil, plantilla=plantilla, tipo=tipo,
                                      lugar=lugar)
        auditoria.registrar(request, 'CREAR', consulta, paciente_id=paciente.pk)
        return redirect('clinica:consulta_editar', pk=consulta.pk)
    if request.method == 'GET' and cita is not None and cita.consulta_id:
        messages.info(request, 'Esta cita ya se atendió.')
        return redirect('clinica:consulta', pk=cita.consulta_id)

    consulta = srv.consulta_nueva(paciente=paciente, profesional=perfil, plantilla=plantilla, tipo=tipo, lugar=lugar)
    formularios = _formularios(consulta, request.POST if request.method == 'POST' else None)
    if request.method == 'POST':
        if all(f.is_valid() for _, f in formularios):
            accion = request.POST.get('accion')
            if cita is not None and cita.consulta_id:
                messages.warning(request, 'La cita ya tenía una consulta: esta se guardó aparte.')
            desde = timezone.now()
            creada = srv.crear_consulta_completa(
                paciente=paciente, profesional=perfil, plantilla=consulta.plantilla, tipo=tipo, lugar=lugar,
                datos_por_seccion={item['seccion_id']: f.datos_limpios for item, f in formularios}, cita=cita,
                fecha_hora=_inicio(request.POST.get('inicio')), cerrar=accion == 'cerrar', usuario=request.user)
            auditoria.registrar(request, 'CREAR', creada, paciente_id=paciente.pk)
            vincular_dictado(request, creada)
            _aviso_control(request, creada, desde)
            if creada.estado == Consulta.Estado.CERRADA:
                messages.success(request, 'Consulta guardada y cerrada.')
                return redirect('clinica:consulta', pk=creada.pk)
            if accion == 'cerrar':
                messages.warning(request, 'Guardada, pero no se cerró. Falta: ' + ', '.join(srv.faltantes(creada)))
            else:
                messages.success(request, 'Consulta guardada.')
            return redirect('clinica:consulta_editar', pk=creada.pk)
        messages.error(request, 'Revisa los campos marcados en rojo; no se guardó nada.')
    from .selectors import consultas_visibles
    return render(request, 'clinica/consulta_form.html', {
        'titulo': f'Nueva consulta · {paciente}', 'consulta': consulta, 'formularios': formularios, 'nueva': True,
        'cita': cita, 'previas': consultas_visibles(request, paciente)[:5],
        'accesos': registro.accesos_consulta(consulta.especialidad.codigo, paciente),
        'dictado': _dictado(request),
        'antecedentes': getattr(paciente, 'antecedentes', None), 'faltan': [], **_glosario(request, paciente)})


@login_required
@requiere('historia.ver')
def editar(request, pk):
    consulta = _consulta_visible(request, pk)
    if not srv.puede_editar(request.membresia, consulta):
        return redirect('clinica:consulta', pk=pk)
    formularios = _formularios(consulta, request.POST if request.method == 'POST' else None)
    if request.method == 'POST':
        if all(f.is_valid() for _, f in formularios):
            desde = timezone.now()
            srv.guardar_secciones(consulta, {item['seccion_id']: f.datos_limpios for item, f in formularios})
            auditoria.registrar(request, 'EDITAR', consulta, paciente_id=consulta.paciente_id)
            vincular_dictado(request, consulta)
            _aviso_control(request, consulta, desde)
            if request.POST.get('accion') == 'cerrar':
                try:
                    srv.cerrar_consulta(consulta, request.user)
                except ErrorDeNegocio as e:
                    messages.warning(request, f'Guardada, pero no se cerró. {e}')
                    return redirect('clinica:consulta_editar', pk=pk)
                auditoria.registrar(request, 'CERRAR', consulta, paciente_id=consulta.paciente_id)
                messages.success(request, 'Consulta cerrada.')
                return redirect('clinica:consulta', pk=pk)
            messages.success(request, 'Consulta guardada.')
            return redirect('clinica:consulta_editar', pk=pk)
        messages.error(request, 'Revisa los campos marcados en rojo; no se guardó nada.')
    from .selectors import consultas_visibles
    previas = [c for c in consultas_visibles(request, consulta.paciente) if c.pk != consulta.pk][:5]
    antecedentes = getattr(consulta.paciente, 'antecedentes', None)
    return render(request, 'clinica/consulta_form.html', {
        'titulo': f'Consulta · {consulta.paciente}', 'consulta': consulta, 'formularios': formularios,
        'previas': previas, 'antecedentes': antecedentes, 'faltan': srv.faltantes(consulta),
        'accesos': registro.accesos_consulta(consulta.especialidad.codigo, consulta.paciente),
        'dictado': _dictado(request),
        **_glosario(request, consulta.paciente)})


@login_required
@requiere('historia.ver')
def detalle(request, pk):
    consulta = _consulta_visible(request, pk)
    auditoria.registrar(request, 'VER', consulta, paciente_id=consulta.paciente_id)
    lectura = srv.lectura(consulta)
    con_datos = {item['seccion_id'] for item, _ in lectura}
    return render(request, 'clinica/consulta.html', {
        'titulo': f'Consulta · {consulta.paciente}', 'consulta': consulta, 'lectura': lectura,
        'vacias': [i for i in consulta.estructura if i['seccion_id'] not in con_datos],
        'es_autor': request.membresia.perfil_activo and consulta.profesional_id == request.membresia.perfil_activo.pk,
        'enmiendas': consulta.enmiendas.select_related('seccion', 'creado_por'),
        'adjuntos': consulta.adjuntos.all(), 'notas': consulta.notas_evolucion.select_related('creado_por'),
        'hoy': timezone.localdate()})


@login_required
@requiere('historia.ver')
def imprimir(request, pk):
    """Historia de la consulta lista para imprimir o guardar como PDF desde el navegador."""
    consulta = _consulta_visible(request, pk)
    auditoria.registrar(request, 'IMPRIMIR', consulta, paciente_id=consulta.paciente_id)
    return render(request, 'clinica/consulta_imprimir.html', {
        'consulta': consulta, 'lectura': srv.lectura(consulta), 'config': request.tenant.configuracion,
        'enmiendas': consulta.enmiendas.select_related('seccion')})


@login_required
@requiere('historia.ver')
def enmendar(request, pk, seccion_id):
    consulta = _consulta_visible(request, pk)
    perfil = request.membresia.perfil_activo
    if consulta.profesional_id != perfil.pk or consulta.estado != Consulta.Estado.CERRADA:
        raise PermissionDenied
    item = next((i for i in consulta.estructura if i['seccion_id'] == seccion_id), None)
    if item is None:
        raise Http404
    form = FormularioSeccion(item['campos'], request.POST or None,
                             initial=srv.datos_guardados(consulta).get(seccion_id) or {},
                             prefix=f's{seccion_id}', contexto=srv.contexto_calculo(consulta))
    if request.method == 'POST' and form.is_valid():
        try:
            srv.enmendar(consulta, seccion_id, form.datos_limpios, request.POST.get('motivo'))
        except ErrorDeNegocio as e:
            messages.error(request, str(e))
        else:
            auditoria.registrar(request, 'ENMENDAR', consulta, paciente_id=consulta.paciente_id,
                                detalle=item['nombre'])
            messages.success(request, 'Enmienda registrada.')
            return redirect('clinica:consulta', pk=pk)
    return render(request, 'clinica/consulta_enmendar.html', {
        'titulo': f'Enmendar · {item["nombre"]}', 'consulta': consulta, 'item': item, 'form': form})


@login_required
@requiere('historia.ver')
@require_POST
def anular(request, pk):
    consulta = _consulta_visible(request, pk)
    if consulta.profesional_id != request.membresia.perfil_activo.pk:
        raise PermissionDenied
    srv.anular_consulta(consulta, request.POST.get('motivo'))
    auditoria.registrar(request, 'ANULAR', consulta, paciente_id=consulta.paciente_id,
                        detalle=request.POST.get('motivo', ''))
    messages.success(request, 'Consulta anulada. Queda en la historia marcada como anulada.')
    return redirect('pacientes:detalle', pk=consulta.paciente_id)


@login_required
@requiere('historia.ver')
@require_POST
def adjuntar(request, pk):
    consulta = _consulta_visible(request, pk)
    archivo = request.FILES.get('archivo')
    if not archivo:
        messages.error(request, 'Elige un archivo.')
    elif archivo.size > MAX_ADJUNTO:
        messages.error(request, 'El archivo supera 10 MB.')
    else:
        Adjunto.objects.create(paciente=consulta.paciente, consulta=consulta, archivo=archivo,
                               nombre=(request.POST.get('nombre') or archivo.name)[:200],
                               tipo_contenido=getattr(archivo, 'content_type', '')[:100], tamano=archivo.size)
        messages.success(request, 'Archivo adjuntado.')
    return redirect('clinica:consulta', pk=pk)


@login_required
@requiere('historia.ver')
def adjunto(request, pk):
    """Los adjuntos solo se entregan por aquí, con permiso y auditoría (ADR-017)."""
    a = get_object_or_404(Adjunto.objects.select_related('consulta'), pk=pk)
    if a.consulta and not srv.puede_ver(request.membresia, a.consulta):
        raise PermissionDenied
    auditoria.registrar(request, 'VER', a, paciente_id=a.paciente_id)
    respuesta = FileResponse(a.archivo.open('rb'), content_type=a.tipo_contenido or 'application/octet-stream')
    respuesta['Content-Disposition'] = f'inline; filename="{a.nombre}"'
    respuesta['Cache-Control'] = 'no-store'
    return respuesta


@login_required
@requiere('historia.ver')
def cie10(request):
    """Opciones para el campo de diagnóstico: <option value="J06.9 · Infección…">."""
    q = normalizar_texto(request.GET.get('q', ''))
    opciones = []
    if len(q) >= 2:
        qs = Cie10.objects.all()
        for palabra in q.split():
            qs = qs.filter(busqueda__contains=palabra)
        opciones = qs[:20]
    return HttpResponse(format_html_join('', '<option value="{} · {}"></option>',
                                         ((c.codigo, c.descripcion) for c in opciones)))


@login_required
@requiere('historia.ver')
def ficha_especialidad(request, paciente_pk, codigo):
    """Ficha de la especialidad del paciente (p. ej. ficha pediátrica) fuera de la consulta, como en Pediae."""
    from apps.pacientes.selectors import puede_ver_paciente
    from apps.plataforma.models import Especialidad
    paciente = get_object_or_404(Paciente.objects.all(), pk=paciente_pk)
    if not puede_ver_paciente(request.membresia, paciente):
        raise PermissionDenied
    especialidad = get_object_or_404(Especialidad.objects.filter(activa=True), codigo=codigo)
    items = srv.items_ficha(codigo)
    if not items:
        raise Http404
    puede_editar = request.membresia.perfil_activo is not None
    guardados = srv.datos_ficha(paciente, items)
    datos = request.POST if request.method == 'POST' and puede_editar else None
    formularios = [(i, FormularioSeccion(i['campos'], datos, initial=guardados.get(i['seccion_id']) or {},
                                         prefix=f's{i["seccion_id"]}', exigir_requeridos=False)) for i in items]
    if datos is not None:
        if all(f.is_valid() for _, f in formularios):
            srv.guardar_ficha(paciente, items, {i['seccion_id']: f.datos_limpios for i, f in formularios})
            auditoria.registrar(request, 'EDITAR', paciente, paciente_id=paciente.pk,
                                detalle=f'Ficha de {especialidad.nombre}')
            messages.success(request, f'Ficha de {especialidad.nombre.lower()} guardada.')
            return redirect('pacientes:detalle', pk=paciente.pk)
        messages.error(request, 'Revisa los campos marcados en rojo; no se guardó nada.')
    else:
        auditoria.registrar(request, 'VER', paciente, paciente_id=paciente.pk, detalle=f'Ficha de {especialidad.nombre}')
    return render(request, 'clinica/ficha_especialidad.html', {
        'titulo': f'Ficha de {especialidad.nombre.lower()} · {paciente}', 'paciente': paciente,
        'especialidad': especialidad, 'formularios': formularios, 'puede_editar': puede_editar})


def _glosario(request, paciente):
    """Medicamentos activos del glosario y edad en meses para la calculadora de dosis del récipe."""
    from apps.core.fechas import edad_meses

    from .views_medicamentos import visibles
    meds = visibles(request).filter(activo=True).order_by('nombre').only('pk', 'nombre', 'presentacion')
    return {'glosario': list(meds),
            'edad_meses': edad_meses(paciente.fecha_nacimiento) if paciente.fecha_nacimiento else ''}


@login_required
@requiere('historia.ver')
@require_POST
def calcular(request):
    """Vista previa de los campos calculados de una sección (percentiles, IMC, EG, FPP…) mientras se escribe."""
    from django.http import JsonResponse
    from django.utils.dateparse import parse_date

    from apps.core.fechas import edad_meses

    from . import esquemas
    from .models import SeccionClinica
    prefijo = request.POST.get('_prefijo', '')
    if not (prefijo.startswith('s') and prefijo[1:].isdigit()):
        return JsonResponse({}, status=400)
    seccion = get_object_or_404(SeccionClinica.objects.visibles(), pk=int(prefijo[1:]))
    contexto = {}
    pk = request.POST.get('_paciente')
    if pk and pk.isdigit():
        paciente = get_object_or_404(Paciente.objects.all(), pk=pk)
        fecha = parse_date(request.POST.get('_fecha') or '') or timezone.localdate()
        contexto = {'paciente': paciente, 'sexo': paciente.sexo, 'fecha': fecha,
                    'edad_meses': edad_meses(paciente.fecha_nacimiento, fecha)}
    try:                                    # superficie corporal de la consulta (volúmenes indexados)
        sc = float((request.POST.get('_sc') or '').replace(',', '.').split()[0])
        if 0 < sc < 4:
            contexto['sc'] = sc
    except (ValueError, IndexError):
        pass
    campos = esquemas.campos_efectivos(seccion.esquema)
    form = FormularioSeccion(campos, request.POST, prefix=prefijo, contexto=contexto, exigir_requeridos=False)
    form.is_valid()
    limpios = getattr(form, 'datos_limpios', {}) or {}
    return JsonResponse({c['clave']: esquemas.texto_valor(c, limpios.get(c['clave']))
                         for c in campos if c['tipo'] == 'calculado'})


@login_required
@requiere('consultas.crear')
@require_POST
def nota_evolucion(request, pk):
    """Agrega una nota de evolución con fecha (la consulta puede estar cerrada: no la modifica)."""
    from datetime import date

    from .models import NotaEvolucion
    consulta = _consulta_visible(request, pk)
    texto = (request.POST.get('texto') or '').strip()
    if consulta.estado == Consulta.Estado.ANULADA or not texto:
        messages.error(request, 'Escribe la nota.' if not texto else 'La consulta está anulada.')
        return redirect('clinica:consulta', pk=pk)
    try:
        fecha = date.fromisoformat(request.POST.get('fecha') or '')
    except ValueError:
        fecha = timezone.localdate()
    nota = NotaEvolucion.objects.create(consulta=consulta, paciente=consulta.paciente, fecha=fecha, texto=texto[:2000])
    auditoria.registrar(request, 'CREAR', nota, paciente_id=consulta.paciente_id, detalle='Nota de evolución')
    messages.success(request, 'Nota de evolución agregada.')
    return redirect(f"{reverse('clinica:consulta', args=[pk])}#evolucion")


@login_required
@requiere('consultas.crear')
@require_POST
def nota_evolucion_eliminar(request, pk, nota_pk):
    from .models import NotaEvolucion
    consulta = _consulta_visible(request, pk)
    nota = get_object_or_404(NotaEvolucion.objects.filter(consulta=consulta), pk=nota_pk)
    if nota.creado_por_id != request.user.pk:
        raise PermissionDenied
    auditoria.registrar(request, 'ANULAR', nota, paciente_id=consulta.paciente_id, detalle='Quitó nota de evolución')
    nota.delete()
    messages.success(request, 'Nota eliminada.')
    return redirect(f"{reverse('clinica:consulta', args=[pk])}#evolucion")


def _dictado(request):
    """¿Se muestra «Dictar consulta»? Solo a profesionales y si la plataforma lo activó para el consultorio."""
    from apps.dictado import servicios as dictado
    if request.membresia.perfil_activo is None or not request.tenant.configuracion.dictado_activo:
        return None
    limite = dictado.limite_minutos(request.tenant)
    usados = dictado.minutos_usados(request.tenant)
    return {'limite': limite, 'usados': usados, 'agotado': bool(limite and usados >= limite)}
