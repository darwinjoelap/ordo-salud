"""Datos del tablero de inicio. Cada módulo aporta lo suyo sin que core lo importe al cargar."""
from django.utils import timezone

from .permisos import permisos_de


def resumen_inicio(request):
    permisos = permisos_de(request.membresia)
    hoy = timezone.localdate()
    hora = timezone.localtime().hour
    datos = {'hoy': hoy, 'saludo': 'Buenos días' if hora < 12 else 'Buenas tardes' if hora < 19 else 'Buenas noches'}
    if 'pacientes.ver' in permisos:
        from apps.pacientes.selectors import alcance_inicial, pacientes_recientes, total_pacientes
        alcance = alcance_inicial(request.membresia)
        datos['pacientes_mios'] = alcance == 'mios'
        datos['total_pacientes'] = total_pacientes(request.membresia, alcance)
        datos['pacientes_recientes'] = pacientes_recientes(6, request.membresia, alcance)
    perfil = request.membresia.perfil_activo if request.membresia else None
    if 'agenda.ver' in permisos:
        from apps.agenda.models import Cita
        citas = (Cita.objects.filter(fecha=hoy).select_related('paciente', 'profesional__membresia__usuario', 'tipo')
                 .order_by('hora_inicio'))
        datos['citas_hoy'] = list(citas.filter(profesional=perfil) if perfil else citas)
        datos['citas_hoy_propias'] = perfil is not None
        activas = [c for c in datos['citas_hoy'] if c.estado in Cita.ACTIVAS]
        datos['citas_activas'] = len(activas)
        datos['citas_en_sala'] = sum(1 for c in activas if c.estado == Cita.Estado.EN_SALA)
    if 'cobros.gestionar' in permisos:
        from apps.cobros.servicios import caja
        del_dia = caja(hoy)
        datos['cobrado_hoy'] = del_dia['total_usd']
        datos['pagos_hoy'] = len(del_dia['pagos'])
    if perfil is not None:
        from apps.clinica.selectors import consultas_en_curso
        from datetime import timedelta

        from apps.clinica.consultas import faltantes
        en_curso = list(consultas_en_curso(perfil))
        limite = timezone.now() - timedelta(hours=request.tenant.configuracion.horas_edicion_consulta)
        for c in en_curso:          # vencida y sin poder cerrarse sola: decir qué falta
            c.vencida = c.fecha_hora < limite
            c.falta = faltantes(c) if c.vencida else []
        datos['en_curso'] = en_curso
    return datos
