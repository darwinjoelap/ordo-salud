# Fase 18a — Migración de Pediae a Ordo Salud

> Fuente: respaldo de producción `pediae_2026-11-08.dump` (PostgreSQL 18, convertido a SQL) y el inventario de Cloudinary
> (`cloudinary_inventario.csv`). Código de Pediae en `C:\proyectos\pediae` (solo lectura; misma versión que producción:
> última migración `consultas.0023`). Pediae **no se toca**: se lee una copia y sigue funcionando hasta el día del cambio.

## 1. Inventario (2026-11-08)
| Consultorio (slug) | Pacientes | Consultas | Citas | Usuarios | Consultas desde → hasta |
|---|---|---|---|---|---|
| `dra-anaisbaez` | 145 | 169 | 166 | 1 | 2026-08-22 → 2026-11-07 |
| `pediae` | 23 | 154 | 67 | 1 | 2025-08-25 → 2026-09-13 |
| `dra-vicky` | 0 | 0 | 0 | 1 | — |

Otros: 23 adjuntos (imagen/PDF), 106 vacunas aplicadas (35 vacunas por consultorio), 30 pesquisas realizadas,
16 medicamentos con dosificación, 9 procedimientos, 10 servicios, 183 servicios cobrados en consultas, 3 lugares de
consulta, 1 superusuario de plataforma. Tipos de consulta: control sano 309 · enfermedad 13 · seguimiento 1.
Citas: atendida 178 · programada 29 · tentativa 11 · confirmada 9 · no asistió 6. Consultas pagadas: 240 de 323.

**Cloudinary** (cuenta compartida con Ginea, plan Free, 1,2/25 créditos): de Pediae son los 23 adjuntos + 7 imágenes de
perfil (firma, sello, banner, logo, membrete) = **28,5 MB, todos presentes**. En `ginea/` quedan 160 archivos que no usa
Pediae (de Ginea). `samples/`, `cld-sample*` y los 4 videos son de ejemplo de Cloudinary (no se migran).

## 2. Mapeo Pediae → Ordo Salud
Ordo Salud Pediatría se portó de Pediae (ADR-036/043), así que casi todo tiene campo propio.

| Pediae | Ordo Salud |
|---|---|
| `tenant_tenant` (+ plan, suscripción) | `plataforma.Tenant` + especialidad Pediatría + plan (se asigna a mano) |
| `configuracion_configconsultorio` | `ConfiguracionTenant` (nombre, dirección, teléfono, WhatsApp, color, horario, duración de cita); logo y membrete → R2 |
| `accounts_usuario` (con tenant) | `Usuario` del consultorio + `Membresia` (titular) + `PerfilProfesional` (MPPS, credenciales, especialidad; firma/sello/banner → R2). **Contraseña: se copia el hash** (entran con la misma clave) |
| `pacientes_paciente`: nombre_completo | `nombres` + `apellidos` desde `pediae_nombres.csv` revisado (decisión 6) |
| cédula / no_cedulado | tipo + número (V-12345678 → V / 12345678) |
| representante, padre, madre | `Representante` (principal = representante; madre/padre como adicionales si hay nombre) |
| alergias, crónicas, cirugías, medicación, antec_* | `nucleo.antecedentes` y `ped.familiares` (ficha) |
| perinatales (edad materna, gestación, vía de parto, PAN/TAN, neonatales…) | `ped.perinatales` (ficha) |
| alimentación (LME, fórmula, actual) | `ped.alimentacion` (ficha) |
| desarrollo, esfínteres | `ped.desarrollo_hitos` (ficha) |
| entorno (padres, sueño, mascotas, agua, tabaquismo) | `ped.entorno` (ficha) · traumatismos/exantemáticas → `ped.patologicos` |
| `consultas_consulta`: tipo_consulta | `ped.tipo` |
| motivo_consulta / sintomas_actuales | `nucleo.motivo` (motivo / enfermedad actual) |
| peso, talla, PC, FC, FR, T°, SpO₂, TA «100/60» | `ped.antropometria` + `nucleo.signos_vitales` (TA se separa en sistólica/diastólica) |
| percentiles y clasificación nutricional | se **recalculan** con las tablas OMS de Ordo Salud (ver decisión 3) |
| examen_fisico (un texto) | `nucleo.examen_fisico.general` |
| diagnostico (texto libre) | `nucleo.diagnosticos`: una fila con la descripción, sin código CIE |
| tratamiento / indicaciones | `nucleo.plan` (indicaciones) — el tratamiento como texto, no como récipe estructurado |
| laboratorio | `nucleo.ordenes.laboratorio` (la plantilla pediátrica usa «Órdenes») |
| observaciones / proxima_cita | `nucleo.plan` (plan / próximo control) |
| hábitos (apetito, comidas, sueño, siestas, deposiciones…) | `ped.habitos` |
| desarrollo_psicomotor | `ped.desarrollo` |
| `consultas_adjuntoconsulta` | `Adjunto` (archivo copiado de Cloudinary a R2, nombre aleatorio; nombre original se conserva) |
| `consultas_consultaservicio` / `pagado` / `notas_pago` | cobros (ver decisión 2) |
| `consultas_procedimiento` (+ servicios) | procedimientos sin consulta (ADR-040) |
| `consultas_medicamento` (dosificación por kg, rangos de edad) | glosario de medicamentos (ADR-037, calculadora de dosis) |
| `pacientes_vacuna` / `vacunaaplicada` | catálogo de vacunas de Ordo Salud (se empareja por nombre; las que no estén, como vacuna propia del consultorio) |
| `pacientes_pesquisa` / `pesquisarealizada` | pesquisas de Ordo Salud (mismo criterio) |
| `agenda_lugarconsulta` / `agenda_cita` | `Lugar` / `Cita` (estados: atendida, programada, tentativa, confirmada, no asistió) |
| `servicios_servicio` | servicios con precio USD · `tasacambio` no (la tasa viene del BCV) |
| sesiones, admin log, envíos offline | no se migran |

## 3. Decisiones (Darwin, 2026-11-08)
1. **Consultorios:** solo `dra-anaisbaez`. `pediae` y `dra-vicky` no se migran.
2. **Cobros históricos:** como cargos + pagos, con la tasa guardada, exoneraciones y descuentos de cada servicio.
   Consulta pagada = un pago (USD, método «Otro») en la fecha de la consulta por el saldo de sus cargos.
3. **Percentiles:** se recalculan con las tablas OMS de Ordo Salud (el gancho de Antropometría guarda la medición).
4. **Enlace:** `dra-anaisbaez.salud.ordove.com` (mismo slug). Misma contraseña (se copia el hash `pbkdf2_sha256`).
5. **Fecha del cambio:** 2026-11-08.
6. **Nombres:** Pediae guardaba todo en `nombre_completo`. Se parten con `pediae_nombres.csv` (propuesta automática
   con los apellidos de padre/madre/representante; Darwin revisa las filas `REVISAR`/`probable` antes de importar).
   Posibles duplicados (4): se importan **separados**; se unen a mano después si corresponde.

## 4. Comando `importar_pediae`
`apps/especialidades/pediatria/management/commands/importar_pediae.py`. Lee Pediae **solo con SELECT** (conexión en
modo lectura) y escribe todo en **una transacción**: si falla algo, no queda nada. Si el consultorio ya existe en Ordo
Salud, se niega (no se migra dos veces). `--ensayo` hace todo y lo deshace; `--sin-archivos` omite Cloudinary.
- Valores fuera de los rangos de Ordo Salud no se cargan en el campo: salen en los avisos y, en consultas, quedan
  escritos en el plan («Dato de Pediae fuera de rango (no cargado): …»).
- «Próximo control» no crea citas durante la importación (las citas vienen de Pediae).
- Consultas: cerradas, con su fecha; la cita de Pediae queda enlazada y «atendida». Primera = primera consulta del paciente.
- Archivos: adjuntos e imágenes de perfil se descargan de Cloudinary (públicos, basta `--nube <cuenta>`) y se suben a R2.
- Los avisos muestran solo n.º de Pediae y fecha (sin nombres): se pueden compartir.

**Ensayo 2026-11-08** (respaldo real → base local vacía, sin archivos), 23 s, ~9.000 escrituras:
pacientes 145/145 · citas 166/166 (enlazadas 140) · consultas 169/169 · vacunas 104/104 · pesquisas 29/29 ·
procedimientos 6/6 · glosario 13/13 · servicios 9/9 · lugares 1/1 · representantes 108 · cargos 180
(US$8.370 = 7.665 consultas + 705 procedimientos; descuentos 40; 4 exonerados; todos con tasa) · pagos 141
(US$7.730) · mediciones OMS 163 (6 consultas sin antropometría). 6 avisos: semanas de gestación «2», edad de la madre
«6», talla «7205», temperatura «98» (°F) y «24», PC «0».

## 5. Día del cambio (en Railway, por `railway ssh`: ~9.000 escrituras por internet serían ~30 min)
1. `git push` (el comando va con el código) y esperar el despliegue.
2. Avisar a la doctora que **deje de usar Pediae** (si tiene borradores sin conexión, que sincronice antes).
3. Respaldo final de Pediae (`pg_dump`, como el del 2026-11-08) en `C:\proyectos\respaldos`.
4. `railway ssh` (servicio `web`) → pegar el CSV revisado en `/tmp/nombres.csv` → `--ensayo` → si cuadra, sin `--ensayo`.
5. Verificar: entrar a `dra-anaisbaez.salud.ordove.com` con su clave, abrir 5–10 historias, curvas, cobros, adjuntos.
6. Plataforma (`admin.`): asignar plan/suscripción; dictado si aplica.
7. Aviso a la doctora: enlace nuevo, misma clave, desinstalar la app vieja e instalar la nueva.
8. Quitar el proxy TCP (enlace público) de la base de Pediae.

## 6. Plan
- [x] 18.1 Respaldo, inventario de base y de Cloudinary, mapeo
- [x] 18.2 Decisiones
- [x] 18.3 Comando `importar_pediae` + tests de conversiones (`tests/test_importar_pediae.py`)
- [x] 18.4 Ensayo en local con el respaldo real (conteos y montos cuadran) · [ ] Darwin revisa nombres (CSV)
- [ ] 18.5 Día del cambio (sección 5)
- [ ] 18.6 A las 2–4 semanas sin problemas: apagar Pediae y borrar sus archivos de Cloudinary (y el respaldo local)

> Datos reales: el respaldo vive en `C:\proyectos\respaldos` (fuera de los repos) y en el entorno de trabajo de Claude
> solo mientras dura la migración.
