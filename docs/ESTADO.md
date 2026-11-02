# ESTADO — Ordo Salud

> Se actualiza al **cerrar cada sesión** y es lo primero que se lee al abrir la siguiente.
> Menos de 100 líneas: el detalle de fases cerradas va a `HISTORIAL.md`; las decisiones, a `DECISIONES.md`.

**Última actualización:** 2026-11-01
**Fase actual:** 15 Cardiología pediátrica · **demo en producción** para la Dra. Lyna Sierra
**Repositorio:** `github.com/darwinjoelap/ordo-salud` (privado), rama `main` — código en `C:\proyectos\ordo-salud`
**Último commit:** archivos en Cloudflare R2 (ADR-051), pusheado 2026-10-31 · entorno: `venv\Scripts\Activate.ps1` (Python 3.14)
**Producción:** Railway proyecto `ordo-salud` (servicios `web` + `Postgres`) · `https://dra-sierra.salud.ordove.com` · respaldo `web-production-052d8.up.railway.app` · R2 `ordo-salud-media`

---

## Retomar aquí (2026-11-02)
Desplegado el 2026-11-01: migraciones, `probar_almacenamiento` OK (R2 prod), especialidades, superusuario
`darwinjoelap`, `demo_cardiologia` (4 pacientes ficticios), banner/logo, plan con dictado, `*.salud.ordove.com`
(DNS only en Cloudflare, importado con archivo de zona). Pendiente:
1. Confirmar: clave de `lsierra` cambiada (se creó con la de ejemplo); `BASE_DOMAIN=salud.ordove.com` en Railway;
   segundo dominio `salud.ordove.com` (para redirigir `/dra-sierra/`); `admin.salud.ordove.com` entra a la plataforma.
2. `GEMINI_API_KEY` con facturación → prueba de dictado real (2–3 min + nota de voz del teléfono) y costo.
3. **Antes del 2026-12-01**: Railway deja de leer `railway.json`/`railway.cron.json` (Config as Code) →
   `railway config migrate` a `.railway/railway.ts` y revisar (igual en Ordo Lab).
4. Servicio cron (`railway.cron.json`: cierre de consultas, tasa BCV, recordatorios) — no creado aún.
5. Favicon (`/favicon.ico` da 404).
6. Con la doctora: comparar Z-score con ParameterZ, revisión del informe, abreviaturas de ritmo.
7. Antes de pacientes reales: `demo_cardiologia --consultorio dra-sierra --borrar`.

## Hecho en esta etapa (2026-10-22 → 10-31)
- ADR-045/046 Dictado de toda la consulta con IA (Gemini Flash), «Subir grabación» si se va la luz.
- ADR-047 Historia completa en una pantalla (expandir/contraer) · «no aplica» con histerectomía.
- ADR-048 SC por consultorio (Haycock en cardiología pediátrica) · **Z-score PHN/Lopez 2017** (lo que usa la doctora
  en ParameterZ), con «Z manual» que manda si lo escribe.
- ADR-049 **Subdominio por consultorio** (`<enlace>.salud.ordove.com`, `admin.` = plataforma), respaldo por ruta.
- ADR-050 **Excedente de dictado** (US$0.04/min por defecto, tope de seguridad, por cobrar del mes anterior).
- ADR-051 **Cloudflare R2 privado** reemplaza a Cloudinary: depósitos `ordo-salud-media` (prod) y `ordo-salud-dev`
  (PC), un token por depósito; adjuntos con nombre aleatorio y servidos por vista con permiso; logos/firmas con
  enlace firmado (1 h). Comando `probar_almacenamiento`. Los tests nunca tocan R2.
- `demo_cardiologia`: 4 pacientes **ficticios** marcados `[DEMO]` (`--borrar` los elimina).
- Guía `docs/DESPLIEGUE_RAILWAY.md` (fase A demo, fase B dominio).

## Completado antes (código + tests)
- [x] 01–12: esqueleto, tenancy, configuración, tasa BCV, pacientes, motor de secciones, consulta, agenda, cobros,
  documentos PDF, reportes, PWA offline.
- [~] 13 Pediatría y 14 Ginecobstetricia (faltan revisiones con especialistas reales).
- [x] 15 Cardiología pediátrica (informe en su formato, eco estructurado, EKG, notas de evolución, reporte).
- [x] Marca Ordo Salud, suscripciones y planes, perfil profesional, alcance de pacientes por rol, procedimientos.

**Verificación:** 237 tests en verde en SQLite y PostgreSQL 16 (y en la PC de Darwin) · `ruff` limpio ·
`probar_almacenamiento` OK contra R2 `ordo-salud-dev`.

## Negocio (para decidir)
- Competencia: **Umia Salud** (Caracas): Pro US$25/mes con 50 h de IA y 10 GB. Es viable para ellos porque la
  transcripción cuesta ≈ US$0.001–0.004/min (Flash-Lite, Whisper) y casi nadie usa el tope; además tienen directorio
  de pacientes (el software puede ser el gancho).
- Nuestro costo real de dictado es menor que el estimado antes: confirmar con la prueba real (tokens de Gemini).
- Propuesta en evaluación: Esencial US$20–25 · Especialidad + 30 h de dictado US$35–40 · extra US$0.02/min ·
  implementación US$100–200 · Dra. Lyna como fundadora ≈ US$30 por 6 meses. Diferenciar por especialidad
  (eco, Z-score, su informe), offline, BCV/bolívares y soporte local; no competir por horas de IA.
- Ideas pendientes: guardar tokens/costo por sesión de dictado; probar Gemini Flash-Lite en español médico.

## Incompleto / provisional (decir siempre)
- ADR 002–007 y 009–019 provisionales (ADR-020): revisar.
- CIE-10: solo 136 códigos frecuentes; falta CSV oficial.
- Dictado: no probado con clave real de Gemini.
- Al activar R2 en la PC, los logos/firmas subidos antes quedan en `media/` local (resubir si hacen falta).
- **Ginea y Pediae** guardan adjuntos **públicos** en Cloudinary con cédula y nombre en la ruta: su migración (Fase 18)
  debe copiar cada archivo directo a R2 y, verificada, borrar los públicos de allá.
- Cierre automático de consultas solo con el cron diario (segundo servicio en Railway, opcional en el demo).
- Offline: cada dispositivo debe abrir con señal al menos una vez; sin red no hay pacientes nuevos, cobros, PDF ni
  adjuntos. Al pasar al subdominio hay que reinstalar la app en el teléfono.
- Ginecología: falta revisión de la ginecóloga (histerectomía, citología) y gráfico de altura uterina.
- PDFs en Helvetica. Suscripciones sin aviso por correo antes de vencer.

## Preguntas abiertas
- [ ] Precios definitivos y planes (ver «Negocio»).
- [ ] Pediatra: criterio nutricional (peso/edad o IMC/edad OMS).
- [ ] Fuente oficial del CIE-10 en español.
- [ ] Correo de envío (provisional `no-responder@ordosalud.app`).

## Bloqueos
Ninguno.

## Notas
- Proyectos de referencia `C:\proyectos\{ordo,pediae,ginea-saas,biolife}`: **solo lectura**.
- El demo usa **solo pacientes ficticios** (los Word de la doctora tienen datos reales).
- Tests en Postgres: `DATABASE_URL=postgres://… python manage.py test`.
- Claves: `.env` de la PC solo con lo de `ordo-salud-dev`; lo de producción solo en Railway.
- Comandos en producción: `railway ssh` (CLI enlazado al servicio `web`). Cambiar clave de un usuario de consultorio:
  `Usuario.objects.get(username=…, tenant_cuenta__slug=…)` (no `changepassword`: el usuario se repite entre consultorios).
