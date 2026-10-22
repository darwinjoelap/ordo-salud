/* =====================================================================
   offline.js — Ordo Salud · modo sin conexión de consulta (portado de Pediae/Ginea)
   ---------------------------------------------------------------------
   1. Borradores: lo que se escribe en un formulario se guarda en el dispositivo
      (localStorage) mientras se escribe; si se cae la red, se cierra la app o se
      recarga, se ofrece recuperarlo.
   2. Envío seguro: los formularios POST se envían con fetch + timeout. Sin red o
      con red muy lenta, el envío queda en una cola local y se reintenta solo. Cada
      envío lleva una clave única (_idem_key) que el servidor
      (apps.offline.middleware.IdempotenciaMiddleware) usa para no duplicar nada.
   3. Indicador: una píldora muestra "Sin conexión", "Conexión lenta", "N por enviar"…
      Al tocarla se ve la cola.
   4. Precarga: con buena señal descarga la agenda y las fichas/consultas de los
      pacientes citados para que el service worker las tenga sin datos.

   Lo incluye base.html solo para usuarios con consultorio (no soporte):
     window.OFFLINE_CFG = {app:'ordo-salud', tenant:'<slug>', user:'<pk>', loginUrl:'/cuenta/entrar/'}
   Excluir un formulario:            <form ... data-offline="off">
   Destino alternativo sin conexión: <form ... data-offline-alt="/ruta/">  (p. ej. «Atender» → consulta nueva)
   ===================================================================== */
(function () {
  'use strict';

  var CFG = window.OFFLINE_CFG || {};
  if (!CFG.user || window.__offlineJsCargado) return;
  window.__offlineJsCargado = true;

  var APP = CFG.app || 'ordo-salud';
  var TENANT = String(CFG.tenant || '-');
  var USER = String(CFG.user);
  var LOGIN_URL = CFG.loginUrl || '/cuenta/entrar/';
  var PING_URL = CFG.pingUrl || '/offline/ping/';

  var TIMEOUT_ENVIO = 20000;      // ms máximo esperando respuesta al guardar
  var TIMEOUT_PING = 6000;
  var LENTO_MS = 2500;            // latencia a partir de la cual se considera "lenta"
  var PING_NORMAL = 30000;
  var PING_PROBLEMA = 8000;
  var SYNC_CADA = 15000;
  var TTL_BORRADOR = 7 * 24 * 3600 * 1000;

  // Acciones que NO se encolan (PDFs, eliminar, sesión). Con red funcionan igual que siempre.
  var EXCLUIR_ACTION = /(salir|entrar|pdf|documentos|imprimir|anular|adjuntar|eliminar|clave)/i;
  var SALIR_ACTION = /\/salir\/?$/i;

  var CACHE_PAGINAS = 'ordo-paginas-v1';   // mismo nombre que en el service worker (apps/core/pwa.py)
  var PRECARGA_CADA = 20 * 60 * 1000;     // refrescar copias como máximo cada 20 min (en la agenda: cada 3 min)

  var NS = 'ofl:' + APP + ':' + TENANT + ':' + USER + ':';
  var K_OUTBOX = NS + 'outbox';
  var K_DRAFT = NS + 'draft:';
  var K_PRECARGA = NS + 'precarga';

  var estado = { red: 'online', fallosPing: 0, sincronizando: false, auth: true };
  var outboxCache = [];

  /* ───────────────────────── utilidades ───────────────────────── */

  function uuid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      var r = Math.random() * 16 | 0;
      return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
    });
  }

  function getCookie(nombre) {
    var m = document.cookie.match('(?:^|;)\\s*' + nombre + '=([^;]*)');
    return m ? decodeURIComponent(m[1]) : '';
  }

  function lsGet(k, def) {
    try { var v = localStorage.getItem(k); return v ? JSON.parse(v) : def; } catch (e) { return def; }
  }
  function lsSet(k, v) {
    try { localStorage.setItem(k, JSON.stringify(v)); return true; } catch (e) { return false; }
  }
  function lsDel(k) { try { localStorage.removeItem(k); } catch (e) { /* nada */ } }

  function hora(ts) {
    var d = new Date(ts);
    var hoy = new Date();
    var hh = d.toLocaleTimeString('es-VE', { hour: '2-digit', minute: '2-digit' });
    if (d.toDateString() === hoy.toDateString()) return 'hoy ' + hh;
    return d.toLocaleDateString('es-VE', { day: '2-digit', month: '2-digit' }) + ' ' + hh;
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function paginaActual() { return location.pathname + location.search; }

  /* ───────────────────────── cola (outbox) ───────────────────────── */

  function outboxLeer() {
    var lista = lsGet(K_OUTBOX, []);
    outboxCache = Array.isArray(lista) ? lista : [];
    return outboxCache;
  }
  function outboxGuardar(lista) {
    outboxCache = lista;
    var ok = lsSet(K_OUTBOX, lista);
    pintarIndicador();
    return ok;
  }
  function outboxPut(item) {
    var lista = outboxLeer().filter(function (i) { return i.id !== item.id; });
    lista.push(item);
    return outboxGuardar(lista);
  }
  function outboxDel(id) {
    outboxGuardar(outboxLeer().filter(function (i) { return i.id !== id; }));
  }
  function outboxPorDraft(draftId) {
    if (!draftId) return null;
    return outboxLeer().filter(function (i) { return i.draft === draftId; })[0] || null;
  }

  /* ───────────────────────── formularios ───────────────────────── */

  function esPost(form) {
    return form && form.tagName === 'FORM' && (form.getAttribute('method') || '').toLowerCase() === 'post';
  }

  function rastreable(form) {
    if (!esPost(form)) return false;
    if (form.dataset.offline === 'off') return false;
    var target = form.getAttribute('target');
    if (target && target !== '_self') return false;
    if ((form.enctype || '').indexOf('multipart') !== -1 && form.querySelector('input[type=file]')) return false;
    var action = form.getAttribute('action') || '';
    if (EXCLUIR_ACTION.test(action)) return false;
    return true;
  }

  // Borradores solo en formularios "de página" (no en modales con action dinámica)
  function conBorrador(form) {
    return rastreable(form) && !form.closest('.modal');
  }

  function formsPost() {
    return Array.prototype.filter.call(document.forms, esPost);
  }

  function draftIdDe(form) {
    if (!conBorrador(form)) return null;
    var idx = formsPost().indexOf(form);
    return paginaActual() + '#' + (form.id || idx);
  }

  function tituloDe(form) {
    if (form.dataset.offlineTitulo) return form.dataset.offlineTitulo;
    var h = document.querySelector('main h1, main h2, main h3, main h4, main h5');
    var t = h ? h.textContent.replace(/\s+/g, ' ').trim() : document.title;
    return t.slice(0, 80) || 'Formulario';
  }

  var SALTAR = { csrfmiddlewaretoken: 1, _idem_key: 1 };

  function serializarBorrador(form) {
    var campos = [];
    Array.prototype.forEach.call(form.elements, function (el) {
      if (!el.name || SALTAR[el.name]) return;
      var tipo = (el.type || '').toLowerCase();
      if (/^(file|password|submit|button|reset|image)$/.test(tipo)) return;
      if (tipo === 'checkbox' || tipo === 'radio') {
        campos.push([el.name, el.value, el.checked ? 1 : 0]);
      } else if (tipo === 'select-multiple') {
        var sel = Array.prototype.filter.call(el.options, function (o) { return o.selected; })
          .map(function (o) { return o.value; });
        campos.push([el.name, sel]);
      } else {
        campos.push([el.name, el.value]);
      }
    });
    return campos;
  }

  function aplicarBorrador(form, campos) {
    var porNombre = {};
    campos.forEach(function (c) { (porNombre[c[0]] = porNombre[c[0]] || []).push(c); });
    var tocados = [];
    Array.prototype.forEach.call(form.elements, function (el) {
      if (!el.name || SALTAR[el.name] || !porNombre[el.name]) return;
      var tipo = (el.type || '').toLowerCase();
      var lista = porNombre[el.name];
      if (tipo === 'checkbox' || tipo === 'radio') {
        var match = lista.filter(function (c) { return c[1] === el.value; })[0];
        if (match) el.checked = !!match[2];
      } else if (tipo === 'select-multiple') {
        var vals = lista[0][1] || [];
        Array.prototype.forEach.call(el.options, function (o) { o.selected = vals.indexOf(o.value) !== -1; });
      } else if (!/^(file|password|submit|button|reset|image)$/.test(tipo)) {
        var c = lista.shift();
        if (c) el.value = c[1];
      }
      tocados.push(el);
    });
    form.__oflRestaurando = true;
    tocados.forEach(function (el) {
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    });
    form.__oflRestaurando = false;
  }

  function guardarBorrador(form) {
    var id = draftIdDe(form);
    if (!id) return;
    var ok = lsSet(K_DRAFT + id, {
      t: Date.now(), pagina: paginaActual(), titulo: tituloDe(form), campos: serializarBorrador(form)
    });
    notaForm(form, ok ? '<i class="bi bi-phone"></i> Guardado en este dispositivo · ' + hora(Date.now())
                      : '<i class="bi bi-exclamation-triangle"></i> No se pudo guardar el borrador en el dispositivo');
  }

  function borrarBorrador(draftId) { if (draftId) lsDel(K_DRAFT + draftId); }

  function purgarBorradoresViejos() {
    try {
      for (var i = localStorage.length - 1; i >= 0; i--) {
        var k = localStorage.key(i);
        if (!k || k.indexOf('ofl:' + APP + ':') !== 0 || k.indexOf(':draft:') === -1) continue;
        var d = lsGet(k, null);
        if (!d || Date.now() - d.t > TTL_BORRADOR) lsDel(k);
      }
    } catch (e) { /* nada */ }
  }

  var temporizadores = new WeakMap();
  function programarGuardado(form) {
    clearTimeout(temporizadores.get(form));
    temporizadores.set(form, setTimeout(function () { guardarBorrador(form); }, 400));
  }

  function alCambiar(e) {
    var t = e.target;
    var form = t && (t.form || (t.closest && t.closest('form')));
    if (!form || form.__oflRestaurando || !conBorrador(form)) return;
    if (t.closest && t.closest('.ofl-banner')) return;
    form.__oflSucio = true;
    programarGuardado(form);
  }

  // Al salir/ocultar la app: guardar ya lo que esté a medias (sin esperar el debounce)
  function guardarTodoLoSucio() {
    formsPost().forEach(function (f) { if (f.__oflSucio && conBorrador(f)) guardarBorrador(f); });
  }

  /* ───────────────────────── avisos dentro del formulario ───────────────────────── */

  function notaForm(form, html) {
    var n = form.querySelector(':scope > .ofl-nota');
    if (!n) {
      n = document.createElement('div');
      n.className = 'ofl-nota';
      form.appendChild(n);
    }
    n.innerHTML = html;
  }

  function bannerForm(form, tipo, html) {
    var b = form.querySelector(':scope > .ofl-banner');
    if (!b) {
      b = document.createElement('div');
      form.insertBefore(b, form.firstChild);
    }
    b.className = 'ofl-banner alert alert-' + tipo + ' py-2 px-3 small';
    b.innerHTML = html;
    return b;
  }
  function quitarBanner(form) {
    var b = form.querySelector(':scope > .ofl-banner');
    if (b) b.remove();
  }

  function bloquear(form, texto) {
    form.__oflEnviando = true;
    Array.prototype.forEach.call(form.querySelectorAll('button[type=submit], button:not([type]), input[type=submit]'), function (b) {
      if (b.disabled) return;   // ya estaba deshabilitado por la página: no tocar
      if (b.__oflTexto === undefined) b.__oflTexto = b.tagName === 'INPUT' ? b.value : b.innerHTML;
      b.__oflDeshabilitado = true;
      b.disabled = true;
    });
    var principal = form.querySelector('button[type=submit], button:not([type]), input[type=submit]');
    if (principal && texto) {
      if (principal.tagName === 'INPUT') principal.value = texto;
      else principal.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>' + esc(texto);
    }
  }
  function desbloquear(form) {
    form.__oflEnviando = false;
    Array.prototype.forEach.call(form.querySelectorAll('button, input[type=submit]'), function (b) {
      if (!b.__oflDeshabilitado) return;
      if (b.__oflTexto !== undefined) {
        if (b.tagName === 'INPUT') b.value = b.__oflTexto; else b.innerHTML = b.__oflTexto;
        b.__oflTexto = undefined;
      }
      b.__oflDeshabilitado = false;
      b.disabled = false;
    });
  }

  function ofrecerBorrador(form) {
    var id = draftIdDe(form);
    if (!id) return;
    var enCola = outboxPorDraft(id);
    if (enCola) {
      mostrarEstadoCola(form, enCola);
      return;
    }
    var d = lsGet(K_DRAFT + id, null);
    if (!d || !d.campos) return;
    if (Date.now() - d.t > TTL_BORRADOR) { borrarBorrador(id); return; }
    try {
      if (sessionStorage.getItem('ofl:saltarBanner') === id) {
        sessionStorage.removeItem('ofl:saltarBanner');
        return;
      }
    } catch (e) { /* nada */ }
    if (JSON.stringify(d.campos) === JSON.stringify(serializarBorrador(form))) return;

    var b = bannerForm(form, 'warning',
      '<div class="d-flex flex-wrap align-items-center gap-2">' +
      '<span class="flex-grow-1"><i class="bi bi-life-preserver me-1"></i>' +
      '<strong>Hay un borrador sin guardar</strong> de ' + esc(hora(d.t)) + '. Lo escrito no se perdió.</span>' +
      '<button type="button" class="btn btn-sm btn-warning" data-ofl="recuperar">Recuperar</button>' +
      '<button type="button" class="btn btn-sm btn-outline-secondary" data-ofl="descartar">Descartar</button></div>');
    b.querySelector('[data-ofl=recuperar]').onclick = function () {
      aplicarBorrador(form, d.campos);
      quitarBanner(form);
      notaForm(form, '<i class="bi bi-check2-circle"></i> Borrador recuperado · revisa y guarda');
    };
    b.querySelector('[data-ofl=descartar]').onclick = function () {
      if (!confirm('¿Descartar el borrador? Lo escrito en él se perderá.')) return;
      borrarBorrador(id);
      quitarBanner(form);
    };
  }

  function mostrarEstadoCola(form, item) {
    var textos = {
      pendiente: '<i class="bi bi-phone me-1"></i><strong>Guardado en este dispositivo.</strong> Se enviará solo cuando la conexión mejore. Puedes seguir trabajando.',
      enviando: '<i class="bi bi-arrow-repeat me-1"></i><strong>Enviando…</strong> lo escrito ya está guardado en este dispositivo.',
      login: '<i class="bi bi-person-lock me-1"></i><strong>Tu sesión se cerró.</strong> Lo escrito está guardado en este dispositivo. <a href="' + esc(loginUrl()) + '">Inicia sesión</a> y se enviará solo.',
      revisar: '<i class="bi bi-exclamation-circle me-1"></i><strong>No se pudo guardar:</strong> el formulario tiene datos por corregir. Pulsa guardar para ver qué falta.',
      error: '<i class="bi bi-exclamation-triangle me-1"></i><strong>Error del servidor al guardar.</strong> Lo escrito está a salvo en este dispositivo. Vuelve a intentar en un momento.'
    };
    var tipos = { pendiente: 'info', enviando: 'info', login: 'warning', revisar: 'danger', error: 'danger' };
    bannerForm(form, tipos[item.estado] || 'info', textos[item.estado] || textos.pendiente);
    if (item.estado === 'revisar' || item.estado === 'error' || item.estado === 'login') {
      var d = lsGet(K_DRAFT + item.draft, null);
      if (d && d.campos && JSON.stringify(d.campos) !== JSON.stringify(serializarBorrador(form))) {
        aplicarBorrador(form, d.campos);
      }
    }
  }

  function loginUrl() {
    return LOGIN_URL + '?next=' + encodeURIComponent(paginaActual());
  }

  /* ───────────────────────── envío ───────────────────────── */

  function entradasParaEnvio(form, submitter, clave) {
    var fd = new FormData(form);
    if (submitter && submitter.name && !fd.has(submitter.name)) fd.append(submitter.name, submitter.value || '');
    fd.set('_idem_key', clave);
    var entradas = [];
    fd.forEach(function (v, k) {
      if (typeof v === 'string') entradas.push([k, v]);
    });
    return entradas;
  }

  function enviarItem(item) {
    var fd = new FormData();
    var csrf = getCookie('csrftoken');
    item.entries.forEach(function (p) {
      fd.append(p[0], (p[0] === 'csrfmiddlewaretoken' && csrf) ? csrf : p[1]);
    });
    var headers = { 'X-Offline-Form': '1', 'X-Idempotency-Key': item.id };
    if (csrf) headers['X-CSRFToken'] = csrf;
    var ctrl = window.AbortController ? new AbortController() : null;
    var timer = setTimeout(function () { if (ctrl) ctrl.abort(); }, TIMEOUT_ENVIO);
    var t0 = Date.now();

    return fetch(item.url, {
      method: 'POST', body: fd, credentials: 'same-origin', headers: headers,
      redirect: 'follow', signal: ctrl ? ctrl.signal : undefined
    }).then(function (res) {
      clearTimeout(timer);
      registrarLatencia(Date.now() - t0);
      var ct = res.headers.get('Content-Type') || '';
      if (res.status === 409) return { tipo: 'procesando' };
      if (res.status === 401) return { tipo: 'login' };
      if (res.redirected && res.url.indexOf(LOGIN_URL) !== -1) return { tipo: 'login' };
      if (res.ok && ct.indexOf('application/json') !== -1) {
        return res.json().then(function (d) {
          return d && d.redirect ? { tipo: 'ok', redirect: d.redirect } : { tipo: 'errores' };
        }, function () { return { tipo: 'errores' }; });
      }
      if (res.status === 403) return { tipo: 'prohibido' };
      if (res.status === 502 || res.status === 503 || res.status === 504) return { tipo: 'red' };
      if (res.status >= 500) return { tipo: 'servidor', status: res.status };
      if (res.ok) return { tipo: 'errores' };
      return { tipo: 'servidor', status: res.status };
    }, function () {
      clearTimeout(timer);
      return { tipo: 'red' };
    });
  }

  function reenviarNativo(form, submitter, clave) {
    form.__oflNativo = true;
    var h = form.querySelector('input[name=_idem_key]');
    if (!h) { h = document.createElement('input'); h.type = 'hidden'; h.name = '_idem_key'; form.appendChild(h); }
    h.value = clave;
    if (submitter && submitter.name) {
      var s = document.createElement('input');
      s.type = 'hidden'; s.name = submitter.name; s.value = submitter.value || '';
      form.appendChild(s);
    }
    HTMLFormElement.prototype.submit.call(form);
  }

  function alEnviar(e) {
    var form = e.target;
    if (!esPost(form) || form.__oflNativo) return;
    if (e.defaultPrevented) return;

    // Sin conexión, algunos botones llevan a otra página guardada (p. ej. «Atender» → consulta nueva)
    var alt = form.getAttribute('data-offline-alt');
    if (alt && (estado.red === 'offline' || navigator.onLine === false || window.__OFFLINE_COPIA)) {
      e.preventDefault();
      location.assign(alt);
      return;
    }

    if (!rastreable(form)) {
      if (navigator.onLine === false) {
        e.preventDefault();
        toast('Sin conexión: esta acción necesita internet. Inténtalo cuando vuelva la señal.', 'danger');
      } else if (SALIR_ACTION.test(form.getAttribute('action') || '')) {
        e.preventDefault();
        if (pendientes().length &&
            !confirm('Hay ' + pendientes().length + ' registro(s) guardados en este dispositivo que aún no se han enviado.\n' +
                     'Se enviarán cuando vuelvas a entrar con tu usuario en este dispositivo.\n\n¿Salir de todos modos?')) {
          return;
        }
        // Al salir se borran las páginas guardadas en el dispositivo (privacidad)
        borrarCopias().then(function () {
          form.__oflNativo = true;
          HTMLFormElement.prototype.submit.call(form);
        });
      }
      return;
    }

    e.preventDefault();
    if (form.__oflEnviando) return;   // doble toque
    var submitter = e.submitter || null;
    var draftId = draftIdDe(form);
    if (draftId) guardarBorrador(form);

    var previo = outboxPorDraft(draftId);
    var firma = form.action + '|' + JSON.stringify(serializarBorrador(form));
    var clave;
    if (previo) clave = previo.id;                                   // mismo formulario en cola → se reemplaza
    else if (form.__oflClave && form.__oflFirma === firma) clave = form.__oflClave;   // reenvío idéntico
    else clave = uuid();
    form.__oflClave = clave;
    form.__oflFirma = firma;

    var item = {
      id: clave, user: USER, url: form.action, draft: draftId, titulo: tituloDe(form),
      pagina: paginaActual(), creado: (previo && previo.creado) || Date.now(), intentos: 0,
      estado: 'enviando', enviandoDesde: Date.now(),
      entries: entradasParaEnvio(form, submitter, clave)
    };
    // Primero a la cola local (si se cierra la app a mitad del envío, no se pierde)
    var guardadoLocal = outboxPut(item);

    if (estado.red === 'offline' && guardadoLocal) {
      item.estado = 'pendiente';
      outboxPut(item);
      encolado(form, item);
      return;
    }

    bloquear(form, estado.red === 'online' ? 'Guardando…' : 'Guardando (conexión lenta)…');
    if (estado.red !== 'online') {
      bannerForm(form, 'info', '<i class="bi bi-hourglass-split me-1"></i>La conexión está lenta. Lo escrito ya está guardado en este dispositivo; si no responde, se enviará solo.');
    }

    enviarItem(item).then(function (r) {
      if (r.tipo === 'ok') {
        outboxDel(item.id);
        borrarBorrador(draftId);
        location.assign(r.redirect);
        return;
      }
      desbloquear(form);
      if (r.tipo === 'errores') {
        // El servidor rechazó datos (validación): se reenvía normal para que muestre los errores
        outboxDel(item.id);
        try { if (draftId) sessionStorage.setItem('ofl:saltarBanner', draftId); } catch (e2) { /* nada */ }
        bloquear(form, 'Verificando…');
        reenviarNativo(form, submitter, clave);
        return;
      }
      if (r.tipo === 'login') {
        item.estado = 'login'; outboxPut(item);
        estado.auth = false;
        mostrarEstadoCola(form, item);
        return;
      }
      if (r.tipo === 'servidor' || r.tipo === 'prohibido') {
        item.estado = 'error'; item.detalle = r.status || r.tipo; outboxPut(item);
        mostrarEstadoCola(form, item);
        toast('No se pudo guardar (error ' + (r.status || 403) + '). Lo escrito está a salvo en este dispositivo.', 'danger');
        return;
      }
      // red / timeout / procesando → queda en cola
      if (!guardadoLocal) {
        toast('Sin conexión y sin espacio en el dispositivo: NO cierres esta página y vuelve a pulsar guardar.', 'danger', 12000);
        return;
      }
      item.estado = 'pendiente'; outboxPut(item);
      if (r.tipo === 'red') marcarProblema();
      encolado(form, item);
    });
  }

  function encolado(form, item) {
    desbloquear(form);
    mostrarEstadoCola(form, item);
    toast('Guardado en este dispositivo. Se enviará automáticamente cuando la conexión mejore.', 'info');
    programarSync(5000);
  }

  /* ───────────────────────── sincronización ───────────────────────── */

  function pendientes() {
    return outboxLeer().filter(function (i) { return i.user === USER; });
  }

  function listosParaEnviar(manual) {
    var ahora = Date.now();
    return pendientes().filter(function (i) {
      if (i.estado === 'pendiente') return true;
      if (i.estado === 'enviando') return ahora - (i.enviandoDesde || 0) > 30000;   // envío interrumpido
      if (i.estado === 'login') return estado.auth;
      if (i.estado === 'error') return manual;
      return false;
    }).sort(function (a, b) { return a.creado - b.creado; });
  }

  var timerSync = null;
  function programarSync(ms) {
    clearTimeout(timerSync);
    timerSync = setTimeout(function () { sincronizar(false); }, ms);
  }

  function sincronizar(manual) {
    if (estado.sincronizando) return;
    var cola = listosParaEnviar(manual);
    if (!cola.length) { pintarIndicador(); return; }
    if (navigator.onLine === false) { pintarIndicador(); return; }
    estado.sincronizando = true;
    pintarIndicador();

    var i = 0;
    (function siguiente() {
      if (i >= cola.length) { fin(); return; }
      var item = cola[i++];
      item.estado = 'enviando'; item.enviandoDesde = Date.now(); item.intentos = (item.intentos || 0) + 1;
      outboxPut(item);
      enviarItem(item).then(function (r) {
        if (r.tipo === 'ok') {
          outboxDel(item.id);
          borrarBorrador(item.draft);
          toast('<i class="bi bi-check2-circle me-1"></i>Enviado: ' + esc(item.titulo), 'success');
          if (item.pagina === paginaActual()) { location.assign(r.redirect); return; }
          siguiente();
        } else if (r.tipo === 'errores') {
          item.estado = 'revisar'; outboxPut(item);
          toast('«' + esc(item.titulo) + '» necesita revisión antes de guardarse. Toca el indicador para abrirlo.', 'warning', 9000);
          siguiente();
        } else if (r.tipo === 'login') {
          item.estado = 'login'; outboxPut(item);
          estado.auth = false;
          fin();
        } else if (r.tipo === 'procesando') {
          item.estado = 'pendiente'; outboxPut(item);
          siguiente();
        } else if (r.tipo === 'servidor' || r.tipo === 'prohibido') {
          item.estado = 'error'; item.detalle = r.status || r.tipo; outboxPut(item);
          siguiente();
        } else {
          item.estado = 'pendiente'; outboxPut(item);
          marcarProblema();
          fin();
        }
      });
    })();

    function fin() {
      estado.sincronizando = false;
      pintarIndicador();
      refrescarBannersDePagina();
      if (listosParaEnviar(false).length) programarSync(SYNC_CADA);
    }
  }

  function refrescarBannersDePagina() {
    formsPost().forEach(function (form) {
      var id = draftIdDe(form);
      if (!id) return;
      var item = outboxPorDraft(id);
      if (item) mostrarEstadoCola(form, item);
    });
  }

  /* ───────────────────────── estado de la red ───────────────────────── */

  function registrarLatencia(ms) {
    if (ms > LENTO_MS) cambiarRed('lento');
    else if (estado.red !== 'online') cambiarRed('online');
  }

  function marcarProblema() {
    estado.fallosPing++;
    cambiarRed(navigator.onLine === false || estado.fallosPing >= 2 ? 'offline' : 'lento');
  }

  function conexionDebil() {
    var c = navigator.connection;
    return !!(c && (c.saveData || /(^|-)2g$/.test(c.effectiveType || '')));
  }

  function cambiarRed(nuevo) {
    if (nuevo === 'online' && conexionDebil()) nuevo = 'lento';
    var anterior = estado.red;
    if (anterior === nuevo) { pintarIndicador(); return; }
    estado.red = nuevo;
    if (nuevo === 'offline') toast('<i class="bi bi-wifi-off me-1"></i>Sin conexión. Puedes seguir escribiendo: todo se guarda en este dispositivo.', 'danger', 7000);
    else if (nuevo === 'lento' && anterior === 'online') toast('<i class="bi bi-reception-1 me-1"></i>Conexión lenta. Lo que escribas se guarda en el dispositivo.', 'warning', 6000);
    else if (nuevo === 'online') {
      toast('<i class="bi bi-wifi me-1"></i>Conexión restablecida.', 'success', 3500);
      programarSync(500);
    }
    pintarIndicador();
    programarPing();
  }

  var timerPing = null;
  function programarPing() {
    clearTimeout(timerPing);
    timerPing = setTimeout(ping, estado.red === 'online' ? PING_NORMAL : PING_PROBLEMA);
  }

  function ping() {
    if (document.hidden) { programarPing(); return; }
    var ctrl = window.AbortController ? new AbortController() : null;
    var t0 = Date.now();
    var timer = setTimeout(function () { if (ctrl) ctrl.abort(); }, TIMEOUT_PING);
    fetch(PING_URL + '?t=' + t0, { cache: 'no-store', credentials: 'same-origin', signal: ctrl ? ctrl.signal : undefined })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (d) {
        clearTimeout(timer);
        estado.fallosPing = 0;
        var antesAuth = estado.auth;
        estado.auth = !!d.auth;
        cambiarRed(Date.now() - t0 > LENTO_MS ? 'lento' : 'online');
        if (estado.auth && (!antesAuth || listosParaEnviar(false).length)) programarSync(300);
        if (estado.auth && estado.red === 'online' && !window.__OFFLINE_COPIA) setTimeout(function () { precargar(false); }, 1500);
        pintarIndicador();
      })
      .catch(function () { clearTimeout(timer); marcarProblema(); })
      .then(programarPing);
  }

  /* ───────────────────────── interfaz: indicador, panel, toasts ───────────────────────── */

  function inyectarCss() {
    if (document.getElementById('ofl-css')) return;
    var css = '' +
      '.ofl-pill{position:fixed;z-index:1080;left:50%;transform:translateX(-50%);' +
      'bottom:calc(var(--os-tabbar-alto,64px) + env(safe-area-inset-bottom) + 12px);display:none;' +
      'align-items:center;gap:.4rem;padding:.45rem .9rem;border-radius:999px;border:0;color:#fff;font-size:.82rem;' +
      'font-weight:600;box-shadow:0 4px 14px rgba(0,0,0,.25);cursor:pointer;max-width:92vw;white-space:nowrap}' +
      '@media (min-width:992px){.ofl-pill{bottom:18px;left:calc(50% + var(--os-sidebar-ancho,240px) / 2)}}' +
      'body:has(.os-barra-acciones) .ofl-pill{margin-bottom:64px}body:has(.os-barra-acciones) .ofl-panel{margin-bottom:64px}' +
      '.ofl-pill{font-family:inherit}.ofl-pill.on{display:inline-flex}.ofl-pill.offline{background:#A23B32}' +
      '.ofl-pill.lento{background:#A15C07}.ofl-pill.cola{background:#145F8F}.ofl-pill.login{background:#3E5161}' +
      '.ofl-pill.ok{background:#1C8577}' +
      '.ofl-dot{width:8px;height:8px;border-radius:50%;background:#fff;opacity:.9}' +
      '.ofl-panel{position:fixed;z-index:1081;left:50%;transform:translateX(-50%);' +
      'bottom:calc(var(--os-tabbar-alto,64px) + env(safe-area-inset-bottom) + 58px);width:min(420px,94vw);' +
      'max-height:55vh;overflow:auto;background:#fff;border:1px solid #DCE4EB;border-radius:16px;' +
      'box-shadow:0 8px 28px rgba(31,64,61,.18);display:none;font-size:.85rem}' +
      '@media (min-width:992px){.ofl-panel{bottom:64px;left:calc(50% + var(--os-sidebar-ancho,240px) / 2)}}' +
      '.ofl-panel.on{display:block}.ofl-panel .ofl-row{padding:.6rem .9rem;border-bottom:1px solid #E8EEF3}' +
      '.ofl-toasts{position:fixed;z-index:1090;top:12px;left:50%;transform:translateX(-50%);width:min(440px,94vw);display:flex;flex-direction:column;gap:.4rem;pointer-events:none}' +
      '.ofl-toast{pointer-events:auto;padding:.6rem .9rem;border-radius:.5rem;color:#fff;font-size:.85rem;box-shadow:0 4px 14px rgba(0,0,0,.2);line-height:1.35}' +
      '.ofl-toast.success{background:#3F7A63}.ofl-toast.danger{background:#A23B32}.ofl-toast.warning{background:#A15C07}' +
      '.ofl-toast.info{background:#145F8F}' +
      '.ofl-nota{font-size:.75rem;color:#4B5E6D;margin-top:.5rem;text-align:right}' +
      '.ofl-nota .bi{margin-right:.2rem}';
    var st = document.createElement('style');
    st.id = 'ofl-css';
    st.textContent = css;
    document.head.appendChild(st);
  }

  var pill, panel, toasts;
  function crearUi() {
    inyectarCss();
    pill = document.createElement('button');
    pill.type = 'button';
    pill.className = 'ofl-pill';
    pill.setAttribute('aria-live', 'polite');
    pill.onclick = function () { panel.classList.toggle('on'); if (panel.classList.contains('on')) pintarPanel(); };
    panel = document.createElement('div');
    panel.className = 'ofl-panel';
    toasts = document.createElement('div');
    toasts.className = 'ofl-toasts';
    document.body.appendChild(pill);
    document.body.appendChild(panel);
    document.body.appendChild(toasts);
    document.addEventListener('click', function (e) {
      if (panel.classList.contains('on') && !panel.contains(e.target) && e.target !== pill && !pill.contains(e.target)) {
        panel.classList.remove('on');
      }
    });
  }

  function pintarIndicador() {
    if (!pill) return;
    var cola = pendientes();
    var nCola = cola.filter(function (i) { return i.estado === 'pendiente' || i.estado === 'enviando'; }).length;
    var nRevisar = cola.filter(function (i) { return i.estado === 'revisar' || i.estado === 'error'; }).length;
    var nLogin = cola.filter(function (i) { return i.estado === 'login'; }).length;

    var partes = [], clase = '';
    if (estado.red === 'offline') { partes.push('Sin conexión'); clase = 'offline'; }
    else if (estado.red === 'lento') { partes.push('Conexión lenta'); clase = 'lento'; }

    if (nLogin) { partes.push('Sesión cerrada · ' + nLogin + ' por enviar'); clase = clase || 'login'; }
    if (nCola) {
      partes.push(estado.sincronizando ? 'Enviando ' + nCola + '…' : nCola + ' por enviar');
      clase = clase || 'cola';
    }
    if (nRevisar) { partes.push(nRevisar + ' por revisar'); clase = clase || 'offline'; }

    if (!partes.length) {
      pill.className = 'ofl-pill';
      panel.classList.remove('on');
      return;
    }
    var icono = estado.sincronizando ? '<span class="spinner-border spinner-border-sm"></span>' : '<span class="ofl-dot"></span>';
    pill.innerHTML = icono + '<span>' + esc(partes.join(' · ')) + '</span>';
    pill.className = 'ofl-pill on ' + clase;
    if (panel.classList.contains('on')) pintarPanel();
  }

  var ETIQUETAS = {
    pendiente: 'En cola', enviando: 'Enviando…', login: 'Requiere iniciar sesión',
    revisar: 'Revisar datos', error: 'Error del servidor'
  };

  function pintarPanel() {
    var cola = pendientes().sort(function (a, b) { return a.creado - b.creado; });
    var html = '<div class="ofl-row d-flex align-items-center gap-2" style="background:#F4F7FA">' +
      '<strong class="flex-grow-1">' + (estado.red === 'offline' ? '<i class="bi bi-wifi-off text-danger me-1"></i>Sin conexión'
        : estado.red === 'lento' ? '<i class="bi bi-reception-1 text-warning me-1"></i>Conexión lenta'
        : '<i class="bi bi-wifi text-success me-1"></i>Conectado') + '</strong>' +
      (cola.length ? '<button type="button" class="btn btn-sm btn-primary" data-ofl="sync">Enviar ahora</button>' : '') +
      '</div>';
    if (!cola.length) {
      html += '<div class="ofl-row text-muted">No hay nada pendiente. Lo que escribas se guarda en este dispositivo mientras tanto.</div>';
    }
    var pre = lsGet(K_PRECARGA, null);
    html += '<div class="ofl-row small d-flex align-items-center gap-2"><span class="flex-grow-1 text-muted">' +
      '<i class="bi bi-phone me-1"></i>' + (estado.precargando ? 'Guardando agenda y fichas para usar sin conexión…'
        : pre && pre.t ? 'Agenda y fichas guardadas para usar sin conexión · ' + esc(hora(pre.t))
        : 'Aún no se han guardado páginas para usar sin conexión.') + '</span>' +
      (estado.red === 'online' && !estado.precargando ? '<button type="button" class="btn btn-sm btn-outline-secondary" data-ofl="precargar">Actualizar</button>' : '') +
      '</div>';
    cola.forEach(function (i) {
      html += '<div class="ofl-row">' +
        '<div class="d-flex justify-content-between gap-2"><strong>' + esc(i.titulo) + '</strong>' +
        '<span class="badge bg-' + ({ revisar: 'danger', error: 'danger', login: 'warning' }[i.estado] || 'primary') + '">' +
        esc(ETIQUETAS[i.estado] || i.estado) + '</span></div>' +
        '<div class="text-muted small">' + esc(hora(i.creado)) + (i.intentos ? ' · ' + i.intentos + ' intento(s)' : '') + '</div>' +
        '<div class="mt-1 d-flex gap-2">' +
        (i.pagina !== paginaActual() ? '<a class="btn btn-sm btn-outline-primary" href="' + esc(i.pagina) + '">Abrir</a>' : '') +
        (i.estado === 'login' ? '<a class="btn btn-sm btn-outline-secondary" href="' + esc(loginUrl()) + '">Iniciar sesión</a>' : '') +
        '<button type="button" class="btn btn-sm btn-link text-danger ms-auto" data-ofl="quitar" data-id="' + esc(i.id) + '">Quitar de la cola</button>' +
        '</div></div>';
    });
    panel.innerHTML = html;
    var b = panel.querySelector('[data-ofl=sync]');
    if (b) b.onclick = function () { estado.fallosPing = 0; sincronizar(true); ping(); };
    var bp = panel.querySelector('[data-ofl=precargar]');
    if (bp) bp.onclick = function () { precargar(true); };
    Array.prototype.forEach.call(panel.querySelectorAll('[data-ofl=quitar]'), function (btn) {
      btn.onclick = function () {
        if (!confirm('¿Quitar este registro de la cola? No se enviará al servidor.\n(El borrador del formulario se conserva en este dispositivo.)')) return;
        outboxDel(btn.getAttribute('data-id'));
        pintarPanel();
      };
    });
  }

  function toast(html, tipo, ms) {
    if (!toasts) return;
    var t = document.createElement('div');
    t.className = 'ofl-toast ' + (tipo || 'info');
    t.innerHTML = html;
    toasts.appendChild(t);
    setTimeout(function () { t.remove(); }, ms || 4500);
  }

  /* ───────────────────────── páginas sin conexión (Fase 2A) ───────────────────────── */

  // Descarga por adelantado la agenda y las fichas/consultas de las pacientes citadas,
  // para que el Service Worker las tenga disponibles sin datos.
  function precargar(forzar) {
    if (!('serviceWorker' in navigator) || !navigator.serviceWorker.controller) return;
    if (estado.red !== 'online' || estado.precargando || document.hidden) return;
    var info = lsGet(K_PRECARGA, {}) || {};
    var espera = /\/agenda\//.test(location.pathname) ? 3 * 60 * 1000 : PRECARGA_CADA;
    if (!forzar && info.t && Date.now() - info.t < espera) return;

    estado.precargando = true;
    if (panel && panel.classList.contains('on')) pintarPanel();
    var guardadas = 0;
    fetch('/offline/precache/', { credentials: 'same-origin', cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : { urls: [] }; })
      .then(function (d) {
        var urls = (d && d.urls) || [];
        var i = 0;
        (function siguiente() {
          if (i >= urls.length || estado.red !== 'online') { fin(); return; }
          var u = urls[i++];
          fetch(u, { credentials: 'same-origin', headers: { 'X-Offline-Prefetch': '1' } })
            .then(function (r) { if (r.ok && !r.redirected) guardadas++; })
            .catch(function () { /* se reintenta en la próxima precarga */ })
            .then(siguiente);
        })();
      })
      .catch(fin);

    function fin() {
      estado.precargando = false;
      if (guardadas) lsSet(K_PRECARGA, { t: Date.now(), n: guardadas });
      if (forzar && guardadas) toast('<i class="bi bi-check2-circle me-1"></i>Agenda y fichas guardadas para usar sin conexión.', 'success', 3000);
      if (panel && panel.classList.contains('on')) pintarPanel();
    }
  }

  function borrarCopias() {
    lsDel(K_PRECARGA);
    var tareas = [];
    try { if (window.caches) tareas.push(caches.delete(CACHE_PAGINAS)); } catch (e) { /* nada */ }
    return Promise.race([
      Promise.all(tareas).catch(function () {}),
      new Promise(function (r) { setTimeout(r, 1500); })
    ]);
  }

  // La página vino de la copia guardada (sin red o red muy lenta)
  function avisoCopia() {
    var c = window.__OFFLINE_COPIA;
    if (!c) return;
    // Los mensajes de Django de la copia son viejos: no mostrarlos
    Array.prototype.forEach.call(document.querySelectorAll('main .alert-dismissible'), function (a) { a.remove(); });
    var cont = document.querySelector('main.os-main') || document.querySelector('main') || document.body;
    var div = document.createElement('div');
    div.className = 'alert alert-secondary py-2 px-3 small d-flex align-items-center gap-2 ofl-copia';
    div.innerHTML = '<i class="bi bi-phone"></i><span class="flex-grow-1"><strong>Copia guardada en este dispositivo</strong>' +
      (c.guardado ? ' · ' + esc(hora(c.guardado)) : '') +
      (c.motivo === 'lento' ? ' (la conexión está muy lenta).' : ' (sin conexión).') +
      ' Lo que registres se enviará solo.</span>' +
      '<button type="button" class="btn btn-sm btn-outline-secondary">Actualizar</button>';
    div.querySelector('button').onclick = function () { location.reload(); };
    cont.insertBefore(div, cont.firstChild);
    estado.red = c.motivo === 'lento' ? 'lento' : 'offline';   // sin toast: el aviso ya lo explica
    if (estado.red === 'offline') estado.fallosPing = 2;
  }

  /* ───────────────────────── arranque ───────────────────────── */

  function iniciar() {
    var chipViejo = document.getElementById('os-sin-conexion');   // la píldora de este archivo lo reemplaza
    if (chipViejo) chipViejo.remove();
    crearUi();
    purgarBorradoresViejos();
    outboxLeer();

    document.addEventListener('input', alCambiar, true);
    document.addEventListener('change', alCambiar, true);
    document.addEventListener('click', alCambiar, true);
    document.addEventListener('submit', alEnviar, false);
    window.addEventListener('pagehide', guardarTodoLoSucio);   // fase burbuja: corre después de los handlers propios del form

    avisoCopia();
    formsPost().forEach(function (f) { if (conBorrador(f)) ofrecerBorrador(f); });

    window.addEventListener('online', function () { estado.fallosPing = 0; ping(); });
    window.addEventListener('offline', function () { cambiarRed('offline'); });
    if (navigator.connection && navigator.connection.addEventListener) {
      navigator.connection.addEventListener('change', function () { cambiarRed(estado.red === 'offline' ? 'offline' : 'online'); });
    }
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) { guardarTodoLoSucio(); return; }
      ping(); programarSync(1000);
    });
    window.addEventListener('pageshow', function (e) {
      if (e.persisted) formsPost().forEach(function (f) { desbloquear(f); f.__oflNativo = false; });
    });

    if (navigator.onLine === false) cambiarRed('offline');
    else if (conexionDebil() && !window.__OFFLINE_COPIA) cambiarRed('lento');
    pintarIndicador();
    setTimeout(ping, 1500);
    programarSync(2000);

    // API mínima para depurar desde la consola
    window.OfflineOrdo = { estado: estado, cola: pendientes, sincronizar: function () { sincronizar(true); },
                            precargar: function () { precargar(true); } };
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
})();
