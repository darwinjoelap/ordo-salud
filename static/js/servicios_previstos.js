(() => {
  const panel = document.querySelector('[data-servicios-previstos]');
  if (!panel) return;
  const profesional = document.getElementById('id_profesional');
  const tipo = document.getElementById('id_tipo');
  const especialistas = JSON.parse(document.getElementById('profesionales-servicios').textContent);
  const predeterminados = JSON.parse(document.getElementById('tipos-servicios').textContent);
  const filas = [...panel.querySelectorAll('[data-servicio-especialidad]')];
  let preseleccion = panel.dataset.explicito === '1' ? null : tipo.value;

  function actualizar(sugerir) {
    const especialidad = String(especialistas[profesional.value] || '');
    const [servicio, especialidadTipo] = predeterminados[tipo.value] || [];
    const predeterminado = filas.find((fila) => fila.querySelector('input').value === String(servicio));
    const compatible = (fila) => !!especialidad &&
      (!fila.dataset.servicioEspecialidad || fila.dataset.servicioEspecialidad === especialidad);
    if (sugerir && preseleccion !== null) {
      const servicioAnterior = predeterminados[preseleccion]?.[0];
      const anterior = filas.find((fila) => fila.querySelector('input').value === String(servicioAnterior));
      if (anterior) anterior.querySelector('input').checked = false;
    }
    if (sugerir && predeterminado && compatible(predeterminado) &&
        (!especialidadTipo || String(especialidadTipo) === especialidad) &&
        !filas.some((fila) => fila.querySelector('input').checked)) {
      predeterminado.querySelector('input').checked = true;
      preseleccion = tipo.value;
    } else if (sugerir) {
      preseleccion = null;
    }

    let hayOpciones = false;
    filas.forEach((fila) => {
      const input = fila.querySelector('input');
      const disponible = compatible(fila);
      fila.classList.toggle('d-none', !disponible && !input.checked);
      fila.querySelector('[data-incompatible]').classList.toggle('d-none', disponible || !input.checked);
      input.disabled = !disponible && !input.checked;
      hayOpciones ||= disponible || input.checked;
    });
    panel.querySelector('[data-sin-servicios]').classList.toggle('d-none', hayOpciones);
  }

  panel.addEventListener('change', () => {
    preseleccion = null;
    actualizar(false);
  });
  tipo.addEventListener('change', () => actualizar(true));
  profesional.addEventListener('change', () => actualizar(true));
  actualizar(preseleccion !== null);
})();
