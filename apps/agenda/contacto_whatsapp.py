"""Entrega de WhatsApp solo después de autorizar la acción en servidor."""
from uuid import UUID

from django.http import HttpResponse, JsonResponse

from apps.configuracion import whatsapp
from apps.core import auditoria
from apps.core.models import Auditoria

APERTURAS = ('business', 'web')
ACCIONES = (*APERTURAS, 'copiar', 'validar')


def clave_intento(request):
    try:
        return str(UUID(request.POST.get('clave_intento', '')))
    except ValueError:
        return None


def respuesta(accion, url):
    if not url:
        return JsonResponse({'error': 'El contacto ya no está disponible. Revisa el destinatario.'}, status=409)
    if accion == 'validar':
        return HttpResponse(status=204)
    if accion == 'copiar':
        from urllib.parse import parse_qs, urlparse

        return JsonResponse({'mensaje': parse_qs(urlparse(url).query).get('text', [''])[0]})
    return JsonResponse({'destino': whatsapp.intent_business(url) if accion == 'business' else url})


def registrar_intento(request, *, objetivo, paciente_id, clave, contexto):
    """La vista ya bloqueó el paciente. Revalidar siempre, incluso si la clave se repite."""
    tipo = objetivo._meta.label
    objeto_id = str(objetivo.pk)
    detalle = f'Intento WhatsApp · {contexto} · {clave}'
    if Auditoria.objects.filter(usuario=request.user, objeto_tipo=tipo, objeto_id=objeto_id,
                                paciente_id=paciente_id, detalle=detalle).exists():
        return False
    auditoria.registrar(request, 'EDITAR', objetivo, paciente_id=paciente_id, detalle=detalle)
    return True
