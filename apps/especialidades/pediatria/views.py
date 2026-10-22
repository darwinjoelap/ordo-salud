"""Vistas de pediatría: esquema de vacunas y pesquisas del paciente, catálogo propio del consultorio."""
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core import auditoria
from apps.core.excepciones import ErrorDeNegocio
from apps.core.permisos import requiere
from apps.pacientes.models import Paciente
from apps.pacientes.selectors import puede_ver_paciente

from . import vacunas as srv
from .models import Pesquisa, PesquisaRealizada, Vacuna, VacunaAplicada


def _paciente(request, pk):
    paciente = get_object_or_404(Paciente.objects.all(), pk=pk)
    if not puede_ver_paciente(request.membresia, paciente):
        raise PermissionDenied
    return paciente


def _fecha(texto):
    try:
        return date.fromisoformat(texto) if texto else None
    except ValueError:
        return None


@login_required
@requiere('historia.ver')
def vacunas(request, pk):
    paciente = _paciente(request, pk)
    filas = srv.esquema(paciente)
    return render(request, 'pediatria/vacunas.html', {
        'titulo': f'Vacunas · {paciente}', 'paciente': paciente, 'grupos': srv.por_grupos(filas),
        'conteo': {e: sum(1 for f in filas if f['estado'] == e) for e in srv.ESTADOS},
        'pesquisas': srv.pesquisas(paciente), 'hoy': date.today()})


@login_required
@requiere('consultas.crear')
@require_POST
def vacuna_registrar(request, pk):
    paciente = _paciente(request, pk)
    vacuna = get_object_or_404(Vacuna.objects.visibles(), pk=request.POST.get('vacuna'))
    try:
        _, creada = srv.registrar_vacuna(paciente, vacuna, fecha=_fecha(request.POST.get('fecha')),
                                         lote=request.POST.get('lote', '').strip()[:60],
                                         observaciones=request.POST.get('observaciones', '').strip()[:300],
                                         usuario=request.user)
    except ErrorDeNegocio as e:
        messages.error(request, str(e))
    else:
        auditoria.registrar(request, 'CREAR' if creada else 'EDITAR', paciente, paciente_id=paciente.pk,
                            detalle=f'Vacuna {vacuna}')
        messages.success(request, f'{vacuna} registrada.')
    return redirect(f"{reverse('pediatria:vacunas', args=[pk])}#v-{vacuna.pk}")


@login_required
@requiere('consultas.crear')
@require_POST
def vacunas_lote(request, pk):
    """«Cargar carnet»: varias dosis de una vez."""
    paciente = _paciente(request, pk)
    ids = [i for i in request.POST.getlist('vacunas') if i.isdigit()]
    seleccion = list(Vacuna.objects.visibles().filter(pk__in=ids))
    if not seleccion:
        messages.warning(request, 'No marcaste ninguna vacuna.')
        return redirect('pediatria:vacunas', pk=pk)
    try:
        nuevas = srv.registrar_lote(paciente, seleccion, fecha=_fecha(request.POST.get('fecha')), usuario=request.user)
    except ErrorDeNegocio as e:
        messages.error(request, str(e))
    else:
        auditoria.registrar(request, 'CREAR', paciente, paciente_id=paciente.pk,
                            detalle=f'Carnet de vacunas: {nuevas} dosis')
        messages.success(request, f'{nuevas} dosis registrada{"s" if nuevas != 1 else ""} del carnet.')
    return redirect('pediatria:vacunas', pk=pk)


@login_required
@requiere('consultas.crear')
@require_POST
def vacuna_eliminar(request, pk, va_pk):
    paciente = _paciente(request, pk)
    va = get_object_or_404(VacunaAplicada.objects.filter(paciente=paciente), pk=va_pk)
    auditoria.registrar(request, 'ANULAR', paciente, paciente_id=paciente.pk, detalle=f'Quitó vacuna {va.vacuna}')
    va.delete()
    messages.success(request, 'Registro de vacuna eliminado.')
    return redirect(f"{reverse('pediatria:vacunas', args=[pk])}#v-{va.vacuna_id}")


@login_required
@requiere('consultas.crear')
@require_POST
def pesquisa_registrar(request, pk):
    paciente = _paciente(request, pk)
    pesquisa = get_object_or_404(Pesquisa.objects.visibles(), pk=request.POST.get('pesquisa'))
    try:
        srv.registrar_pesquisa(paciente, pesquisa, fecha=_fecha(request.POST.get('fecha')),
                               resultado=request.POST.get('resultado', '').strip()[:300], usuario=request.user)
    except ErrorDeNegocio as e:
        messages.error(request, str(e))
    else:
        messages.success(request, f'Pesquisa «{pesquisa}» registrada.')
    volver = request.POST.get('volver') or ''
    if volver.startswith('/') and not volver.startswith('//'):
        return redirect(volver)
    return redirect('pediatria:vacunas', pk=pk)


@login_required
@requiere('consultas.crear')
@require_POST
def pesquisa_eliminar(request, pk, pr_pk):
    paciente = _paciente(request, pk)
    get_object_or_404(PesquisaRealizada.objects.filter(paciente=paciente), pk=pr_pk).delete()
    messages.success(request, 'Registro de pesquisa eliminado.')
    return redirect('pediatria:vacunas', pk=pk)


@login_required
@requiere('plantillas.clinica')
def catalogo(request):
    """Vacunas y pesquisas propias del consultorio (el esquema del sistema no se edita, se puede ocultar)."""
    if request.method == 'POST':
        accion = request.POST.get('accion')
        try:
            if accion == 'vacuna':
                nombre = request.POST.get('nombre', '').strip()
                if not nombre:
                    raise ErrorDeNegocio('Indica el nombre de la vacuna.')
                Vacuna.objects.create(
                    tenant=request.tenant, nombre=nombre[:100], enfermedad=request.POST.get('enfermedad', '')[:200],
                    dosis=int(request.POST.get('dosis') or 1), edad_meses=int(request.POST.get('edad_meses') or 0),
                    edad_max_meses=int(request.POST['edad_max_meses']) if request.POST.get('edad_max_meses') else None,
                    grupo=request.POST.get('grupo', '').strip()[:60] or 'Otras vacunas',
                    anual=bool(request.POST.get('anual')), orden=200)
                messages.success(request, f'Vacuna «{nombre}» agregada.')
            elif accion == 'pesquisa':
                nombre = request.POST.get('nombre', '').strip()
                if not nombre:
                    raise ErrorDeNegocio('Indica el nombre de la pesquisa.')
                Pesquisa.objects.create(tenant=request.tenant, nombre=nombre[:100],
                                        descripcion=request.POST.get('descripcion', '')[:200], orden=200)
                messages.success(request, f'Pesquisa «{nombre}» agregada.')
            elif accion in ('quitar_vacuna', 'quitar_pesquisa'):
                modelo = Vacuna if accion == 'quitar_vacuna' else Pesquisa
                obj = get_object_or_404(modelo.objects.filter(tenant=request.tenant), pk=request.POST.get('id'))
                obj.activa = False
                obj.save(update_fields=['activa'])
                messages.success(request, f'«{obj.nombre}» quitada del catálogo.')
        except (ErrorDeNegocio, ValueError) as e:
            messages.error(request, str(e) if isinstance(e, ErrorDeNegocio) else 'Revisa los números.')
        return redirect('pediatria:catalogo')
    return render(request, 'pediatria/catalogo.html', {
        'titulo': 'Vacunas y pesquisas', 'sistema': Vacuna.objects.filter(tenant__isnull=True, activa=True),
        'propias': Vacuna.objects.filter(tenant=request.tenant, activa=True),
        'pesquisas_sistema': Pesquisa.objects.filter(tenant__isnull=True, activa=True),
        'pesquisas_propias': Pesquisa.objects.filter(tenant=request.tenant, activa=True)})
