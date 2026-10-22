"""
Equipo de un tenant: agregar personas, cambiar rol, desactivar, restablecer contraseña y perfil profesional.

Reglas (de Ordo, adaptadas):
- Nadie modifica su propia membresía (evita quedarse sin acceso por error).
- Solo un Titular puede asignar el rol Titular o modificar a otro Titular.
- Siempre queda al menos un Titular activo.
- Cada tenant tiene sus propios usuarios (Usuario.tenant_cuenta): solo se restablece la clave de cuentas
  de ESTE tenant.
- Rol MÉDICO exige perfil profesional con una especialidad habilitada en el tenant.
- Se respetan los límites de usuarios y de profesionales del plan.
"""
import secrets

from django.contrib.auth import get_user_model
from django.db import transaction

from apps.core.excepciones import ErrorDeNegocio
from apps.core.permisos import Rol
from apps.core.tenancy import usando_tenant

from .models import Membresia, PerfilProfesional

ALFABETO = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'


class ErrorEquipo(ErrorDeNegocio):
    pass


def clave_temporal():
    return 'Ordo-' + ''.join(secrets.choice(ALFABETO) for _ in range(10))


def roles_asignables(actor):
    return [(v, n) for v, n in Rol.choices if v != Rol.TITULAR or actor.rol == Rol.TITULAR]


def puede_gestionar(actor, objetivo):
    if actor.pk is not None and actor.pk == objetivo.pk:
        return False
    return not (objetivo.rol == Rol.TITULAR and actor.rol != Rol.TITULAR)


def solo_en_este_tenant(usuario, tenant):
    return not usuario.is_superuser and usuario.tenant_cuenta_id == tenant.pk


def _validar_rol(actor, rol):
    if rol not in Rol.values:
        raise ErrorEquipo('Rol inválido.')
    if rol == Rol.TITULAR and actor.rol != Rol.TITULAR:
        raise ErrorEquipo('Solo un Titular puede asignar el rol Titular.')


def _activos(tenant):
    return Membresia.objects.filter(tenant=tenant, activa=True, usuario__is_superuser=False)


def _validar_limite_usuarios(tenant, excluir_pk=None):
    limite = tenant.max_usuarios
    if limite is not None and _activos(tenant).exclude(pk=excluir_pk).count() >= limite:
        raise ErrorEquipo(f'Tu plan permite {limite} usuarios activos. Desactiva a alguien o pide ampliar el plan.')


def _validar_limite_profesionales(tenant, excluir_membresia_pk=None):
    limite = tenant.max_profesionales
    if limite is None:
        return
    n = (PerfilProfesional.todos.filter(tenant=tenant, activo=True, membresia__activa=True)
         .exclude(membresia_id=excluir_membresia_pk).count())
    if n >= limite:
        raise ErrorEquipo(f'Tu plan permite {limite} profesionales. Pide ampliar el plan para agregar otro.')


def validar_especialidad(tenant, especialidad):
    if especialidad is None:
        raise ErrorEquipo('Indica la especialidad del profesional.')
    if not tenant.especialidades.filter(pk=especialidad.pk).exists():
        raise ErrorEquipo(f'La especialidad {especialidad} no está habilitada en este consultorio.')


def _quedaria_sin_titular(m, nuevo_rol, nueva_activa):
    if m.rol != Rol.TITULAR or (nuevo_rol == Rol.TITULAR and nueva_activa):
        return False
    otros = _activos(m.tenant).filter(rol=Rol.TITULAR).exclude(pk=m.pk)
    return not otros.exists()


@transaction.atomic
def crear_perfil(membresia, especialidad, **datos):
    """Crea (o reactiva) el perfil profesional de una membresía."""
    tenant = membresia.tenant
    validar_especialidad(tenant, especialidad)
    _validar_limite_profesionales(tenant, excluir_membresia_pk=membresia.pk)
    with usando_tenant(tenant):
        perfil, _ = PerfilProfesional.todos.update_or_create(
            membresia=membresia, defaults={'especialidad': especialidad, 'activo': True, 'tenant': tenant, **datos})
    _asegurar_plantillas(perfil)
    return perfil


@transaction.atomic
def guardar_perfil(membresia, form):
    """Guarda el formulario del perfil profesional validando especialidad y límite del plan."""
    tenant = membresia.tenant
    perfil = form.instance
    anterior = (PerfilProfesional.todos.filter(pk=perfil.pk).values_list('especialidad_id', 'activo').first()
                if perfil.pk else None)
    validar_especialidad(tenant, form.cleaned_data.get('especialidad') or perfil.especialidad)
    if anterior is None or not anterior[1]:
        _validar_limite_profesionales(tenant, excluir_membresia_pk=membresia.pk)
    perfil = form.save(commit=False)
    perfil.activo = True
    perfil.save()
    if anterior is None or anterior[0] != perfil.especialidad_id:
        _asegurar_plantillas(perfil)
    return perfil


def _asegurar_plantillas(perfil):
    """Al nacer un profesional, su especialidad debe tener plantillas en el tenant (copiadas del módulo)."""
    from apps.clinica.servicios import asegurar_plantillas_especialidad
    with usando_tenant(perfil.tenant):
        asegurar_plantillas_especialidad(perfil.especialidad)


@transaction.atomic
def agregar(tenant, actor, username, nombre, apellido, rol, email='', especialidad=None, titulo='Dr.'):
    """Crea un usuario propio del tenant con clave temporal. Devuelve (membresia, clave_temporal)."""
    from apps.usuarios.models import normalizar_usuario
    _validar_rol(actor, rol)
    username = normalizar_usuario(username)
    U = get_user_model()
    if U.objects.filter(tenant_cuenta=tenant, username=username).exists():
        raise ErrorEquipo(f'Ya existe el usuario "{username}" en este consultorio. Si está inactivo, reactívalo.')
    if rol == Rol.MEDICO and especialidad is None:
        raise ErrorEquipo('Un médico necesita su especialidad.')
    _validar_limite_usuarios(tenant)
    clave = clave_temporal()
    usuario = U.objects.create_user(username, clave, tenant_cuenta=tenant, email=email or '',
                                    first_name=nombre.strip(), last_name=apellido.strip(), debe_cambiar_clave=True)
    m = Membresia.objects.create(usuario=usuario, tenant=tenant, rol=rol)
    if especialidad is not None:
        crear_perfil(m, especialidad, titulo=titulo or '')
    return m, clave


@transaction.atomic
def actualizar(actor, m, rol, activa):
    m = Membresia.objects.select_for_update().get(pk=m.pk)
    if not puede_gestionar(actor, m):
        raise ErrorEquipo('No puedes modificar esta membresía.')
    _validar_rol(actor, rol)
    if _quedaria_sin_titular(m, rol, activa):
        raise ErrorEquipo('El consultorio debe conservar al menos un Titular activo.')
    perfil = m.perfil_activo
    if rol == Rol.MEDICO and perfil is None:
        raise ErrorEquipo('Para el rol Médico, primero carga su perfil profesional (especialidad).')
    if activa and not m.activa:
        _validar_limite_usuarios(m.tenant, excluir_pk=m.pk)
        if perfil is not None:
            _validar_limite_profesionales(m.tenant, excluir_membresia_pk=m.pk)
    m.rol, m.activa = rol, activa
    m.save(update_fields=['rol', 'activa'])
    return m


@transaction.atomic
def desactivar_perfil(actor, m):
    if m.rol == Rol.MEDICO:
        raise ErrorEquipo('Cambia primero el rol (p. ej. a Asistente) antes de quitarle el perfil profesional.')
    perfil = m.perfil_activo
    if perfil is not None:
        perfil.activo = False
        perfil.save(update_fields=['activo', 'actualizado_en'])


@transaction.atomic
def restablecer_clave(actor, m):
    if not puede_gestionar(actor, m):
        raise ErrorEquipo('No puedes modificar esta membresía.')
    if not solo_en_este_tenant(m.usuario, m.tenant):
        raise ErrorEquipo('Esta persona también trabaja en otro consultorio: debe cambiar su contraseña ella '
                          'misma desde "Mi perfil".')
    clave = clave_temporal()
    u = m.usuario
    u.set_password(clave)
    u.debe_cambiar_clave = True
    u.save(update_fields=['password', 'debe_cambiar_clave'])
    return clave
