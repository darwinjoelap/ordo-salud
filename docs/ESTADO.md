# ESTADO — Ordo Salud

> Se actualiza al **cerrar cada sesión** y es lo primero que se lee al abrir la siguiente.
> Menos de 100 líneas: el detalle de fases cerradas va a `HISTORIAL.md`; las decisiones, a `DECISIONES.md`.

**Última actualización:** 2026-11-01
**Fase actual:** 15 Cardiología pediátrica · **demo en producción** para la Dra. Lyna Sierra
**Repositorio:** `github.com/darwinjoelap/ordo-salud` (privado), rama `main` — código en `C:\proyectos\ordo-salud`
**Último commit:** `fae3dee` servicio de tareas en Railway IaC (ADR-056), 2026-11-02 · entorno: `venv\Scripts\Activate.ps1` (Python 3.14)
**Producción:** Railway proyecto `ordo-salud` (servicios `web` + `Postgres`) · `https://dra-sierra.salud.ordove.com` · respaldo `web-production-052d8.up.railway.app` · R2 `ordo-salud-media`

---

## Consultorio de pruebas (`consultorio_pruebas`)
Unidad `pruebas.salud.ordove.com` con pacientes ficticios [DEMO]; se le agrega un médico por especialidad
(`--medico <codigo> --usuario … --clave …`). Paquete de escenarios: **pediatría** (13 casos: curvas, desnutrición,
obesidad, alergia + IA, asma + procedimiento, RN prematuro, adolescente, gemelas, cobros parciales/exonerado, agenda
hoy/mañana/no asistió, datos incompletos, borradores). Pendiente detectado: **edad corregida en prematuros** (hoy
percentiles por edad cronológica). Próximos paquetes: ginecología, cardiología pediátrica, medicina general.

## 2026-11-11 tarde — ADR-066 antecedentes personales de ginecología
Tras desplegar: `sincronizar_especialidades` y `refrescar_plantillas ginecologia` (Railway). Migración `pacientes 0004`.

## 2026-11-11 — ADR-065 observación importante · récipe con peso/talla · consultas sin cerrar en inicio
Migraciones `clinica 0010` y `configuracion 0010`. SW `f23`. Sugerencias IA sin esquema forzado (bucle de ceros).

## 2026-11-09 noche — ADR-064 agenda por médico
Con «Los médicos pueden ver todos los pacientes y todas las agendas» apagada (por defecto), cada médico ve solo su
agenda. Migración `configuracion 0009` (solo cambia el texto de la opción).

## 2026-11-09 noche — «Completar y sugerir con IA» (ADR-060, ampliación)
El botón completa las filas del récipe que la doctora escribió solo con el nombre (con el glosario si coincide, sin IA
ni costo; si no, la IA da la ficha y el sistema calcula), no repite lo ya indicado y lo nuevo va aparte («También
podrías agregar», sin marcar). Nombre escrito que está en el glosario → enlace «Calcular con glosario» en esa fila.
308 tests OK (SQLite y Postgres). SW `f22`.

## 2026-11-09 — ADR-060 sugerir indicaciones con IA · ADR-061 dictado por especialidad
Fix 500 (código CIE largo) y medicamentos de solo-indicaciones en el récipe. Sugerencias IA: activar por consultorio
en la plataforma (empezar con la Dra. Anais). 282 tests OK (SQLite y Postgres) + prueba en navegador.
**Desde 2027 Gemini cuesta el doble:** cambiar `IA_PRECIO_ENTRADA=1.50` y `IA_PRECIO_SALIDA=7.50` en Railway y revisar precios.

## 2026-11-08 tarde — ADR-057/058/059 (código listo, falta push)
Soporte con control total (ve y edita historias; no crea consultas ni firma documentos) · plantilla editable del
recordatorio de WhatsApp · tasa euro BCV y elección USD/EUR por consultorio. 265 tests OK (SQLite y Postgres).
Tras desplegar: Plataforma → Tasa BCV → «Consultar BCV» para que la de hoy traiga el euro.

## Retomar aquí (2026-11-08) — Migraciones hechas (Fase 18)
**Ginea → Ordo Salud en producción** (`dra-pereira`, `sinergia-femenina`; `importar_ginea`, todo cuadra). Pendiente:
plan con 2 profesionales para Sinergia, avisos a usuarios, quitar proxy TCP de Ginea y de Pediae, en 2–4 semanas
apagar Pediae/Ginea y borrar Cloudinary. Detalle: `docs/roadmap/18_migracion_pediae.md` §7.

### Pediae (Fase 18a)
**Importada a producción el 2026-11-08** (`importar_pediae`, todo cuadra). Antes: ensayado con el respaldo real (conteos y montos cuadran; ver
`docs/roadmap/18_migracion_pediae.md` §4). Nombres aprobados; Dylan Zheng se une (`--unir 49=109`). Falta: día del cambio (§5, en
Railway por `railway ssh`) → aviso a la Dra. Báez (`dra-anaisbaez.salud.ordove.com`, misma clave).

## Antes (2026-11-02)
En producción desde el 2026-11-01 (Railway + `*.salud.ordove.com` + R2 + Gemini prepago US$30, proyecto aparte).
Dictado: tras ADR-052/053/054 **funciona mucho mejor** (transcripción fiel y reparte los datos en los campos). Pendiente:
1. Confirmar que en Railway se corrió `sincronizar_especialidades` + `refrescar_plantillas cardiologia_pediatrica`
   (eco sin valores por defecto, ADR-053).
2. Dictado probado OK también con eco y con archivo adjunto (2026-11-02). Ajustes finos: **después de que la
   doctora lo pruebe**. Ver costo real en AI Studio → Gasto.
3. ~~Migrar `railway.json` a `.railway/railway.ts`~~ hecho 2026-11-02 (ADR-055). **Ordo Lab**: hacer lo mismo
   antes del 2026-12-01 (`railway config migrate --service <web>`, variables unmanaged, plan sin «destroy»).
4. ~~Servicio `tareas`~~ hecho 2026-11-02 (ADR-056): primera corrida OK (tasa BCV 889,5754, 1 consulta cerrada).
   Revisar mañana que corrió solo a las 07:00. Favicon da 404.
5. Con la doctora: comparar Z-score con ParameterZ (anillo pulmonar = PVSAX), revisión del informe, abreviaturas de
   ritmo. Luego pasarle el demo (`dra-sierra.salud.ordove.com`, usuario `lsierra`).
6. Antes de pacientes reales: `demo_cardiologia --consultorio dra-sierra --borrar`.
7. Negocio: definir precios (ver «Negocio»), con el costo real del dictado.

## Hecho el 2026-11-01
- Despliegue: proyecto Railway `ordo-salud`, R2 prod probado, carga inicial, demo, dominio `*.salud.ordove.com`
  (DNS only; `salud.ordove.com` sin asterisco no se agregó: opcional, se declara en `.railway/railway.ts`), `BASE_DOMAIN`, admin en `admin.salud.ordove.com`.
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
