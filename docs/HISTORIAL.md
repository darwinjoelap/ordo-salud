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
