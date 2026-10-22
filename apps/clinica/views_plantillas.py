"""Plantillas de historia y secciones personalizadas (Fase 06)."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.excepciones import ErrorDeNegocio
from apps.core.permisos import tiene_permiso

from . import esquemas, selectors, servicios
from .forms import CamposFormSet, NuevaPlantillaForm, SeccionPersonalizadaForm
from .formularios import FormularioSeccion
from .models import PlantillaSeccion, SeccionClinica


def _puede_ver(request):
    if not (tiene_permiso(request, 'plantillas.propias') or tiene_permiso(request, 'plantillas.clinica')):
        raise PermissionDenied


def _puede_editar(request, plantilla):
    if plantilla.profesional_id:
        perfil = request.membresia.perfil_activo if request.membresia else None
        return perfil is not None and perfil.pk == plantilla.profesional_id
    return tiene_permiso(request, 'plantillas.clinica')


def _plantilla_editable(request, pk):
    plantilla = get_object_or_404(selectors.plantillas_visibles(request.membresia), pk=pk)
    if not _puede_editar(request, plantilla):
        raise PermissionDenied
    return plantilla


@login_required
def plantillas(request):
    _puede_ver(request)
    perfil = request.membresia.perfil_activo
    visibles = selectors.plantillas_visibles(request.membresia)
    form = NuevaPlantillaForm(tenant=request.tenant, plantillas=visibles,
                              puede_clinica=tiene_permiso(request, 'plantillas.clinica'),
                              es_profesional=perfil is not None,
                              initial={'especialidad': perfil.especialidad if perfil else None})
    for p in visibles:
        p.editable = _puede_editar(request, p)
    return render(request, 'clinica/plantillas.html', {'titulo': 'Plantillas de historia', 'plantillas': visibles,
                                                       'form': form, 'perfil': perfil})


@login_required
@require_POST
def plantilla_nueva(request):
    _puede_ver(request)
    perfil = request.membresia.perfil_activo
    puede_clinica = tiene_permiso(request, 'plantillas.clinica')
    form = NuevaPlantillaForm(request.POST, tenant=request.tenant,
                              plantillas=selectors.plantillas_visibles(request.membresia),
                              puede_clinica=puede_clinica, es_profesional=perfil is not None)
    if not form.is_valid():
        messages.error(request, 'Revisa el nombre y la especialidad de la plantilla.')
        return redirect('clinica:plantillas')
    d = form.cleaned_data
    de_clinica = puede_clinica and (d.get('de_clinica') or perfil is None)
    if not de_clinica and perfil is None:
        raise PermissionDenied
    plantilla = servicios.crear_plantilla(nombre=d['nombre'], especialidad=d['especialidad'],
                                          profesional=None if de_clinica else perfil, copiar_de=d.get('copiar_de'))
    messages.success(request, f'Plantilla «{plantilla}» creada. Agrega y ordena sus secciones.')
    return redirect('clinica:plantilla', pk=plantilla.pk)


@login_required
def plantilla(request, pk):
    _puede_ver(request)
    p = get_object_or_404(selectors.plantillas_visibles(request.membresia), pk=pk)
    editable = _puede_editar(request, p)
    perfil = request.membresia.perfil_activo
    return render(request, 'clinica/plantilla.html', {
        'titulo': f'Historia · {p}', 'plantilla': p, 'items': selectors.items_de(p), 'editable': editable,
        'catalogo': selectors.catalogo_para(p, request.tenant) if editable else [],
        'puede_copiar': not editable and perfil is not None and tiene_permiso(request, 'plantillas.propias')})


@login_required
@require_POST
def plantilla_copiar(request, pk):
    """«Hacer mi copia»: la médica parte de una plantilla que no puede editar y la ajusta a su gusto."""
    _puede_ver(request)
    perfil = request.membresia.perfil_activo
    if perfil is None or not tiene_permiso(request, 'plantillas.propias'):
        raise PermissionDenied
    origen = get_object_or_404(selectors.plantillas_visibles(request.membresia), pk=pk)
    copia = servicios.crear_plantilla(nombre=f'{origen.nombre} (mía)'[:100], especialidad=origen.especialidad,
                                      profesional=perfil, copiar_de=origen)
    messages.success(request, f'Listo: «{copia}» es tuya. Marca o desmarca las secciones que quieras.')
    return redirect('clinica:plantilla', pk=copia.pk)


@login_required
@require_POST
def plantilla_accion(request, pk):
    p = _plantilla_editable(request, pk)
    accion = request.POST.get('accion')
    item = None
    if request.POST.get('item'):
        item = get_object_or_404(PlantillaSeccion.objects.filter(plantilla=p), pk=request.POST['item'])
    if accion == 'agregar':
        seccion = get_object_or_404(SeccionClinica.objects.visibles(request.tenant), pk=request.POST.get('seccion'))
        servicios.agregar_seccion(p, seccion)
    elif accion == 'quitar' and item:
        servicios.quitar_seccion(item)
    elif accion in ('subir', 'bajar') and item:
        servicios.mover_seccion(item, -1 if accion == 'subir' else 1)
    elif accion == 'predeterminada':
        servicios.marcar_predeterminada(p)
        messages.success(request, f'«{p}» es ahora la plantilla predeterminada.')
    elif accion == 'renombrar':
        nombre = request.POST.get('nombre', '').strip()
        if nombre:
            p.nombre = nombre[:100]
            p.save(update_fields=['nombre', 'actualizado_en'])
    elif accion == 'activa':
        if p.es_predeterminada and p.activa:
            raise ErrorDeNegocio('Marca otra plantilla como predeterminada antes de desactivar esta.')
        p.activa = not p.activa
        p.save(update_fields=['activa', 'actualizado_en'])
    destino = request.POST.get('volver') or ''
    ancla = request.POST.get('ancla', '')
    return redirect(destino if destino.startswith('/') and not destino.startswith('//') else
                    f'/plantillas/{p.pk}/' + (f'#{ancla}' if ancla.replace('-', '').isalnum() else ''))


@login_required
def plantilla_item(request, pk, item_pk):
    """Ajustes de una sección dentro de la plantilla: campos visibles, etiquetas, obligatorios y textos por defecto."""
    p = _plantilla_editable(request, pk)
    item = get_object_or_404(PlantillaSeccion.objects.filter(plantilla=p).select_related('seccion'), pk=item_pk)
    campos = [c for c in item.seccion.campos if c['tipo'] != 'calculado']
    if request.method == 'POST':
        ajustes = {
            'ocultos': [c['clave'] for c in campos if not request.POST.get(f'visible_{c["clave"]}')
                        and not c.get('requerido')],
            'etiquetas': {c['clave']: request.POST.get(f'etiqueta_{c["clave"]}', '') for c in campos
                          if request.POST.get(f'etiqueta_{c["clave"]}', '').strip() not in ('', c.get('etiqueta'))},
            'requeridos': [c['clave'] for c in campos if request.POST.get(f'requerido_{c["clave"]}')],
            'por_defecto': {c['clave']: request.POST.get(f'defecto_{c["clave"]}', '').strip() for c in campos
                            if c['tipo'] in ('texto', 'texto_largo')},
        }
        servicios.actualizar_item(item, obligatoria=bool(request.POST.get('obligatoria')),
                                  colapsada=bool(request.POST.get('colapsada')), ajustes=ajustes)
        messages.success(request, f'Ajustes de «{item.seccion}» guardados.')
        return redirect('clinica:plantilla', pk=p.pk)
    a = item.ajustes
    filas = [{'def': c, 'visible': c['clave'] not in a.get('ocultos', []),
              'etiqueta': (a.get('etiquetas') or {}).get(c['clave'], ''),
              'requerido': c.get('requerido') or c['clave'] in a.get('requeridos', []),
              'requerido_fijo': bool(c.get('requerido')),
              'defecto': (a.get('por_defecto') or {}).get(c['clave'], ''),
              'tipo_texto': esquemas.TIPOS.get(c['tipo'], c['tipo'])} for c in campos]
    return render(request, 'clinica/plantilla_item.html', {
        'titulo': f'{item.seccion} · {p}', 'plantilla': p, 'item': item, 'filas': filas})


@login_required
def plantilla_vista_previa(request, pk):
    """La historia tal como la verá el médico. Con «Probar» valida lo escrito sin guardar nada."""
    _puede_ver(request)
    p = get_object_or_404(selectors.plantillas_visibles(request.membresia), pk=pk)
    items = selectors.items_de(p)
    probado = request.method == 'POST'
    for item in items:
        item.form = FormularioSeccion(item.campos, request.POST if probado else None, prefix=f's{item.seccion_id}')
        if probado:
            item.valido = item.form.is_valid()
            item.resultado = [(c, esquemas.texto_valor(c, item.form.datos_limpios.get(c['clave'])))
                              for c in item.campos if item.form.datos_limpios.get(c['clave']) is not None] \
                if item.valido else []
    if probado:
        if all(i.valido for i in items):
            messages.success(request, 'Todo válido. Así se guardaría (no se guardó nada).')
        else:
            messages.warning(request, 'Hay campos por corregir (no se guardó nada).')
    return render(request, 'clinica/plantilla_vista_previa.html', {
        'titulo': f'Vista previa · {p}', 'plantilla': p, 'items': items, 'probado': probado})


# ── Secciones personalizadas ──────────────────────────────────────────────────

@login_required
def secciones(request):
    _puede_ver(request)
    return render(request, 'clinica/secciones.html', {
        'titulo': 'Secciones de historia', 'personalizadas': selectors.secciones_personalizadas(request.tenant),
        'catalogo': selectors.catalogo(request.tenant), 'puede_crear': tiene_permiso(request, 'plantillas.clinica')
        or tiene_permiso(request, 'plantillas.propias')})


def _campos_iniciales(seccion):
    filas = []
    for n, c in enumerate(seccion.campos):
        lineas = c.get('opciones') or [s.get('etiqueta', s['clave']) for s in c.get('subcampos', [])]
        filas.append({'clave': c['clave'], 'etiqueta': c.get('etiqueta', ''), 'tipo': c['tipo'],
                      'opciones': '\n'.join(o[1] if isinstance(o, (list, tuple)) else str(o) for o in lineas),
                      'unidad': c.get('unidad', ''), 'minimo': c.get('min'), 'maximo': c.get('max'),
                      'decimales': c.get('decimales'), 'ancho': esquemas.ancho(c),
                      'requerido': c.get('requerido', False), 'ayuda': c.get('ayuda', ''), 'orden': n})
    return filas


@login_required
def seccion_editar(request, pk=None):
    _puede_ver(request)
    seccion = None
    if pk is not None:
        seccion = get_object_or_404(SeccionClinica.objects.filter(tenant=request.tenant,
                                                                  tipo=SeccionClinica.Tipo.PERSONALIZADA), pk=pk)
    inicial = ({'nombre': seccion.nombre, 'descripcion': seccion.descripcion, 'ambito': seccion.ambito,
                'especialidad': seccion.especialidad} if seccion else
               {'especialidad': getattr(request.membresia.perfil_activo, 'especialidad', None)})
    form = SeccionPersonalizadaForm(request.POST or None, tenant=request.tenant, initial=inicial)
    formset = CamposFormSet(request.POST or None, prefix='campos',
                            initial=_campos_iniciales(seccion) if seccion else [{'ancho': 6, 'tipo': 'texto'}])
    if request.method == 'POST' and form.is_valid() and formset.is_valid():
        campos = [f.cleaned_data for f in formset.forms
                  if f.cleaned_data and not f.cleaned_data.get('DELETE')]
        campos.sort(key=lambda c: c.get('orden') if c.get('orden') is not None else 999)
        d = form.cleaned_data
        try:
            seccion = servicios.guardar_seccion_personalizada(
                seccion=seccion, nombre=d['nombre'], ambito=d['ambito'], especialidad=d['especialidad'],
                descripcion=d['descripcion'], campos=campos)
        except ErrorDeNegocio as e:
            messages.error(request, str(e))
        else:
            messages.success(request, f'Sección «{seccion}» guardada (versión {seccion.version}). '
                                      'Agrégala a tus plantillas para usarla.')
            return redirect('clinica:secciones')
    return render(request, 'clinica/seccion_form.html', {
        'titulo': f'Sección · {seccion}' if seccion else 'Nueva sección', 'form': form, 'formset': formset,
        'seccion': seccion})


@login_required
def seccion_vista(request, pk):
    _puede_ver(request)
    seccion = get_object_or_404(SeccionClinica.objects.visibles(request.tenant), pk=pk)
    form = FormularioSeccion(esquemas.campos_efectivos(seccion.esquema), prefix='s')
    return render(request, 'clinica/seccion_vista.html', {'titulo': str(seccion), 'seccion': seccion, 'form': form})


@login_required
@require_POST
def seccion_activa(request, pk):
    if not tiene_permiso(request, 'plantillas.clinica'):
        raise PermissionDenied
    seccion = get_object_or_404(SeccionClinica.objects.filter(tenant=request.tenant), pk=pk)
    seccion.activa = not seccion.activa
    seccion.save(update_fields=['activa', 'actualizado_en'])
    return redirect('clinica:secciones')

