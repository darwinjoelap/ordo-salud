(() => {
  const android = /Android/i.test(navigator.userAgent);
  document.querySelectorAll('[data-whatsapp-agenda]').forEach((formulario) => {
    const botones = [...formulario.querySelectorAll('[data-whatsapp]')];
    const [preparar, business, web] = botones;
    const estado = formulario.querySelector('[data-whatsapp-estado]');
    let ocupado = false;
    let clave = null;
    preparar.hidden = !android;
    if (android) web.textContent = 'Abrir con wa.me';

    formulario.addEventListener('submit', (evento) => evento.preventDefault());
    botones.forEach((boton) => boton.addEventListener('click', async () => {
      if (ocupado) return;
      ocupado = true;
      botones.forEach((b) => { b.disabled = true; });
      const accion = boton.dataset.whatsapp;
      estado.textContent = 'Verificando contacto…';
      try {
        if (!clave) {
          const bytes = Array.from(crypto.getRandomValues(new Uint8Array(16)),
                                  (n) => n.toString(16).padStart(2, '0'));
          clave = bytes.join('');
        }
        const datos = new FormData(formulario);
        datos.set('accion', accion);
        datos.set('clave_intento', clave);
        const respuesta = await fetch(formulario.action, {
          method: 'POST', body: datos, credentials: 'same-origin', cache: 'no-store', redirect: 'error',
        });
        if (!respuesta.ok) throw new Error();
        if (accion === 'validar' && respuesta.status === 204) {
          business.hidden = false;
          preparar.hidden = true;
          estado.textContent = 'Contacto validado. Pulsa Abrir WhatsApp Business.';
          return;
        }

        const resultado = await respuesta.json();
        if (accion === 'copiar' && typeof resultado.mensaje === 'string') {
          try {
            await navigator.clipboard.writeText(resultado.mensaje);
            estado.textContent = 'Mensaje copiado.';
          } catch {
            window.prompt('Copia el mensaje:', resultado.mensaje);
            estado.textContent = '';
          }
          return;
        }
        if (accion !== 'copiar' && accion !== 'validar' && typeof resultado.destino === 'string' &&
            (/^https:\/\/wa\.me\//.test(resultado.destino) ||
             (accion === 'business' && android && resultado.destino.startsWith('intent://send/')))) {
          estado.textContent = accion === 'business'
            ? 'Intento registrado. Si Business no abre, usa wa.me.'
            : 'Intento registrado.';
          window.location.assign(resultado.destino);
          return;
        }
        throw new Error();
      } catch {
        preparar.hidden = !android;
        business.hidden = true;
        estado.textContent = 'No se pudo validar o registrar el contacto. Revisa la autorización o reintenta.';
      } finally {
        ocupado = false;
        botones.forEach((b) => { b.disabled = false; });
      }
    }));
  });
})();
