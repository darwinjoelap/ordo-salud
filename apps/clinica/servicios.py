"""
Servicios del motor de historia: catálogo de secciones, plantillas y secciones personalizadas (Fase 06).
"""
import logging

from django.db import transaction

from apps.core.excepciones import ErrorDeNegocio
from apps.core.tenancy import tenant_actual, usuario_actual

from . import registro
from .esquemas import ErrorEsquema, asegurar_valido, slug_clave
from .models import PlantillaHistoria, PlantillaSeccion, SeccionClinica, SeccionClinicaVersion

log = logging.getLogger('apps.clinica')


# ── Catálogo del sistema ──────────────────────────────────────────────────────

@transaction.atomic
def sincronizar_catalogo(verbosidad=1):
    """Copia el registro (núcleo + módulos instalados) a Especialidad y SeccionClinica. Idempotente."""
    from apps.plataforma.models import Especialidad
    especialidades = {}
    for codigo, e in registro.especialidades().items():
        obj, creada = Especialidad.objects.update_or_create(codigo=codigo, defaults={
            'nombre': e.nombre, 'color': e.color, 'icono': e.icono, 'orden': e.orden, 'modulo': e.modulo})
        especialidades[codigo] = obj
        if creada and verbosidad:
            log.info('Especialidad registrada: %s', e.nombre)
    for codigo, s in registro.secciones().items():
        defaults = {'nombre': s.nombre, 'descripcion': s.descripcion, 'tipo': s.tipo, 'ambito': s.ambito,
                    'orden': s.orden, 'especialidad': especialidades.get(s.especialidad)}
        actual = SeccionClinica.objects.filter(tenant__isnull=True, codigo=codigo).first()
        if actual is None:
            SeccionClinica.objects.create(codigo=codigo, version=s.version, esquema=s.esquema, **defaults)
            continue
        if actual.version != s.version or actual.esquema != s.esquema:
            if actual.version != s.version:
                SeccionClinicaVersion.objects.get_or_create(seccion=actual, version=actual.version,
                                                            defaults={'esquema': actual.esquema})
            actual.version, actual.esquema = s.version, s.esquema
        for campo, valor in defaults.items():
            setattr(actual, campo, valor)
        actual.activa = True
        actual.save()
    # Secciones del sistema que ya no están registradas (módulo desinstalado): se desactivan, no se borran
    SeccionClinica.objects.filter(tenant__isnull=True).exclude(codigo__in=registro.secciones().keys()) \
        .update(activa=False)


def actualizar_plantillas_de_modulos():
    """
    Tras instalar o actualizar un módulo de especialidad (post_migrate): los consultorios que ya tenían esa
    especialidad reciben las plantillas nuevas del módulo. Las plantillas iniciales que el módulo ya no ofrece (p. ej.
    las de la especialidad «básica») se desactivan —no se borran: las consultas viejas conservan su estructura— y la
    predeterminada pasa a la del módulo. Idempotente.
    """
    from apps.core.tenancy import usando_tenant
    from apps.plataforma.models import Tenant
    modulos = {c: e for c, e in registro.especialidades().items() if not e.basica and e.plantillas}
    if not modulos:
        return
    for tenant in Tenant.objects.filter(especialidades__codigo__in=modulos.keys()).distinct():
        with usando_tenant(tenant):
            for especialidad in tenant.especialidades.filter(codigo__in=modulos.keys()):
                definicion = modulos[especialidad.codigo]
                vigentes = {f'{especialidad.codigo}:{p.nombre}' for p in definicion.plantillas}
                viejas = (PlantillaHistoria.objects.filter(especialidad=especialidad, profesional__isnull=True,
                                                           activa=True, origen__startswith=f'{especialidad.codigo}:')
                          .exclude(origen__in=vigentes))
                if not viejas.exists() and PlantillaHistoria.objects.filter(
                        especialidad=especialidad, origen__in=vigentes).count() == len(vigentes):
                    continue
                nueva = next((p for p in definicion.plantillas if p.predeterminada), definicion.plantillas[0])
                origen_nueva = f'{especialidad.codigo}:{nueva.nombre}'
                existia = PlantillaHistoria.objects.filter(especialidad=especialidad, origen=origen_nueva).exists()
                cambia_predeterminada = viejas.filter(es_predeterminada=True).exists() or not existia
                viejas.update(activa=False, es_predeterminada=False)
                asegurar_plantillas_especialidad(especialidad)
                if cambia_predeterminada:       # la predeterminada nueva del módulo pasa a ser la del consultorio
                    sistema = PlantillaHistoria.objects.filter(especialidad=especialidad, profesional__isnull=True)
                    sistema.update(es_predeterminada=False)
                    sistema.filter(origen=origen_nueva).update(es_predeterminada=True, activa=True)
                log.info('%s: plantillas de %s actualizadas.', tenant.nombre, especialidad.nombre)


def refrescar_plantillas_sistema(especialidad):
    """
    Rehace, en el consultorio activo, las plantillas iniciales de la especialidad tal como las define hoy su módulo
    (orden, secciones, ajustes). Las plantillas propias de cada médico no se tocan; las consultas ya abiertas tampoco
    (su estructura está congelada). Se pierden los cambios hechos a mano sobre las plantillas del sistema.
    Devuelve cuántas plantillas rehízo.
    """
    asegurar_plantillas_especialidad(especialidad)
    hechas = 0
    for definicion in _definiciones_plantillas(especialidad):
        plantilla = PlantillaHistoria.objects.filter(especialidad=especialidad, profesional__isnull=True,
                                                     origen=f'{especialidad.codigo}:{definicion.nombre}').first()
        if plantilla is None:
            continue
        plantilla.items.all().delete()
        for orden, item in enumerate(definicion.secciones, 1):
            codigo, opciones = (item, {}) if isinstance(item, str) else item
            seccion = SeccionClinica.objects.filter(tenant__isnull=True, codigo=codigo, activa=True).first()
            if seccion is None:
                continue
            PlantillaSeccion.objects.create(plantilla=plantilla, seccion=seccion, orden=orden * 10,
                                            obligatoria=opciones.get('obligatoria', False),
                                            colapsada=opciones.get('colapsada', False),
                                            ajustes=opciones.get('ajustes', {}))
        plantilla.descripcion = definicion.descripcion
        plantilla.activa = True
        plantilla.save()
        hechas += 1
    return hechas


def _definiciones_plantillas(especialidad):
    definicion = registro.especialidad(especialidad.codigo)
    return (definicion.plantillas if definicion and definicion.plantillas else registro.plantillas_nucleo())


@transaction.atomic
def asegurar_plantillas_especialidad(especialidad):
    """
    Copia al tenant activo las plantillas iniciales de la especialidad (si aún no las tiene).
    Se llama al habilitar una especialidad y al crear un profesional.
    """
    if tenant_actual() is None:
        raise ErrorDeNegocio('Se necesita un consultorio activo para crear plantillas.')
    existentes = PlantillaHistoria.objects.filter(especialidad=especialidad, profesional__isnull=True)
    hay_predeterminada = existentes.filter(es_predeterminada=True).exists()
    for definicion in _definiciones_plantillas(especialidad):
        origen = f'{especialidad.codigo}:{definicion.nombre}'
        if existentes.filter(origen=origen).exists():
            continue
        plantilla = PlantillaHistoria.objects.create(
            nombre=definicion.nombre, descripcion=definicion.descripcion, especialidad=especialidad, origen=origen,
            es_predeterminada=definicion.predeterminada and not hay_predeterminada)
        hay_predeterminada = hay_predeterminada or plantilla.es_predeterminada
        for orden, item in enumerate(definicion.secciones, 1):
            codigo, opciones = (item, {}) if isinstance(item, str) else item
            seccion = SeccionClinica.objects.filter(tenant__isnull=True, codigo=codigo, activa=True).first()
            if seccion is None:
                log.warning('Plantilla %s: la sección %s no existe en el catálogo.', origen, codigo)
                continue
            PlantillaSeccion.objects.create(plantilla=plantilla, seccion=seccion, orden=orden * 10,
                                            obligatoria=opciones.get('obligatoria', False),
                                            colapsada=opciones.get('colapsada', False),
                                            ajustes=opciones.get('ajustes', {}))
    if not hay_predeterminada:
        primera = existentes.order_by('id').first()
        if primera:
            primera.es_predeterminada = True
            primera.save(update_fields=['es_predeterminada', 'actualizado_en'])


# ── Plantillas ────────────────────────────────────────────────────────────────

def _validar_seccion_usable(seccion, especialidad):
    tenant = tenant_actual()
    if seccion.tenant_id not in (None, tenant.pk):
        raise ErrorDeNegocio('Esa sección no pertenece a este consultorio.')
    if not seccion.activa:
        raise ErrorDeNegocio('Esa sección está desactivada.')
    if seccion.especialidad_id and not tenant.especialidades.filter(pk=seccion.especialidad_id).exists():
        raise ErrorDeNegocio(f'La sección «{seccion}» es de una especialidad no habilitada en el consultorio.')


@transaction.atomic
def crear_plantilla(*, nombre, especialidad, profesional=None, copiar_de=None, descripcion=''):
    tenant = tenant_actual()
    if not tenant.especialidades.filter(pk=especialidad.pk).exists():
        raise ErrorDeNegocio('Esa especialidad no está habilitada en el consultorio.')
    plantilla = PlantillaHistoria.objects.create(nombre=nombre.strip(), descripcion=descripcion,
                                                 especialidad=especialidad, profesional=profesional)
    if copiar_de is not None:
        for item in copiar_de.items.all():
            PlantillaSeccion.objects.create(plantilla=plantilla, seccion=item.seccion, orden=item.orden,
                                            obligatoria=item.obligatoria, colapsada=item.colapsada,
                                            ajustes=dict(item.ajustes))
    if not PlantillaHistoria.objects.filter(especialidad=especialidad, profesional=profesional,
                                            es_predeterminada=True).exclude(pk=plantilla.pk).exists():
        plantilla.es_predeterminada = True
        plantilla.save(update_fields=['es_predeterminada'])
    return plantilla


@transaction.atomic
def marcar_predeterminada(plantilla):
    PlantillaHistoria.objects.filter(especialidad=plantilla.especialidad, profesional=plantilla.profesional) \
        .exclude(pk=plantilla.pk).update(es_predeterminada=False)
    plantilla.es_predeterminada = True
    plantilla.activa = True
    plantilla.save(update_fields=['es_predeterminada', 'activa', 'actualizado_en'])


@transaction.atomic
def agregar_seccion(plantilla, seccion):
    _validar_seccion_usable(seccion, plantilla.especialidad)
    if plantilla.items.filter(seccion=seccion).exists():
        raise ErrorDeNegocio(f'«{seccion}» ya está en la plantilla.')
    # Entra en su lugar natural (según el orden del catálogo), no al final: así casi nunca hay que moverla.
    items = list(plantilla.items.select_related('seccion').order_by('orden', 'id'))
    pos = next((n for n, i in enumerate(items) if i.seccion.orden > seccion.orden), len(items))
    nuevo = PlantillaSeccion(plantilla=plantilla, seccion=seccion)
    items.insert(pos, nuevo)
    for n, i in enumerate(items, 1):
        i.orden = n * 10
        if i is nuevo:
            i.save()
        else:
            PlantillaSeccion.objects.filter(pk=i.pk).update(orden=i.orden)
    return nuevo


@transaction.atomic
def quitar_seccion(item):
    item.delete()


@transaction.atomic
def mover_seccion(item, direccion):
    """direccion: -1 (subir) o +1 (bajar). Reordena de 10 en 10."""
    items = list(item.plantilla.items.order_by('orden', 'id'))
    i = next(n for n, x in enumerate(items) if x.pk == item.pk)
    j = i + (1 if direccion > 0 else -1)
    if 0 <= j < len(items):
        items[i], items[j] = items[j], items[i]
    for n, x in enumerate(items, 1):
        if x.orden != n * 10:
            x.orden = n * 10
            x.save(update_fields=['orden'])


@transaction.atomic
def actualizar_item(item, *, obligatoria, colapsada, ajustes):
    claves = {c['clave'] for c in item.seccion.campos}
    limpio = {
        'ocultos': [c for c in ajustes.get('ocultos', []) if c in claves],
        'etiquetas': {c: str(v).strip()[:120] for c, v in (ajustes.get('etiquetas') or {}).items()
                      if c in claves and str(v).strip()},
        'por_defecto': {c: v for c, v in (ajustes.get('por_defecto') or {}).items()
                        if c in claves and v not in ('', None)},
        'requeridos': [c for c in ajustes.get('requeridos', []) if c in claves],
    }
    item.obligatoria, item.colapsada = obligatoria, colapsada
    item.ajustes = {k: v for k, v in limpio.items() if v}
    item.save(update_fields=['obligatoria', 'colapsada', 'ajustes'])
    return item


# ── Secciones personalizadas ──────────────────────────────────────────────────

def armar_esquema(campos_formulario, claves_existentes=None):
    """
    De la lista que arma el editor (etiqueta, tipo, opciones…) al esquema JSON. Conserva la clave de los campos
    que ya existían (para no perder datos guardados) y crea claves nuevas a partir de la etiqueta.
    """
    usadas, campos = set(), []
    claves_existentes = set(claves_existentes or [])
    for c in campos_formulario:
        clave = c.get('clave') if c.get('clave') in claves_existentes else None
        clave = clave or slug_clave(c['etiqueta'], usadas | claves_existentes)
        usadas.add(clave)
        campo = {'clave': clave, 'tipo': c['tipo'], 'etiqueta': c['etiqueta'].strip()}
        for opcional in ('ayuda', 'unidad'):
            if c.get(opcional):
                campo[opcional] = c[opcional].strip()
        if c.get('requerido'):
            campo['requerido'] = True
        if c.get('ancho'):
            campo['ancho'] = int(c['ancho'])
        if c['tipo'] in ('opcion', 'opciones'):
            campo['opciones'] = [x.strip() for x in (c.get('opciones') or '').splitlines() if x.strip()]
        if c['tipo'] == 'tabla':
            columnas = [x.strip() for x in (c.get('opciones') or '').splitlines() if x.strip()]
            subusadas = set()
            campo['subcampos'] = []
            for col in columnas:
                sub = slug_clave(col, subusadas)
                subusadas.add(sub)
                campo['subcampos'].append({'clave': sub, 'tipo': 'texto', 'etiqueta': col})
        if c['tipo'] == 'numero':
            for origen, destino in (('minimo', 'min'), ('maximo', 'max')):
                if c.get(origen) is not None:
                    campo[destino] = float(c[origen])
            campo['decimales'] = int(c.get('decimales') or 0)
        if c['tipo'] == 'escala':
            campo['min'] = int(c['minimo']) if c.get('minimo') is not None else 0
            campo['max'] = int(c['maximo']) if c.get('maximo') is not None else 10
        if c['tipo'] == 'texto_largo':
            campo['filas'] = 3
        campos.append(campo)
    return {'campos': campos}


@transaction.atomic
def guardar_seccion_personalizada(*, seccion=None, nombre, ambito, especialidad=None, descripcion='', campos):
    """Crea o actualiza una sección PERSONALIZADA del tenant activo. Un cambio de esquema sube la versión."""
    if not campos:
        raise ErrorDeNegocio('Agrega al menos un campo a la sección.')
    esquema = armar_esquema(campos, [c['clave'] for c in seccion.campos] if seccion else [])
    try:
        asegurar_valido(esquema, permitir_calculado=False)
    except ErrorEsquema as e:
        raise ErrorDeNegocio(f'La sección tiene errores: {e}')
    tenant = tenant_actual()
    if seccion is None:
        base = slug_clave(nombre, set())
        codigo, n = f'per.{base}', 2
        while SeccionClinica.objects.filter(tenant=tenant, codigo=codigo).exists():
            codigo, n = f'per.{base}_{n}', n + 1
        return SeccionClinica.objects.create(tenant=tenant, codigo=codigo, nombre=nombre.strip(),
                                             descripcion=descripcion, tipo=SeccionClinica.Tipo.PERSONALIZADA,
                                             ambito=ambito, especialidad=especialidad, esquema=esquema,
                                             creada_por=usuario_actual(), orden=500)
    if seccion.tenant_id != tenant.pk or seccion.tipo != SeccionClinica.Tipo.PERSONALIZADA:
        raise ErrorDeNegocio('Solo se pueden editar las secciones personalizadas de este consultorio.')
    if esquema != seccion.esquema:
        SeccionClinicaVersion.objects.get_or_create(seccion=seccion, version=seccion.version,
                                                    defaults={'esquema': seccion.esquema})
        seccion.version += 1
        seccion.esquema = esquema
    seccion.nombre, seccion.descripcion, seccion.ambito = nombre.strip(), descripcion, ambito
    seccion.especialidad = especialidad
    seccion.save()
    return seccion
