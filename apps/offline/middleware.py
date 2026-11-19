"""
IdempotenciaMiddleware (de Pediae/Ginea): evita duplicados cuando un formulario se envía más de una vez.

Va AL FINAL de MIDDLEWARE (después de MessageMiddleware): necesita request.user y los mensajes.
Solo actúa en POST con `_idem_key` (o header X-Idempotency-Key), que agrega offline.js.
- Misma clave ya completada → misma redirección, sin volver a procesar.
- Con X-Offline-Form (fetch de offline.js) las redirecciones vuelven como JSON {ok, redirect}.
- Sesión vencida → 401 {login: true}; clave aún en proceso → 409.
- Respuestas 200 (errores de formulario), 4xx y 5xx liberan la clave para poder reintentar.
"""
import re
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import resolve_url
from django.urls import Resolver404, resolve
from django.utils import timezone

from .models import SolicitudIdempotente

CLAVE_RE = re.compile(r'^[A-Za-z0-9-]{8,64}$')
HEADER_OFFLINE = 'HTTP_X_OFFLINE_FORM'
MINUTOS_PROCESANDO = 2
DIAS_RETENCION = 7


class ContencionOfflineMiddleware:
    """Intercepta el protocolo de la cola antes de redirecciones, permisos y recibos previos."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == 'POST' and request.META.get(HEADER_OFFLINE) == '1':
            try:
                destino = resolve(request.path_info)
            except Resolver404:
                destino = None
            if destino and destino.func.__module__.startswith('apps.'):
                # El cliente conserva el elemento como error y solo lo reintenta manualmente.
                return JsonResponse({'estado': 'revision_necesaria'}, status=403)
        return self.get_response(request)


def _clave(request):
    clave = (request.META.get('HTTP_X_IDEMPOTENCY_KEY') or '').strip()
    if not clave:
        try:
            clave = (request.POST.get('_idem_key') or '').strip()
        except Exception:  # noqa: BLE001  cuerpo ilegible: que lo maneje la vista
            clave = ''
    return clave if CLAVE_RE.match(clave) else ''


def _es_login(location):
    return bool(location) and resolve_url(settings.LOGIN_URL) in location


def _respuesta(request, location):
    if request.META.get(HEADER_OFFLINE):
        return JsonResponse({'ok': True, 'redirect': location})
    return HttpResponseRedirect(location)


def limpiar_viejas():
    return SolicitudIdempotente.objects.filter(creado__lt=timezone.now() - timedelta(days=DIAS_RETENCION)).delete()[0]


class IdempotenciaMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method != 'POST':
            return self.get_response(request)
        clave = _clave(request)
        if not clave:
            return self.get_response(request)

        # Estas operaciones verifican el intento dentro de la vista con permisos y contexto actuales.
        # Un recibo de navegación antiguo no puede sustituir esa comprobación.
        try:
            ruta = resolve(request.path_info)
        except Resolver404:
            ruta = None
        if ruta and ruta.view_name in (
                'agenda:recordatorio', 'agenda:contacto_cumpleanos', 'agenda:recordatorio_inactividad',
                'agenda:cobrar_cita'):
            return self.get_response(request)
        if ruta and ruta.view_name == 'clinica:consulta_nueva' and request.POST.get('independiente') == '1':
            # H1 comprueba la firma ligada a este usuario, consultorio, perfil y paciente.
            return self.get_response(request)

        user = getattr(request, 'user', None)
        usuario_id = user.pk if user is not None and user.is_authenticated else None
        clave_db = f'{usuario_id or 0}:{clave}'
        try:
            with transaction.atomic():
                registro = SolicitudIdempotente.objects.create(clave=clave_db, usuario_id=usuario_id,
                                                               ruta=request.path[:300])
        except IntegrityError:
            previo = SolicitudIdempotente.objects.filter(clave=clave_db).first()
            if previo is None:
                return self.get_response(request)
            if previo.estado == SolicitudIdempotente.OK:
                messages.info(request, 'Esta información ya se había guardado. No se duplicó.')
                return _respuesta(request, previo.location or request.path)
            if previo.creado > timezone.now() - timedelta(minutes=MINUTOS_PROCESANDO):
                return JsonResponse({'ok': False, 'estado': 'procesando'}, status=409)
            previo.creado = timezone.now()        # huérfano (el servidor se cayó a mitad): se toma el relevo
            previo.save(update_fields=['creado'])
            registro = previo

        response = self.get_response(request)
        location = response.get('Location', '') if response.status_code in (301, 302, 303) else ''
        if _es_login(location):
            registro.delete()
            if request.META.get(HEADER_OFFLINE):
                return JsonResponse({'ok': False, 'login': True, 'redirect': location}, status=401)
            return response
        if location:
            registro.estado = SolicitudIdempotente.OK
            registro.location = location[:500]
            registro.save(update_fields=['estado', 'location'])
            if request.META.get(HEADER_OFFLINE):
                nueva = JsonResponse({'ok': True, 'redirect': location})
                nueva.cookies = response.cookies      # conserva mensajes y sesión
                return nueva
            return response
        registro.delete()
        return response
