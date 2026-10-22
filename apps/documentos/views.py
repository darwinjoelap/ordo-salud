from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.clinica.consultas import puede_ver
from apps.clinica.models import Consulta
from apps.core import auditoria
from apps.core.pdf import respuesta_pdf
from apps.core.permisos import requiere, tiene_permiso
from apps.pacientes.models import Paciente

from . import servicios as srv
from .forms import AnularForm
from .models import DocumentoEmitido
from .registro import disponibles, documento


def _consulta(request, pk):
    consulta = get_object_or_404(Consulta.objects.select_related('paciente', 'profesional__membresia__usuario',
                                                                 'especialidad', 'lugar'), pk=pk)
    if not puede_ver(request.membresia, consulta):
        raise PermissionDenied
    return consulta


def _puede_ver_documento(request, doc):
    if doc.tipo == 'recibo':
        return tiene_permiso(request, 'cobros.gestionar')
    if not tiene_permiso(request, 'historia.ver'):
        return False
    return doc.consulta is None or puede_ver(request.membresia, doc.consulta)


@login_required
@requiere('historia.ver')
def emitir(request, codigo):
    definicion = documento(codigo)
    if definicion is None or definicion.extra.get('interno'):
        raise Http404
    perfil = request.membresia.perfil_activo
    consulta = _consulta(request, request.GET.get('consulta') or request.POST.get('consulta')) \
        if (request.GET.get('consulta') or request.POST.get('consulta')) else None
    paciente = consulta.paciente if consulta else get_object_or_404(Paciente.objects.all(), pk=request.GET.get('paciente')
                                                                    or request.POST.get('paciente'))
    if definicion.requiere_consulta:
        if consulta is None:
            raise Http404
        if consulta.profesional_id != perfil.pk:
            messages.error(request, f'«{definicion.nombre}» lo emite quien atendió la consulta. '
                                    'Puedes imprimir la historia desde la consulta.')
            return redirect('clinica:consulta', pk=consulta.pk)
    if definicion.formulario is None:
        # Sin formulario: desde la consulta se reutiliza su número; desde la ficha se emite uno nuevo.
        doc = (srv.documento_de_consulta(codigo, consulta) if consulta is not None
               else srv.emitir(codigo, paciente=paciente, profesional=perfil))
        auditoria.registrar(request, 'IMPRIMIR', doc, paciente_id=paciente.pk, detalle=doc.numero)
        return redirect(_url_pdf(doc))
    inicial = {'ciudad': consulta.lugar.ciudad if consulta and consulta.lugar_id else ''}
    if definicion.inicial:
        inicial.update(definicion.inicial(paciente, consulta))
    form = definicion.formulario(request.POST or None, initial=inicial, paciente=paciente, request=request)
    if request.method == 'POST' and form.is_valid():
        doc = srv.emitir(codigo, paciente=paciente, profesional=perfil, consulta=consulta, datos=form.datos())
        auditoria.registrar(request, 'CREAR', doc, paciente_id=paciente.pk, detalle=doc.numero)
        messages.success(request, f'{definicion.nombre} {doc.numero} emitido.')
        return redirect('documentos:documento', pk=doc.pk)
    return render(request, 'documentos/emitir.html', {
        'titulo': definicion.nombre, 'definicion': definicion, 'form': form, 'paciente': paciente,
        'consulta': consulta})


def _url_pdf(doc):
    return reverse('documentos:pdf', args=[doc.pk])


@login_required
def ver(request, pk):
    doc = get_object_or_404(DocumentoEmitido.objects.select_related('paciente', 'consulta', 'profesional'), pk=pk)
    if not _puede_ver_documento(request, doc):
        raise PermissionDenied
    perfil = request.membresia.perfil_activo if request.membresia else None
    return render(request, 'documentos/documento.html', {
        'titulo': f'{doc.definicion.nombre if doc.definicion else doc.tipo} {doc.numero}', 'doc': doc,
        'es_firmante': bool(perfil and doc.profesional_id == perfil.pk), 'form_anular': AnularForm()})


@login_required
def pdf(request, pk):
    doc = get_object_or_404(DocumentoEmitido.objects.select_related(
        'paciente', 'consulta__lugar', 'profesional__membresia__usuario', 'profesional__especialidad',
        'tenant__configuracion'), pk=pk)
    if not _puede_ver_documento(request, doc) or doc.definicion is None:
        raise PermissionDenied
    perfil = request.membresia.perfil_activo if request.membresia else None
    # La imagen de la firma solo la pone quien firma: otro usuario imprime con la raya en blanco.
    con_firma = bool(perfil and doc.profesional_id == perfil.pk) and request.GET.get('firma') != '0'
    auditoria.registrar(request, 'IMPRIMIR', doc, paciente_id=doc.paciente_id, detalle=doc.numero)
    return respuesta_pdf(srv.pdf(doc, con_firma=con_firma), doc.numero, doc.paciente.nombre_completo, doc.fecha)


@login_required
@require_POST
def anular(request, pk):
    doc = get_object_or_404(DocumentoEmitido.objects.all(), pk=pk)
    perfil = request.membresia.perfil_activo if request.membresia else None
    if not (perfil and doc.profesional_id == perfil.pk) and not tiene_permiso(request, 'tenant.configurar'):
        raise PermissionDenied
    form = AnularForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Indica el motivo de la anulación.')
    else:
        srv.anular(doc, form.cleaned_data['motivo'])
        auditoria.registrar(request, 'ANULAR', doc, paciente_id=doc.paciente_id, detalle=form.cleaned_data['motivo'])
        messages.success(request, f'Documento {doc.numero} anulado.')
    return redirect('documentos:documento', pk=doc.pk)


@login_required
@requiere('cobros.gestionar')
def recibo(request, pago_pk):
    from apps.cobros.models import Pago
    pago = get_object_or_404(Pago.objects.select_related('paciente'), pk=pago_pk)
    doc = srv.recibo_de_pago(pago)
    return redirect(_url_pdf(doc))


def menu_documentos(request, consulta=None):
    """Para las plantillas: documentos que el usuario puede emitir (en la consulta o la ficha)."""
    perfil = request.membresia.perfil_activo if request.membresia else None
    if perfil is None:
        return []
    salida = disponibles(especialidad=perfil.especialidad.codigo if perfil.especialidad_id else None,
                         con_consulta=consulta is not None)
    if consulta is not None and consulta.profesional_id != perfil.pk:
        salida = [d for d in salida if not d.requiere_consulta]
    return [d for d in salida if not d.extra.get('interno')]


@login_required
def prueba(request, perfil_pk=None):
    """PDF de muestra con el perfil del profesional: banner o logo, marca de agua, firma y sello al pie."""
    from types import SimpleNamespace

    from django.utils import timezone

    from apps.core.pdf import Paragraph
    from apps.equipo.models import PerfilProfesional

    from .generadores.base import CUERPO, construir, lugar_y_fecha, titulo
    propio = request.membresia.perfil_activo if request.membresia else None
    if perfil_pk is not None and (propio is None or propio.pk != perfil_pk):
        if not tiene_permiso(request, 'usuarios.gestionar'):
            raise PermissionDenied
        perfil = get_object_or_404(PerfilProfesional.objects.all(), pk=perfil_pk)
    else:
        perfil = propio
    if perfil is None:
        raise Http404
    hoy = timezone.localdate()
    doc = SimpleNamespace(tenant=request.tenant, profesional=perfil, numero='MUESTRA', fecha=hoy,
                          datos={}, consulta_id=None, consulta=None)
    cuerpo = lugar_y_fecha(hoy) + titulo('Documento de muestra', request.tenant)
    cuerpo.append(Paragraph(
        'Así se verán sus récipes, informes, reposos y constancias: encabezado con su banner o con su logo y '
        'datos profesionales, el logo tenue de fondo y su firma y sello fijos al pie de cada hoja.', CUERPO))
    return respuesta_pdf(construir(doc, cuerpo), 'muestra', perfil.nombre_con_titulo)
