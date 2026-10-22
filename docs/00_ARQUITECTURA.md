# 00 — Arquitectura de Ordo Salud

> Decisiones estructurales. Cada una tiene su ADR en `DECISIONES.md`.
> Leer antes de empezar cualquier fase nueva.

## 1. Lo que se quiere resolver

Ginea y Pediae funcionan en producción, pero cada uno es **un sistema por especialidad**:
los campos de la especialidad viven como columnas fijas en `Paciente` y `Consulta`
(Pediae: ~140 columnas en `Paciente`; Ginea: antecedentes gineco-obstétricos en el mismo
modelo). Agregar Cardiología así significaría un tercer repositorio y un tercer conjunto de
arreglos duplicados (hoy ya se replican a mano los cambios entre Ginea y Pediae).

Ordo Salud separa **lo común** (paciente, agenda, consulta, récipe, cobro, reportes, PWA)
de **lo específico** (secciones clínicas, cálculos, documentos y reportes de cada
especialidad), para que una especialidad nueva sea un **módulo**, no un sistema.

## 2. Vista general

```
                    ┌───────────────────────── Plataforma (superusuario) ─────────────────────────┐
                    │ tenants · planes · suscripciones · tasa global · especialidades habilitadas │
                    └──────────────────────────────────────────────────────────────────────────────┘
 Tenant (consultorio / clínica)
 ├── Configuración: marca, lugares, visibilidad de la historia, módulos activos
 ├── Equipo: Membresías (titular, administrador, médico, asistente)
 │     └── Médico → PerfilProfesional (especialidad, MPPS/colegio, firma, sello)
 ├── Pacientes (ficha base común + antecedentes por sección)
 ├── Agenda (por profesional y lugar; vista individual o de toda la clínica)
 ├── Consultas ── usan una PlantillaHistoria ── compuesta de SeccionesClinicas
 │                                               ├── núcleo (signos vitales, examen físico, …)
 │                                               ├── de módulo (Pediatría, Ginecología, Cardiología…)
 │                                               └── personalizadas (las crea el médico)
 ├── Documentos PDF (récipe, informe, referencia, reposo, constancias de módulo)
 ├── Cobros (servicios en USD, tasa congelada, pagos en USD/Bs)
 └── Reportes (clínicos, agenda, financieros; por médico, especialidad y período)
```

## 3. Multi-tenancy (ADR-003, ADR-004)

**Esquema compartido** con FK `tenant` en cada tabla de negocio, con el patrón de Ordo:

- `apps/core/tenancy.py`: `ContextVar` con el tenant activo; `TenantModel` abstracto con
  `objects` (filtra por tenant activo, **vacío si no hay**) y `todos` (sin filtro).
- `TenantActivoMiddleware` fija `request.tenant` y `request.membresia` desde la sesión.
- Entrada por enlace propio `/<slug>/` → login con usuario único **por tenant**
  (`usuarios/backends.py` de Ordo). Subdominios (`dra-x.ordosalud.com.ve`) quedan para cuando
  exista el dominio; el diseño no cambia, solo cómo se resuelve el tenant.
- Un usuario puede pertenecer a **varios tenants** (médico que atiende en dos clínicas):
  la `Membresia` lleva el rol; el selector de tenant ya existe en Ordo.
- Superusuario = soporte: entra a cualquier tenant con membresía virtual (no se guarda) y
  queda registrado en la auditoría.

¿Por qué no `django-tenants` (esquemas) como Biolife? Los tenants aquí son pequeños
(1–15 usuarios) y muchos; un solo esquema mantiene migraciones de un paso, reportes de
plataforma simples y es lo que ya está probado en Ordo. El aislamiento se garantiza por el
manager que falla cerrado **más** tests de aislamiento obligatorios (Fase 02).

> Lección de Ginea/Pediae: sus FK `tenant` son `null=True` y el filtro se escribe a mano en
> cada vista. En Ordo Salud el FK es obligatorio y `editable=False`, y el filtro es automático.

## 4. Capas y módulos

```
apps/
├── core/            tenancy, middleware, permisos, FormBase, pdf base, secuencias, pwa, auditoría
├── plataforma/      Tenant, Plan, Suscripcion, panel /plataforma/
├── usuarios/        Usuario (login por tenant), Mi perfil, cambio de clave obligatorio
├── equipo/          Membresia, Rol, PerfilProfesional, Especialidad (catálogo)
├── configuracion/   ConfiguracionTenant, Lugar, identidad visual, membrete
├── tasas/           TasaCambio global (BCV) + TasaTenant (copiado de Ordo)
├── pacientes/       Paciente, Representante, antecedentes base, duplicados
├── agenda/          HorarioAtencion, Bloqueo, TipoCita, Cita, recordatorios
├── clinica/         ★ motor: SeccionClinica, PlantillaHistoria, Consulta, RegistroSeccion,
│                      SignosVitales, Diagnostico (CIE-10), Prescripcion, OrdenExamen,
│                      Adjunto, Enmienda, registro de especialidades
├── cobros/          Servicio, Cargo, Pago, estado de cuenta
├── documentos/      generadores PDF comunes + registro de documentos de módulos
├── reportes/        tableros y exportaciones (consultas JSONB + relacionales)
├── offline/         idempotencia + endpoints de precarga (portado de Pediae)
├── dictado/         (Fase 17) transcripción + estructuración por IA, opcional por plan
└── especialidades/
    ├── general/       Medicina general / interna (secciones básicas)
    ├── pediatria/     portado de Pediae
    ├── ginecologia/   portado de Ginea
    └── cardiologia/   nuevo (con la doctora cardióloga como referencia)
```

Reglas de dependencia:

- `core` no importa a nadie. Todos pueden importar `core`.
- `clinica` conoce `pacientes`, `equipo`, `agenda` (por service público), **nunca** a
  `especialidades/*`.
- Una especialidad importa `clinica` (para registrarse) y `pacientes`; nunca a otra especialidad.
- La comunicación entre apps de dominio va por `services.py` públicos o señales
  (`consulta_cerrada`, `cita_atendida`, `pago_registrado`).

## 5. ★ El motor de historia configurable (ADR-006, ADR-007)

Es la pieza central. Tres conceptos:

### 5.1 Sección clínica
Una unidad de historia con nombre, campos y lógica. Tres tipos:

| Tipo | Quién la define | Datos | Ejemplos |
|---|---|---|---|
| **Núcleo** | código de `clinica` | tablas propias | Signos vitales, Diagnósticos, Prescripción, Órdenes de exámenes |
| **De módulo** | código de una especialidad | JSONB validado por esquema **+ cálculos en Python**, o tablas propias si lo necesita | Antropometría con percentiles, Vacunas (Pediatría); Control prenatal con FPP (Ginecología); ECG (Cardiología) |
| **Personalizada** | el médico, desde la app | JSONB validado por el esquema que él armó | "Evaluación de pie diabético", "Escala de dolor" |

Cada sección tiene un **ámbito**:
- `CONSULTA` — se llena en cada visita (examen físico, control prenatal).
- `PACIENTE` — persiste entre visitas y se actualiza (antecedentes perinatales,
  gineco-obstétricos, vacunas). Se guarda con historial de versiones.

### 5.2 Esquema de campos
Las secciones de módulo y personalizadas declaran sus campos con un mismo formato JSON
(ver `01_MODELO_DATOS.md §6`). Tipos: texto corto, texto largo, número (unidad, rango,
decimales), fecha, sí/no, opción única, opción múltiple, lista de chequeo, escala, tabla
repetible y **calculado** (solo módulos). Cada campo admite `requerido`, `ayuda`,
`por_defecto` y `visible_si` (mostrar solo si otro campo cumple una condición).

Este mismo esquema sirve para: renderizar el formulario, validar en el servidor, imprimir
el PDF, armar reportes y **ser el contrato del dictado por voz** (la IA debe devolver JSON
que cumpla el esquema; ver §9).

### 5.3 Plantilla de historia
El médico compone su historia **eligiendo secciones del catálogo** (las del núcleo, las de
su especialidad, las de otras especialidades habilitadas y las personalizadas del tenant),
las ordena, marca cuáles son obligatorias o vienen colapsadas, y puede **ocultar o
renombrar campos** dentro de una sección. Puede tener varias plantillas (primera vez,
control, control prenatal, niño sano) y una predeterminada por tipo de cita.

Al abrir una consulta se **congela una copia** de la estructura de la plantilla
(`Consulta.estructura`), de modo que editar la plantilla después no altera consultas viejas
ni sus PDFs.

### 5.4 Por qué JSONB y no columnas ni EAV
- Columnas fijas (Ginea/Pediae): cada especialidad = migraciones y modelos nuevos; no permite
  que el médico arme nada.
- EAV (una fila por valor): consultas lentas y reportes dolorosos.
- **JSONB con esquema versionado**: flexible, se indexa (GIN), PostgreSQL consulta dentro del
  JSON para reportes, y la validación vive en un solo lugar. Los datos que necesitan
  relaciones o series (signos vitales, diagnósticos, vacunas aplicadas, prescripciones)
  siguen siendo **tablas** para poder graficar y contar.

## 6. Visibilidad de la historia (ADR-008)

Configurable por tenant en `ConfiguracionTenant.visibilidad_historia`:

| Valor | Ficha base y alergias | Consultas de otros médicos |
|---|---|---|
| `COMPARTIDA` (por defecto) | todos | todos los médicos las ven |
| `POR_ESPECIALIDAD` | todos | solo médicos de la misma especialidad |
| `PRIVADA` | todos | solo su autor (el titular puede abrir con motivo, queda auditado) |

Alergias, medicación actual y antecedentes críticos **siempre** son visibles para todo médico
del tenant: es un tema de seguridad del paciente. Asistentes ven ficha base, agenda y cobros,
no el contenido clínico (permiso `historia.ver`).

## 7. Agenda multi-profesional (ADR-013)

- `HorarioAtencion` por profesional + lugar + día de semana (bloques con duración de turno).
- `Bloqueo` (vacaciones, congreso) y `TipoCita` (duración, color, servicio y plantilla por defecto).
- `Cita` con profesional, especialidad, lugar, tipo; hora opcional para **tentativas**
  (como Pediae). Estados: tentativa, programada, confirmada, en sala, atendida, cancelada, no asistió.
- Validación de solapamiento por profesional en el service (`select_for_update`).
- Vistas: día/semana del médico; vista de **toda la clínica** (columnas por médico) para
  recepción; si el tenant tiene un solo médico, los selectores se ocultan.
- Recordatorio por WhatsApp (enlace `wa.me`, a representante si es menor — lógica de Pediae).
- "Atender" desde la cita abre la consulta con la plantilla del tipo de cita.

## 8. Tasa del dólar (ADR-011)

Se copia `apps/tasas` de Ordo sin cambios de lógica:
- `TasaCambio` global, actualizada por el **servicio cron de Railway** (`tareas_programadas`
  a diario, lectura de bcv.org.ve con el arreglo de certificado intermedio por AIA).
- `TasaTenant` para que un consultorio cargue la suya si el BCV falló; se usa la más reciente
  y, el mismo día, la del tenant.
- Indicador en la barra superior (amarillo si no es de hoy).
- Cada `Cargo` y `Pago` **guarda la tasa usada**; los reportes en Bs usan esa tasa, no la de hoy.

## 9. Dictado por voz (ADR-012, Fase 17)

Opcional por plan/tenant. Flujo:

1. En la consulta, el médico graba (MediaRecorder del navegador; funciona en iPhone instalada).
2. El audio sube a `dictado` → **transcripción** (proveedor intercambiable).
3. **Estructuración**: un LLM recibe la transcripción + los esquemas de las secciones de la
   plantilla y devuelve JSON que **debe validar** contra esos esquemas.
4. La app muestra lo propuesto resaltado; el médico **revisa y acepta**. Nada se guarda sin revisión.
5. Se registra uso (minutos, tokens) para cobrarlo como complemento.

Diseño: interfaz `ProveedorTranscripcion` / `ProveedorEstructuracion` en `dictado/proveedores/`
para cambiar de proveedor sin tocar el resto. Política de retención del audio configurable
(por defecto se borra tras transcribir). La elección de proveedor y su costo se evalúa al
iniciar la Fase 17 (opciones en la ficha de la fase).

## 10. PWA (ADR-014)

- Manifest + service worker de Ordo (`core/pwa.py`): `standalone`, iconos maskable,
  `apple-touch-icon`, aviso de instalación (Android) y guía para iPhone (Compartir → Añadir a inicio).
- **Visor de PDF** de Ordo (`/visor/`): resuelve el pendiente de Pediae de constancias que
  no abren en el móvil instalado.
- **Offline de consulta** portado de Pediae (`offline/` + `offline.js` + `sw.js`):
  borradores locales, cola de envíos con idempotencia, precarga de agenda de hoy/mañana y
  fichas citadas. Se mantiene "online-first" para todo lo demás.

## 11. Documentos y reportes

- `documentos/` aporta encabezado/pie por tenant (de `core/pdf.py` de Ordo) y los PDF comunes:
  récipe e indicaciones, informe médico, referencia, reposo, constancia de asistencia.
- Cada módulo registra los suyos (Pediatría: niño sano, lactancia; Ginecología: control prenatal).
- Firma y sello por profesional; membrete por tenant o por profesional.
- PDFs servidos por vista con login (no URL pública); abiertos en el visor en la PWA.
- `reportes/`: consultas por período/médico/especialidad, diagnósticos más frecuentes (CIE-10),
  pacientes nuevos vs. controles, agenda (asistencia, no asistió), ingresos USD/Bs, cuentas
  por cobrar. Cada módulo puede aportar reportes (p. ej. cobertura de vacunas). Export Excel y PDF.

## 12. Despliegue (ADR-002)

- Dockerfile + `railway.json` (preDeploy `migrate`, healthcheck `/salud/`) — copiado de Ordo.
- Servicio cron con `railway.cron.json` (`tareas_programadas`: tasa BCV, limpieza de
  idempotencia, recordatorios futuros).
- `staging` desde la Fase 01; `production` al cerrar la ruta crítica.
- Respaldos: los de Railway Pro + `pg_dump` semanal a almacenamiento externo (Fase 15).
- Región: elegir la de EE. UU. Este (latencia más baja desde Venezuela); no hay restricción de
  región para los usuarios — es una web pública.

## 13. Seguridad y cumplimiento

- Auditoría: quién abrió/creó/modificó qué historia (`core.Auditoria`).
- Consulta cerrada inmutable; enmiendas con motivo y autor.
- Contraseña temporal + cambio obligatorio (Ordo). 2FA para titulares en la Fase 19.
- Sesión con expiración por inactividad configurable; HTTPS y cookies seguras en producción.
- Sentry sin datos clínicos en los eventos (`send_default_pii=False`, filtro de campos).
