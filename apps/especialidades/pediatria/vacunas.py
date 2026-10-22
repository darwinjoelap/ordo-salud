"""Esquema de vacunación y pesquisas del paciente (lógica de Pediae `pacientes/views.py`)."""
from django.db import transaction

from apps.core.excepciones import ErrorDeNegocio
from apps.core.fechas import edad_meses

from .models import Pesquisa, PesquisaRealizada, Vacuna, VacunaAplicada

ULTIMOS = ('Vacunación anual', 'Otras vacunas')
ESTADOS = {'aplicada': ('Aplicada', 'success'), 'pendiente': ('Pendiente', 'warning'),
           'atrasada': ('Atrasada', 'danger'), 'futura': ('Más adelante', 'secondary')}


def esquema(paciente):
    """[{vacuna, estado, aplicada (última), historial}] para todas las vacunas del catálogo visible."""
    meses = edad_meses(paciente.fecha_nacimiento) if paciente.fecha_nacimiento else None
    aplicaciones = {}
    for va in (VacunaAplicada.objects.filter(paciente=paciente).select_related('registrada_por')
               .order_by('-fecha', '-creado_en')):
        aplicaciones.setdefault(va.vacuna_id, []).append(va)
    salida = []
    for v in Vacuna.objects.visibles():
        historial = aplicaciones.get(v.pk, [])
        if historial:
            estado = 'aplicada'
        elif meses is None:
            estado = 'pendiente'
        elif v.edad_max_meses is not None and meses > v.edad_max_meses:
            estado = 'atrasada'
        elif meses >= v.edad_meses:
            estado = 'pendiente'
        else:
            estado = 'futura'
        salida.append({'vacuna': v, 'estado': estado, 'texto': ESTADOS[estado][0], 'color': ESTADOS[estado][1],
                       'aplicada': historial[0] if historial else None, 'historial': historial})
    return salida


def por_grupos(filas):
    """Agrupa por etapa en orden cronológico; «Vacunación anual» y «Otras vacunas» al final."""
    grupos = {}
    for f in filas:
        grupos.setdefault(f['vacuna'].grupo or 'Otras vacunas', []).append(f)

    def orden(item):
        nombre, vacunas = item
        return (1, 0) if nombre in ULTIMOS else (0, min(f['vacuna'].edad_meses for f in vacunas))
    return [{'nombre': n, 'vacunas': v} for n, v in sorted(grupos.items(), key=orden)]


def resumen(paciente):
    filas = esquema(paciente)
    aplicadas = sum(1 for f in filas if f['estado'] == 'aplicada')
    return {'total': len(filas), 'aplicadas': aplicadas,
            'atrasadas': [f for f in filas if f['estado'] == 'atrasada'],
            'pendientes': [f for f in filas if f['estado'] == 'pendiente'],
            'al_dia': not any(f['estado'] in ('atrasada', 'pendiente') for f in filas)}


def aviso_consulta(paciente):
    """Insignia del botón «Vacunas» en la consulta."""
    r = resumen(paciente)
    if r['atrasadas']:
        return (f"{len(r['atrasadas'])} atrasada{'s' if len(r['atrasadas']) > 1 else ''}", 'danger')
    if r['pendientes']:
        return (f"{len(r['pendientes'])} pendiente{'s' if len(r['pendientes']) > 1 else ''}", 'warning')
    return ('Al día', 'success')


@transaction.atomic
def registrar_lote(paciente, vacunas, *, fecha=None, usuario=None):
    """Carga del carnet: marca varias dosis como aplicadas (misma fecha, o sin fecha). Devuelve cuántas nuevas."""
    nuevas = 0
    for v in vacunas:
        if not v.anual and VacunaAplicada.objects.filter(paciente=paciente, vacuna=v).exists():
            continue
        registrar_vacuna(paciente, v, fecha=fecha, observaciones='Cargada del carnet', usuario=usuario)
        nuevas += 1
    return nuevas


@transaction.atomic
def registrar_vacuna(paciente, vacuna, *, fecha=None, lote='', observaciones='', usuario=None):
    """Dosis única: crea o completa el registro. Vacuna anual: siempre una aplicación nueva."""
    if not Vacuna.objects.visibles().filter(pk=vacuna.pk).exists():
        raise ErrorDeNegocio('Esa vacuna no está en el catálogo del consultorio.')
    if fecha and paciente.fecha_nacimiento and fecha < paciente.fecha_nacimiento:
        raise ErrorDeNegocio('La fecha de aplicación es anterior al nacimiento.')
    if vacuna.anual:
        return VacunaAplicada.objects.create(paciente=paciente, vacuna=vacuna, fecha=fecha, lote=lote,
                                             observaciones=observaciones, registrada_por=usuario), True
    va, creada = VacunaAplicada.objects.get_or_create(paciente=paciente, vacuna=vacuna, defaults={
        'fecha': fecha, 'lote': lote, 'observaciones': observaciones, 'registrada_por': usuario})
    if not creada:
        for campo, valor in (('fecha', fecha), ('lote', lote), ('observaciones', observaciones)):
            if valor:
                setattr(va, campo, valor)
        va.registrada_por = usuario
        va.save()
    return va, creada


def pesquisas(paciente):
    realizadas = {p.pesquisa_id: p for p in PesquisaRealizada.objects.filter(paciente=paciente)}
    return [{'pesquisa': p, 'realizada': realizadas.get(p.pk)} for p in Pesquisa.objects.visibles()]


def registrar_pesquisa(paciente, pesquisa, *, fecha=None, resultado='', usuario=None):
    if not Pesquisa.objects.visibles().filter(pk=pesquisa.pk).exists():
        raise ErrorDeNegocio('Esa pesquisa no está en el catálogo del consultorio.')
    pr, creada = PesquisaRealizada.objects.get_or_create(paciente=paciente, pesquisa=pesquisa, defaults={
        'fecha': fecha, 'resultado': resultado, 'registrada_por': usuario})
    if not creada:
        if fecha:
            pr.fecha = fecha
        if resultado:
            pr.resultado = resultado
        pr.save()
    return pr


# ── Bloque en «Procedimiento» (vacunas aplicadas sin consulta) ────────────────

ORDEN_ESTADO = {'atrasada': 0, 'pendiente': 1, 'futura': 2, 'aplicada': 3}


def contexto_procedimiento(request, paciente):
    """Vacunas para marcar: atrasadas y pendientes primero; las anuales aunque ya tengan dosis."""
    if paciente.fecha_nacimiento is None or (paciente.edad_anios or 0) >= 19:
        return None
    filas = [f for f in esquema(paciente) if f['estado'] != 'aplicada' or f['vacuna'].anual]
    if not filas:
        return None
    filas.sort(key=lambda f: (ORDEN_ESTADO[f['estado']], f['vacuna'].edad_meses, f['vacuna'].orden))
    return {'filas': filas}


def guardar_procedimiento(request, paciente, post, fecha):
    ids = post.getlist('vacunas')
    if not ids:
        return []
    lote = (post.get('vacuna_lote') or '').strip()[:60]
    hechas = []
    for v in Vacuna.objects.visibles().filter(pk__in=ids):
        registrar_vacuna(paciente, v, fecha=fecha, lote=lote, usuario=request.user)
        hechas.append(f'Vacuna {v.nombre} (dosis {v.dosis})')
    return hechas
