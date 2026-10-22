"""
Dictado de toda la consulta con IA (ADR-045): esquema para la IA, validación del resultado, minutos del plan y
procesamiento (en segundo plano: la doctora espera con el formulario abierto y se llena al terminar).
"""
import threading

from django.conf import settings
from django.db import close_old_connections
from django.db.models import Sum
from django.utils import timezone

from apps.clinica import esquemas
from apps.core.tenancy import usando_tenant

from . import proveedores
from .models import SesionDictado

MAX_BYTES = 120 * 1024 * 1024         # grabaciones del teléfono (.m4a) de hasta ~1,5 h
MAX_SEGUNDOS = 90 * 60
TIPOS_IGNORADOS = {'subtitulo', 'calculado'}

VOCABULARIO = {
    '': 'Historia clínica, enfermedad actual, examen físico, tensión arterial, frecuencia cardíaca, saturación, '
        'diagnóstico, CIE-10, récipe, indicaciones.',
    'cardiologia_pediatrica': 'EKG, QTc, ecocardiograma transtorácico, situs solitus, levocardia, VCI, Qp:Qs, '
                              'ostium secundum, ostium primum, CIA, CIV, ductus, TAPSE, FEVI, Teichholz, SIVd, DdVI, '
                              'PPd, SIVs, DsVI, PPs, TSVD, TAP, Zscore, gradiente, regurgitación, tricúspide, mitral, '
                              'Tetralogía de Fallot, infundibulotomía, parche transanular, BPEIM, BPEIA, R1, R2, '
                              'soplo sistólico eyectivo, Holter, PAN, TAN, I/Q.',
    'pediatria': 'percentil, antropometría, perímetro cefálico, lactancia materna exclusiva, pentavalente, '
                 'neumococo, rotavirus, BCG, hitos del desarrollo.',
    'ginecologia': 'FUR, FPP, edad gestacional, altura uterina, FCF, citología, colposcopia, VPH, DIU, gestas, '
                   'partos, cesáreas, abortos.',
}

SISTEMA = """Eres el asistente de historia clínica de {especialidad} en un consultorio de Venezuela.
Recibes la transcripción de lo que la doctora dictó en una consulta y debes ubicar cada dato en el campo correcto de
la herramienta `llenar_historia`.

Reglas:
- Usa SOLO lo que se dijo. No inventes, no completes con valores normales ni con lo que «suele ser».
- Si un dato no se mencionó, no incluyas ese campo.
- Números con punto decimal y en la unidad del campo (si dicta «diez punto cuatro kilos», peso = 10.4).
- En campos de opciones usa exactamente uno de los valores permitidos.
- Los campos de texto van en prosa médica clara, como la doctora lo dictó (corrige solo puntuación y muletillas).
- La tensión arterial «99 sobre 60» es sistólica 99 y diastólica 60.
- Lo que no encaje en ningún campo va completo en `no_ubicado`, para que ella lo ubique.
- No incluyas el nombre ni datos de identificación del paciente.
Paciente: {paciente}."""


def minutos_usados(tenant, ahora=None):
    ahora = ahora or timezone.now()
    inicio = timezone.localtime(ahora).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    segundos = (SesionDictado.objects.filter(tenant=tenant, creado_en__gte=inicio)
                .exclude(estado=SesionDictado.Estado.ERROR).aggregate(s=Sum('segundos'))['s'] or 0)
    return round(segundos / 60, 1)


def limite_minutos(tenant):
    """Minutos al mes del plan. 0 o sin plan = sin límite."""
    plan = getattr(tenant, 'plan', None)
    return plan.minutos_dictado_mes if plan is not None else 0


def puede_dictar(tenant, segundos=0):
    """(sí/no, motivo)."""
    if not tenant.configuracion.dictado_activo:
        return False, 'El dictado con IA no está activo para este consultorio.'
    limite = limite_minutos(tenant)
    if limite and minutos_usados(tenant) + segundos / 60 > limite:
        return False, f'Se agotaron los {limite} minutos de dictado del mes.'
    return True, ''


# ── Esquema que recibe la IA ──────────────────────────────────────────────────────────────────────────────────

def _propiedad(campo):
    descripcion = campo.get('etiqueta') or campo['clave']
    if campo.get('unidad'):
        descripcion += f" (en {campo['unidad']})"
    if campo.get('ayuda'):
        descripcion += f". {campo['ayuda']}"
    tipo = campo['tipo']
    if tipo == 'numero' or tipo == 'escala':
        prop = {'type': 'number'}
        for k in ('min', 'max'):
            if campo.get(k) is not None:
                prop['minimum' if k == 'min' else 'maximum'] = campo[k]
    elif tipo == 'si_no':
        prop = {'type': 'boolean'}
    elif tipo == 'opcion':
        opciones = esquemas.opciones_de(campo)
        prop = {'type': 'string', 'enum': [v for v, _ in opciones]}
        descripcion += '. Valores: ' + '; '.join(f'{v} = {t}' for v, t in opciones)
    elif tipo == 'opciones':
        opciones = esquemas.opciones_de(campo)
        prop = {'type': 'array', 'items': {'type': 'string', 'enum': [v for v, _ in opciones]}}
        descripcion += '. Valores: ' + '; '.join(f'{v} = {t}' for v, t in opciones)
    elif tipo == 'fecha':
        prop = {'type': 'string', 'description': 'AAAA-MM-DD'}
    elif tipo == 'hora':
        prop = {'type': 'string', 'description': 'HH:MM'}
    elif tipo == 'tabla':
        subs = campo.get('subcampos', [])
        prop = {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False, 'properties': {
            s['clave']: {'type': 'string', 'description': s.get('etiqueta', s['clave'])} for s in subs}}}
    else:
        prop = {'type': 'string'}
    prop['description'] = (prop.get('description', '') + ' ' + descripcion).strip()
    return prop


def herramienta(estructura):
    secciones = {}
    for item in estructura:
        props = {c['clave']: _propiedad(c) for c in item['campos'] if c['tipo'] not in TIPOS_IGNORADOS}
        if props:
            secciones[item['codigo']] = {'type': 'object', 'description': item['nombre'], 'properties': props,
                                         'additionalProperties': False}
    return {
        'name': 'llenar_historia',
        'description': 'Ubica lo dictado en los campos de la historia de esta consulta.',
        'input_schema': {'type': 'object', 'required': ['secciones'], 'properties': {
            'secciones': {'type': 'object', 'properties': secciones, 'additionalProperties': False},
            'no_ubicado': {'type': 'string', 'description': 'Lo dictado que no encaja en ningún campo.'}}},
    }


def contexto_paciente(paciente):
    partes = [paciente.get_sexo_display().lower() if paciente.sexo else 'sexo no indicado']
    if paciente.edad_texto:
        partes.append(paciente.edad_texto)
    return ', '.join(partes)


# ── Validar lo que devolvió la IA ─────────────────────────────────────────────────────────────────────────────

def validar(entrada, estructura):
    """
    Devuelve (resultado, avisos). resultado = {'campos': [...], 'tablas': [...], 'llenados': n} listo para el
    formulario; avisos = valores que la IA dio pero no pasan la validación del campo (van a «no ubicado»).
    """
    secciones = (entrada or {}).get('secciones') or {}
    campos, tablas, avisos, llenados = [], [], [], 0
    for item in estructura:
        datos = secciones.get(item['codigo']) or {}
        if not isinstance(datos, dict):
            continue
        prefijo = f"s{item['seccion_id']}"
        for c in item['campos']:
            if c['tipo'] in TIPOS_IGNORADOS or c['clave'] not in datos:
                continue
            valor = datos[c['clave']]
            if c['tipo'] == 'tabla':
                filas = [{s['clave']: str(f.get(s['clave'], '')).strip() for s in c.get('subcampos', [])
                          if f.get(s['clave']) not in (None, '')} for f in (valor or []) if isinstance(f, dict)]
                filas = [f for f in filas if f]
                if filas:
                    tablas.append({'prefijo': prefijo, 'clave': c['clave'], 'filas': filas})
                    llenados += len(filas)
                continue
            errores = {}
            limpio = esquemas.normalizar_valor(c, valor, errores)
            if errores or limpio in (None, '', []):
                if valor not in (None, '', []):
                    avisos.append(f"{item['nombre']} · {c.get('etiqueta') or c['clave']}: {valor}")
                continue
            campos.append({'prefijo': prefijo, 'clave': c['clave'], 'tipo': c['tipo'], 'valor': limpio,
                           'texto': esquemas.texto_valor(c, limpio)})
            llenados += 1
    return {'campos': campos, 'tablas': tablas, 'llenados': llenados}, avisos


# ── Procesar ──────────────────────────────────────────────────────────────────────────────────────────────────

def procesar(sesion_id, audio, nombre, tipo, estructura, especialidad_codigo, especialidad_nombre):
    """Convierte, envía a la IA y valida. El audio solo vive en esta función (no se guarda en ningún lado)."""
    from . import audio as conversor
    # En el hilo no hay consultorio activo: se lee sin el filtro por tenant y luego se activa el de la sesión.
    sesion = SesionDictado.todos.select_related('tenant', 'paciente').get(pk=sesion_id)
    with usando_tenant(sesion.tenant):
        try:
            datos, tipo_mime, segundos = conversor.convertir(audio, nombre, tipo)
            if segundos:                                   # duración real (también para archivos subidos)
                sesion.segundos = min(segundos, MAX_SEGUNDOS)
            vocabulario = VOCABULARIO[''] + ' ' + VOCABULARIO.get(especialidad_codigo, '')
            sistema = SISTEMA.format(especialidad=especialidad_nombre or 'medicina',
                                     paciente=contexto_paciente(sesion.paciente))
            r = proveedores.procesar_audio(datos, tipo_mime, vocabulario, sistema, herramienta(estructura))
            if not sesion.segundos and r.segundos_audio:
                sesion.segundos = min(r.segundos_audio, MAX_SEGUNDOS)
            resultado, avisos = validar(r.entrada, estructura)
            no_ubicado = '\n'.join(t for t in [((r.entrada or {}).get('no_ubicado') or '').strip(), *avisos] if t)
            sesion.transcripcion, sesion.resultado, sesion.no_ubicado = r.transcripcion, resultado, no_ubicado
            sesion.modelo_transcripcion, sesion.modelo_ia = r.modelo_transcripcion, r.modelo_ia
            sesion.tokens_entrada, sesion.tokens_salida = r.tokens_entrada, r.tokens_salida
            sesion.estado = SesionDictado.Estado.LISTO
        except proveedores.ErrorProveedor as e:
            sesion.estado, sesion.error = SesionDictado.Estado.ERROR, str(e)[:300]
        except Exception as e:  # noqa: BLE001 - cualquier falla deja la sesión en error, nunca colgada
            sesion.estado, sesion.error = SesionDictado.Estado.ERROR, f'Error inesperado: {e.__class__.__name__}'
        sesion.terminado_en = timezone.now()
        sesion.save()


def lanzar(*args):
    """En producción, en un hilo (la petición responde al momento y el navegador consulta el estado)."""
    if getattr(settings, 'DICTADO_SINCRONO', False):
        procesar(*args)
        return

    def tarea():
        try:
            procesar(*args)
        except Exception:  # noqa: BLE001 - nunca dejar la sesión «procesando» para siempre
            SesionDictado.todos.filter(pk=args[0], estado=SesionDictado.Estado.PROCESANDO).update(
                estado=SesionDictado.Estado.ERROR, error='Error inesperado al procesar el dictado.',
                terminado_en=timezone.now())
        finally:
            close_old_connections()
    threading.Thread(target=tarea, daemon=True).start()
