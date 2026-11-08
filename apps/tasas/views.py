import logging
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.core.numeros import numero
from apps.core.permisos import requiere

from . import servicios
from .models import TasaCambio, TasaTenant


@login_required
@requiere('tasa.cargar')
def tasa(request):
    """Tasa del día: ver la vigente, cargar una propia si el BCV no actualizó, o volver a la del BCV."""
    hoy = timezone.localdate()
    tenant = request.tenant
    if request.method == 'POST':
        accion = request.POST.get('accion')
        if accion == 'borrar':
            try:
                fecha = date.fromisoformat(request.POST.get('fecha', ''))
            except ValueError:
                fecha = None
            if fecha:
                servicios.borrar_del_tenant(tenant, fecha)
                messages.success(request, 'Tasa propia eliminada: se usa la del BCV.')
        elif accion == 'bcv':
            try:
                t = servicios.actualizar_desde_bcv()
                eur = f' · EUR {t.bs_por_eur}' if t.bs_por_eur else ' (sin euro)'
                messages.success(request, f'BCV consultado: USD {t.bs_por_usd}{eur} ({t.fecha:%d/%m/%Y}).')
            except Exception as e:  # noqa: BLE001 - el sitio del BCV falla seguido
                logging.getLogger('apps.tasas').warning('Consulta al BCV desde %s falló: %s', tenant, e)
                messages.error(request, 'El BCV no respondió. Puedes cargar la tasa del día a mano.')
        else:
            valor = numero(request.POST.get('valor', ''))
            eur = numero(request.POST.get('valor_eur', '')) if (request.POST.get('valor_eur') or '').strip() else None
            if valor is None or valor <= 0 or (eur is not None and eur <= 0):
                messages.error(request, 'Indica tasas mayores que cero (ej.: 36,5021).')
            elif eur is None and servicios.referencia(tenant) == 'EUR':
                messages.error(request, 'Tu consultorio trabaja con la tasa del euro: indica también Bs por EUR.')
            else:
                servicios.registrar_del_tenant(tenant, valor.quantize(Decimal('0.0001')), request.user, hoy,
                                               eur=eur.quantize(Decimal('0.0001')) if eur else None)
                messages.success(request, f'Tasa de hoy guardada: USD {valor}' + (f' · EUR {eur}' if eur else '') + '.')
        return redirect('tasas:tasa')
    return render(request, 'tasas/tasa.html', {
        'titulo': 'Tasa del día', 'hoy': hoy, 'vigente': servicios.tasa_vigente(tenant),
        'referencia': servicios.referencia(tenant),
        'bcv': servicios.tasa_global(), 'propias': TasaTenant.objects.select_related('registrada_por')[:30],
        'historial_bcv': TasaCambio.objects.all()[:15]})
