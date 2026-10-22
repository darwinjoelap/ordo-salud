"""
PWA: manifest, service worker, página sin conexión, visor de PDF e instrucciones de instalación (de Ordo).

Service worker (Fase 12, lógica de Pediae):
- estáticos: primero caché (llevan hash gracias a WhiteNoise);
- páginas de consulta (inicio, agenda, pacientes, ficha, consulta nueva/en curso): primero red y se guarda
  una copia en `ordo-paginas-v1`; sin red o con red muy lenta se muestra la copia (marcada como copia);
- otras páginas: red; sin red, una página que lista las copias disponibles;
- llegar al login (sesión cerrada o vencida) o cerrar sesión borra las copias (privacidad); se purgan a los 7 días;
- los POST nunca pasan por aquí: los maneja static/js/offline.js con su cola e idempotencia.
"""
import json

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render, resolve_url
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
    'js/offline.js',
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
          .replace('__PRECARGA__', json.dumps(precarga)).replace('__STATIC__', settings.STATIC_URL)
          .replace('__LOGIN__', resolve_url(settings.LOGIN_URL)))
    r = HttpResponse(js, content_type='application/javascript; charset=utf-8')
    r['Service-Worker-Allowed'] = '/'
    return r


@cache_control(max_age=86400, public=True)
def offline(request):
    return render(request, 'core/offline.html', {'titulo': 'Sin conexión'})


SW_REVISION = 'f14'    # subir al cambiar la lógica del service worker

SW_JS = r"""// Ordo Salud service worker · __VERSION__
const VERSION = '__VERSION__';
const CACHE_STATIC = 'ordo-static-' + VERSION;
const CACHE_PAGINAS = 'ordo-paginas-v1';     // no cambia con la versión: no perder copias al actualizar
const PRECARGA = __PRECARGA__;
const STATIC = '__STATIC__';
const LOGIN = '__LOGIN__';
const TIMEOUT_CON_COPIA = 5000;               // si hay copia, esperar la red como máximo esto
const TIMEOUT_SIN_COPIA = 30000;
const DIAS_COPIA = 7;

// Páginas que se guardan para usar sin conexión
const PAGINAS_OFFLINE = [
  /^\/$/,
  /^\/agenda\/$/,
  /^\/pacientes\/$/,
  /^\/pacientes\/\d+\/$/,
  /^\/pacientes\/\d+\/consultas\/nueva\/$/,
  /^\/consultas\/\d+\/(editar\/)?$/,
  /^\/pacientes\/\d+\/ficha\/[a-z_]+\/$/,
  /^\/esp\/[a-z_]+\/pacientes\/\d+\/vacunas\/$/,
];
const esPaginaOffline = (url) => PAGINAS_OFFLINE.some((re) => re.test(url.pathname));
const esLogin = (url) => url.pathname === LOGIN;

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE_STATIC)
    .then((c) => Promise.all(PRECARGA.map((u) => c.add(u).catch(() => null))))
    .then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys()
    .then((claves) => Promise.all(claves
      .filter((k) => k.startsWith('ordo-') && k !== CACHE_STATIC && k !== CACHE_PAGINAS)
      .map((k) => caches.delete(k))))
    .then(purgarViejas)
    .then(() => self.clients.claim()));
});

self.addEventListener('message', (e) => {
  const d = e.data || {};
  const responder = (datos) => { if (e.ports && e.ports[0]) e.ports[0].postMessage(datos); };
  if (d.tipo === 'borrar-paginas') e.waitUntil(caches.delete(CACHE_PAGINAS).then(() => responder({ ok: true })));
  else if (d.tipo === 'listar-paginas') e.waitUntil(listarPaginas().then((l) => responder({ ok: true, paginas: l })));
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/offline/ping') || url.pathname.startsWith('/offline/precache')) return;

  if (url.pathname.startsWith(STATIC)) { e.respondWith(cacheFirst(req)); return; }

  const navegacion = req.mode === 'navigate';
  const precarga = req.headers.get('X-Offline-Prefetch') === '1';
  if (navegacion && esLogin(url)) {             // sesión cerrada o vencida → borrar copias
    e.waitUntil(caches.delete(CACHE_PAGINAS));
    return;
  }
  if ((navegacion || precarga) && esPaginaOffline(url)) {
    e.respondWith(networkFirstPagina(e, req, url, precarga));
    return;
  }
  if (navegacion) e.respondWith(fetch(req).catch(() => paginaSinConexion()));
});

function cacheFirst(req) {
  return caches.match(req).then((r) => r || fetch(req).then((resp) => {
    if (resp && resp.ok) { const copia = resp.clone(); caches.open(CACHE_STATIC).then((c) => c.put(req, copia)); }
    return resp;
  }));
}

function guardable(resp) {
  return resp && resp.ok && !resp.redirected && (resp.headers.get('Content-Type') || '').indexOf('text/html') !== -1;
}

function guardarPagina(url, resp) {
  return resp.clone().text().then((html) => {
    const headers = new Headers(resp.headers);
    headers.set('X-Offline-Guardado', String(Date.now()));
    const titulo = (html.match(/<title>([\s\S]*?)<\/title>/i) || [])[1] || '';
    headers.set('X-Offline-Titulo', encodeURIComponent(titulo.replace(/\s+/g, ' ').trim()));
    return caches.open(CACHE_PAGINAS).then((c) => c.put(url.href, new Response(html, { status: 200, headers })));
  });
}

function buscarCopia(url) {
  return caches.open(CACHE_PAGINAS).then((c) => c.match(url.href, { ignoreVary: true }).then((r) => {
    if (r) return r;
    // «Consulta nueva» con otro ?cita= → sirve la misma pantalla del paciente (offline.js ajusta la cita)
    if (/^\/pacientes\/\d+\/consultas\/nueva\/$/.test(url.pathname)) {
      return c.match(url.origin + url.pathname, { ignoreVary: true, ignoreSearch: true });
    }
    return null;
  }));
}

function marcarCopia(resp, motivo) {
  return resp.text().then((html) => {
    const ts = resp.headers.get('X-Offline-Guardado') || '';
    const marca = '<script>window.__OFFLINE_COPIA={guardado:' + (Number(ts) || 0) + ',motivo:"' + motivo + '"};</script>';
    html = html.indexOf('</head>') !== -1 ? html.replace('</head>', marca + '</head>') : marca + html;
    const headers = new Headers(resp.headers);
    headers.set('Content-Type', 'text/html; charset=utf-8');
    return new Response(html, { status: 200, headers });
  });
}

function extender(e, promesa) {
  try { e.waitUntil(promesa); } catch (err) { /* el evento ya terminó */ }
  return promesa;
}

function networkFirstPagina(e, req, url, precarga) {
  const red = fetch(req).then((resp) => {
    if (guardable(resp)) {
      const p = extender(e, guardarPagina(url, resp));
      if (precarga) return p.then(() => resp);   // la precarga espera a que quede guardada
    } else if (resp && resp.redirected && esLogin(new URL(resp.url))) {
      extender(e, caches.delete(CACHE_PAGINAS));
    }
    return resp;
  });
  if (precarga) return red;

  return buscarCopia(url).then((copia) => {
    const espera = new Promise((ok) => setTimeout(() => ok('timeout'), copia ? TIMEOUT_CON_COPIA : TIMEOUT_SIN_COPIA));
    return Promise.race([red.catch(() => 'sin-red'), espera]).then((r) => {
      if (r instanceof Response) return r;
      if (copia) return marcarCopia(copia, r === 'timeout' ? 'lento' : 'sin-red');
      if (r === 'timeout') return red.catch(() => paginaSinConexion());
      return paginaSinConexion();
    });
  });
}

function listarPaginas() {
  return caches.open(CACHE_PAGINAS).then((c) => c.keys().then((claves) => Promise.all(claves.map((k) =>
    c.match(k).then((r) => ({
      url: k.url,
      titulo: decodeURIComponent(r.headers.get('X-Offline-Titulo') || ''),
      guardado: Number(r.headers.get('X-Offline-Guardado')) || 0,
    }))))));
}

function purgarViejas() {
  const limite = Date.now() - DIAS_COPIA * 86400000;
  return caches.open(CACHE_PAGINAS).then((c) => c.keys().then((claves) => Promise.all(claves.map((k) =>
    c.match(k).then((r) => { if ((Number(r && r.headers.get('X-Offline-Guardado')) || 0) < limite) return c.delete(k); })))));
}

const esc = (s) => String(s).replace(/[&<>"]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));

function hora(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  return d.toLocaleDateString('es-VE', { day: '2-digit', month: '2-digit' }) + ' ' +
    d.toLocaleTimeString('es-VE', { hour: 'numeric', minute: '2-digit' });
}

function paginaSinConexion() {
  return listarPaginas().then((lista) => {
    lista.sort((a, b) => b.guardado - a.guardado);
    const items = lista.map((p) => {
      const u = new URL(p.url);
      const t = (p.titulo || u.pathname).split(' · Ordo Salud')[0];
      return '<a class="item" href="' + esc(u.pathname + u.search) + '">' + esc(t) + '<small>Guardada ' + esc(hora(p.guardado)) + '</small></a>';
    }).join('');
    const html = '<!doctype html><html lang="es"><head><meta charset="utf-8">' +
      '<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#0B2E4C"><title>Sin conexión · Ordo Salud</title>' +
      '<style>body{font-family:Inter,system-ui,sans-serif;margin:0;background:#F4F7FA;color:#10222F}' +
      '.box{max-width:540px;margin:0 auto;padding:28px 16px}h1{font-family:Nunito,Inter,sans-serif;font-weight:800;color:#0C385B;font-size:1.35rem;margin:.6rem 0 .5rem}' +
      '.chip{display:inline-block;background:#A23B32;color:#fff;border-radius:999px;padding:.25rem .75rem;font-size:.8rem;font-weight:600}' +
      'p{color:#4B5E6D;line-height:1.5}.item{display:block;background:#fff;border:1px solid #DCE4EB;border-radius:14px;padding:.85rem 1rem;margin:.55rem 0;' +
      'color:#0C385B;text-decoration:none;font-weight:600}.item small{display:block;color:#4B5E6D;font-weight:400;margin-top:.15rem}' +
      'button{margin-top:1rem;width:100%;height:48px;border:0;border-radius:12px;background:#145F8F;color:#fff;font-size:1rem;font-weight:600}</style>' +
      '</head><body><div class="box"><span class="chip">Sin conexión</span>' +
      '<h1>Esta pantalla no está guardada en el dispositivo</h1>' +
      '<p>Puedes seguir trabajando con las pantallas guardadas. Lo que registres se enviará solo cuando vuelva la señal.</p>' +
      (items || '<p><em>Todavía no hay pantallas guardadas. Abre Ordo Salud con internet al menos una vez en este dispositivo.</em></p>') +
      '<button onclick="location.reload()">Reintentar</button></div></body></html>';
    return new Response(html, { status: 200, headers: { 'Content-Type': 'text/html; charset=utf-8' } });
  });
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
