// Ordo Salud: comportamiento de las secciones de historia (visible_si, filas de tabla, editor de secciones).
(function () {
  'use strict';

  function valorDe(contenedor, nombre) {
    const els = contenedor.querySelectorAll('[name="' + nombre + '"]');
    if (!els.length) return null;
    const el = els[0];
    if (el.type === 'radio') {
      const marcado = Array.from(els).find(function (x) { return x.checked; });
      if (!marcado) return null;
      return marcado.value === 'si' ? true : marcado.value === 'no' ? false : marcado.value;
    }
    if (el.type === 'checkbox') return Array.from(els).filter(function (x) { return x.checked; }).map(function (x) { return x.value; });
    return el.value;
  }

  function cumple(cond, valor) {
    if ('igual' in cond) return valor === cond.igual || (Array.isArray(valor) && valor.indexOf(cond.igual) >= 0);
    if ('en' in cond) return cond.en.indexOf(valor) >= 0;
    if ('distinto' in cond) return valor !== cond.distinto;
    return !!valor;
  }

  function actualizar(seccion) {
    seccion.querySelectorAll('[data-visible-si]').forEach(function (el) {
      const cond = JSON.parse(el.dataset.visibleSi);
      const prefijo = el.name.indexOf('-') >= 0 ? el.name.slice(0, el.name.lastIndexOf('-') + 1) : '';
      const ver = cumple(cond, valorDe(seccion, prefijo + cond.campo));
      const caja = el.closest('[data-campo]');
      if (caja) caja.hidden = !ver;
    });
  }

  document.querySelectorAll('[data-seccion]').forEach(function (s) {
    actualizar(s);
    s.addEventListener('change', function () { actualizar(s); });
  });

  // Tablas: «Agregar fila» clona la última fila con índices nuevos
  document.addEventListener('click', function (e) {
    const btn = e.target.closest('[data-agregar-fila]');
    if (!btn) return;
    const cuerpo = document.getElementById(btn.dataset.agregarFila);
    const filas = cuerpo.querySelectorAll('tr');
    const ultima = filas[filas.length - 1];
    const nueva = ultima.cloneNode(true);
    const n = filas.length;
    nueva.querySelectorAll('input, select, textarea').forEach(function (el) {
      el.name = el.name.replace(/__\d+__/, '__' + n + '__');
      if (el.id) el.id = el.id.replace(/__\d+__/, '__' + n + '__');
      if (el.tagName === 'SELECT') el.selectedIndex = 0; else el.value = '';
    });
    cuerpo.appendChild(nueva);
  });

  // Editor de secciones personalizadas (formset): agregar campo, mover y mostrar opciones según el tipo
  const editor = document.getElementById('editor-campos');
  if (editor) {
    const total = document.getElementById('id_campos-TOTAL_FORMS');
    const molde = document.getElementById('molde-campo').innerHTML;
    function opcionesSegunTipo(fila) {
      const tipo = fila.querySelector('[name$="-tipo"]').value;
      fila.querySelectorAll('[data-para]').forEach(function (el) {
        el.hidden = el.dataset.para.split(' ').indexOf(tipo) < 0;
      });
    }
    function renumerar() {
      editor.querySelectorAll('.js-campo').forEach(function (fila, i) {
        const orden = fila.querySelector('[name$="-orden"]'); if (orden) orden.value = i;
      });
    }
    editor.querySelectorAll('.js-campo').forEach(opcionesSegunTipo);
    renumerar();
    editor.addEventListener('change', function (e) {
      if (e.target.name && e.target.name.endsWith('-tipo')) opcionesSegunTipo(e.target.closest('.js-campo'));
    });
    document.getElementById('agregar-campo').addEventListener('click', function () {
      const n = parseInt(total.value, 10);
      const div = document.createElement('div');
      div.innerHTML = molde.replace(/__prefix__/g, n);
      const fila = div.firstElementChild;
      editor.appendChild(fila);
      total.value = n + 1;
      opcionesSegunTipo(fila); renumerar();
      fila.querySelector('[name$="-etiqueta"]').focus();
    });
    editor.addEventListener('click', function (e) {
      const b = e.target.closest('[data-mover]');
      if (!b) return;
      const fila = b.closest('.js-campo');
      if (b.dataset.mover === 'arriba' && fila.previousElementSibling) fila.parentNode.insertBefore(fila, fila.previousElementSibling);
      if (b.dataset.mover === 'abajo' && fila.nextElementSibling) fila.parentNode.insertBefore(fila.nextElementSibling, fila);
      renumerar();
    });
  }
})();

// Glosario de medicamentos en el récipe: calcula la dosis (peso/edad) y llena la primera fila libre.
(function () {
  const barra = document.querySelector('[data-glosario]');
  if (!barra || !barra.querySelector('#glosario-med')) return;
  const tarjeta = barra.closest('[data-seccion]');
  const peso = barra.querySelector('#glosario-peso');
  const msg = barra.querySelector('[data-glosario-msg]');

  function pesoDelFormulario() {
    const campos = document.querySelectorAll('[name$="-peso_kg"]');
    for (const c of campos) { if (c.value) return c.value; }
    return '';
  }
  // El peso se toma de antropometría/signos vitales mientras el médico no lo cambie a mano
  function sincronizarPeso() { if (!peso.dataset.manual) peso.value = pesoDelFormulario(); }
  peso.addEventListener('input', function () { peso.dataset.manual = '1'; });
  document.addEventListener('input', function (e) { if (e.target.name && e.target.name.endsWith('-peso_kg')) sincronizarPeso(); });
  sincronizarPeso();

  function filaLibre() {
    const nombres = tarjeta.querySelectorAll('[name*="-medicamentos__"][name$="__medicamento"]');
    for (const n of nombres) { if (!n.value.trim()) return n; }
    const boton = tarjeta.querySelector('[data-agregar-fila]');
    if (!boton) return null;
    boton.click();
    const todos = tarjeta.querySelectorAll('[name*="-medicamentos__"][name$="__medicamento"]');
    return todos[todos.length - 1];
  }
  function poner(base, sufijo, valor) {
    const el = tarjeta.querySelector('[name="' + base + sufijo + '"]');
    if (el && valor) el.value = valor;
  }

  barra.querySelector('[data-glosario-agregar]').addEventListener('click', function () {
    const sel = barra.querySelector('#glosario-med');
    if (!sel.value) { sel.focus(); return; }
    const url = barra.dataset.url.replace('/0/', '/' + sel.value + '/') + '?' + new URLSearchParams({
      peso: peso.value.replace(',', '.'), edad_meses: barra.dataset.edadMeses,
      nivel: barra.querySelector('#glosario-nivel').value});
    msg.textContent = 'Calculando…';
    fetch(url, {headers: {'X-Requested-With': 'fetch'}}).then(function (r) {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    }).then(function (d) {
      const campo = filaLibre();
      if (!campo) { msg.textContent = 'No encontré la tabla del récipe.'; return; }
      const base = campo.name.replace(/medicamento$/, '');
      campo.value = d.medicamento;
      poner(base, 'dosis', d.dosis);
      poner(base, 'frecuencia', d.frecuencia);
      poner(base, 'duracion', d.duracion);
      const obs = tarjeta.querySelector('[name$="-observaciones"]');
      if (obs && d.texto && d.calculada) obs.value = (obs.value ? obs.value.trimEnd() + '\n' : '') + d.texto;
      msg.innerHTML = '';
      const ok = document.createElement('div');
      ok.className = 'text-success';
      ok.textContent = '✓ ' + d.medicamento + (d.dosis ? ': ' + d.dosis : '') + (d.dosis_mg && d.dosis_mg !== d.dosis ? ' (' + d.dosis_mg + ')' : '');
      msg.appendChild(ok);
      (d.alertas || []).forEach(function (a) {
        const div = document.createElement('div');
        div.className = 'text-' + a.tipo;
        div.textContent = a.msg;
        msg.appendChild(div);
      });
      sel.value = '';
    }).catch(function () { msg.textContent = 'No se pudo calcular (¿sin conexión?). Escribe la dosis a mano.'; });
  });
})();
