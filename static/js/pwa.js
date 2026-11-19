// Ordo Salud PWA: registro del service worker, aviso de instalación y estado de conexión.
(function () {
  'use strict';
  const CLAVE = 'ordo.instalar.descartado';
  const DIAS = 30;

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(function () {});
    });
  }

  const standalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
  if (standalone) document.documentElement.classList.add('os-instalada');

  // PDF dentro de la app instalada: abrirlos directo saca de la app y "atrás" la cierra.
  // Los enlaces/formularios con data-pdf se muestran en el visor interno (/visor/), que sí vuelve con "atrás".
  if (standalone) {
    const visor = function (href) {
      const u = new URL(href, location.href);
      return u.origin === location.origin ? '/visor/?u=' + encodeURIComponent(u.pathname + u.search) : null;
    };
    document.addEventListener('click', function (e) {
      const a = e.target.closest('a[data-pdf]');
      const destino = a && visor(a.href);
      if (destino) { e.preventDefault(); location.href = destino; }
    });
    document.addEventListener('submit', function (e) {
      const f = e.target;
      if (!f.matches || !f.matches('form[data-pdf]') || (f.method || 'get').toLowerCase() !== 'get') return;
      const destino = visor(f.action.split('?')[0] + '?' + new URLSearchParams(new FormData(f)).toString());
      if (destino) { e.preventDefault(); location.href = destino; }
    });
  }

  let revisionInventario = 0;
  async function revisarPendientes() {
    const aviso = document.getElementById('os-transicion-pwa');
    if (!aviso) return;
    const revision = ++revisionInventario;
    const indicios = new Set();
    function mostrar(enCurso = false) {
      if (revision !== revisionInventario) return;
      aviso.querySelectorAll('[data-estado]').forEach((el) => {
        const estado = el.dataset.estado;
        if (estado === 'sin-indicios') el.hidden = enCurso || indicios.size > 0;
        else el.hidden = !(indicios.has(estado) || (enCurso && estado === 'incompleto'));
      });
      if (indicios.size) aviso.open = true;
    }
    try {
      for (let i = 0; i < localStorage.length; i++) {
        const clave = localStorage.key(i);
        if (!/^ofl:(ordo-salud|omnis):/.test(clave)) continue;
        const tipo = /^ofl:[^:]+:[^:]+:[^:]+:(draft:.+|outbox|precarga)$/.exec(clave)?.[1];
        if (tipo?.startsWith('draft:')) indicios.add('borrador');
        else indicios.add(tipo || 'otro');
      }
    } catch (err) {
      indicios.add('inaccesible');
    }
    mostrar(true);
    try {
      if (!window.caches?.keys) indicios.add('incompleto');
      else if ((await window.caches.keys()).some((nombre) =>
        nombre === 'ordo-paginas-v1' || nombre === 'omnis-paginas-v1')) indicios.add('paginas');
    } catch (err) {
      indicios.add('inaccesible');
    }
    mostrar(true);
    try {
      if (!window.indexedDB?.databases) indicios.add('incompleto');
      else if ((await window.indexedDB.databases()).some((base) => base.name === 'ordo-dictado')) {
        indicios.add('dictado');
      }
    } catch (err) {
      indicios.add('inaccesible');
    }
    mostrar();
  }
  revisarPendientes();
  if (navigator.serviceWorker) navigator.serviceWorker.addEventListener('controllerchange', revisarPendientes);
  window.addEventListener('storage', revisarPendientes);
  window.addEventListener('pageshow', (evento) => {
    if (!evento.persisted) return;
    // Una página restaurada puede pertenecer a una sesión anterior. Bloquear su uso sin descartar el DOM.
    const bloqueo = document.getElementById('os-pagina-restaurada');
    if (bloqueo && !bloqueo.open) {
      // El diálogo no permite volver a interactuar con el documento de la sesión anterior.
      bloqueo.addEventListener('cancel', (e) => e.preventDefault(), {once: false});
      bloqueo.querySelector('[data-os-recargar]').addEventListener('click', () => location.reload(), {once: true});
      bloqueo.showModal();
    }
  });

  function descartadoReciente() {
    try {
      const t = parseInt(localStorage.getItem(CLAVE) || '0', 10);
      return t && (Date.now() - t) < DIAS * 864e5;
    } catch (e) { return false; }
  }
  function descartar() {
    try { localStorage.setItem(CLAVE, String(Date.now())); } catch (e) {}
    const b = document.getElementById('os-instalar'); if (b) b.hidden = true;
  }

  function mostrar(modo) {
    const b = document.getElementById('os-instalar');
    if (!b || standalone || descartadoReciente()) return;
    b.querySelectorAll('[data-modo]').forEach(function (el) { el.hidden = el.dataset.modo !== modo; });
    b.hidden = false;
  }

  // Android / Chrome / Edge: prompt nativo
  let evento = null;
  window.addEventListener('beforeinstallprompt', function (e) {
    e.preventDefault();
    evento = e;
    mostrar('nativo');
  });
  window.addEventListener('appinstalled', descartar);

  document.addEventListener('click', function (e) {
    if (e.target.closest('[data-os-instalar]') && evento) {
      evento.prompt();
      evento.userChoice.finally(function () { evento = null; descartar(); });
    }
    if (e.target.closest('[data-os-descartar]')) descartar();
  });

  // iPhone / iPad (Safari): no hay prompt, se explica cómo hacerlo
  const ua = navigator.userAgent;
  const esIOS = /iPad|iPhone|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const esSafari = /Safari/.test(ua) && !/CriOS|FxiOS|EdgiOS/.test(ua);
  if (esIOS && esSafari) window.addEventListener('load', function () { setTimeout(function () { mostrar('ios'); }, 1500); });

  // Estado de conexión
  function conexion() {
    const a = document.getElementById('os-sin-conexion');
    if (a) a.hidden = navigator.onLine;
  }
  window.addEventListener('online', conexion);
  window.addEventListener('offline', conexion);
  document.addEventListener('DOMContentLoaded', conexion);
})();
