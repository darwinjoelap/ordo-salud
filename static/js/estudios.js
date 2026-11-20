/* Selector de exámenes para órdenes y preoperatorio; no toca datos fuera del formulario. */
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-catalogo-estudios]').forEach((panel) => {
    const modo = panel.dataset.modo;
    const lista = panel.querySelector('[data-catalogo-lista]');
    const alta = panel.querySelector('[data-alta-estudio]');
    const editor = alta?.querySelector('[data-alta-panel]');
    const error = alta?.querySelector('[data-alta-error]');

    function controles(fila) {
      const selector = modo === 'orden'
        ? 'input[type="checkbox"][name="examenes"]'
        : 'input[type="checkbox"][name$="-seleccionado"]';
      return fila.querySelector(selector);
    }
    function mostrarCampos() {
      panel.querySelectorAll('[data-fila-estudio]').forEach((fila) => {
        const seleccion = controles(fila);
        const detalles = fila.querySelector('[data-detalles-estudio]');
        if (detalles && seleccion) detalles.hidden = !seleccion.checked;
      });
    }
    panel.addEventListener('change', (evento) => {
      if (evento.target.matches('input[type="checkbox"]')) mostrarCampos();
    });
    mostrarCampos();

    if (!alta || !editor) return;
    alta.querySelector('[data-alta-abrir]').addEventListener('click', () => {
      editor.hidden = !editor.hidden;
      if (!editor.hidden) alta.querySelector('[data-alta-nombre]').focus();
      if (error) error.textContent = '';
    });
    alta.querySelector('[data-alta-cancelar]').addEventListener('click', () => {
      editor.hidden = true;
      if (error) error.textContent = '';
    });

    function nuevoElemento(tag, attrs = {}, texto = '') {
      const el = document.createElement(tag);
      Object.entries(attrs).forEach(([key, val]) => el.setAttribute(key, val));
      if (texto) el.textContent = texto;
      return el;
    }
    function hidden(fila, nombre, valor) {
      fila.appendChild(nuevoElemento('input', {
        type: 'hidden', name: nombre, value: String(valor ?? ''),
      }));
    }
    function campo(fila, prefijo, nombre, tipo, titulo, valor = '') {
      const envoltorio = nuevoElemento('div', {class: 'mb-2'});
      const id = prefijo + '-' + nombre;
      envoltorio.appendChild(nuevoElemento('label', {class: 'form-label', for: id}, titulo));
      let input;
      if (tipo === 'textarea') {
        input = nuevoElemento('textarea', {id, name: prefijo + '-' + nombre,
          class: 'form-control', rows: '2'});
        input.value = valor;
      } else {
        input = nuevoElemento('input', {id, name: prefijo + '-' + nombre,
          type: tipo, class: 'form-control', value: valor});
      }
      envoltorio.appendChild(input);
      fila.appendChild(envoltorio);
    }
    function crearFilaOrden(estudio) {
      const fila = nuevoElemento('fieldset', {class: 'border rounded p-2 mb-2',
        'data-fila-estudio': ''});
      const label = nuevoElemento('label', {class: 'd-flex gap-2 align-items-center'});
      const check = nuevoElemento('input', {class: 'form-check-input m-0',
        type: 'checkbox', name: 'examenes', value: estudio.id});
      check.checked = true;
      label.appendChild(check);
      label.appendChild(nuevoElemento('span', {class: 'fw-semibold'}, estudio.nombre));
      label.appendChild(nuevoElemento('span', {class: 'small text-muted ms-auto'},
        estudio.categoria));
      fila.appendChild(label);
      const detalles = nuevoElemento('div', {class: 'mt-2', 'data-detalles-estudio': ''});
      const cont = nuevoElemento('div', {class: 'mb-2'});
      const id = 'id_indicacion_' + estudio.id;
      cont.appendChild(nuevoElemento('label', {class: 'form-label', for: id},
        'Indicaciones u observaciones'));
      cont.appendChild(nuevoElemento('textarea', {class: 'form-control',
        name: 'indicacion_' + estudio.id, id, rows: '2', maxlength: '1000'}));
      detalles.appendChild(cont);
      fila.appendChild(detalles);
      lista.appendChild(fila);
    }
    function crearFilaPreoperatorio(estudio) {
      const total = panel.querySelector('input[name="estudios-TOTAL_FORMS"]');
      const n = Number(total?.value);
      if (!total || !Number.isSafeInteger(n) || n >= 100) {
        throw new Error('La valoración tiene demasiados estudios; guarda y vuelve a abrirla.');
      }
      const prefijo = 'estudios-' + n;
      const fila = nuevoElemento('fieldset', {class: 'border rounded p-2 mb-2',
        'data-fila-estudio': ''});
      hidden(fila, prefijo + '-catalogo', estudio.id);
      hidden(fila, prefijo + '-nombre', estudio.nombre);
      hidden(fila, prefijo + '-tipo', estudio.categoria);
      hidden(fila, prefijo + '-control_seleccion', 'on');
      const label = nuevoElemento('label', {class: 'd-flex gap-2 align-items-center mb-1'});
      const check = nuevoElemento('input', {class: 'form-check-input m-0',
        type: 'checkbox', name: prefijo + '-seleccionado', value: 'on'});
      check.checked = true;
      label.appendChild(check);
      label.appendChild(nuevoElemento('span', {class: 'fw-semibold'}, estudio.nombre));
      label.appendChild(nuevoElemento('span', {class: 'small text-muted ms-auto'},
        estudio.categoria));
      fila.appendChild(label);
      const detalles = nuevoElemento('div', {'data-detalles-estudio': ''});
      campo(detalles, prefijo, 'fecha', 'date', 'Fecha del examen');
      campo(detalles, prefijo, 'unidad', 'text', 'Unidad (opcional)');
      campo(detalles, prefijo, 'resultado', 'textarea', 'Resultado / hallazgos (si está disponible)');
      campo(detalles, prefijo, 'observaciones', 'textarea', 'Observaciones');
      const adjuntos = panel.querySelector('select[name^="estudios-"][name$="-adjuntos"]');
      if (adjuntos) {
        const cont = nuevoElemento('div', {class: 'mb-2'});
        const id = prefijo + '-adjuntos';
        cont.appendChild(nuevoElemento('label', {class: 'form-label', for: id}, 'Adjuntos existentes'));
        const selector = adjuntos.cloneNode(true);
        selector.name = id;
        selector.id = id;
        selector.querySelectorAll('option').forEach((op) => { op.selected = false; });
        cont.appendChild(selector);
        detalles.appendChild(cont);
      }
      fila.appendChild(detalles);
      lista.appendChild(fila);
      total.value = String(n + 1);
    }

    alta.querySelector('[data-alta-guardar]').addEventListener('click', async (evento) => {
      const boton = evento.currentTarget;
      boton.disabled = true;
      if (error) error.textContent = '';
      try {
        const datos = new FormData();
        const contenedor = panel.closest('form');
        const token = contenedor?.querySelector('input[name="csrfmiddlewaretoken"]')?.value;
        if (token) datos.append('csrfmiddlewaretoken', token);
        datos.append('consulta', panel.dataset.consulta || '');
        datos.append('nombre', alta.querySelector('[data-alta-nombre]').value.trim());
        datos.append('categoria', alta.querySelector('[data-alta-categoria]').value);
        datos.append('descripcion', alta.querySelector('[data-alta-descripcion]').value.trim());
        const respuesta = await fetch(alta.dataset.endpoint, {
          method: 'POST', body: datos, credentials: 'same-origin',
          headers: {'Accept': 'application/json'},
        });
        const cuerpo = await respuesta.json();
        if (!respuesta.ok) {
          const mensajes = Object.values(cuerpo.errores || {}).flat().map(
            (e) => typeof e === 'string' ? e : e.message
          );
          throw new Error(mensajes.join(' ') || 'No se pudo registrar el examen.');
        }
        if (modo === 'orden') crearFilaOrden(cuerpo);
        else crearFilaPreoperatorio(cuerpo);
        editor.hidden = true;
        alta.querySelector('[data-alta-nombre]').value = '';
        alta.querySelector('[data-alta-descripcion]').value = '';
        mostrarCampos();
      } catch (ex) {
        if (error) error.textContent = ex.message || 'No se pudo registrar el examen.';
      } finally {
        boton.disabled = false;
      }
    });
  });
});
