// Dictado de toda la consulta con IA (ADR-045): graba en el navegador, sube el audio, espera el resultado y llena
// el formulario. Los campos llenados por la IA quedan resaltados hasta que la doctora los toque. Nada se guarda solo.
(function () {
  const caja = document.getElementById('os-dictado');
  if (!caja) return;
  const $ = function (sel) { return caja.querySelector(sel); };
  const vistas = {inicio: $('.os-dictado-inicio'), grabando: $('.os-dictado-grabando'),
                  procesando: $('.os-dictado-procesando'), listo: $('.os-dictado-listo')};
  let grabador = null, trozos = [], segundos = 0, reloj = null, flujo = null, descartar = false;
  let pendiente = null;          // {audio: Blob, segundos, nombre, origen} que no se pudo enviar
  const CLAVE = 'dictado:' + (caja.dataset.consulta ? 'c' + caja.dataset.consulta : 'p' + caja.dataset.paciente);

  // ── Grabación pendiente en el equipo (IndexedDB): sobrevive a un corte de luz, de internet o a recargar ──────
  function bd() {
    return new Promise(function (ok, mal) {
      if (!window.indexedDB) { mal(new Error('sin IndexedDB')); return; }
      const r = indexedDB.open('ordo-dictado', 1);
      r.onupgradeneeded = function () { r.result.createObjectStore('pendientes'); };
      r.onsuccess = function () { ok(r.result); };
      r.onerror = function () { mal(r.error); };
    });
  }
  function guardarPendiente(p) {
    return bd().then(function (db) { db.transaction('pendientes', 'readwrite').objectStore('pendientes').put(
      {audio: p.audio, segundos: p.segundos, nombre: p.nombre, origen: p.origen, fecha: Date.now()}, CLAVE); })
      .catch(function () {});
  }
  function borrarPendiente() {
    pendiente = null;
    $('.os-dictado-pendiente').classList.add('d-none');
    return bd().then(function (db) { db.transaction('pendientes', 'readwrite').objectStore('pendientes').delete(CLAVE); })
      .catch(function () {});
  }
  function mostrarPendiente(p, motivo) {
    pendiente = p;
    const m = String(Math.floor((p.segundos || 0) / 60)).padStart(2, '0'), s = String((p.segundos || 0) % 60).padStart(2, '0');
    $('[data-pendiente-texto]').textContent = (motivo ? motivo + ' ' : '') + 'Hay una grabación sin enviar' +
      (p.segundos ? ' (' + m + ':' + s + ')' : '') + '. Quedó guardada en este equipo.';
    $('.os-dictado-pendiente').classList.remove('d-none');
  }
  bd().then(function (db) {
    const r = db.transaction('pendientes').objectStore('pendientes').get(CLAVE);
    r.onsuccess = function () { if (r.result && r.result.audio) mostrarPendiente(r.result); };
  }).catch(function () {});

  function ver(nombre) {
    Object.keys(vistas).forEach(function (k) { vistas[k].classList.toggle('d-none', k !== nombre); });
  }
  function token() {
    const c = document.querySelector('input[name=csrfmiddlewaretoken]');
    return c ? c.value : '';
  }
  function mostrarReloj() {
    const m = String(Math.floor(segundos / 60)).padStart(2, '0'), s = String(segundos % 60).padStart(2, '0');
    $('[data-reloj]').textContent = m + ':' + s;
  }

  async function grabar() {
    if (!$('[data-consentimiento]').checked) { alert('Marca primero que el paciente o su representante autoriza la grabación.'); return; }
    if (!navigator.mediaDevices || !window.MediaRecorder) { alert('Este navegador no permite grabar. Usa Chrome o Edge.'); return; }
    try {
      flujo = await navigator.mediaDevices.getUserMedia({audio: true});
    } catch (e) {
      alert('No se pudo usar el micrófono. Revisa el permiso del navegador.'); return;
    }
    const tipo = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find(function (t) { return MediaRecorder.isTypeSupported(t); }) || '';
    grabador = new MediaRecorder(flujo, tipo ? {mimeType: tipo, audioBitsPerSecond: 32000} : undefined);
    trozos = []; segundos = 0; descartar = false;
    grabador.ondataavailable = function (e) { if (e.data && e.data.size) trozos.push(e.data); };
    grabador.onstop = function () {
      flujo.getTracks().forEach(function (t) { t.stop(); });
      clearInterval(reloj);
      if (descartar) { ver('inicio'); return; }
      const blob = new Blob(trozos, {type: grabador.mimeType || 'audio/webm'});
      const p = {audio: blob, segundos: segundos, nombre: 'dictado.' + ((blob.type || '').includes('mp4') ? 'm4a' : 'webm'),
                 origen: 'grabacion'};
      guardarPendiente(p).then(function () { enviar(p); });
    };
    grabador.start(1000);
    reloj = setInterval(function () { if (grabador.state === 'recording') { segundos++; mostrarReloj(); } }, 1000);
    mostrarReloj();
    ver('grabando');
  }

  function pausar(boton) {
    if (!grabador) return;
    if (grabador.state === 'recording') {
      grabador.pause(); caja.classList.add('pausado'); boton.innerHTML = '<i class="bi bi-play-fill"></i> Seguir';
    } else if (grabador.state === 'paused') {
      grabador.resume(); caja.classList.remove('pausado'); boton.innerHTML = '<i class="bi bi-pause-fill"></i> Pausa';
    }
  }

  async function enviar(p) {
    if (!navigator.onLine) { mostrarPendiente(p, 'Sin conexión.'); ver('inicio'); return; }
    pendiente = p;
    $('.os-dictado-pendiente').classList.add('d-none');
    ver('procesando');
    const datos = new FormData();
    datos.append('audio', p.audio, p.nombre);
    datos.append('segundos', p.segundos || 0);
    datos.append('origen', p.origen);
    datos.append('consentimiento', '1');
    if (caja.dataset.consulta) datos.append('consulta', caja.dataset.consulta);
    datos.append('paciente', caja.dataset.paciente);
    datos.append('plantilla', caja.dataset.plantilla);
    try {
      const r = await fetch(caja.dataset.subir, {method: 'POST', body: datos, credentials: 'same-origin',
                                                  headers: {'X-CSRFToken': token(), 'X-Requested-With': 'fetch'}});
      const j = await r.json();
      if (!r.ok) {
        ver('inicio');
        mostrarPendiente(p);
        alert(j.error || 'No se pudo enviar el dictado.');
        return;
      }
      esperar(j.id, 0);
    } catch (e) {
      ver('inicio');
      mostrarPendiente(p, 'No se pudo enviar (¿sin conexión?).');
    }
  }

  function esperar(id, intentos) {
    const url = caja.dataset.estado.replace('/0/', '/' + id + '/');
    fetch(url, {credentials: 'same-origin'}).then(function (r) { return r.json(); }).then(function (j) {
      if (j.estado === 'PROCESANDO') {
        if (intentos > 120) { fallo('Tardó demasiado. Intenta de nuevo.'); return; }
        setTimeout(function () { esperar(id, intentos + 1); }, 2000);
      } else if (j.estado === 'ERROR') {
        fallo(j.error || 'No se pudo procesar el dictado.');
      } else {
        borrarPendiente();                // ya llegó el resultado: la copia local sobra
        aplicar(j);
        const oculto = document.querySelector('input[name=dictado]');
        if (oculto) oculto.value = id;
      }
    }).catch(function () { setTimeout(function () { esperar(id, intentos + 1); }, 3000); });
  }

  function fallo(mensaje) {
    ver('inicio');
    if (pendiente) mostrarPendiente(pendiente, 'No se pudo procesar.');
    alert(mensaje + '\nLo escrito en el formulario no se perdió.');
  }

  function marcar(el) {
    const zona = el.closest('[data-campo]') || el;
    zona.classList.add('os-ia-llenado');
    const quitar = function () { zona.classList.remove('os-ia-llenado'); };
    zona.addEventListener('input', quitar, {once: true});
    zona.addEventListener('change', quitar, {once: true});
    const seccion = el.closest('.collapse');
    if (seccion && !seccion.classList.contains('show') && window.bootstrap) bootstrap.Collapse.getOrCreateInstance(seccion).show();
  }

  function avisar(el) { el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true})); }

  function poner(nombre, campo) {
    const els = document.querySelectorAll('[name="' + nombre + '"]');
    if (!els.length) return false;
    const valor = campo.valor;
    const primero = els[0];
    if (primero.type === 'radio') {
      const buscado = campo.tipo === 'si_no' ? (valor ? 'si' : 'no') : String(valor);
      const r = Array.from(els).find(function (e) { return e.value === buscado; });
      if (!r) return false;
      r.checked = true; avisar(r); marcar(r);
    } else if (primero.type === 'checkbox') {
      const lista = Array.isArray(valor) ? valor.map(String) : [String(valor)];
      els.forEach(function (e) { e.checked = lista.includes(e.value); });
      avisar(primero); marcar(primero);
    } else if (primero.tagName === 'SELECT') {
      primero.value = campo.tipo === 'si_no' ? (valor ? 'si' : 'no') : String(valor);
      avisar(primero); marcar(primero);
    } else {
      let texto = typeof valor === 'number' ? String(valor) : String(valor);
      if (campo.tipo === 'texto_largo' && primero.value.trim() && primero.value.trim() !== texto) texto = primero.value.trimEnd() + '\n' + texto;
      primero.value = texto; avisar(primero); marcar(primero);
    }
    return true;
  }

  function aplicar(j) {
    const res = j.resultado || {};
    let puestos = 0;
    const sobrantes = [];
    (res.campos || []).forEach(function (c) {
      if (poner(c.prefijo + '-' + c.clave, c)) puestos++; else sobrantes.push(c.clave + ': ' + c.texto);
    });
    (res.tablas || []).forEach(function (t) {
      t.filas.forEach(function (fila, i) {
        let ok = false;
        Object.keys(fila).forEach(function (sub) {
          if (poner(t.prefijo + '-' + t.clave + '__' + i + '__' + sub, {tipo: 'texto', valor: fila[sub]})) ok = true;
        });
        if (ok) puestos++; else sobrantes.push(Object.values(fila).join(' · '));
      });
    });
    const no = [j.no_ubicado || '', sobrantes.join('\n')].filter(Boolean).join('\n');
    $('[data-resumen]').innerHTML = (j.prueba ? '<span class="badge text-bg-secondary me-1">Modo de prueba</span>' : '') +
      '<i class="bi bi-stars text-warning me-1"></i><b>' + puestos + ' campos llenados</b> por la IA (resaltados en amarillo). ' +
      'Revísalos y luego <b>Guardar</b>. ' + '<button type="button" class="btn btn-link btn-sm p-0" data-accion="otra">Dictar otra parte</button>';
    $('[data-transcripcion]').textContent = j.transcripcion || '';
    $('[data-no-ubicado]').classList.toggle('d-none', !no);
    $('[data-no-ubicado-texto]').textContent = no;
    $('.os-dictado-detalle').classList.remove('d-none');
    ver('listo');
    const primero = document.querySelector('.os-ia-llenado');
    if (primero) primero.scrollIntoView({behavior: 'smooth', block: 'center'});
  }

  function duracion(archivo) {
    return new Promise(function (ok) {
      const a = document.createElement('audio');
      const url = URL.createObjectURL(archivo);
      a.preload = 'metadata';
      a.onloadedmetadata = function () { URL.revokeObjectURL(url); ok(isFinite(a.duration) ? Math.round(a.duration) : 0); };
      a.onerror = function () { URL.revokeObjectURL(url); ok(0); };     // el servidor mide la duración real
      a.src = url;
    });
  }
  $('[data-archivo]').addEventListener('change', async function () {
    const archivo = this.files[0];
    this.value = '';
    if (!archivo) return;
    if (!$('[data-consentimiento]').checked) { alert('Marca primero que el paciente o su representante autoriza la grabación.'); return; }
    const p = {audio: archivo, segundos: await duracion(archivo), nombre: archivo.name || 'grabacion.m4a', origen: 'archivo'};
    enviar(p);
  });

  caja.addEventListener('click', function (e) {
    const b = e.target.closest('[data-accion]');
    if (!b) return;
    const accion = b.dataset.accion;
    if (accion === 'subir') { $('[data-archivo]').click(); return; }
    if (accion === 'reintentar' && pendiente) {
      if (!$('[data-consentimiento]').checked) { $('[data-consentimiento]').checked = true; }
      enviar(pendiente); return;
    }
    if (accion === 'descargar' && pendiente) {
      const a = document.createElement('a');
      a.href = URL.createObjectURL(pendiente.audio);
      a.download = 'dictado-' + new Date().toISOString().slice(0, 16).replace(/[:T]/g, '-') + '.' + (pendiente.nombre.split('.').pop() || 'webm');
      a.click(); return;
    }
    if (accion === 'descartar-pendiente' && confirm('¿Descartar la grabación guardada en este equipo?')) { borrarPendiente(); return; }
    if (accion === 'grabar' || accion === 'otra') grabar();
    else if (accion === 'pausar') pausar(b);
    else if (accion === 'terminar' && grabador) grabador.stop();
    else if (accion === 'cancelar' && grabador && confirm('¿Descartar esta grabación?')) { descartar = true; grabador.stop(); }
  });
  window.addEventListener('beforeunload', function (e) {
    if (grabador && grabador.state !== 'inactive') { e.preventDefault(); e.returnValue = ''; }
  });
})();
