from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.agenda.servicios import fecha_de
from apps.core.permisos import requiere
from apps.pacientes.models import Paciente

from . import servicios as srv
from .forms import CargoForm, PagoForm, ServicioForm
from .models import Cargo, Pago, Servicio


@login_required
@requiere('servicios.gestionar')
def servicios(request):
    form = ServicioForm(request.POST or None, tenant=request.tenant)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Servicio agregado.')
        return redirect('cobros:servicios')
    return render(request, 'cobros/servicios.html', {
        'titulo': 'Servicios y precios', 'form': form,
        'servicios': Servicio.objects.select_related('especialidad').order_by('-activo', 'nombre')})


@login_required
@requiere('servicios.gestionar')
def servicio_editar(request, pk):
    servicio = get_object_or_404(Servicio.objects.all(), pk=pk)
    form = ServicioForm(request.POST or None, instance=servicio, tenant=request.tenant)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Servicio actualizado.')
        return redirect('cobros:servicios')
    return render(request, 'cobros/servicio_form.html', {'titulo': f'Servicio · {servicio}', 'form': form})


@login_required
@requiere('cobros.gestionar')
def cuenta(request, paciente_pk):
    paciente = get_object_or_404(Paciente.objects.all(), pk=paciente_pk)
    consulta = None
    if request.GET.get('consulta') or request.POST.get('consulta'):
        from apps.clinica.models import Consulta
        consulta = Consulta.objects.filter(pk=request.GET.get('consulta') or request.POST.get('consulta'),
                                           paciente=paciente).first()
    accion = request.POST.get('accion')
    form_cargo = CargoForm(request.POST if accion == 'cargo' else None)
    form_pago = PagoForm(request.POST if accion == 'pago' else None,
                         initial={'moneda': 'USD', 'metodo': 'EFECTIVO'})
    if accion == 'cargo' and form_cargo.is_valid():
        d = form_cargo.cleaned_data
        srv.crear_cargo(paciente=paciente, servicio=d['servicio'], descripcion=d['descripcion'],
                        precio_usd=d['precio_usd'], descuento_usd=d['descuento_usd'] or 0, exonerado=d['exonerado'],
                        consulta=consulta, profesional=consulta.profesional if consulta else None)
        messages.success(request, 'Cargo agregado.')
        return redirect('cobros:cuenta', paciente_pk=paciente.pk)
    if accion == 'pago' and form_pago.is_valid():
        d = form_pago.cleaned_data
        pago = srv.registrar_pago(paciente=paciente, monto=d['monto'], moneda=d['moneda'], metodo=d['metodo'],
                                  referencia=d['referencia'], notas=d['notas'])
        messages.success(request, f'Pago registrado: equivale a $ {pago.monto_usd}.')
        return redirect('cobros:cuenta', paciente_pk=paciente.pk)
    return render(request, 'cobros/cuenta.html', {
        'titulo': f'Cuenta · {paciente}', 'paciente': paciente, 'consulta': consulta,
        'form_cargo': form_cargo, 'form_pago': form_pago, **srv.estado_cuenta(paciente),
        'precios': {s.pk: str(s.precio_usd) for s in Servicio.objects.filter(activo=True)}})


@login_required
@requiere('cobros.gestionar')
@require_POST
def cargo_anular(request, pk):
    cargo = get_object_or_404(Cargo.objects.all(), pk=pk)
    srv.anular_cargo(cargo, request.POST.get('motivo', ''))
    messages.success(request, 'Cargo anulado.')
    return redirect('cobros:cuenta', paciente_pk=cargo.paciente_id)


@login_required
@requiere('cobros.gestionar')
@require_POST
def pago_anular(request, pk):
    pago = get_object_or_404(Pago.objects.all(), pk=pk)
    srv.anular_pago(pago, request.POST.get('motivo', ''))
    messages.success(request, 'Pago anulado.')
    return redirect('cobros:cuenta', paciente_pk=pago.paciente_id)


@login_required
@requiere('cobros.gestionar')
def por_cobrar(request):
    return render(request, 'cobros/por_cobrar.html', {
        'titulo': 'Cuentas por cobrar', **srv.informe_por_cobrar()})


@login_required
@requiere('cobros.gestionar')
def caja(request):
    fecha = fecha_de(request.GET.get('fecha'), timezone.localdate())
    return render(request, 'cobros/caja.html', {'titulo': 'Caja del día', 'fecha': fecha, **srv.caja(fecha)})
