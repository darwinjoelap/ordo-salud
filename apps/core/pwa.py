"""Instalación PWA, caché de recursos públicos y visor PDF."""
import json

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import cache_control, never_cache

PRECARGA = [
    'vendor/bootstrap/bootstrap.min.css',
    'vendor/bootstrap-icons/bootstrap-icons.min.css',
    'css/ordo-salud.css',
    'vendor/bootstrap/bootstrap.bundle.min.js',
    'vendor/htmx/htmx.min.js',
    'js/pwa.js',
    'js/whatsapp.js',
    'js/secciones.js',
    'img/marca/ordo-salud-icono.svg',
    'img/marca/ordo-salud-logo.svg',
    'img/marca/ordo-salud-logo-blanco.svg',
    'vendor/fuentes/inter-latin.woff2',
    'vendor/fuentes/nunito-latin-700.woff2',
    'vendor/fuentes/nunito-latin-800.woff2',
    'img/marca/pwa/icon-192.png',
]

COLOR_TEMA = '#0B2E4C'   # barra del sistema marina, como la barra superior en el teléfono


@cache_control(max_age=3600, public=True)
def manifest(request):
    datos = {
        'id': '/',
        'name': 'Ordo Salud — Consultas médicas',
        'short_name': 'Ordo Salud',
        'description': 'Historia clínica, agenda, récipes y cobros para consultorios y clínicas.',
        'lang': 'es',
        'start_url': '/?origen=app',
        'scope': '/',
        'display': 'standalone',
        'orientation': 'any',
        'background_color': '#F4F7FA',
        'theme_color': COLOR_TEMA,
        'icons': [
            {'src': static('img/marca/pwa/icon-192.png'), 'sizes': '192x192', 'type': 'image/png'},
            {'src': static('img/marca/pwa/icon-512.png'), 'sizes': '512x512', 'type': 'image/png'},
            {'src': static('img/marca/pwa/icon-maskable-512.png'), 'sizes': '512x512', 'type': 'image/png',
             'purpose': 'maskable'},
        ],
        'shortcuts': [
            {'name': 'Pacientes', 'url': '/pacientes/',
             'icons': [{'src': static('img/marca/pwa/icon-192.png'), 'sizes': '192x192'}]},
        ],
    }
    return JsonResponse(datos, content_type='application/manifest+json', json_dumps_params={'ensure_ascii': False})


@never_cache
def service_worker(request):
    precarga = [static(r) for r in PRECARGA]
    js = (SW_JS.replace('__VERSION__', f'{SW_REVISION}-{settings.ORDO_VERSION}')
          .replace('__PRECARGA__', json.dumps(precarga)))
    r = HttpResponse(js, content_type='application/javascript; charset=utf-8')
    r['Service-Worker-Allowed'] = '/'
    return r


@never_cache
def offline(request):
    return render(request, 'core/offline.html', {'titulo': 'Sin conexión'})


SW_REVISION = 'f28'

SW_JS = r"""// Ordo Salud service worker · __VERSION__
const CACHE_STATIC = 'ordo-static-__VERSION__';
const PUBLICOS = new Set(__PRECARGA__.map((ruta) => new URL(ruta, self.location.origin).href));

async function recursoPublico(url) {
  const cache = await caches.open(CACHE_STATIC);
  const copia = await cache.match(url);
  if (copia) return copia;
  // La lista es cerrada y la petición jamás incluye una sesión.
  const respuesta = await fetch(url, { credentials: 'omit', redirect: 'error' });
  const tipo = respuesta.headers.get('Content-Type') || '';
  const reglas = respuesta.headers.get('Cache-Control') || '';
  if (respuesta.ok && /(^|,)\s*public\s*(,|$)/i.test(reglas) && !/no-store|private/i.test(reglas) &&
      /^(text\/(css|javascript)|application\/(javascript|font-woff)|font\/|image\/)/i.test(tipo)) {
    await cache.put(url, respuesta.clone());
  }
  return respuesta;
}

self.addEventListener('install', (evento) => {
  evento.waitUntil(Promise.allSettled([...PUBLICOS].map(recursoPublico)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (evento) => {
  // Durante el inventario solo se utiliza CACHE_STATIC. Las cachés legadas se conservan aisladas.
  evento.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (evento) => {
  const solicitud = evento.request;
  const url = new URL(solicitud.url);
  if (url.origin !== self.location.origin) return;
  if (solicitud.method === 'GET' && PUBLICOS.has(url.href) && solicitud.mode !== 'navigate') {
    evento.respondWith(recursoPublico(url.href));
    return;
  }

  const red = fetch(solicitud, { cache: 'no-store' });
  // Las respuestas de la aplicación nunca entran a Cache Storage, incluida la precarga antigua.
  evento.respondWith(solicitud.mode === 'navigate' ? red.catch(paginaSinConexion) : red);
});

function paginaSinConexion() {
  return new Response(
    '<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width">' +
    '<title>Sin conexión · Ordo Salud</title><h1>Sin conexión</h1>' +
    '<p>Conéctate a internet para abrir Ordo Salud.</p><button onclick="location.reload()">Reintentar</button></html>',
    {status: 503, headers: {'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store'}}
  );
}
"""

@login_required
def visor_pdf(request):
    """
    Muestra un PDF de la app DENTRO de la app (pdf.js). En la PWA instalada, abrir el PDF directo saca al usuario
    de la app (problema de constancias de Pediae en el móvil). Solo acepta rutas internas (?u=/recipes/5/pdf/).
    """
    u = request.GET.get('u', '')
    if not u.startswith('/') or u.startswith('//') or '\\' in u \
            or not url_has_allowed_host_and_scheme(u, allowed_hosts=None):
        raise Http404
    return render(request, 'core/visor_pdf.html', {'titulo': 'Documento', 'url_pdf': u})


def instalar(request):
    return render(request, 'core/instalar.html', {'titulo': 'Instalar Ordo Salud'})
