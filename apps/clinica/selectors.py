from django.db.models import Count, Q

from . import esquemas
from .models import PlantillaHistoria, SeccionClinica


def plantillas_visibles(membresia, especialidad=None):
    """Plantillas de la clínica + las propias del profesional (si lo es)."""
    perfil = membresia.perfil_activo if membresia else None
    filtro = Q(profesional__isnull=True)
    if perfil is not None:
        filtro |= Q(profesional=perfil)
    qs = (PlantillaHistoria.objects.filter(filtro).select_related('especialidad', 'profesional__membresia__usuario')
          .annotate(n_secciones=Count('items')))
    if especialidad is not None:
        qs = qs.filter(especialidad=especialidad)
    return qs.order_by('especialidad__nombre', 'profesional', '-es_predeterminada', 'nombre')


def plantilla_completa(pk):
    return PlantillaHistoria.objects.select_related('especialidad', 'profesional__membresia__usuario').get(pk=pk)


def items_de(plantilla):
    items = list(plantilla.items.select_related('seccion', 'seccion__especialidad').order_by('orden', 'id'))
    for item in items:
        item.campos = esquemas.campos_efectivos(item.seccion.esquema, item.ajustes)
    return items


def secciones_para(plantilla, tenant):
    """Secciones que se pueden agregar, agrupadas: [(titulo, [secciones])]."""
    ya = set(plantilla.items.values_list('seccion_id', flat=True))
    habilitadas = set(tenant.especialidades.values_list('pk', flat=True))
    qs = (SeccionClinica.objects.visibles(tenant).filter(activa=True).exclude(pk__in=ya)
          .select_related('especialidad').order_by('orden', 'nombre'))
    grupos = {'nucleo': [], 'propia': [], 'otras': [], 'personalizadas': []}
    for s in qs:
        if s.tipo == SeccionClinica.Tipo.NUCLEO or (s.tipo == SeccionClinica.Tipo.MODULO and not s.especialidad_id):
            grupos['nucleo'].append(s)
        elif s.tipo == SeccionClinica.Tipo.PERSONALIZADA:
            grupos['personalizadas'].append(s)
        elif s.especialidad_id == plantilla.especialidad_id:
            grupos['propia'].append(s)
        elif s.especialidad_id in habilitadas:
            grupos['otras'].append(s)
    return [(t, grupos[k]) for k, t in (('propia', f'De {plantilla.especialidad}'), ('nucleo', 'Generales'),
                                         ('otras', 'De otras especialidades del consultorio'),
                                         ('personalizadas', 'Personalizadas del consultorio')) if grupos[k]]


def catalogo_para(plantilla, tenant):
    """
    Todas las secciones que puede llevar la plantilla, marcadas si ya están (para «armar la historia» con casillas):
    [{'titulo', 'ayuda', 'secciones': [{'seccion', 'incluida', 'item', 'campos'}]}].
    """
    items = {i.seccion_id: i for i in plantilla.items.all()}
    habilitadas = set(tenant.especialidades.values_list('pk', flat=True))
    qs = (SeccionClinica.objects.visibles(tenant).filter(activa=True).select_related('especialidad')
          .order_by('orden', 'nombre'))
    esp = plantilla.especialidad
    grupos = {
        'ficha': {'titulo': f'Ficha de {esp.nombre.lower()}', 'ayuda': 'Datos de la paciente que se conservan entre '
                  'consultas: lo que escribas aquí actualiza su ficha.', 'secciones': []},
        'consulta': {'titulo': f'Consulta de {esp.nombre.lower()}', 'ayuda': 'Se llenan en cada visita.',
                     'secciones': []},
        'nucleo': {'titulo': 'Generales (todas las especialidades)', 'ayuda': 'Motivo, signos vitales, examen '
                   'físico, diagnóstico, plan, récipe, órdenes…', 'secciones': []},
        'personalizadas': {'titulo': 'Creadas en el consultorio', 'ayuda': '', 'secciones': []},
        'otras': {'titulo': 'De otras especialidades del consultorio', 'ayuda': '', 'secciones': []},
    }
    for s in qs:
        if s.tipo == SeccionClinica.Tipo.NUCLEO or (s.tipo == SeccionClinica.Tipo.MODULO and not s.especialidad_id):
            clave = 'nucleo'
        elif s.tipo == SeccionClinica.Tipo.PERSONALIZADA:
            clave = 'personalizadas'
        elif s.especialidad_id == plantilla.especialidad_id:
            clave = 'ficha' if s.ambito == SeccionClinica.Ambito.PACIENTE else 'consulta'
        elif s.especialidad_id in habilitadas:
            clave = 'otras'
        else:
            continue
        campos = [c.get('etiqueta') for c in s.campos if c['tipo'] not in ('subtitulo',) and c.get('etiqueta')]
        grupos[clave]['secciones'].append({'seccion': s, 'incluida': s.pk in items, 'item': items.get(s.pk),
                                           'campos': campos})
    return [g for g in grupos.values() if g['secciones']]


def secciones_personalizadas(tenant):
    return SeccionClinica.objects.filter(tenant=tenant).select_related('especialidad').order_by('-activa', 'nombre')


def catalogo(tenant):
    """Todas las secciones visibles (para consultar el catálogo)."""
    return SeccionClinica.objects.visibles(tenant).filter(activa=True).select_related('especialidad') \
        .order_by('tipo', 'especialidad__nombre', 'orden', 'nombre')


def consultas_visibles(request, paciente):
    """Consultas del paciente que el profesional puede ver según la visibilidad del consultorio (ADR-008)."""
    from .consultas import puede_ver
    from .models import Consulta
    qs = (Consulta.objects.filter(paciente=paciente).select_related('profesional__membresia__usuario',
                                                                    'especialidad', 'tenant__configuracion')
          .order_by('-fecha_hora'))
    return [c for c in qs if puede_ver(request.membresia, c)]


def resumen_paciente(request, paciente):
    """Datos clínicos para la ficha del paciente (solo profesionales)."""
    from apps.configuracion.models import Lugar

    from .consultas import plantilla_para
    from .models import Consulta, SignosVitales
    perfil = request.membresia.perfil_activo
    consultas = consultas_visibles(request, paciente)
    ids = [c.pk for c in consultas]
    signos = list(SignosVitales.objects.filter(consulta_id__in=ids).order_by('-fecha')[:12])
    en_curso = next((c for c in consultas if c.estado == Consulta.Estado.BORRADOR and perfil
                     and c.profesional_id == perfil.pk), None)
    return {
        'consultas': consultas,
        'historial': historial(consultas, paciente),
        'signos': signos,
        'ultimo_signo': signos[0] if signos else None,
        'consulta_en_curso': en_curso,
        'plantillas_consulta': (plantillas_visibles(request.membresia, perfil.especialidad).filter(activa=True)
                                if perfil else []),
        'lugares': Lugar.objects.filter(activo=True),
        'tipos_consulta': Consulta.Tipo.choices,
        'ocultas': Consulta.objects.filter(paciente=paciente).count() - len(consultas),
        'plantilla_sugerida': plantilla_para(perfil) if perfil else None,
        **fichas_y_paneles(request, paciente),
    }


def fichas_y_paneles(request, paciente):
    """
    Lo que aportan los perfiles de especialidad a la ficha del paciente: la ficha de cada especialidad del
    consultorio (la del profesional que mira, o las que ya tienen datos) y los paneles de los módulos
    (curvas de crecimiento, vacunas…).
    """
    from . import registro
    from .consultas import items_ficha, lectura_ficha
    perfil = request.membresia.perfil_activo
    propia = perfil.especialidad.codigo if perfil and perfil.especialidad_id else None
    codigos = list(request.tenant.especialidades.order_by('orden').values_list('codigo', 'nombre'))
    fichas = []
    for codigo, nombre in codigos:
        if not items_ficha(codigo):
            continue
        lectura = lectura_ficha(paciente, codigo)
        if lectura or codigo == propia:
            fichas.append({'codigo': codigo, 'nombre': nombre, 'lectura': lectura})
    paneles = []
    for panel in registro.paneles({c for c, _ in codigos}):
        contexto = panel.contexto(request, paciente) if panel.contexto else {}
        if contexto is not None:
            paneles.append({'def': panel, 'ctx': contexto})
    return {'fichas_especialidad': fichas, 'paneles_especialidad': paneles}


def consultas_en_curso(perfil, limite=10):
    from .models import Consulta
    return (Consulta.objects.filter(profesional=perfil, estado=Consulta.Estado.BORRADOR)
            .select_related('paciente').order_by('-fecha_hora')[:limite])


def historial(consultas, paciente):
    """
    Línea de tiempo de la ficha (como el «Historial de consultas» de Pediae): consultas y procedimientos, del más
    reciente al más viejo, con lo esencial de cada consulta para leerlo sin abrirla.
    """
    from django.db.models import Prefetch

    from .models import Procedimiento, RegistroSeccion
    ids = [c.pk for c in consultas]
    planes = {r.consulta_id: r.datos for r in RegistroSeccion.objects.filter(
        consulta_id__in=ids, seccion__codigo='nucleo.plan')}
    from .models import Consulta
    detalle = {c.pk: c for c in Consulta.objects.filter(pk__in=ids).prefetch_related(
        Prefetch('medicamentos'), 'diagnosticos').select_related('signos')}
    salida = []
    for c in consultas:
        d = detalle.get(c.pk)
        signos = getattr(d, 'signos', None) if d else None
        plan = planes.get(c.pk) or {}
        salida.append({'tipo': 'consulta', 'fecha': c.fecha_hora, 'consulta': c,
                       'diagnosticos': list(d.diagnosticos.all()) if d else [],
                       'medicamentos': list(d.medicamentos.all()) if d else [],
                       'plan': plan.get('plan', ''), 'indicaciones': plan.get('indicaciones', ''),
                       'proximo_control': plan.get('proximo_control', ''), 'signos': signos})
    for p in (Procedimiento.objects.filter(paciente=paciente).select_related('profesional__membresia__usuario')
              .prefetch_related('cargos')[:50]):
        salida.append({'tipo': 'procedimiento', 'fecha': p.creado_en, 'procedimiento': p})
    salida.sort(key=lambda e: e['fecha'], reverse=True)
    primera = next((e for e in salida if e['tipo'] == 'consulta'), None)
    if primera:
        primera['abierta'] = True            # la última consulta se ve desplegada al entrar
    return salida
