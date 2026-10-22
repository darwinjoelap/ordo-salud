from django.conf import settings
from django.utils import timezone

from .permisos import permisos_de


def marca(request):
    """Datos globales para todas las plantillas."""
    membresia = getattr(request, 'membresia', None)
    tenant = getattr(request, 'tenant', None)
    tasa = None
    if tenant is not None:
        from apps.tasas.servicios import tasa_vigente
        tasa = tasa_vigente(tenant)
    aviso = None
    gracia = None
    if tenant and membresia and membresia.rol in ('TITULAR', 'ADMIN'):
        dias = tenant.dias_para_vencer
        if dias is not None and 0 <= dias <= 7:
            aviso = dias
    if tenant and membresia and tenant.en_gracia:
        gracia = tenant.dias_de_gracia_restantes      # lo ve todo el equipo: mañana pueden quedar sin acceso
    return {
        'PRODUCTO': settings.PRODUCTO,
        'ORDO_VERSION': settings.ORDO_VERSION,
        'aviso_vencimiento': aviso,
        'aviso_gracia': gracia,
        'tasa': tasa,
        'tasa_desactualizada': bool(tasa and tasa.fecha < timezone.localdate()),
        'tenant': tenant,
        'config': getattr(tenant, 'configuracion', None) if tenant else None,
        'membresia': membresia,
        'membresias': getattr(request, 'membresias', []),
        'profesional': getattr(membresia, 'perfil_activo', None) if membresia else None,
        'permisos': permisos_de(membresia),
    }
