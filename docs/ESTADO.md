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

## 2026-11-18 — Privacidad de contacto y PWA

**Contención e inventario f28 (local, publicación pendiente).** Durante esta fase las instrucciones de
cierre y limpieza de f27 que siguen son históricas. Conservar abiertos los perfiles afectados. Cerrar la
última conexión a IndexedDB puede completar un borrado ya solicitado. El worker nuevo sirve rutas
dinámicas solo por red y conserva las cachés anteriores para inventario. El aviso enumera nombres de
almacenes, sin leer formularios ni audios. Una cola o una base existente pueden estar vacías.

El POST de la cola con `X-Offline-Form: 1` recibe 403 antes de resolver la sesión o aceptar un recibo
de idempotencia. Los clientes históricos examinados conservan el elemento en error para revisión manual.
El formulario nativo con solo `_idem_key` también lo admite la idempotencia general. Mantener una pausa
operativa en las pestañas antiguas requiere aprobación antes de publicar. No usar sus botones de envío
ni enlaces WhatsApp. El comportamiento exacto de f25/f26 requiere ensayar los artefactos distribuidos.

**Corrección de transición f27 (local).** El worker elimina la caché de páginas anterior y conserva las
claves de borradores, la cola y la base de dictados. El aviso de la aplicación detecta indicios sin leer
el contenido de los dictados ni mostrar datos a otra sesión. La descripción de f26 que sigue es histórica.

**Control previo a publicar desde f25.** Coordinar una pausa de WhatsApp en pestañas antiguas e inventariar
perfiles, dispositivos, pestañas y ventanas instaladas. Con la sesión y el consultorio originales, terminar
los pendientes visibles y corroborar cada cambio en el registro correspondiente del servidor. Documentar
el resultado por dispositivo sin copiar datos clínicos en el registro de despliegue. Una redirección o un
timeout requieren conciliación manual antes de reintentar. Ante pendientes sin identificar, conservar el
perfil y detener la actualización de ese dispositivo. Evitar pasar por f26 o borrar datos del sitio.
Evitar cerrar sesión o cambiar de usuario en una pestaña antigua durante el rescate. Su código conserva
sus propias reglas de descarte y caducidad. Si f26 ya solicitó borrar IndexedDB, f27 no puede cancelar esa
solicitud ni restaurar datos eliminados.

Tras confirmar el trabajo, cerrar todas las ventanas y pestañas antiguas, incluidas las de la PWA. Reabrir,
comprobar el controlador f27 y probar con una autorización revocada que Agenda no abre ni copia el contacto.
Un enlace directo ya entregado a una pestaña que ejecuta código anterior sigue disponible allí. Reemplazar
el controlador de red no reemplaza el documento ni retira enlaces copiados fuera de Ordo.
En el ensayo sintético con dos pestañas, mantener una conexión antigua a IndexedDB abierta al activar
f27 y verificar que siga disponible. Inspeccionar Cache Storage después de cerrar sesión y entrar con
otra cuenta. Solo deben quedar recursos públicos de la aplicación y la agenda debe fallar sin conexión.

Cada apertura y copia en Agenda requiere un POST actual, con CSRF, alcance y destinatario revalidados. Las citas y
cumpleaños conservan su regla de contacto y respetan «No contactar». Inactividad exige autorización vigente para
el número del destinatario. En Android, «Preparar Business» habilita la acción y el segundo toque vuelve a validar.
Si el navegador bloquea el salto a Business, usa «Abrir con wa.me», que vuelve a pasar por el servidor. Ninguna
apertura confirma el envío. Los mensajes ya copiados y los enlaces guardados fuera de Ordo quedan bajo el control
del dispositivo o de WhatsApp.

SW `f26`. Las vistas y peticiones de la aplicación requieren red y usan `no-store`. Solo se almacenan recursos
públicos permitidos. Se limpia la caché anterior, la cola de formularios y el audio pendiente antiguo. El dictado
puede reintentarse mientras la pestaña siga abierta. Se conservan instalación y visor PDF. Para validar la
actualización en una PWA instalada, cierra las pestañas antiguas y comprueba que el nuevo SW controló la página
y eliminó `ordo-paginas-v1`, las claves `ofl:ordo-salud:` y la base `ordo-dictado`. Repite con logout y cambio
de usuario. Verifica Business y wa.me en Android, iOS y escritorio, así como los rechazos antes de abrir o copiar.

## 2026-11-18 — Correcciones de integridad antes de publicar

El bloqueo común se toma primero sobre el paciente. Los inicios y cobros por cita toman después la cita de origen
y luego las filas clínicas o financieras que necesiten. Las anulaciones toman paciente y atención. Los ganchos
de consulta que actualizan la ficha o programan un control conservan el bloqueo del paciente. El admin de citas
protege los vínculos clínicos y remite la eliminación a la agenda. Cuenta conserva FIFO entre cargos válidos. Los pagos aplicados requieren el flujo
autorizado en Cuenta antes de anular la atención. La anulación conserva los importes históricos.

El inicio desde una cita comprueba su consulta bajo bloqueo antes de crear. Un reintento abre la consulta existente.
Desde la ficha, «Nueva consulta independiente» conserva plantilla, tipo y lugar y omite la vinculación automática.
La relación única cita/consulta existente respalda el inicio. Estas correcciones no requieren migraciones.

## 2026-11-18 — Cobro rápido por cita · fase 4

Agenda muestra el saldo de los cargos enlazados por cita, consulta o procedimiento. Los cargos ambiguos y los saldos
de citas canceladas o con ausencia se revisan en Cuenta. El pago confirmado se aplica solo a esa cita, sin excedentes.
La conciliación general de Cuenta conserva el orden por antigüedad. Cobro rápido recalcula saldo y tasa bajo bloqueo,
registra el pago y cada aplicación, y reconoce reintentos con la misma confirmación. Migración: `cobros 0006`.

Verificación manual pendiente: abrir el modal desde tarjeta, fila sin hora y detalle, confirmar un abono en USD y otro
en Bs, comprobar la actualización del indicador y el asiento en Caja, y revisar el aviso tras cambiar saldo o tasa.

## 2026-11-18 — Servicios previstos al agendar · fase 3

Agenda conserva Tipo de cita y permite guardar uno o varios servicios compatibles con el profesional. El nombre
y precio USD se guardan con la selección. La consulta genera los cargos al iniciarse; un procedimiento presenta
la selección para confirmar qué se realizó. Cargos previos se revisan en Cobros. Las citas antiguas conservan el
predeterminado de Tipo de cita hasta guardar una selección explícita. Migración: `agenda 0007`.

Verificación manual pendiente: selección en móvil al cambiar profesional y tipo, precios históricos en detalle y
preselección de procedimientos, aviso por cargos previos y reenvío de un formulario desactualizado.

## 2026-11-18 — Recordatorios sugeridos · fase 2

La agenda de hoy propone seguimiento por episodio desde la última consulta cerrada o procedimiento no anulado. Una cita
vinculada debe estar atendida. Las próximas citas activas suspenden la sugerencia. El plazo sigue en Configuración →
Agenda (12 meses por defecto, 0 desactiva). El descarte y el envío declarado cierran el episodio, incluso si se cambia
el plazo. Un intento pendiente se puede revisar y resolver. En ficha se registra el permiso de WhatsApp por número
del adulto o del representante principal. Ordo abre un borrador manual y registra eventos sin guardar su mensaje.
Migraciones nuevas: `pacientes 0005` y `agenda 0006`. Se reutiliza `configuracion 0011`.

## 2026-11-18 — WhatsApp de agenda · fase 1

Android intenta abrir Business al tocar la acción en agenda y ofrece un enlace alternativo a `wa.me`. iOS y
escritorio usan `wa.me` y el sistema decide cómo abrirlo. Las acciones incluyen «Copiar mensaje». La marca de cita
registra un intento en línea y la asistencia se sigue confirmando desde agenda. SW `f25`.

Verificación manual pendiente con datos sintéticos y sin enviar mensajes:
- Android en Chrome y en navegador integrado, con las dos apps, solo Business, solo personal y ninguna. Probar la
  acción principal, la alternativa explícita y la copia, y comprobar el teléfono y los caracteres del borrador.
- PWA instalada en Android. Actualizar desde la versión anterior, repetir las pruebas y volver a agenda para
  comprobar la marca del intento. Con el registro sin conexión, comprobar el aviso de fallo.
- iOS en Safari y PWA, y escritorio con y sin sesión de WhatsApp Web. Verificar el destino de `wa.me` y que el
  contenido se pueda copiar, incluida la copia manual si se deniega acceso al portapapeles.
- Repetir desde detalle y agenda diaria, cumpleaños y el aviso existente sin consulta. Salir del borrador sin
  enviarlo y verificar que la cita conserve su estado y que Compartir acceso de Plataforma use su enlace habitual.

## 2026-11-16 — WhatsApp Business primero · pacientes sin consulta · eliminar citas no atendidas
El ajuste inicial intentaba abrir WhatsApp Business en Android, con alternativa `wa.me`. Agenda del día: «Hace N
meses sin consulta» (Configuración → Agenda, 12 por defecto, 0 = apagado). Citas sin consulta/cobro/procedimiento se
pueden eliminar (queda en auditoría). Migración `configuracion 0011`. SW `f24`. Comando `citas_sin_consulta`.

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
