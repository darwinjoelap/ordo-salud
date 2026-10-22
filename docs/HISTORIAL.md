# HISTORIAL — Omnis

> Resumen de cada fase **cerrada** (lo que se hizo, commits, verificación, pendientes que pasaron
> a otra fase). Lo más reciente arriba. El detalle vivo está en `ESTADO.md` mientras la fase está abierta.

## Plantilla de entrada

```
### Fase NN — Nombre (AAAA-MM-DD)
- Hecho: …
- Verificado: N tests en verde (SQLite + PostgreSQL), ruff limpio, prueba manual de Darwin
- Commits: `abc1234`, `def5678`
- ADR: 0XX, 0YY
- Pasó a otra fase: … (Fase MM)
```

---

### Dictado con Gemini y subir grabación (2026-10-22)
- Hecho: proveedor Gemini Flash (una llamada: transcripción + campos), conversión a MP3 y duración real con ffmpeg, «Subir grabación» del teléfono, grabación pendiente guardada en el equipo con reintento.
- Verificado: 216 tests en verde (SQLite + PostgreSQL), ruff limpio; en navegador: subir .m4a, grabar sin internet → queda guardada → recargar → enviar.
- ADR: 046 · Falta: prueba con clave real de Gemini (nivel pagado).

### Dictado de la consulta con IA (2026-10-22)
- Hecho: grabar, transcribir (OpenAI), ordenar en la historia (Claude Sonnet 5.5), validar y llenar el formulario resaltado; minutos por plan; audio no se guarda; modo de prueba sin claves.
- Verificado: 212 tests en verde (SQLite + PostgreSQL), ruff limpio; prueba en navegador con micrófono simulado (modo de prueba y llenado con respuesta simulada). Falta la prueba con claves reales.
- ADR: 045

### Fase 15 — Cardiología pediátrica, primera entrega (2026-10-22)
- Hecho: módulo con antecedentes y párrafo automático, EKG y eco estructurados con cálculos y prosa, informe médico en el formato de la doctora con imágenes y notas de evolución, panel, reporte, dictado por voz opcional.
- Verificado: 206 tests en verde (SQLite + PostgreSQL), ruff limpio; su caso complejo cargado y el PDF comparado con su Word
- ADR: 044
- Pendiente: SC y Z-score con la doctora, revisión del informe, ecocardiografía fetal

### Ajustes de pediatría (2026-10-22)
- Hecho: datos del menor en el formulario, registro rápido con «abrir historia / agendar», carnet de vacunas de una vez y botón «Vacunas» en la consulta, referencia con antecedentes elegidos, historia clínica completa en PDF, percentiles y demás calculados en vivo, PDF sin errores con «<» o «&».
- Verificado: 197 tests en verde (SQLite + PostgreSQL), ruff limpio, capturas (formulario, carnet, consulta, referencia) y PDF de la historia revisados
- ADR: 043

### Reportes fijos y por especialidad (2026-10-22)
- Hecho: pestañas General + una por especialidad; sexo solo si es relevante; reporte GO con enfermedades, VIH, VPH (diagnóstico y vacuna), ITS, citología alterada, condiciones y hábitos (también en Excel); morbilidad en pediatría.
- Ampliado: «CIE-10» → «Código»; filtro por diagnóstico (tocar una enfermedad filtra); PDF de los reportes de GO y pediatría; controles prenatales por mes con EG promedio.
- Verificado: 190 tests en verde (SQLite + PostgreSQL), ruff limpio, capturas y PDF revisados con datos de prueba; falta prueba manual de Darwin con datos reales
- ADR: 042

### Procedimientos, agenda y «Armar historia» (2026-10-22)
- Hecho: procedimientos sin consulta (varios por día, cargos por servicio, vacunas en pediatría), agenda del día como Pediae, historial de consultas desplegable en la ficha, editor de plantillas con interruptores y «Hacer mi copia».
- Verificado: tests (SQLite + PostgreSQL), ruff limpio, capturas escritorio y móvil.
- ADR: 040, 041.

### Fase 14 Ginecología y obstetricia (2026-10-21, falta revisión clínica)
- Hecho: módulo GO desde Ginea (ficha, consulta, control prenatal con EG/FPP, paneles, constancia de embarazo, carnet prenatal, reporte + Excel), sexo F por defecto en GO; arreglos: editar paciente (500) y documentos sin formulario desde la ficha.
- Verificado: 181 tests (SQLite + PostgreSQL), ruff limpio, capturas escritorio y móvil.
- ADR: 039.

### Cambio de marca: Omnis → Ordo Salud (2026-10-21)
- Hecho: logo en SVG y todas sus presentaciones, rediseño (paleta del logo, Nunito, menú marino) en la app y en el lienzo de diseño, renombre completo del código (textos, archivos, ajustes, cachés, prefijo CSS `os-`), migraciones de colores por defecto, carpeta y repo `ordo-salud`.
- Verificado: 169 tests (SQLite + PostgreSQL), ruff limpio, capturas escritorio y móvil.
- ADR: 038.

### Fase 13 Pediatría — avance (2026-10-21, fase abierta)
- Hecho: perfil por especialidad (paneles, reportes, rutas y páginas offline por módulo), ficha pediátrica en página propia, curvas OMS SVG/PDF, vacunas (35 dosis, anual) y pesquisas, constancias pediátricas, reporte pediátrico + Excel, glosario de medicamentos con calculadora de dosis en el récipe (núcleo).
- Verificado: 169 tests (SQLite + PostgreSQL), ruff limpio, `makemigrations --check`, capturas escritorio y móvil.
- ADR: 034, 035, 036, 037.

### Panel de suscripciones (2026-10-21)
- Hecho: planes en el panel, días de gracia (plan + consultorio), anular la última renovación con motivo, tablero de suscripciones, navegación del panel, registro de accesos de soporte (también en la auditoría del consultorio) y aviso de gracia al equipo.
- Verificado: 128 tests (SQLite + PostgreSQL), ruff limpio, capturas del panel.
- ADR: 033.

### Fase 12 — PWA offline de consulta (2026-10-20)
- Hecho: app `offline` (idempotencia, ping, precarga), `offline.js` portado de Pediae (borradores, cola, píldora), service worker con copias de páginas y página «sin conexión» que lista lo guardado; consulta nueva en un solo envío (GET formulario / POST completa) que vincula la cita y genera el cargo; «Atender» sin red → consulta nueva guardada.
- Verificado: 118 tests (SQLite + PostgreSQL), ruff limpio, E2E con servidor apagado (copia, cola, sincronización).
- ADR: 032.

### Fase 11 + perfil Pediae (2026-10-20)
- Hecho: app `reportes` (tablero, PDF, Excel), perfil profesional con logo/marca de agua/banner, firma y sello fijos al pie de los PDF, documento de muestra por médico.
- Verificado: 107 tests (SQLite + PostgreSQL), ruff limpio, capturas escritorio/móvil y PDF revisados.
- ADR: 030, 031.

### Fases 01–10 — Base, clínica, agenda, cobros y documentos (2026-10-20)
- Hecho: esqueleto y despliegue preparado (sin crear Railway); tenancy fail-closed con `TenantModel`;
  login por enlace del consultorio; roles + pseudo-rol PROFESIONAL; plataforma (planes, suscripciones,
  soporte sin acceso a historias); configuración, lugares y perfil profesional; tasa BCV (de Ordo);
  pacientes/representantes; motor de secciones (esquema JSON versionado, plantillas del médico, secciones
  personalizadas); consulta (borrador, cierre, enmienda, anulación, CIE-10, signos, prescripción, adjuntos,
  cierre automático); agenda multi-profesional; cobros con abonos y saldo a favor; documentos PDF con
  número correlativo (récipe dos columnas de Ginea, informe, referencia, reposo, constancia, recibo).
- Verificado: 96 tests (SQLite + PostgreSQL 16), ruff limpio, E2E Playwright escritorio/móvil.
- Commits: sin repositorio todavía (archivos en `C:\proyectos\omnis`).
- ADR: 020–027 (provisionales).
- Pasó a otra fase: offline de consulta (12), adjuntos `authenticated` (15), CIE-10 completo (pendiente de archivo).

### Fase 00 — Diseño (2026-10-19, abierta hasta aprobar ADR)
- Revisión de Ginea, Pediae, Ordo y Biolife; paquete de documentación inicial.
