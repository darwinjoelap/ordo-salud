// Sugerir récipe e indicaciones con IA (ADR-060). La IA elige y redacta; las dosis las calcula el servidor.
// Nada entra a la historia hasta que la profesional marca lo que quiere y toca «Agregar al récipe».
(function () {
  const caja = document.querySelector('[data-sugerir-ia]');
  if (!caja) return;
  const tarjeta = caja.closest('[data-seccion]');
  const panel = caja.querySelector('[data-sugerir-ia-panel]');
  const boton = caja.querySelector('[data-sugerir-ia-btn]');

  function token() {
    const c = document.querySelector('input[name=csrfmiddlewaretoken]');
    return c ? c.value : '';
  }
  function el(tag, clase, texto) {
    const e = document.createElement(tag);
    if (clase) e.className = clase;
    if (texto !== undefined) e.textContent = texto;
    return e;
  }

  // Lo escrito en la consulta (cualquier especialidad): «Sección · Campo» → valor. Sin el récipe.
  function etiqueta(campo) {
    if (campo.id) {
      const l = document.querySelector('label[for="' + campo.id + '"]');
      if (l && l.textContent.trim()) return l.textContent.trim().replace(/\s*\*$/, '');
    }
    return campo.getAttribute('placeholder') || campo.name.split('-').pop().replace(/__\d+__/, ' ').replace(/_/g, ' ');
  }
  function camposConsulta() {
    const salida = {};
    document.querySelectorAll('[data-seccion]').forEach(function (sec) {
      if (sec.dataset.codigo === 'nucleo.prescripcion') return;
      const cab = sec.querySelector('.card-header');
      const titulo = cab ? cab.textContent.trim().split('\n')[0].trim() : '';
      sec.querySelectorAll('input, textarea, select').forEach(function (c) {
        if (!c.name || c.type === 'hidden' || c.type === 'file' || c.disabled) return;
        let valor = '';
        if (c.type === 'checkbox' || c.type === 'radio') {
          if (!c.checked) return;
          valor = c.value === 'on' ? 'sí' : (c.closest('label') ? c.closest('label').textContent.trim() : c.value);
        } else if (c.tagName === 'SELECT') {
          valor = c.value ? c.options[c.selectedIndex].text : '';
        } else {
          valor = c.value.trim();
        }
        if (!valor) return;
        // Radios: la etiqueta es la opción elegida → la clave es solo la sección
        const clave = c.type === 'radio' ? (titulo || c.name) : (titulo ? titulo + ' · ' : '') + etiqueta(c);
        salida[clave] = salida[clave] ? salida[clave] + '; ' + valor : valor;
      });
    });
    return salida;
  }
  function peso() {
    const manual = document.querySelector('#glosario-peso');
    if (manual && manual.value) return manual.value;
    for (const c of document.querySelectorAll('[name$="-peso_kg"]')) { if (c.value) return c.value; }
    return '';
  }

  function agregarTexto(campo, texto) {
    if (campo && texto) campo.value = (campo.value ? campo.value.trimEnd() + '\n' : '') + texto;
  }

  function guardarEnGlosario(ficha, btn) {
    btn.disabled = true;
    fetch(caja.dataset.urlGlosario, {method: 'POST', body: JSON.stringify(ficha),
      headers: {'X-CSRFToken': token(), 'X-Requested-With': 'fetch', 'Content-Type': 'application/json'}})
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (d) { btn.replaceWith(el('span', 'small text-success', '✓ Guardado en tu glosario: ' + d.nombre)); })
      .catch(function () { btn.disabled = false; btn.textContent = 'No se pudo guardar · reintentar'; });
  }

  function tarjetaFila(f) {
    const fila = el('div', 'border-top pt-2 mt-2');
    const linea = el('label', 'd-flex gap-2 align-items-start');
    const check = el('input', 'form-check-input mt-1');
    check.type = 'checkbox';
    const peligro = (f.alertas || []).some(function (a) { return a.tipo === 'danger'; });
    check.checked = Boolean(f.fila) && !peligro;          // completar: marcado; adicionales: a criterio de ella
    linea.appendChild(check);
    const cuerpo = el('div', 'flex-grow-1');
    const titulo = el('div', 'fw-semibold', (f.fila ? f.fila + '. ' : '+ ') + f.medicamento);
    if (f.origen === 'ia') titulo.appendChild(el('span', 'badge text-bg-warning ms-2', 'IA · verificar'));
    if (f.origen === 'glosario') titulo.appendChild(el('span', 'badge text-bg-success ms-2', 'de tu glosario'));
    cuerpo.appendChild(titulo);
    cuerpo.appendChild(el('div', 'small', [f.dosis, f.frecuencia, f.duracion].filter(Boolean).join(' · ') || 'Sin dosis calculada'));
    if (f.texto) cuerpo.appendChild(el('div', 'small fst-italic', '«' + f.texto + '»'));
    if (f.ficha) cuerpo.appendChild(el('div', 'small text-muted', 'Ficha: ' + f.ficha));
    if (f.nota) cuerpo.appendChild(el('div', 'small text-muted', f.nota));
    (f.alertas || []).forEach(function (a) { cuerpo.appendChild(el('div', 'small text-' + a.tipo, a.msg)); });
    linea.appendChild(cuerpo);
    fila.appendChild(linea);
    if (f.para_glosario) {
      const g = el('button', 'btn btn-link btn-sm p-0 ms-4', 'Guardar esta ficha en mi glosario');
      g.type = 'button';
      g.addEventListener('click', function () { guardarEnGlosario(f.para_glosario, g); });
      fila.appendChild(g);
    }
    return {nodo: fila, check: check, datos: f};
  }

  function mostrar(d) {
    panel.innerHTML = '';
    const card = el('div', 'border rounded p-2 bg-body-tertiary');
    card.appendChild(el('div', 'fw-semibold mb-1', 'Sugerencia (revisa antes de agregar)'));
    (d.alertas || []).forEach(function (a) { card.appendChild(el('div', 'small text-warning-emphasis', '⚠ ' + a)); });
    const filas = [];
    const completar = (d.filas || []).filter(function (f) { return f.fila; });
    const nuevas = (d.filas || []).filter(function (f) { return !f.fila; });
    [[completar, 'Completar tu récipe'], [nuevas, 'También podrías agregar']].forEach(function (grupo) {
      if (!grupo[0].length) return;
      card.appendChild(el('div', 'small text-uppercase text-muted fw-semibold mt-2', grupo[1]));
      grupo[0].forEach(function (f) { const t = tarjetaFila(f); card.appendChild(t.nodo); filas.push(t); });
    });
    if (!filas.length && !d.indicaciones) card.appendChild(el('div', 'small text-muted', 'No hay nada que agregar.'));
    let indic = null;
    if (d.indicaciones) {
      const bloque = el('div', 'border-top pt-2 mt-2');
      bloque.appendChild(el('div', 'small fw-semibold', 'Indicaciones generales (puedes editarlas aquí)'));
      indic = el('textarea', 'form-control form-control-sm mt-1');
      indic.rows = 3;
      indic.value = d.indicaciones;
      bloque.appendChild(indic);
      card.appendChild(bloque);
    }
    const acciones = el('div', 'd-flex gap-2 mt-2');
    const ok = el('button', 'btn btn-sm btn-primary', 'Agregar lo marcado');
    ok.type = 'button';
    const no = el('button', 'btn btn-sm btn-outline-secondary', 'Descartar');
    no.type = 'button';
    acciones.appendChild(ok);
    acciones.appendChild(no);
    card.appendChild(acciones);
    panel.appendChild(card);

    no.addEventListener('click', function () { panel.innerHTML = ''; });
    ok.addEventListener('click', function () {
      const obs = tarjeta.querySelector('[name$="-observaciones"]');
      const rx = window.OrdoRecipe(tarjeta);
      filas.forEach(function (x) {
        if (!x.check.checked || !rx) return;
        const f = x.datos;
        const destino = (f.fila && rx.fila(f.fila)) || rx.libre();
        const vacio = function (clave) {
          const c = destino.querySelector('[name$="__' + clave + '"]');
          return c && !c.value.trim();
        };
        // En la fila de ella: se completa lo vacío y no se pisa lo que escribió
        const nombre = destino.querySelector('[name$="__medicamento"]');
        if (!nombre.value.trim() || f.medicamento.toLowerCase().indexOf(nombre.value.trim().toLowerCase()) === 0) {
          rx.poner(destino, 'medicamento', f.medicamento);        // «Amoxicilina» → «Amoxicilina susp. 250 mg/5 mL»
        }
        ['dosis', 'frecuencia', 'duracion'].forEach(function (k) { if (vacio(k)) rx.poner(destino, k, f[k]); });
        if (vacio('indicacion')) rx.poner(destino, 'indicacion', f.texto);
      });
      if (indic && indic.value.trim()) {
        const plan = document.querySelector('[data-codigo="nucleo.plan"] [name$="-indicaciones"]');
        agregarTexto(plan || obs, indic.value.trim());
      }
      panel.innerHTML = '';
      panel.appendChild(el('div', 'small text-success', '✓ Agregado. Revisa el récipe antes de guardar.'));
    });
  }

  boton.addEventListener('click', function () {
    boton.disabled = true;
    panel.innerHTML = '';
    panel.appendChild(el('div', 'small text-muted', 'Pensando la sugerencia… (unos segundos)'));
    fetch(caja.dataset.url, {method: 'POST', body: JSON.stringify({campos: camposConsulta(), peso: peso(),
                                                         recipe: (window.OrdoRecipe(tarjeta) || {leer: function () { return []; }}).leer()}),
      headers: {'X-CSRFToken': token(), 'X-Requested-With': 'fetch', 'Content-Type': 'application/json'}})
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (d) {
          if (!r.ok) throw new Error(d.error || ('Error ' + r.status));
          return d;
        });
      })
      .then(mostrar)
      .catch(function (e) {
        panel.innerHTML = '';
        panel.appendChild(el('div', 'small text-danger', e.message && e.message !== 'Failed to fetch'
          ? e.message : 'No se pudo pedir la sugerencia (¿sin conexión?).'));
      })
      .finally(function () { boton.disabled = false; });
  });
})();
