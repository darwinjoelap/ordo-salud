// Dictado por voz (opcional, lo activa la plataforma para el consultorio). Usa el reconocimiento de voz del
// navegador (Chrome/Edge en computadora o Android). Agrega un micrófono a cada texto largo de la historia (para
// dictar o corregir un solo campo; el dictado de toda la consulta con IA está en dictado_ia.js).
(function () {
  const Reconocimiento = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Reconocimiento) return;            // navegador sin dictado: no se muestra nada
  const REEMPLAZOS = [[/\s*punto y aparte\s*/gi, '.\n'], [/\s*nueva línea\s*/gi, '\n'], [/\s*punto y coma\s*/gi, '; '],
                      [/\s*dos puntos\s*/gi, ': '], [/\s*punto\s*/gi, '. '], [/\s*coma\s*/gi, ', ']];
  let activo = null;

  function limpiar(texto) {
    REEMPLAZOS.forEach(function (r) { texto = texto.replace(r[0], r[1]); });
    return texto;
  }

  function detener() {
    if (!activo) return;
    activo.rec.stop();
    activo.boton.classList.remove('os-dictando');
    activo.boton.setAttribute('aria-pressed', 'false');
    activo = null;
  }

  function iniciar(campo, boton) {
    detener();
    const rec = new Reconocimiento();
    rec.lang = 'es-VE';
    rec.continuous = true;
    rec.interimResults = false;
    rec.onresult = function (e) {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (!e.results[i].isFinal) continue;
        let texto = limpiar(e.results[i][0].transcript.trim());
        const antes = campo.value;
        if (antes && !/[\s\n]$/.test(antes)) texto = ' ' + texto;
        if (!antes || /[.\n]\s*$/.test(antes)) texto = texto.replace(/^\s*(\S)/, function (m, c) { return m.replace(c, c.toUpperCase()); });
        campo.value = antes + texto;
        campo.dispatchEvent(new Event('input', {bubbles: true}));
      }
    };
    rec.onend = function () { if (activo && activo.rec === rec) detener(); };
    rec.onerror = function () { detener(); };
    rec.start();
    activo = {rec: rec, boton: boton};
    boton.classList.add('os-dictando');
    boton.setAttribute('aria-pressed', 'true');
  }

  document.querySelectorAll('.os-seccion textarea:not([disabled])').forEach(function (campo) {
    if (campo.closest('table')) return;   // tablas (récipe, diagnósticos): se escriben a mano
    const boton = document.createElement('button');
    boton.type = 'button';
    boton.className = 'btn btn-sm btn-outline-secondary os-mic';
    boton.title = 'Dictar (di «punto», «coma», «punto y aparte»)';
    boton.setAttribute('aria-label', 'Dictar en este campo');
    boton.setAttribute('aria-pressed', 'false');
    boton.innerHTML = '<i class="bi bi-mic"></i>';
    boton.addEventListener('click', function () {
      if (activo && activo.boton === boton) detener(); else iniciar(campo, boton);
    });
    const envoltura = document.createElement('div');
    envoltura.className = 'os-con-mic';
    campo.parentNode.insertBefore(envoltura, campo);
    envoltura.appendChild(campo);
    envoltura.appendChild(boton);
  });
})();
