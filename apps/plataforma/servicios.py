"""
Panel de plataforma (solo superusuarios): alta y control de tenants (consultorios y clínicas).
El enlace de cada tenant es su slug: https://<dominio>/<slug>/
"""
import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.excepciones import ErrorDeNegocio
from apps.core.fechas import sumar_meses
from apps.core.permisos import Rol

from .models import AccesoSoporte, Suscripcion, Tenant

# Primeros segmentos de URL que usa Ordo Salud: no pueden ser enlaces de un tenant
RESERVADOS = {
    'admin', 'api', 'cuenta', 'equipo', 'configuracion', 'tasa', 'servicios', 'cobros', 'pacientes', 'agenda',
    'consultas', 'clinica', 'historia', 'plantillas', 'secciones', 'documentos', 'reportes', 'plataforma',
    'salud', 'offline', 'instalar', 'visor', 'static', 'media', 'favicon.ico', 'manifest.webmanifest', 'sw.js',
    '__debug__', 'ordo', 'ordo-salud', 'www', 'app', 'soporte', 'ayuda', 'login', 'entrar', 'dictado', 'cie10',
    'adjuntos', 'citas', 'esp',
}
PATRON = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')


def validar_enlace(slug, excluir_pk=None):
    slug = (slug or '').strip().lower()
    if not 3 <= len(slug) <= 40 or not PATRON.match(slug):
        raise ValidationError('Usa de 3 a 40 letras minúsculas, números o guiones (ej. dra-perez).')
    if slug in RESERVADOS:
        raise ValidationError(f'"{slug}" está reservado por Ordo Salud. Elige otro.')
    if Tenant.objects.filter(slug=slug).exclude(pk=excluir_pk).exists():
        raise ValidationError('Ese enlace ya lo usa otro consultorio.')
    return slug


def habilitar_especialidades(tenant, especialidades):
    """Habilita especialidades y copia al tenant las plantillas iniciales de cada módulo."""
    from apps.clinica.servicios import asegurar_plantillas_especialidad
    from apps.core.tenancy import usando_tenant
    tenant.especialidades.add(*especialidades)
    with usando_tenant(tenant):
        for especialidad in especialidades:
            asegurar_plantillas_especialidad(especialidad)


@transaction.atomic
def crear_tenant(datos):
    """
    datos: nombre, slug, plan, activo_hasta, notas, especialidades (lista),
           usuario_titular, nombre_titular, apellido_titular, email_titular,
           titular_es_profesional (bool), especialidad_titular, titulo_titular.
    Devuelve (tenant, titular, clave_temporal). El Titular es un usuario propio del tenant.
    """
    from apps.equipo.models import Membresia
    from apps.equipo.servicios import clave_temporal, crear_perfil

    tenant = Tenant.objects.create(
        nombre=datos['nombre'], slug=datos['slug'], plan=datos.get('plan'),
        activo_hasta=datos.get('activo_hasta'), notas=datos.get('notas', ''))
    especialidades = list(datos.get('especialidades') or [])
    if datos.get('titular_es_profesional') and datos.get('especialidad_titular') \
            and datos['especialidad_titular'] not in especialidades:
        especialidades.append(datos['especialidad_titular'])
    habilitar_especialidades(tenant, especialidades)

    U = get_user_model()
    clave = clave_temporal()
    titular = U.objects.create_user(datos['usuario_titular'], clave, tenant_cuenta=tenant,
                                    email=datos.get('email_titular') or '',
                                    first_name=(datos.get('nombre_titular') or '').strip(),
                                    last_name=(datos.get('apellido_titular') or '').strip(), debe_cambiar_clave=True)
    m = Membresia.objects.create(usuario=titular, tenant=tenant, rol=Rol.TITULAR)
    if datos.get('titular_es_profesional') and datos.get('especialidad_titular'):
        crear_perfil(m, datos['especialidad_titular'], titulo=datos.get('titulo_titular') or 'Dr.')
    return tenant, titular, clave


@transaction.atomic
def actualizar_tenant(tenant, datos):
    for campo in ('nombre', 'slug', 'plan', 'estado', 'activo_hasta', 'limite_usuarios', 'limite_profesionales',
                  'dias_gracia', 'notas'):
        if campo in datos:
            setattr(tenant, campo, datos[campo])
    tenant.save()
    if 'especialidades' in datos:
        nuevas = [e for e in datos['especialidades'] if not tenant.especialidades.filter(pk=e.pk).exists()]
        tenant.especialidades.set(datos['especialidades'])
        habilitar_especialidades(tenant, nuevas)
    if 'dictado_activo' in datos:
        config = tenant.configuracion
        config.dictado_activo = datos['dictado_activo']
        config.save(update_fields=['dictado_activo', 'actualizado_en'])
    return tenant


@transaction.atomic
def renovar(tenant, *, meses, monto_usd=0, referencia='', notas='', plan=None, usuario=None):
    """
    Registra una renovación: extiende `activo_hasta` desde el vencimiento. Si ya venció y está en días de gracia,
    también sigue desde el vencimiento (los días de gracia no se regalan); si ya estaba bloqueado, desde hoy.
    """
    hoy = timezone.localdate()
    if tenant.activo_hasta and (tenant.activo_hasta >= hoy or tenant.en_gracia):
        desde = tenant.activo_hasta + timedelta(days=1)
    else:
        desde = hoy
    hasta = sumar_meses(desde, meses) - timedelta(days=1)
    plan = plan or tenant.plan
    Suscripcion.objects.create(tenant=tenant, plan=plan, desde=desde, hasta=hasta, monto_usd=monto_usd,
                               referencia=referencia, notas=notas, hasta_anterior=tenant.activo_hasta,
                               plan_anterior=tenant.plan, creado_por=usuario)
    tenant.activo_hasta = hasta
    tenant.plan = plan
    if tenant.estado != Tenant.Estado.ACTIVO:
        tenant.estado = Tenant.Estado.ACTIVO
    tenant.save(update_fields=['activo_hasta', 'plan', 'estado'])
    return tenant


@transaction.atomic
def anular_renovacion(suscripcion, *, motivo, usuario=None):
    """
    Anula una renovación mal cargada. Solo la última vigente del consultorio (las siguientes se calcularon
    encadenadas desde ella): el vencimiento y el plan vuelven a como estaban antes de registrarla.
    """
    motivo = (motivo or '').strip()
    if not motivo:
        raise ErrorDeNegocio('Indica el motivo de la anulación.')
    if suscripcion.anulada:
        raise ErrorDeNegocio('Esa renovación ya está anulada.')
    tenant = Tenant.objects.select_for_update().get(pk=suscripcion.tenant_id)
    ultima = tenant.suscripciones.filter(anulada=False).order_by('-creado_en', '-pk').first()
    if ultima is None or ultima.pk != suscripcion.pk:
        raise ErrorDeNegocio('Solo se puede anular la última renovación vigente. Anula primero las más recientes.')
    suscripcion.anulada = True
    suscripcion.motivo_anulacion = motivo[:200]
    suscripcion.anulada_por = usuario
    suscripcion.anulada_en = timezone.now()
    suscripcion.save(update_fields=['anulada', 'motivo_anulacion', 'anulada_por', 'anulada_en'])
    tenant.activo_hasta = suscripcion.hasta_anterior          # None = no tenía vencimiento
    tenant.plan = suscripcion.plan_anterior
    tenant.save(update_fields=['activo_hasta', 'plan'])
    return tenant


def entrar_soporte(tenant, usuario, motivo=''):
    """Abre un acceso de soporte y lo deja en la auditoría del consultorio (lo ve el titular)."""
    from apps.core.models import Auditoria
    from apps.core.tenancy import usando_tenant
    acceso = AccesoSoporte.objects.create(usuario=usuario, tenant=tenant, motivo=(motivo or '')[:200])
    detalle = 'Entrada de soporte de Ordo Salud' + (f': {motivo}' if motivo else '')
    with usando_tenant(tenant):
        Auditoria.objects.create(usuario=usuario, accion=Auditoria.Accion.SOPORTE, objeto_tipo='plataforma.Tenant',
                                 objeto_id=str(tenant.pk), detalle=detalle[:300])
    return acceso


def salir_soporte(acceso_id):
    if acceso_id:
        AccesoSoporte.objects.filter(pk=acceso_id, fin__isnull=True).update(fin=timezone.now())


def tablero_suscripciones(hoy=None, meses=12):
    """Cifras del panel: estado de los consultorios, vencimientos próximos, cobrado por mes y MRR estimado."""
    from collections import OrderedDict
    from decimal import Decimal

    from django.db.models import Sum
    from django.db.models.functions import TruncMonth
    hoy = hoy or timezone.localdate()
    tenants = list(Tenant.objects.select_related('plan').order_by('activo_hasta', 'nombre'))
    por_estado = {'ACTIVO': [], 'GRACIA': [], 'VENCIDO': [], 'SUSPENDIDO': []}
    for t in tenants:
        por_estado[t.estado_servicio].append(t)
    limite = hoy + timedelta(days=30)
    vencen = [t for t in por_estado['ACTIVO'] if t.activo_hasta and t.activo_hasta <= limite]
    mrr = sum((t.plan.precio_usd for t in por_estado['ACTIVO'] + por_estado['GRACIA'] if t.plan_id), Decimal('0'))

    inicio = sumar_meses(hoy.replace(day=1), -(meses - 1))
    filas = (Suscripcion.objects.filter(anulada=False, creado_en__date__gte=inicio)
             .annotate(mes=TruncMonth('creado_en')).values('mes').annotate(total=Sum('monto_usd')))
    totales = {(f['mes'].year, f['mes'].month): f['total'] or Decimal('0') for f in filas}
    mensual = OrderedDict()
    for i in range(meses):
        m = sumar_meses(inicio, i)
        mensual[(m.year, m.month)] = totales.get((m.year, m.month), Decimal('0'))
    maximo = max(mensual.values(), default=0) or 1
    nombres = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
    serie = [{'mes': nombres[mm - 1], 'titulo': f'{nombres[mm - 1]} {aa}', 'total': v,
              'pct': round(float(v) / float(maximo) * 100, 1)} for (aa, mm), v in mensual.items()]
    return {
        'por_estado': por_estado, 'vencen': vencen, 'mrr': mrr, 'mensual': serie,
        'cobrado_mes': mensual[(hoy.year, hoy.month)],
        'cobrado_anio': sum((v for (aa, _), v in mensual.items() if aa == hoy.year), Decimal('0')),
        'ultimas': Suscripcion.objects.select_related('tenant', 'plan', 'creado_por')[:15],
    }
