// Dictado de toda la consulta con IA (ADR-045): graba en el navegador, sube el audio, espera el resultado y llena
// el formulario. Los campos llenados por la IA quedan resaltados hasta que la doctora los toque. Nada se guarda solo.
(function () {
  const caja = document.getElementById('os-dictado');
  if (!caja) return;
  const $ = function (sel) { return caja.querySelector(sel); };
  const vistas = {inicio: $('.os-dictado-inicio'), grabando: $('.os-dictado-grabando'),
                  procesando: $('.os-dictado-procesando'), listo: $('.os-dictado-listo')};
  let grabador = null, trozos = [], segundos = 0, reloj = null, flujo = null, descartar = false;

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
    if (!navigator.onLine) { alert('Sin conexión no se puede dictar. Puedes escribir la consulta y se envía al volver la conexión.'); return; }
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
      enviar(new Blob(trozos, {type: grabador.mimeType || 'audio/webm'}));
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

  async function enviar(audio) {
    ver('procesando');
    const datos = new FormData();
    const extension = (audio.type || '').includes('mp4') ? 'm4a' : 'webm';
    datos.append('audio', audio, 'dictado.' + extension);
    datos.append('segundos', segundos);
    datos.append('consentimiento', '1');
    if (caja.dataset.consulta) datos.append('consulta', caja.dataset.consulta);
    datos.append('paciente', caja.dataset.paciente);
    datos.append('plantilla', caja.dataset.plantilla);
    try {
      const r = await fetch(caja.dataset.subir, {method: 'POST', body: datos, credentials: 'same-origin',
                                                  headers: {'X-CSRFToken': token(), 'X-Requested-With': 'fetch'}});
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || 'No se pudo enviar el dictado.');
      esperar(j.id, 0);
    } catch (e) {
      fallo(e.message || 'No se pudo enviar el dictado (¿sin conexión?).');
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
        aplicar(j);
        const oculto = document.querySelector('input[name=dictado]');
        if (oculto) oculto.value = id;
      }
    }).catch(function () { setTimeout(function () { esperar(id, intentos + 1); }, 3000); });
  }

  function fallo(mensaje) {
    ver('inicio');
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

  caja.addEventListener('click', function (e) {
    const b = e.target.closest('[data-accion]');
    if (!b) return;
    const accion = b.dataset.accion;
    if (accion === 'grabar' || accion === 'otra') grabar();
    else if (accion === 'pausar') pausar(b);
    else if (accion === 'terminar' && grabador) grabador.stop();
    else if (accion === 'cancelar' && grabador && confirm('¿Descartar esta grabación?')) { descartar = true; grabador.stop(); }
  });
  window.addEventListener('beforeunload', function (e) {
    if (grabador && grabador.state !== 'inactive') { e.preventDefault(); e.returnValue = ''; }
  });
})();
