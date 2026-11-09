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
    // «No aplica»: se atenúa y no se puede tocar, pero lo escrito se conserva (p. ej. ciclo con histerectomía)
    seccion.querySelectorAll('[data-no-aplica-si]').forEach(function (el) {
      const cond = JSON.parse(el.dataset.noAplicaSi);
      const prefijo = el.name.indexOf('-') >= 0 ? el.name.slice(0, el.name.lastIndexOf('-') + 1) : '';
      const caja = el.closest('[data-campo]');
      if (caja) caja.classList.toggle('os-no-aplica', cumple(cond, valorDe(seccion, prefijo + cond.campo)));
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

// Récipe numerado (ADR-063, como Pediae): agregar a mano, subir/bajar, quitar; los nombres siguen el orden visible.
(function () {
  function iniciar(caja) {
    function filas() { return Array.prototype.slice.call(caja.querySelectorAll('[data-rx-fila]')); }
    function vacia(f) {
      return !Array.prototype.some.call(f.querySelectorAll('input, textarea'), function (el) { return el.value.trim(); });
    }
    function renumerar() {
      filas().forEach(function (f, i) {
        f.querySelector('[data-rx-num]').textContent = i + 1;
        f.querySelectorAll('input, textarea, select').forEach(function (el) {
          el.name = el.name.replace(/__\d+__/, '__' + i + '__');
          if (el.id) el.id = el.id.replace(/__\d+__/, '__' + i + '__');
        });
      });
    }
    function agregar() {
      const todas = filas();
      const nueva = todas[todas.length - 1].cloneNode(true);
      nueva.querySelectorAll('input, textarea').forEach(function (el) { el.value = ''; });
      nueva.querySelectorAll('[data-rx-glosario]').forEach(function (el) { el.remove(); });
      caja.appendChild(nueva);
      renumerar();
      return nueva;
    }
    // Primera fila vacía; si no hay, una nueva. Siempre deja una fila vacía al final para seguir escribiendo.
    function libre() {
      const f = filas().find(vacia) || agregar();
      if (f === filas()[filas().length - 1]) agregar();
      return f;
    }
    function poner(f, clave, valor) {
      const el = f.querySelector('[name$="__' + clave + '"]');
      if (el && valor) { el.value = valor; el.dispatchEvent(new Event('input', {bubbles: true})); }
    }
    caja.closest('[data-campo]').querySelector('[data-rx-agregar]').addEventListener('click', function () {
      libre().querySelector('[name$="__medicamento"]').focus();
    });
    caja.addEventListener('click', function (e) {
      const b = e.target.closest('[data-rx-subir], [data-rx-bajar], [data-rx-quitar]');
      if (!b) return;
      const f = b.closest('[data-rx-fila]');
      if (b.hasAttribute('data-rx-subir') && f.previousElementSibling) caja.insertBefore(f, f.previousElementSibling);
      if (b.hasAttribute('data-rx-bajar') && f.nextElementSibling) caja.insertBefore(f.nextElementSibling, f);
      if (b.hasAttribute('data-rx-quitar')) {
        if (filas().length > 1) f.remove();
        else f.querySelectorAll('input, textarea').forEach(function (el) { el.value = ''; });
      }
      renumerar();
      caja.dispatchEvent(new Event('change', {bubbles: true}));      // borrador sin conexión
    });
    // Fila n (1…) y lo escrito en cada fila (para «Completar y sugerir con IA»)
    function fila(n) { return filas()[n - 1] || null; }
    function leer() {
      return filas().map(function (f, i) {
        const v = function (clave) { const el = f.querySelector('[name$="__' + clave + '"]'); return el ? el.value.trim() : ''; };
        return {fila: i + 1, medicamento: v('medicamento'), dosis: v('dosis'), frecuencia: v('frecuencia'),
                duracion: v('duracion'), indicacion: v('indicacion')};
      }).filter(function (r) { return r.medicamento; });
    }
    caja.ordoRx = {libre: libre, poner: poner, fila: fila, leer: leer};
  }
  document.querySelectorAll('[data-rx]').forEach(iniciar);
  // Para el glosario y la sugerencia con IA
  window.OrdoRecipe = function (dentro) {
    const caja = (dentro || document).querySelector('[data-rx]');
    return caja ? caja.ordoRx : null;
  };
})();

// Glosario de medicamentos en el récipe: calcula la dosis (peso/edad) y llena la primera fila libre.
(function () {
  const barra = document.querySelector('[data-glosario]');
  if (!barra) return;
  const tarjeta = barra.closest('[data-seccion]');
  const peso = barra.querySelector('#glosario-peso');
  const origen = barra.querySelector('[data-glosario-peso-origen]');
  const msg = barra.querySelector('[data-glosario-msg]');

  function pesoDelFormulario() {
    const campos = document.querySelectorAll('[name$="-peso_kg"]');
    for (const c of campos) { if (c.value) return c.value; }
    return '';
  }
  // El peso se toma de antropometría/signos vitales mientras el médico no lo cambie a mano (siempre a la vista)
  function sincronizarPeso() {
    if (!peso.dataset.manual) peso.value = pesoDelFormulario();
    if (origen) origen.textContent = peso.dataset.manual ? '(escrito a mano)' : (peso.value ? '(de esta consulta)' : '(escríbelo para calcular dosis)');
  }
  peso.addEventListener('input', function () { peso.dataset.manual = peso.value ? '1' : ''; sincronizarPeso(); });
  document.addEventListener('input', function (e) { if (e.target.name && e.target.name.endsWith('-peso_kg')) sincronizarPeso(); });
  sincronizarPeso();
  if (!barra.querySelector('#glosario-med')) return;


  // Calcula con la ficha del glosario y llena «fila» (o la primera libre). En una fila ya escrita solo llena lo vacío.
  function calcular(pk, destino) {
    const url = barra.dataset.url.replace('/0/', '/' + pk + '/') + '?' + new URLSearchParams({
      peso: peso.value.replace(',', '.'), edad_meses: barra.dataset.edadMeses,
      nivel: barra.querySelector('#glosario-nivel').value});
    msg.textContent = 'Calculando…';
    return fetch(url, {headers: {'X-Requested-With': 'fetch'}}).then(function (r) {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    }).then(function (d) {
      const rx = window.OrdoRecipe(tarjeta);
      if (!rx) { msg.textContent = 'No encontré el récipe.'; return; }
      const fila = destino || rx.libre();
      const vacio = function (k) { const c = fila.querySelector('[name$="__' + k + '"]'); return c && !c.value.trim(); };
      if (!destino || vacio('medicamento')) rx.poner(fila, 'medicamento', d.medicamento);
      ['dosis', 'frecuencia', 'duracion'].forEach(function (k) { if (vacio(k)) rx.poner(fila, k, d[k]); });
      if (d.texto && (d.calculada || d.con_indicaciones) && vacio('indicacion')) rx.poner(fila, 'indicacion', d.texto);
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
    }).catch(function () { msg.textContent = 'No se pudo calcular (¿sin conexión?). Escribe la dosis a mano.'; });
  }

  barra.querySelector('[data-glosario-agregar]').addEventListener('click', function () {
    const sel = barra.querySelector('#glosario-med');
    if (!sel.value) { sel.focus(); return; }
    calcular(sel.value).then(function () { sel.value = ''; });
  });

  // Nombre escrito a mano que está en el glosario → botón «Calcular con glosario» en esa fila (sin IA)
  function clave(texto) {
    const p = (texto || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').match(/[a-zñ]{4,}/);
    return p ? p[0] : '';
  }
  const opciones = Array.prototype.slice.call(barra.querySelectorAll('#glosario-med option'))
    .filter(function (o) { return o.value; })
    .map(function (o) { return {pk: o.value, nombre: o.textContent.split(' · ')[0].trim(), texto: o.textContent.trim()}; });
  const rxCaja = tarjeta && tarjeta.querySelector('[data-rx]');
  if (rxCaja && opciones.length) {
    let espera;
    rxCaja.addEventListener('input', function (e) {
      if (!e.target.name || !e.target.name.endsWith('__medicamento')) return;
      clearTimeout(espera);
      espera = setTimeout(function () { ofrecer(e.target); }, 300);
    });
    function ofrecer(campo) {
      const fila = campo.closest('[data-rx-fila]');
      if (!fila) return;
      fila.querySelectorAll('[data-rx-glosario]').forEach(function (el) { el.remove(); });
      const k = clave(campo.value);
      const dosis = fila.querySelector('[name$="__dosis"]');
      if (!k || (dosis && dosis.value.trim())) return;
      const m = opciones.find(function (o) { return clave(o.nombre) === k; });
      if (!m) return;
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'btn btn-link btn-sm p-0 small';
      b.setAttribute('data-rx-glosario', '');
      b.textContent = 'Calcular con glosario: ' + m.texto;
      b.addEventListener('click', function () { b.remove(); calcular(m.pk, fila); });
      campo.insertAdjacentElement('afterend', b);
    }
  }
})();

// Campos calculados (percentiles, IMC, EG, FPP…): vista previa mientras se escribe. Sin conexión, se calculan al guardar.
(function () {
  function token() {
    const c = document.querySelector('input[name=csrfmiddlewaretoken]');
    return c ? c.value : '';
  }
  document.querySelectorAll('[data-calculo]').forEach(function (bloque) {
    const prefijo = bloque.dataset.prefijo;
    let espera = null;
    function calcular() {
      const datos = new FormData();
      bloque.querySelectorAll('[name^="' + prefijo + '-"]').forEach(function (el) {
        if ((el.type === 'checkbox' || el.type === 'radio') && !el.checked) return;
        datos.append(el.name, el.value);
      });
      datos.append('_prefijo', prefijo);
      if (bloque.dataset.paciente) datos.append('_paciente', bloque.dataset.paciente);
      if (bloque.dataset.fecha) datos.append('_fecha', bloque.dataset.fecha);
      const sc = document.querySelector('[data-calculado="superficie_corporal"]');
      if (sc && sc.value) datos.append('_sc', sc.value);
      fetch(bloque.dataset.calculo, {method: 'POST', body: datos, credentials: 'same-origin',
                                     headers: {'X-CSRFToken': token(), 'X-Requested-With': 'fetch'}})
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (res) {
          if (!res) return;
          Object.keys(res).forEach(function (clave) {
            const campo = bloque.querySelector('[data-calculado="' + clave + '"]');
            if (campo) campo.value = res[clave] || '';
          });
        })
        .catch(function () { /* sin conexión: se calcula al guardar */ });
    }
    bloque.addEventListener('input', function () { clearTimeout(espera); espera = setTimeout(calcular, 450); });
    bloque.addEventListener('change', function () { clearTimeout(espera); espera = setTimeout(calcular, 150); });
  });
})();

// «Completar lo vacío como normal» (ADR-053): pone el valor normal solo donde no hay nada marcado o escrito.
(function () {
  document.addEventListener('click', function (ev) {
    const boton = ev.target.closest('[data-normales]');
    if (!boton) return;
    const prefijo = boton.dataset.prefijoNormales;
    const normales = JSON.parse(boton.dataset.normales || '{}');
    let marcados = 0;
    Object.keys(normales).forEach(function (clave) {
      const valor = String(normales[clave]);
      const campos = document.querySelectorAll('[name="' + prefijo + '-' + clave + '"]');
      if (!campos.length) return;
      const primero = campos[0];
      if (primero.type === 'radio') {
        if (Array.prototype.some.call(campos, function (r) { return r.checked; })) return;
        const elegido = Array.prototype.find.call(campos, function (r) { return r.value === valor; });
        if (!elegido) return;
        elegido.checked = true;
        elegido.dispatchEvent(new Event('change', {bubbles: true}));
      } else {
        if (primero.value) return;
        primero.value = valor;
        primero.dispatchEvent(new Event('change', {bubbles: true}));
      }
      marcados += 1;
    });
    boton.innerHTML = '<i class="bi bi-check2-all me-1"></i>' + (marcados ? marcados + ' campos completados como normales' : 'No quedaba nada vacío');
  });
})();
