# Fase 13 — Módulo Pediatría

**Modelo sugerido:** Opus (percentiles, dosis y migración de datos tocan seguridad del paciente)
**Depende de:** Fase 12 (cerrada)
**ADR relacionados:** ADR-007 (secciones), ADR-009 (antecedentes de ámbito PACIENTE), ADR-014, ADR-022/024, nuevos ADR-034…
**Se apoya en:** `C:\proyectos\pediae\` (solo lectura) — `pacientes/models.py`, `consultas/models.py`,
`consultas/oms.py`, `pacientes/oms_data.py`, `pacientes/views.py`, `consultas/views.py`, `agenda/views.py`,
`agenda/models.py`, `reportes/views.py`, `pacientes/*_pdf.py`, `consultas/recipe_pdf.py`,
migraciones `pacientes/0017` (esquema de vacunas) y `0018` (pesquisas)

## Objetivo
Una pediatra que hoy usa Pediae puede trabajar en Ordo Salud sin perder nada de lo que usa a diario: ficha pediátrica,
antropometría con percentiles y curvas OMS, vacunas, pesquisas, calculadora de dosis, constancias y reportes
pediátricos; y con los ajustes que se hicieron sobre la marcha en Pediae.

## Fuera de alcance
- Migrar los datos de los consultorios que hoy están en Pediae → Fase 18 (el diseño de esta fase debe permitirla).
- Ginecología → Fase 14. Dictado → Fase 17.

---

## 1. Inventario de Pediae (revisado archivo por archivo, 2026-10-21)

### 1.1 Ficha del paciente (`Paciente`, `PacienteCompletoForm`)
| Bloque | Campos | Notas |
|---|---|---|
| Identificación | nombre, sexo (**opcional**), no cedulado, cédula (**opcional**), fecha de nacimiento, teléfono, correo, dirección, seguro, contacto de emergencia, grupo sanguíneo | Solo el nombre es obligatorio |
| Representante | filiación (madre/padre/otro), parentesco si otro, nombre, cédula `V-12345678-1`, teléfono, ocupación | Elegir filiación copia el nombre en madre/padre |
| Padres | nombre, edad y ocupación de padre y madre | |
| 2. Perinatales | edad materna, n.º de gestación, control prenatal (sí/no) y n.º de consultas, complicaciones (oligoamnios, preeclampsia, infecciones, otra), semanas al nacer, vía de parto (+ indicación de cesárea), peso (g) y talla al nacer, complicaciones neonatales (ictericia, sepsis, dificultad respiratoria, otra), onfalorrexis, prueba del talón (+ detalle), notas libres de embarazo/parto/neonatal | Peso/talla al nacer = primer punto de las curvas |
| 3. Alimentación | LME (sí/no, hasta n meses), fórmula (sí/no, nombre, causa), alimentación actual (completa/selectiva + detalle), notas | |
| 4. Desarrollo | neuromotor acorde (sí/no, área afectada), esfínter vesical y anal (logrado, edad), notas | |
| 6. Patológicos | cirugías/hospitalizaciones, alergias, traumatismos (+detalle), exantemáticas (+detalle), crónicas, medicación actual | |
| 7. Familiares | diabetes, HTA, cardiopatías, epilepsia, asma/atopía, oncológico (+rama), autoinmunes, genéticas, otros | **Se cuentan en reportes** |
| 8. Hábitos y entorno | sueño, evacuación, micción, tabaquismo pasivo, agua de consumo, mascotas (+tipo) | |
- La asistente registra con un formulario corto (nombre, sexo, cédula/representante, nacimiento, teléfono).
  La médica al registrar elige: solo guardar · abrir historia · agendar cita.
- Edad mostrada: `5 años` / `3 años y 2 meses (38 m)` / `1 año y 4 meses (16 m)` / `7 meses y 12 días` / `9 días`.

### 1.2 Consulta (`Consulta`)
- Tipo: **control sano / enfermedad / seguimiento**.
- Antropometría: peso, talla, **perímetro cefálico** → percentil peso/edad, talla/edad, PC/edad (PC hasta 36 m)
  y **clasificación nutricional** por percentil de peso: <p3 desnutrición severa · p3–10 desnutrición ·
  p10–15 riesgo · p15–85 eutrófico · p85–97 sobrepeso · >p97 obesidad.
- Signos vitales: FC, FR, T°, SatO₂, TA (texto).
- Clínica: motivo, enfermedad actual, examen físico, desarrollo psicomotor, diagnóstico, tratamiento, indicaciones,
  paraclínicos, observaciones.
- Hábitos de la consulta: alimentación (tipo, apetito, n.º comidas, notas), sueño (horas, siestas, duración, notas),
  eliminación (frecuencia y consistencia de deposiciones, control de esfínteres, notas).
- **Próxima cita** (fecha) → al guardar crea una cita **TENTATIVA sin hora** con motivo «Control – diagnóstico» y el
  mismo lugar. *(ajuste sobre la marcha)*
- Si la cita ya tenía consulta: GET lleva a esa consulta; POST guarda aparte sin perder lo escrito. *(ajuste)*
- Servicios de la consulta con exonerado y descuento por línea; procedimientos (servicios sin consulta).

### 1.3 Glosario de medicamentos con calculadora (`Medicamento`)
- Por médico/consultorio. Modo **por peso** (mg/kg, mcg/kg, UI/kg con concentración → mL/tabletas/gotas; o
  unidades directas mL/kg, gotas/kg…), **dosis fija** (puffs, sobres) o **por rango de edad** (3 rangos).
- Rango mín/máx por kg con nivel mínimo/estándar(punto medio)/máximo; tope absoluto por dosis; redondeo
  (tabletas a ½, mL a 0,1); alertas de edad mínima/máxima y peso mínimo.
- Plantilla de indicaciones con variables `{{DOSIS}} {{DOSIS_MG}} {{FRECUENCIA}} {{DURACION}} {{PRESENTACION}}
  {{NOMBRE}} {{PESO}}`; en la consulta se elige el medicamento y se inserta el texto ya calculado.

### 1.4 Curvas de crecimiento
- Peso/edad, talla/edad, PC/edad, 0–60 meses, P3-P15-P50-P85-P97 (Chart.js), punto de nacimiento, clic en un
  punto abre la consulta; **PDF de la curva** con membrete.

### 1.5 Vacunas y pesquisas
- Catálogo global (esquema de `0017`: RN, 2/4/6/7/9/12/18 m, 4–6 años, adolescentes, **anual**) + vacunas propias
  del consultorio. Estado por dosis: aplicada · pendiente · atrasada (pasó la edad máxima) · futura.
- Registrar con fecha (opcional), lote y observación; **marcar con un toque** sin fecha; vacuna anual admite varias
  aplicaciones; resumen en la ficha (atrasadas y próximas 3); **PDF del esquema**.
- Pesquisas: eco de cadera, eco renal/abdominal, oftalmológica, audiología (+ propias); fecha y resultado.

### 1.6 Documentos PDF
Constancia de **niño sano** (datos antropométricos, examen, diagnóstico nutricional, inmunizaciones al día o con
pendientes), **reposo**, **certificado de lactancia** (n meses), **constancia de lactancia para el trabajo**
(nombre y cédula de la madre), **informe de referencia** (especialidad, motivo, antecedentes elegidos, última
antropometría), **historia completa**, **esquema de vacunas**, **curvas**, **récipe**; todos con switch «incluir
firma y sello», ciudad y fecha en letras.

### 1.7 Agenda y WhatsApp (ajustes sobre la marcha)
- Cita sin hora = **tentativa**; la agenda del día muestra: con hora · **sin hora asignada** · atendidos sin cita.
- Al agendar: panel de horarios del día (ocupados/libres, sin horas pasadas si es hoy) y aviso de choque.
- Recordatorio por WhatsApp: si hay representante, **saluda al representante** y habla «de la cita de
  {niño}»; al teléfono del representante; hora en 12 h («2:30 pm»); sin hora → no dice hora.
  **Primero el texto automático, después el mensaje adicional del consultorio.**
- **Cumpleaños del día** en la agenda con botón «Felicitar» por WhatsApp al representante: «¡Hola {representante}!
  El equipo de {consultorio} le desea a {niño} un muy feliz cumpleaños, hoy cumple N años…».

### 1.8 Reportes de Pediae
Atenciones con/sin cita y asistencia, consultas por tipo, ingresos cobrados/pendientes/costo/real, servicios top,
por mes (citas, consultas, pacientes nuevos, ingresos), **grupos de edad pediátricos** (0–1, 1–3, 3–6, 6–10,
10–15, 15+), sexo, **estado nutricional**, **antecedentes familiares**, **citas por día de la semana**; PDF;
pagos pendientes.

---

## 2. Lo que Ordo Salud ya tiene (no se rehace)
- [x] Cita sin hora = TENTATIVA; turnos libres al agendar; aviso fuera de horario (Fase 08).
- [x] WhatsApp al representante del menor con saludo a él, hora en 12 h, sin hora si es tentativa, texto
      automático primero y mensaje del consultorio después (verificado en `agenda/servicios.url_whatsapp`).
- [x] Cédula opcional, menor sin documento con representante, hermanos sin documento, aviso de duplicado con enlace.
- [x] Consulta con hora real de apertura (también sin conexión), cita ya atendida → lleva a su consulta.
- [x] Exonerado y descuento por cargo; cargos sin consulta (equivalen a «procedimientos»); por cobrar.
- [x] Récipe 2 columnas, reposo, constancia, informe, referencia con firma/sello y marca de agua (Fases 10–11).
- [x] Reportes base (actividad, asistencia, morbilidad, edad/sexo, ingresos, por profesional) — Fase 11.

## 3. Hallazgos en Pediae que **no** se copian tal cual
1. **Percentiles inexactos.** `consultas/oms.py` usa una tabla LMS reducida con L constante para el peso
   (−0,3521) y S desactualizado para talla > 24 m. Comparado con las tablas oficiales OMS:
   niño de 24 m y 10,0 kg → Pediae **P1,6 (desnutrición severa)**, OMS **P4,4 (desnutrición)**;
   la talla a los 48 m usa S = 0,029 cuando el oficial es 0,040 (percentiles demasiado extremos).
   → Ordo Salud usa las **tablas LMS oficiales OMS completas, mes a mes** (0–60 m) incluidas en el código.
2. Edad en meses para las curvas con `días / 30,44` y en percentiles con `relativedelta`: se unifica (meses
   cumplidos exactos; para < 3 meses la OMS da tablas por día — se evalúa).
3. Constancia de niño sano con «Normopeso (Eutrófico)» **fijo** aunque el niño no lo esté → se toma de la
   clasificación real de la última consulta (y la médica puede corregirlo antes de emitir).
4. Historia PDF falla si una vacuna no tiene fecha (`va.fecha.strftime`). `print` de depuración en
   `editar_medicamento`. → No se trasladan.
5. Peso al nacer en gramos y peso de consulta en kg: se guarda cada uno con su unidad explícita.

## 4. Diseño propuesto (respeta `05_GUIA_ESPECIALIDADES.md`: no se parchea el núcleo)

### 4.1 Núcleo (sirve a todas las especialidades) — ajustes previos
- [x] **Próximo control → cita TENTATIVA sin hora** al guardar/cerrar la consulta (campo `proximo_control` ya
      existe en «Plan»): mismo profesional y lugar, motivo «Control – {diagnóstico principal}», sin duplicar si ya
      hay una cita activa ese día; aviso «Cita tentativa creada para el dd/mm».
- [x] **Cumpleaños del día** en la agenda con «Felicitar» por WhatsApp (representante si es menor, texto
      editable en Configuración).
- [x] Sexo del paciente **opcional** en el registro rápido (como Pediae), con aviso donde se necesita (percentiles).
- [ ] Registro rápido por la asistente y botones de la médica (guardar · historia · agendar).
- [x] Gancho nuevo del registro: `reportes`, `documentos`, `paneles` en la ficha del paciente, rutas y páginas offline por especialidad (ADR-036).

### 4.2 `apps/especialidades/pediatria/`
| Pieza | Tipo | Por qué |
|---|---|---|
| `ped.ficha` (perinatales, alimentación, desarrollo, patológicos, familiares, hábitos/entorno, padres) | Sección **PACIENTE** con historial de versiones | Igual que ADR-009; los familiares se cuentan con JSONB en reportes |
| `ped.antropometria` (peso, talla, PC → percentiles, z-score, clasificación) | Sección CONSULTA + modelo `MedicionCrecimiento` | Se grafica y se cuenta (guía §3) |
| `ped.habitos_consulta` (alimentación, sueño, eliminación) | Sección CONSULTA | |
| `ped.desarrollo` (hitos de la consulta) | Sección CONSULTA | |
| Tipo de consulta pediátrico (control sano / enfermedad / seguimiento) | Plantillas + `Consulta.tipo` | Ver decisión D4 |
| `Vacuna`, `VacunaAplicada`, `Pesquisa`, `PesquisaRealizada` | Modelos | Muchas filas por paciente, PDF, reportes |
| `oms.py` (tablas LMS oficiales, z → percentil) | Cálculo `ped.percentiles` | Con tests contra valores publicados |
| Curvas (SVG propio o Chart.js local, sin CDN — funciona offline) | Vista + PDF | |
| Documentos: niño sano, lactancia, lactancia trabajo, esquema de vacunas, curvas, historia completa | `DocumentoDef` | |
| Reportes: estado nutricional, grupos de edad pediátricos, antecedentes familiares, cobertura de vacunas | Gancho de reportes | |
| Plantillas iniciales: «Control sano», «Consulta por enfermedad», «Seguimiento» | `PlantillaDef` | Revisar con la pediatra |

### 4.3 Glosario de medicamentos con calculadora de dosis
Ver decisión D2 (núcleo o solo pediatría). Modelo `Medicamento` como el de Pediae; servicio
`calcular_dosis(med, peso, edad_meses, nivel)` puro y con tests; botón en la sección de prescripción.

## 5. Decisiones (respondidas por Darwin el 2026-10-21)
- **D1 Percentiles:** ✅ tablas **OMS oficiales** (ADR-034). Se muestran los dos criterios: «estado nutricional
  (peso/edad)» con los cortes que usaban en Pediae y «clasificación OMS (IMC/edad)». ⚠️ Confirmar con la pediatra
  cuál prefiere ver primero y cuál va en la constancia de niño sano.
- **D2 Glosario y calculadora de dosis:** ✅ en el **núcleo**, para todas las especialidades.
- **D3 Mayores de 5 años:** ✅ se incluye OMS 2007 (talla/edad e IMC/edad hasta 19 años; peso/edad hasta 10 años).
- **D4 Tipos de consulta:** se resolvió con **plantillas** (Primera consulta pediátrica · Control de niño sano ·
  Consulta por enfermedad · Seguimiento) sin cambiar los tipos del núcleo; los reportes pediátricos agrupan por
  plantilla.
- **D5 «Horas en consulta»:** ✅ formato 12 h en todo · próxima cita sin hora (tentativa) · panel de horas al agendar.

## 6. Tareas (checklist) — en entregas pequeñas
- [x] 13.1 Núcleo: próximo control → cita tentativa sin hora; cumpleaños en la agenda; panel de horas al agendar;
      12 h en todo; sexo, cédula y representante opcionales (con aviso). *(registro rápido con botones
      guardar · historia · agendar: pendiente)*
- [x] 13.2 Módulo base: especialidad, ficha pediátrica (6 secciones PACIENTE), hábitos y desarrollo de la consulta,
      4 plantillas; los consultorios que ya tenían Pediatría reciben las plantillas nuevas al migrar.
      *(página «Ficha pediátrica» fuera de la consulta: pendiente)*
- [x] 13.3 Antropometría + percentiles OMS (0–19 años) + clasificaciones + `MedicionCrecimiento` + tests contra la
      OMS. *(vista previa de percentiles mientras se escribe: pendiente)*
- [x] 13.4 Curvas de crecimiento (pantalla + PDF), punto de nacimiento, clic → consulta.
- [x] 13.5 Vacunas (catálogo, registro, marcar con un toque, anual, resumen, PDF) y pesquisas.
- [x] 13.6 Glosario + calculadora de dosis + inserción en el récipe (núcleo, ADR-037).
- [~] 13.7 Documentos: niño sano, lactancia, lactancia trabajo, carnet de vacunas, curvas ✔ · falta historia completa.
- [~] 13.8 Reportes pediátricos + Excel ✔ · falta PDF.
- [x] 13.9 Offline: ficha, curvas y vacunas en `PAGINAS_OFFLINE` y en la precarga.
- [ ] 13.10 Revisión con una pediatra real (Dra. de Pediae) antes de cerrar.

## 7. Tests
- [ ] Percentiles contra valores publicados por la OMS (≥ 10 casos por indicador y sexo, incluidos bordes).
- [x] Clasificación nutricional en los límites exactos (p3, p10, p15, p85, p97).
- [x] Calculadora: cada modo, techo absoluto, redondeos, alertas de edad/peso, plantilla con variables.
- [x] Vacunas: estados por edad, anual con varias aplicaciones, catálogo propio aislado por consultorio.
- [x] Próximo control: crea una sola tentativa, sin hora, mismo lugar; no duplica.
- [ ] Cumpleaños: saludo al representante si es menor, al paciente si es adulto; sin teléfono → sin botón.
- [x] PDFs generan sin error (con y sin firma, vacunas sin fecha).
- [ ] Aislamiento entre consultorios en todos los modelos nuevos.

## 8. Criterio de salida (verificable)
- [ ] Una consulta pediátrica completa (ficha, antropometría con percentiles, vacunas, récipe con dosis calculada,
      constancia de niño sano) se hace de punta a punta en escritorio y en el teléfono, también sin conexión.
- [ ] Percentiles iguales a la OMS (tolerancia 0,1 percentil) en los casos de prueba.
- [ ] La pediatra revisa y aprueba textos de constancias y la ficha.
- [ ] 100 % de lo listado en §1 está en Ordo Salud o anotado como pendiente con su motivo.
