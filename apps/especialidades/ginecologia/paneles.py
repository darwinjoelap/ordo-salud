"""Paneles de ginecología en la ficha de la paciente: embarazo en curso y resumen ginecológico."""
from datetime import timedelta

from django.utils import timezone

from apps.clinica import esquemas

from . import obstetricia as ob
from .models import ControlPrenatal
from .secciones import GINECO
from .servicios import control_actual, ficha

CITOLOGIA_VIGENTE_DIAS = 365
ALTERADAS = ('ASC', 'LSIL', 'L-SIL', 'HSIL', 'H-SIL', 'AGC', 'CARCINOMA', 'NIC', 'CIN')


def citologia_alterada(texto):
    t = (texto or '').upper()
    return any(clave in t for clave in ALTERADAS)
ALERTA_PA = (140, 90)


def _fila(control):
    s = control.signos
    pa = f'{s.pa_sistolica}/{s.pa_diastolica}' if s and s.pa_sistolica and s.pa_diastolica else ''
    alerta = bool(s and s.pa_sistolica and s.pa_diastolica and
                  (s.pa_sistolica >= ALERTA_PA[0] or s.pa_diastolica >= ALERTA_PA[1]))
    return {'c': control, 'peso': s.peso_kg if s else None, 'pa': pa, 'alerta_pa': alerta}


def embarazo(request, paciente):
    actual = control_actual(paciente)
    if actual is None:
        return None
    hoy = timezone.localdate()
    dias = actual.eg_dias_en(hoy)
    desde = actual.fpp - timedelta(days=ob.POSTERMINO) if actual.fpp else None
    controles = ControlPrenatal.objects.filter(paciente=paciente).order_by('-fecha')
    if desde:
        controles = controles.filter(fecha__gte=desde)
    filas = [_fila(c) for c in controles[:12]]
    return {'control': actual, 'eg_hoy': ob.texto_eg(dias), 'trimestre': ob.trimestre(dias),
            'faltan': (actual.fpp - hoy).days if actual.fpp else None, 'filas': filas,
            'alerta_pa': any(f['alerta_pa'] for f in filas[:1])}


def resumen(request, paciente):
    if paciente.sexo == 'M':
        return None
    gineco = ficha(paciente, 'go.gineco')
    cito = gineco
    plan = ficha(paciente, 'go.planificacion')
    if not (gineco or plan):
        return {'vacio': True}
    hoy = timezone.localdate()
    fur = ob.a_fecha(gineco.get('fur'))
    cito_fecha = ob.a_fecha(cito.get('citologia_fecha'))
    vencida = cito_fecha is None or (hoy - cito_fecha).days > CITOLOGIA_VIGENTE_DIAS
    histerectomia = bool(gineco.get('histerectomia'))
    # Histerectomía total: sin cuello no toca la citología de rutina (la subtotal lo conserva y sí la necesita).
    # Sin tipo anotado se mantiene el criterio anterior (no avisar), pero se pide completar el tipo.
    if (histerectomia and gineco.get('histerectomia_tipo') != 'SUBTOTAL') or (
            paciente.edad_anios is not None and paciente.edad_anios < 21):
        vencida = False
    if histerectomia:
        fur = None                                    # el ciclo menstrual no aplica
    ooforectomia = gineco.get('ooforectomia')
    metodo = plan.get('metodo', '') or ('Ligadura de trompas' if plan.get('ligadura') else '')
    campo_vih = next(c for c in GINECO.esquema['campos'] if c['clave'] == 'vih_resultado')
    return {
        'formula': ob.formula(gineco), 'incongruente': ob.formula_incongruente(gineco),
        'fur': fur, 'dias_fur': (hoy - fur).days if fur else None,
        'menopausia': gineco.get('menopausia'), 'menopausia_edad': gineco.get('menopausia_edad'),
        'histerectomia': histerectomia,
        'histerectomia_texto': {'TOTAL': 'total', 'SUBTOTAL': 'subtotal (conserva el cuello)'}.get(
            gineco.get('histerectomia_tipo'), ''),
        'histerectomia_sin_tipo': histerectomia and not gineco.get('histerectomia_tipo'),
        'ooforectomia_bilateral': histerectomia and ooforectomia == 'BILATERAL',
        'ciclo': f"cada {gineco['ciclo_dias']} días" if gineco.get('ciclo_dias') and not histerectomia else '',
        'ciclo_regular': gineco.get('ciclo_regular'),
        'cito_fecha': cito_fecha, 'cito_hace': cito.get('citologia_hace', ''),
        'cito_resultado': cito.get('citologia_resultado', ''),
        'cito_alterada': citologia_alterada(cito.get('citologia_resultado')),
        'cito_vencida': vencida, 'vph_vacuna': cito.get('vph_vacuna'), 'vph_diagnostico': cito.get('vph_diagnostico'),
        'vih': esquemas.texto_valor(campo_vih, cito.get('vih_resultado')), 'metodo': metodo,
        'deseo_embarazo': plan.get('deseo_embarazo'),
    }
