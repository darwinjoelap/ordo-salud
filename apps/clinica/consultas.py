"""
Servicios de la consulta clínica (Fase 07). Toda escritura de una consulta pasa por aquí.
"""
import contextlib
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.excepciones import ErrorDeNegocio
from apps.core.fechas import edad_meses
from apps.pacientes.models import AntecedenteBase

from . import esquemas, registro
from .models import (
    Cie10,
    Consulta,
    DiagnosticoConsulta,
    Enmienda,
    ItemPrescripcion,
    PlantillaHistoria,
    RegistroSeccion,
    RegistroSeccionPaciente,
    SeccionClinica,
    SignosVitales,
)

ANTECEDENTES = 'nucleo.antecedentes'
CAMPOS_ANTECEDENTES = ['alergias', 'medicacion_actual', 'enfermedades_cronicas', 'cirugias', 'hospitalizaciones',
                       'transfusiones', 'habitos', 'antecedentes_familiares', 'otros']


# ── Permisos sobre una consulta ───────────────────────────────────────────────

def puede_ver(membresia, consulta):
    """Visibilidad configurable por consultorio (ADR-008)."""
    perfil = membresia.perfil_activo if membresia else None
    if perfil is None:
        return False
    if consulta.profesional_id == perfil.pk:
        return True
    modo = consulta.tenant.configuracion.visibilidad_historia
    if modo == 'COMPARTIDA':
        return True
    if modo == 'POR_ESPECIALIDAD':
        return consulta.especialidad_id == perfil.especialidad_id
    return False


def puede_editar(membresia, consulta):
    perfil = membresia.perfil_activo if membresia else None
    return perfil is not None and consulta.profesional_id == perfil.pk and consulta.editable


# ── Abrir ─────────────────────────────────────────────────────────────────────

def plantilla_para(profesional, especialidad=None):
    """La predeterminada propia del profesional; si no tiene, la predeterminada de la clínica."""
    especialidad = especialidad or profesional.especialidad
    qs = PlantillaHistoria.objects.filter(especialidad=especialidad, activa=True)
    return (qs.filter(profesional=profesional, es_predeterminada=True).first()
            or qs.filter(profesional__isnull=True, es_predeterminada=True).first()
            or qs.filter(profesional__isnull=True).first())


def congelar_estructura(plantilla):
    estructura = []
    for item in plantilla.items.select_related('seccion').order_by('orden', 'id'):
        s = item.seccion
        if not s.activa:
            continue
        estructura.append({
            'seccion_id': s.pk, 'codigo': s.codigo, 'nombre': s.nombre, 'version': s.version, 'ambito': s.ambito,
            'obligatoria': item.obligatoria, 'colapsada': item.colapsada,
            'campos': esquemas.campos_efectivos(s.esquema, item.ajustes),
        })
    return estructura


@transaction.atomic
def abrir_consulta(*, paciente, profesional, plantilla=None, tipo=Consulta.Tipo.PRIMERA, lugar=None,
                   fecha_hora=None):
    plantilla = plantilla or plantilla_para(profesional)
    if plantilla is None:
        raise ErrorDeNegocio('No hay plantillas de historia para tu especialidad. Crea una en «Plantillas».')
    if plantilla.profesional_id not in (None, profesional.pk):
        raise ErrorDeNegocio('Esa plantilla es de otro profesional.')
    if not paciente.activo:
        raise ErrorDeNegocio('El paciente está inactivo.')
    return Consulta.objects.create(
        paciente=paciente, profesional=profesional, especialidad=profesional.especialidad, plantilla=plantilla,
        lugar=lugar, estructura=congelar_estructura(plantilla), fecha_hora=fecha_hora or timezone.now(), tipo=tipo)


def consulta_nueva(*, paciente, profesional, plantilla=None, tipo=Consulta.Tipo.PRIMERA, lugar=None):
    """Consulta SIN guardar, con la estructura de la plantilla: para mostrar el formulario completo antes de
    crearla (así se puede llenar sin conexión y se crea al enviarse)."""
    plantilla = plantilla or plantilla_para(profesional)
    if plantilla is None:
        raise ErrorDeNegocio('No hay plantillas de historia para tu especialidad. Crea una en «Plantillas».')
    return Consulta(paciente=paciente, profesional=profesional, especialidad=profesional.especialidad,
                    plantilla=plantilla, lugar=lugar, estructura=congelar_estructura(plantilla),
                    fecha_hora=timezone.now(), tipo=tipo, tenant=paciente.tenant)


@transaction.atomic
def crear_consulta_completa(*, paciente, profesional, plantilla, tipo, lugar, datos_por_seccion, cita=None,
                            fecha_hora=None, cerrar=False, usuario=None):
    """
    Crea la consulta y guarda sus secciones en un solo paso (envío del formulario completo, quizá desde la cola
    sin conexión: `fecha_hora` es la hora en que el médico abrió el formulario). Con cita, la marca atendida.
    """
    consulta = abrir_consulta(paciente=paciente, profesional=profesional, plantilla=plantilla, tipo=tipo,
                              lugar=lugar, fecha_hora=fecha_hora)
    guardar_secciones(consulta, datos_por_seccion)
    if cita is not None and cita.profesional_id == profesional.pk and not cita.consulta_id:
        from apps.agenda.servicios import vincular_consulta
        vincular_consulta(cita, consulta, profesional)
    if cerrar:
        with contextlib.suppress(ErrorDeNegocio):     # si falta algo queda en curso; la vista avisa qué falta
            cerrar_consulta(consulta, usuario)
    consulta.refresh_from_db()
    return consulta


# ── Leer ──────────────────────────────────────────────────────────────────────

def contexto_calculo(consulta):
    p = consulta.paciente
    contexto = {'paciente': p, 'sexo': p.sexo, 'fecha': timezone.localtime(consulta.fecha_hora).date(),
                'edad_meses': edad_meses(p.fecha_nacimiento, timezone.localtime(consulta.fecha_hora).date())}
    signos = SignosVitales.objects.filter(consulta_id=consulta.pk).first() if consulta.pk else None
    if signos is not None and signos.peso_kg and signos.talla_cm:     # superficie corporal (volúmenes indexados)
        contexto['sc'] = round((float(signos.peso_kg) * float(signos.talla_cm) / 3600) ** 0.5, 2)
    return contexto


def datos_guardados(consulta):
    """{seccion_id: datos} de la consulta + secciones del paciente vigentes + antecedentes base."""
    datos = {r.seccion_id: r.datos for r in consulta.registros.all()} if consulta.pk else {}
    pendientes = [i for i in consulta.estructura if i['ambito'] == 'PACIENTE' and i['seccion_id'] not in datos]
    if pendientes:
        vigentes = {r.seccion_id: r.datos for r in RegistroSeccionPaciente.objects.filter(
            paciente=consulta.paciente, vigente=True, seccion_id__in=[i['seccion_id'] for i in pendientes])}
        for item in pendientes:
            if item['codigo'] == ANTECEDENTES:
                base = AntecedenteBase.objects.filter(paciente=consulta.paciente).first()
                datos[item['seccion_id']] = ({c: getattr(base, c) for c in CAMPOS_ANTECEDENTES if getattr(base, c)}
                                             if base else {})
            else:
                datos[item['seccion_id']] = vigentes.get(item['seccion_id'], {})
    return datos


def lectura(consulta):
    """Secciones con sus valores legibles (pantalla, PDF): [(item, [(campo, texto)])] sin vacías."""
    datos = datos_guardados(consulta)
    salida = []
    for item in consulta.estructura:
        valores = datos.get(item['seccion_id']) or {}
        filas = []
        for c in item['campos']:
            if c['tipo'] in esquemas.TIPOS_SIN_DATO:
                continue
            texto = esquemas.texto_valor(c, valores.get(c['clave']))
            if texto:
                filas.append((c, texto))
        if filas:
            salida.append((item, filas))
    return salida


# ── Ficha de especialidad (secciones de ámbito PACIENTE fuera de la consulta) ──

def items_ficha(codigo_especialidad):
    """Secciones PACIENTE de una especialidad (la «ficha pediátrica», «ficha ginecológica»…), como ítems."""
    secciones = (SeccionClinica.objects.visibles().filter(ambito='PACIENTE', activa=True,
                                                         especialidad__codigo=codigo_especialidad)
                 .order_by('orden', 'nombre'))
    return [{'seccion_id': s.pk, 'codigo': s.codigo, 'nombre': s.nombre, 'version': s.version, 'ambito': s.ambito,
             'obligatoria': False, 'colapsada': False, 'campos': esquemas.campos_efectivos(s.esquema)}
            for s in secciones]


def datos_ficha(paciente, items):
    ids = [i['seccion_id'] for i in items]
    return {r.seccion_id: r.datos for r in RegistroSeccionPaciente.objects.filter(
        paciente=paciente, seccion_id__in=ids, vigente=True)}


def lectura_ficha(paciente, codigo_especialidad):
    """[(item, [(campo, texto)])] de la ficha de la especialidad, sin secciones vacías."""
    items = items_ficha(codigo_especialidad)
    datos = datos_ficha(paciente, items)
    salida = []
    for item in items:
        valores = datos.get(item['seccion_id']) or {}
        filas = [(c, esquemas.texto_valor(c, valores.get(c['clave']))) for c in item['campos']
                 if c['tipo'] not in esquemas.TIPOS_SIN_DATO and valores.get(c['clave']) not in (None, '', [])]
        if filas:
            salida.append((item, filas))
    return salida


@transaction.atomic
def guardar_ficha(paciente, items, datos_por_seccion):
    """Guarda la ficha desde la página del paciente (cada cambio deja una versión nueva, igual que en consulta)."""
    for item in items:
        if item['seccion_id'] in datos_por_seccion:
            _guardar_paciente(None, item, _sin_vacios(datos_por_seccion[item['seccion_id']]), paciente=paciente)


# ── Guardar ───────────────────────────────────────────────────────────────────

def _sin_vacios(datos):
    return {k: v for k, v in (datos or {}).items() if v not in (None, '', [], {})}


def _guardar_paciente(consulta, item, datos, paciente=None):
    paciente = paciente or consulta.paciente
    if item['codigo'] == ANTECEDENTES:
        base, _ = AntecedenteBase.objects.get_or_create(paciente=paciente)
        cambios = [c for c in CAMPOS_ANTECEDENTES if (datos.get(c) or '') != getattr(base, c)]
        for c in cambios:
            setattr(base, c, datos.get(c) or '')
        if cambios:
            base.save()
        return
    actual = RegistroSeccionPaciente.objects.filter(paciente=paciente, seccion_id=item['seccion_id'],
                                                    vigente=True).first()
    if actual is not None and actual.datos == datos:
        return
    if actual is not None:
        actual.vigente = False
        actual.save(update_fields=['vigente', 'actualizado_en'])
    if datos:
        RegistroSeccionPaciente.objects.create(paciente=paciente, seccion_id=item['seccion_id'],
                                               version_seccion=item['version'], datos=datos, consulta=consulta)


def _guardar(consulta, item, datos):
    datos = _sin_vacios(datos)
    completar = registro.preparar(item['codigo'])
    if completar is not None:
        datos = completar(consulta, datos)
    if item['ambito'] == 'PACIENTE':
        _guardar_paciente(consulta, item, datos)
        # también queda una copia en la consulta: así se sabe cómo estaban los antecedentes ese día
    RegistroSeccion.objects.update_or_create(
        consulta=consulta, seccion_id=item['seccion_id'],
        defaults={'datos': datos, 'version_seccion': item['version'], 'tenant': consulta.tenant})
    funcion = registro.al_guardar(item['codigo'])
    if funcion is not None:
        funcion(consulta, datos)


@transaction.atomic
def guardar_secciones(consulta, datos_por_seccion):
    """datos_por_seccion: {seccion_id: datos_limpios}. Solo en consultas en curso."""
    consulta = Consulta.objects.select_for_update().get(pk=consulta.pk)
    if not consulta.editable:
        raise ErrorDeNegocio('La consulta está cerrada: para corregirla registra una enmienda.')
    for item in consulta.estructura:
        if item['seccion_id'] in datos_por_seccion:
            _guardar(consulta, item, datos_por_seccion[item['seccion_id']])
    consulta.save(update_fields=['actualizado_en'])
    return consulta


def faltantes(consulta):
    """Secciones obligatorias vacías y campos obligatorios sin llenar (impiden cerrar)."""
    datos = datos_guardados(consulta)
    salida = []
    for i in consulta.estructura:
        valores = _sin_vacios(datos.get(i['seccion_id']))
        if i['obligatoria'] and not valores:
            salida.append(i['nombre'])
            continue
        campos = esquemas.requeridos_vacios(i['campos'], valores)
        if campos:
            salida.append(f'{i["nombre"]} ({", ".join(campos)})')
    return salida


@transaction.atomic
def cerrar_consulta(consulta, usuario=None, *, automatico=False):
    consulta = Consulta.objects.select_for_update().get(pk=consulta.pk)
    if not consulta.editable:
        raise ErrorDeNegocio('La consulta ya está cerrada o anulada.')
    pendientes = faltantes(consulta)
    if pendientes:
        raise ErrorDeNegocio('Para cerrar la consulta completa: ' + ', '.join(pendientes) + '.')
    consulta.estado = Consulta.Estado.CERRADA
    consulta.cerrada_en = timezone.now()
    consulta.cerrada_por = None if automatico else usuario
    consulta.save(update_fields=['estado', 'cerrada_en', 'cerrada_por', 'actualizado_en'])
    return consulta


@transaction.atomic
def anular_consulta(consulta, motivo):
    motivo = (motivo or '').strip()
    if len(motivo) < 5:
        raise ErrorDeNegocio('Indica el motivo de la anulación.')
    if consulta.estado == Consulta.Estado.ANULADA:
        raise ErrorDeNegocio('La consulta ya está anulada.')
    consulta.estado = Consulta.Estado.ANULADA
    consulta.motivo_anulacion = motivo[:250]
    consulta.save(update_fields=['estado', 'motivo_anulacion', 'actualizado_en'])
    return consulta


@transaction.atomic
def enmendar(consulta, seccion_id, datos, motivo):
    """Corrige una sección de una consulta cerrada guardando el antes y el después."""
    motivo = (motivo or '').strip()
    if len(motivo) < 5:
        raise ErrorDeNegocio('Indica el motivo de la enmienda.')
    if consulta.estado != Consulta.Estado.CERRADA:
        raise ErrorDeNegocio('Solo se enmiendan consultas cerradas; las que están en curso se editan.')
    item = next((i for i in consulta.estructura if i['seccion_id'] == seccion_id), None)
    if item is None:
        raise ErrorDeNegocio('Esa sección no es parte de la consulta.')
    antes = datos_guardados(consulta).get(seccion_id, {})
    despues = _sin_vacios(datos)
    if antes == despues:
        raise ErrorDeNegocio('No hay cambios que registrar.')
    Enmienda.objects.create(consulta=consulta, seccion_id=seccion_id, motivo=motivo[:300], antes=antes,
                            despues=despues)
    _guardar(consulta, item, despues)
    return consulta


def cerrar_vencidas(ahora=None):
    """Cron: cierra las consultas en curso pasado el plazo de edición del consultorio (si están completas)."""
    from apps.core.tenancy import usando_tenant
    from apps.plataforma.models import Tenant
    ahora = ahora or timezone.now()
    cerradas = 0
    for tenant in Tenant.objects.select_related('configuracion'):
        limite = ahora - timedelta(hours=tenant.configuracion.horas_edicion_consulta)
        with usando_tenant(tenant):
            for consulta in Consulta.objects.filter(estado=Consulta.Estado.BORRADOR, fecha_hora__lt=limite):
                if not faltantes(consulta):
                    cerrar_consulta(consulta, automatico=True)
                    cerradas += 1
    return cerradas


# ── Copia a tablas (núcleo) ───────────────────────────────────────────────────

def _decimal(valor):
    return None if valor in (None, '') else Decimal(str(valor))


def _entero(valor):
    return None if valor in (None, '') else int(round(float(valor)))


def sincronizar_signos(consulta, datos):
    item = next((i for i in consulta.estructura if i['codigo'] == 'nucleo.signos_vitales'), None)
    claves = {c['clave'] for c in item['campos']} if item else set()
    antropometria_aparte = item is not None and 'peso_kg' not in claves     # p. ej. pediatría: va en su sección
    if not datos and not antropometria_aparte:
        SignosVitales.objects.filter(consulta=consulta).delete()
        return
    medidas = {} if antropometria_aparte else {
        'peso_kg': _decimal(datos.get('peso_kg')), 'talla_cm': _decimal(datos.get('talla_cm')),
        'imc': _decimal(datos.get('imc'))}
    SignosVitales.objects.update_or_create(consulta=consulta, defaults={
        'tenant': consulta.tenant, 'paciente': consulta.paciente,
        'fecha': timezone.localtime(consulta.fecha_hora).date(), **medidas,
        'pa_sistolica': _entero(datos.get('pa_sistolica')),
        'pa_diastolica': _entero(datos.get('pa_diastolica')), 'fc': _entero(datos.get('fc')),
        'fr': _entero(datos.get('fr')), 'temperatura': _decimal(datos.get('temperatura')),
        'spo2': _entero(datos.get('spo2')), 'glicemia': _entero(datos.get('glicemia')),
        'perimetro_abdominal': _decimal(datos.get('perimetro_abdominal'))})


def completar_diagnosticos(consulta, datos):
    """Códigos en mayúsculas y descripción del catálogo CIE-10 si el médico solo puso el código."""
    filas = datos.get('diagnosticos') or []
    codigos = {(f.get('codigo') or '').strip().upper() for f in filas if f.get('codigo')}
    catalogo = {c.codigo: c.descripcion for c in Cie10.objects.filter(codigo__in=codigos)}
    for f in filas:
        if f.get('codigo'):
            f['codigo'] = f['codigo'].strip().upper()
            if not f.get('descripcion') and f['codigo'] in catalogo:
                f['descripcion'] = catalogo[f['codigo']]
    return datos


def sincronizar_diagnosticos(consulta, datos):
    DiagnosticoConsulta.objects.filter(consulta=consulta).delete()
    filas = datos.get('diagnosticos') or []
    codigos = {(f.get('codigo') or '').strip().upper() for f in filas if f.get('codigo')}
    catalogo = {c.codigo: c for c in Cie10.objects.filter(codigo__in=codigos)}
    for n, f in enumerate(filas):
        codigo = (f.get('codigo') or '').strip().upper()
        cie = catalogo.get(codigo)
        descripcion = (f.get('descripcion') or (cie.descripcion if cie else '')).strip()
        if not descripcion:
            continue
        DiagnosticoConsulta.objects.create(consulta=consulta, paciente=consulta.paciente, cie10=cie, codigo=codigo,
                                           descripcion=descripcion[:300], certeza=f.get('certeza') or '', orden=n)
    primero = DiagnosticoConsulta.objects.filter(consulta=consulta).order_by('orden').first()
    consulta.diagnostico = str(primero)[:300] if primero else ''
    consulta.save(update_fields=['diagnostico'])


def sincronizar_prescripcion(consulta, datos):
    ItemPrescripcion.objects.filter(consulta=consulta).delete()
    for n, f in enumerate(datos.get('medicamentos') or []):
        if f.get('medicamento'):
            ItemPrescripcion.objects.create(
                consulta=consulta, paciente=consulta.paciente, medicamento=f['medicamento'][:200], orden=n,
                **{c: (f.get(c) or '')[:100] for c in ('dosis', 'frecuencia', 'duracion')},
                cantidad=(f.get('cantidad') or '')[:60])


def sincronizar_motivo(consulta, datos):
    consulta.motivo = (datos.get('motivo') or '')[:300]
    consulta.save(update_fields=['motivo'])


registro.registrar_al_guardar('nucleo.signos_vitales', sincronizar_signos)
registro.registrar_preparar('nucleo.diagnosticos', completar_diagnosticos)
registro.registrar_al_guardar('nucleo.diagnosticos', sincronizar_diagnosticos)
registro.registrar_al_guardar('nucleo.prescripcion', sincronizar_prescripcion)
registro.registrar_al_guardar('nucleo.motivo', sincronizar_motivo)


def programar_proximo_control(consulta, datos):
    """«Próximo control» del plan → cita tentativa sin hora en la agenda (de Pediae)."""
    from datetime import date

    from apps.agenda.servicios import programar_control
    texto = (datos or {}).get('proximo_control') or ''
    try:
        fecha = date.fromisoformat(str(texto)[:10]) if texto else None
    except ValueError:
        fecha = None
    programar_control(consulta, fecha)


registro.registrar_al_guardar('nucleo.plan', programar_proximo_control)


def seccion(seccion_id):
    return SeccionClinica.objects.visibles().get(pk=seccion_id)
