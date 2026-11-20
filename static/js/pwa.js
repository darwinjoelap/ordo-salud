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

  const avisoPendientes = document.getElementById('os-transicion-pwa');
  // La X se recuerda al recargar y navegar en la misma pestaña, sin borrar borradores.
  // El aviso volverá a estar disponible en una sesión nueva del navegador.
  const claveAviso = avisoPendientes
    ? 'ordo.transicion.descartado.' + (avisoPendientes.dataset.tenant || '') + '.' +
      (avisoPendientes.dataset.usuario || '')
    : null;
  let avisoCerrado = false;
  try {
    avisoCerrado = Boolean(claveAviso && sessionStorage.getItem(claveAviso) === '1');
  } catch (err) {
    // El almacenamiento de sesión puede estar deshabilitado.
  }
  let revisionInventario = 0;

  function contarDictados(bd) {
    return new Promise((resolver) => {
      const apertura = bd.open('ordo-dictado');
      // La base puede desaparecer entre enumerar y abrir. Abortar evita recrearla.
      apertura.onupgradeneeded = () => apertura.transaction.abort();
      apertura.onerror = apertura.onblocked = () => resolver(0);
      apertura.onsuccess = () => {
        const conexion = apertura.result;
        try {
          if (!conexion.objectStoreNames.contains('pendientes')) {
            resolver(0);
            return;
          }
          const lectura = conexion.transaction('pendientes', 'readonly').objectStore('pendientes').count();
          lectura.onsuccess = () => resolver(lectura.result);
          lectura.onerror = () => resolver(0);
        } catch (err) {
          resolver(0);
        } finally {
          // Deja terminar la lectura y libera la conexión sin bloquear una actualización.
          conexion.close();
        }
      };
    });
  }

  if (avisoPendientes) {
    avisoPendientes.querySelector('[data-os-cerrar-pendientes]').addEventListener('click', () => {
      avisoCerrado = true;
      avisoPendientes.hidden = true;
      try {
        if (claveAviso) sessionStorage.setItem(claveAviso, '1');
      } catch (err) {
        // Se oculta esta página aunque el almacenamiento no esté disponible.
      }
    });
  }

  async function revisarPendientes() {
    if (!avisoPendientes || avisoCerrado) return;
    const revision = ++revisionInventario;
    const indicios = new Set();
    function mostrar() {
      if (revision !== revisionInventario || avisoCerrado) return;
      avisoPendientes.querySelectorAll('[data-estado]').forEach((el) => {
        el.hidden = !indicios.has(el.dataset.estado);
      });
      avisoPendientes.hidden = indicios.size === 0;
    }
    try {
      for (let i = 0; i < localStorage.length; i++) {
        const clave = localStorage.key(i);
        const tipo = /^ofl:(?:ordo-salud|omnis):[^:]+:[^:]+:(draft:.+|outbox)$/.exec(clave)?.[1];
        if (!tipo) continue;
        try {
          const valor = JSON.parse(localStorage.getItem(clave));
          if (tipo === 'outbox' && Array.isArray(valor) && valor.some((item) => item?.id)) {
            indicios.add('outbox');
          } else if (tipo.startsWith('draft:') && Array.isArray(valor?.campos) && valor.campos.length) {
            indicios.add('borrador');
          }
        } catch (err) {
          // Un valor ilegible no acredita un pendiente y se conserva intacto.
        }
      }
    } catch (err) {
      // El almacenamiento local puede estar inaccesible.
    }
    mostrar();
    try {
      const bd = window.indexedDB;
      if (bd?.databases && (await bd.databases()).some((base) => base.name === 'ordo-dictado') &&
          !avisoCerrado && revision === revisionInventario && (await contarDictados(bd)) > 0) {
        indicios.add('dictado');
        mostrar();
      }
    } catch (err) {
      // La enumeración puede estar deshabilitada o fallar.
    }
  }
  revisarPendientes();
  if (navigator.serviceWorker) navigator.serviceWorker.addEventListener('controllerchange', revisarPendientes);
  window.addEventListener('storage', revisarPendientes);
  window.addEventListener('pageshow', (evento) => {
    if (!evento.persisted) return;
    // Al volver del historial, actualizar el inventario sin bloquear la navegación
    // ni recargar formularios que podrían contener datos sin guardar.
    revisarPendientes();
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
