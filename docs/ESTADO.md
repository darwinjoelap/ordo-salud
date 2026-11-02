# ESTADO — Ordo Salud

> Se actualiza al **cerrar cada sesión** y es lo primero que se lee al abrir la siguiente.
> Menos de 100 líneas: el detalle de fases cerradas va a `HISTORIAL.md`; las decisiones, a `DECISIONES.md`.

**Última actualización:** 2026-11-01
**Fase actual:** 15 Cardiología pediátrica · **demo en producción** para la Dra. Lyna Sierra
**Repositorio:** `github.com/darwinjoelap/ordo-salud` (privado), rama `main` — código en `C:\proyectos\ordo-salud`
**Último commit:** dictado con catálogo y lista plana (ADR-054), 2026-11-01 · entorno: `venv\Scripts\Activate.ps1` (Python 3.14)
**Producción:** Railway proyecto `ordo-salud` (servicios `web` + `Postgres`) · `https://dra-sierra.salud.ordove.com` · respaldo `web-production-052d8.up.railway.app` · R2 `ordo-salud-media`

---

## Retomar aquí (2026-11-02)
En producción desde el 2026-11-01 (Railway + `*.salud.ordove.com` + R2 + Gemini prepago US$30, proyecto aparte).
Dictado: tras ADR-052/053/054 **funciona mucho mejor** (transcripción fiel y reparte los datos en los campos). Pendiente:
1. Confirmar que en Railway se corrió `sincronizar_especialidades` + `refrescar_plantillas cardiologia_pediatrica`
   (eco sin valores por defecto, ADR-053).
2. Afinar el dictado con más pruebas: eco completo dictado, signos vitales, diagnósticos; nota de voz del teléfono
   («Subir grabación»); revisar lo que quede en «No se pudo ubicar». Ver costo real en AI Studio → Gasto.
3. ~~Migrar `railway.json` a `.railway/railway.ts`~~ hecho 2026-11-02 (ADR-055). **Ordo Lab**: hacer lo mismo
   antes del 2026-12-01 (`railway config migrate --service <web>`, variables unmanaged, plan sin «destroy»).
4. Servicio `tareas` (ADR-056) declarado en `.railway/railway.ts`: aplicar, cargar sus variables, probar «Run now». Favicon da 404.
5. Con la doctora: comparar Z-score con ParameterZ (anillo pulmonar = PVSAX), revisión del informe, abreviaturas de
   ritmo. Luego pasarle el demo (`dra-sierra.salud.ordove.com`, usuario `lsierra`).
6. Antes de pacientes reales: `demo_cardiologia --consultorio dra-sierra --borrar`.
7. Negocio: definir precios (ver «Negocio»), con el costo real del dictado.

## Hecho el 2026-11-01
- Despliegue: proyecto Railway `ordo-salud`, R2 prod probado, carga inicial, demo, dominio `*.salud.ordove.com` y
  `salud.ordove.com` (DNS only), `BASE_DOMAIN`, admin en `admin.salud.ordove.com`.
- Gemini: clave en proyecto propio, facturación prepaga (saldo de la cuenta de facturación, compartible con otros
  sistemas; vence a los 12 meses; en cero se detienen todas las claves).
- ADR-052 Dictado en dos pasos (transcribir sin datos del paciente / ordenar el texto), detección de silencio
  (ffmpeg, < −45 dB no se envía ni se cobra), 90 s por intento + reintento. Motivo: con silencio inventó un caso.
- ADR-053 Eco y EKG sin valores por defecto + botón «Completar lo vacío como normal»; reglas para no comentar.
- ADR-054 Ordenar con catálogo y lista plana `{campo, valor}` (antes llenaba solo «Motivo»).

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

**Verificación:** 246 tests en verde en SQLite y PostgreSQL 16 (y en la PC de Darwin) · `ruff` limpio ·
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
