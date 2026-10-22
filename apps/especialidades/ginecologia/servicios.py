"""Servicios de ginecología: controles prenatales desde la consulta y actualización de la ficha ginecológica."""
from decimal import Decimal

from django.utils import timezone

from . import obstetricia as ob
from .models import ControlPrenatal

CAMPOS_CLINICOS = ('altura_uterina', 'fcf', 'presentacion', 'movimientos', 'edemas', 'laboratorio')


def ficha(paciente, codigo):
    """Datos vigentes de una sección de la ficha ({} si no hay)."""
    from apps.clinica.models import RegistroSeccionPaciente
    r = RegistroSeccionPaciente.objects.filter(paciente=paciente, seccion__codigo=codigo, vigente=True).first()
    return r.datos if r else {}


def actualizar_ficha(consulta, codigo, cambios):
    """Mezcla `cambios` en la sección de la ficha (nueva versión con historial). No hace nada si no cambia."""
    from apps.clinica.consultas import _guardar_paciente
    from apps.clinica.models import SeccionClinica
    cambios = {k: v for k, v in cambios.items() if v not in (None, '')}
    if not cambios:
        return False
    seccion = SeccionClinica.objects.visibles().filter(codigo=codigo, activa=True).first()
    if seccion is None:
        return False
    actual = ficha(consulta.paciente, codigo)
    nuevo = {**actual, **cambios}
    if nuevo == actual:
        return False
    _guardar_paciente(consulta, {'codigo': codigo, 'seccion_id': seccion.pk, 'version': seccion.version}, nuevo)
    return True


def control_actual(paciente):
    """Último control del embarazo en curso (o None)."""
    ultimo = ControlPrenatal.objects.filter(paciente=paciente).order_by('-fecha', '-pk').first()
    return ultimo if ultimo and ultimo.en_curso else None


def _tipo_de(consulta):
    r = consulta.registros.filter(seccion__codigo='go.tipo').first() if consulta.pk else None
    return (r.datos or {}).get('tipo') if r else None


def sincronizar_control(consulta, datos):
    """
    Gancho al guardar «Control prenatal». Crea/actualiza el control si la consulta es prenatal (tipo «Control
    prenatal», o datos clínicos del feto, o FUR/eco sin sección de tipo). Si no, lo borra.
    """
    tipo = _tipo_de(consulta)
    clinicos = any(datos.get(c) not in (None, '') for c in CAMPOS_CLINICOS)
    fecha = timezone.localtime(consulta.fecha_hora).date()
    dias, metodo = ob.eg_dias(datos, fecha)
    es_prenatal = tipo == 'PRENATAL' or clinicos or (tipo is None and dias is not None)
    if not es_prenatal:
        ControlPrenatal.objects.filter(consulta=consulta).delete()
        return None
    au = datos.get('altura_uterina')
    control, _ = ControlPrenatal.objects.update_or_create(consulta=consulta, defaults={
        'tenant': consulta.tenant, 'paciente': consulta.paciente, 'fecha': fecha,
        'fur': ob.a_fecha(datos.get('fur')), 'eco_fecha': ob.a_fecha(datos.get('eco_fecha')),
        'eco_semanas': datos.get('eco_semanas'), 'eco_dias': datos.get('eco_dias'),
        'eg_dias': dias, 'metodo_eg': metodo, 'fpp': ob.fpp(datos),
        'altura_uterina': Decimal(str(au)) if au not in (None, '') else None,
        'fcf': datos.get('fcf'), 'presentacion': datos.get('presentacion') or '',
        'movimientos': datos.get('movimientos'), 'edemas': datos.get('edemas') or ''})
    if datos.get('fur'):
        actualizar_ficha(consulta, 'go.gineco', {'fur': datos['fur']})
    return control


def desde_actualizar(consulta, datos):
    """Gancho al guardar «Actualizar ficha ginecológica»: FUR y citología → historia gineco-obstétrica."""
    actualizar_ficha(consulta, 'go.gineco', {'fur': datos.get('fur'), 'citologia_fecha': datos.get('citologia_fecha'),
                                             'citologia_resultado': datos.get('citologia_resultado')})


def inicial_prenatal(consulta):
    """Al abrir una consulta con embarazo en curso, el control trae la FUR y la eco de referencia."""
    control = control_actual(consulta.paciente)
    if control is None:
        return {}
    salida = {'fur': control.fur.isoformat() if control.fur else None,
              'eco_fecha': control.eco_fecha.isoformat() if control.eco_fecha else None,
              'eco_semanas': control.eco_semanas, 'eco_dias': control.eco_dias}
    return {k: v for k, v in salida.items() if v not in (None, '')}
