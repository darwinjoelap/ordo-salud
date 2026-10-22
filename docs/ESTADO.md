# ESTADO — Ordo Salud

> Se actualiza al **cerrar cada sesión** y es lo primero que se lee al abrir la siguiente.
> Menos de 100 líneas: el detalle de fases cerradas va a `HISTORIAL.md`; las decisiones, a `DECISIONES.md`.

**Última actualización:** 2026-10-21
**Fase actual:** 13 Pediatría **en curso** (13.1–13.6 y 13.9 hechas; 13.7–13.8 casi; ver `roadmap/13_pediatria.md`) · 14 Ginecobstetricia hecha (falta revisión con ginecóloga) → siguiente: pendientes de 13/14 o Railway staging
**Repositorio:** `github.com/darwinjoelap/ordo-salud` (privado), rama `main` — código en `C:\proyectos\ordo-salud`
**Último commit:** `c0155ed` cambio de marca a Ordo Salud (pusheado 2026-10-21 a `ordo-salud`) · entorno local: `venv\Scripts\Activate.ps1` (carpeta `venv`, no `.venv`; recreado con Python 3.14)
**Staging / producción:** pendientes (Railway no creado)

---

## Retomar aquí (2026-10-22)
1. Darwin: probar en su PC «Armar historia» (menú Historia clínica), la agenda nueva y «Procedimiento» (ficha y agenda).
   Si sigue sin ver secciones: `sincronizar_especialidades` + `refrescar_plantillas <esp> --consultorio <enlace>` y
   Ctrl+F5; si la plantilla es del consultorio y su usuario no la puede editar, usar «Hacer mi copia».
2. Darwin: revisar «Reportes» → pestañas General y Ginecología y obstetricia (ADR-042) con pacientes reales; decir qué
   otra estadística de interés falta (p. ej. por diagnóstico CIE-10 específico, prenatales por mes).

## Completado (código + tests; falta prueba manual de Darwin)
- [x] 01 Esqueleto (settings por entorno, Dockerfile, railway.json, cron, `/salud/`)
- [x] 02 Tenancy, usuarios, equipo, permisos, plataforma, planes, auditoría
- [x] 03 Configuración del tenant, lugares, perfil profesional (firma, sello, membrete)
- [x] 04 Tasa BCV + tasa del tenant; servicios con precio USD
- [x] 05 Pacientes y representantes (duplicados, hermanos, menores)
- [x] 06 Motor de secciones y plantillas (el médico arma su historia)
- [x] 07 Consulta clínica: borrador/cierre/enmienda/anulación, CIE-10, adjuntos, cierre automático
- [x] 08 Agenda multi-profesional (horarios, bloqueos, tipos, sobrecupo, WhatsApp, «Atender»)
- [x] 09 Cobros: cargos, pagos USD/Bs, abonos, saldo a favor, caja del día, por cobrar
- [x] 10 Documentos PDF: récipe (2 columnas), informe, referencia, reposo, constancia, recibo
- [x] 11 Reportes: tablero con filtros, morbilidad CIE-10, agenda, ingresos, por profesional; PDF y Excel (ADR-031)
- [x] 12 PWA offline de consulta: borradores, cola con idempotencia, precarga y copias de agenda/fichas, consulta nueva sin red (ADR-032)
- [~] 13 Pediatría (perfil, ADR-036): historia en el orden de Pediae con tipo de consulta, ficha pediátrica en página propia, percentiles OMS 0–19 años (ADR-034), curvas (pantalla y PDF), vacunas y pesquisas, constancias (niño sano, lactancia ×2, carnet, curvas), reporte pediátrico + Excel, offline · glosario con calculadora de dosis en el núcleo (ADR-037) · ajustes de Pediae en el núcleo (ADR-035)
- [~] 14 Ginecología y obstetricia (ADR-039): ficha GO, consulta como Ginea, control prenatal con EG/FPP, paneles de embarazo y resumen, constancia de embarazo y carnet prenatal, reporte GO + Excel · falta revisión con una ginecóloga real
- [x] Procedimientos sin consulta (ADR-040) · agenda estilo Pediae, historial en la ficha y «Armar historia» con casillas (ADR-041)
- [x] Panel de suscripciones: planes, días de gracia, anular renovación, tablero, registro de accesos de soporte (ADR-033)
- [x] Perfil del médico estilo Pediae: logo/marca de agua, banner, firma y sello fijos al pie (ADR-030)
- [x] Alcance de pacientes por rol (ADR-029): médico ve los suyos; asistente/titular ven todo; configurable
- [x] Marca **Ordo Salud** (ADR-038, reemplaza Omnis): logo en vector, paleta azul marino/verde, Nunito + Inter locales, menú marino, login en dos paneles

**Verificación:** 189 tests en verde en SQLite y PostgreSQL 16 · `ruff` limpio · `makemigrations --check` limpio ·
E2E con navegador: paciente → consulta → cierre → PDF; offline (servidor apagado): copia de agenda, consulta nueva en cola, sincroniza al volver.

## Pendiente inmediato
1. ~~venv + migrate + test en Windows~~ hecho: 118 tests OK en la PC de Darwin, migración `offline.0001` aplicada (2026-10-20).
2. Darwin: prueba manual con `crear_tenant` (ver README) — revisar textos de reposo/constancia y el récipe impreso.
3. Crear proyecto Railway (Postgres, servicio web, servicio cron) → staging.
4. Darwin: probar offline en el teléfono (abrir la agenda con señal, modo avión, atender, volver a la señal).
5. Fase 13/14 módulo Pediatría o Ginecología.

## Incompleto / provisional (decir siempre)
- ADR 002–007 y 009–019 aplicadas como provisionales (ADR-020): revisar.
- Logo: redibujado en SVG desde el PNG entregado (muy fiel, no idéntico); si el diseñador tiene el vector original, reemplazarlo en `static/img/marca/`.
- Dominio y correo de envío: por definir (`ordosalud…`); Railway aún con el nombre viejo si ya se hubiera creado (no lo está).
- PDFs (ReportLab) siguen en Helvetica; solo cambian colores y nombre.
- CIE-10: solo 136 códigos frecuentes; falta CSV oficial → `importar_cie10`.
- Adjuntos: servidos por vista con login, pero aún no como `authenticated` en Cloudinary (ADR-017).
- Cierre automático de consultas: solo cuando corre el cron diario.
- Récipe muy largo: si no cabe en una hoja, se parte en columnas (sin repetir encabezado).
- Offline: cada dispositivo debe abrir Ordo Salud con señal al menos una vez (y la sesión debe seguir abierta); sin red no se crean pacientes nuevos, ni cobros, documentos/PDF o adjuntos; las filas dinámicas (diagnósticos, récipe) de un borrador se recuperan solo si ya existían en la página.
- Sin módulos de especialidad reales (Pediatría/Ginecología): solo Medicina General + básicas.

- Suscripciones: sin aviso por correo antes de vencer (solo dentro de la app); sin descuentos ni prueba gratuita; el ingreso mensual estimado usa el precio de lista del plan.
- Railway con problemas (2026-10-21): se avanza en lo que no depende del despliegue.

- Pediatría: percentiles al guardar (sin vista previa en vivo); falta PDF «historia completa», PDF del reporte pediátrico, informe de referencia con antecedentes seleccionables y registro rápido con botones (guardar · historia · agendar); falta revisión de una pediatra real (13.10).
- Ginecología: sin gráfico de altura uterina; migración de consultorios de Ginea pendiente (Fase 18, ver incompatibilidades en `roadmap/14_ginecologia.md`).
- Corregido 2026-10-21: «Editar datos» del paciente daba error 500 (función que se llamaba a sí misma).
- Glosario: vacío al empezar (sin dosis precargadas, a propósito); en el récipe solo funciona con conexión.

## Preguntas abiertas
- [ ] Pediatra: ¿qué criterio nutricional ve primero (peso/edad como Pediae u OMS IMC/edad)? ¿cuál va en la constancia de niño sano?
- [ ] ¿Qué especialidad lleva el primer médico real a producción (13 ó 14)?
- [ ] ¿Migrar tenants de Ginea/Pediae (Fase 18)?
- [ ] Precio y planes (¿por profesional? ¿dictado como complemento?)
- [ ] Fuente oficial del CIE-10 en español
- [ ] Dominio: por definir (el correo de envío `no-responder@ordosalud.app` es provisional)

## Bloqueos
Ninguno.

## Notas
- Próxima sesión: empezar por la prueba offline en el teléfono (punto 4) y decidir especialidad (13 ó 14) o Railway staging.
- Proyectos de referencia en `C:\proyectos\{ordo,pediae,ginea-saas,biolife}` — **no se tocan** desde aquí.
- Tests en Postgres: `DATABASE_URL=postgres://… python manage.py test`.
