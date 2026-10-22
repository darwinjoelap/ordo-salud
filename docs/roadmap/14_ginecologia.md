# Fase 14 — Ginecología y obstetricia (perfil desde Ginea)

> Fuente: `C:\proyectos\ginea-saas` (solo lectura). Revisado 2026-10-21: `pacientes/models.py`, `pacientes/forms.py`,
> `consultas/{models,forms,views,recipe_pdf,referencia_pdf,reposo_pdf}.py`, `reportes/views.py`, plantillas de
> consulta, ficha y estadísticas, `agenda`, `configuracion`, `accounts`, `servicios`, `tenant`, `CLAUDE.md`.

## 1. Inventario de Ginea

### 1.1 Ficha de la paciente (columnas fijas en `Paciente`)
| Bloque | Campos |
|---|---|
| Datos personales | nombre completo (un solo campo), cédula V-/E- opcional, nacimiento, teléfono, correo, estado civil, instrucción, ocupación, dirección, contacto de emergencia, seguro |
| Antecedentes personales | alergias, enfermedades crónicas, cirugías, medicación actual, tabaquismo, alcoholismo, grupo sanguíneo, transfusiones |
| Antecedentes familiares | cáncer de mama, cáncer de cuello, diabetes, hipertensión (sí/no), autoinmunes, genéticas, otros (texto) |
| Gineco-obstétricos | menarquia, histerectomía, ciclo (días, regular, características), FUR, gestas/partos/cesáreas/abortos (fórmula G P C A), último parto, última citología (fecha, resultado, «hace…»), VPH (diagnóstico, vacuna), VIH (resultado, fecha), ITS previas, inicio de vida sexual, n.º de parejas, dispareunia, menopausia (sí, edad, síntomas) |
| Planificación familiar | método actual, tiempo de uso, métodos anteriores, deseo de embarazo, DIU (tipo, fecha), ligadura |
| Observaciones | texto |

La asistente registra solo datos personales; la médica ve y edita la ficha completa (formularios por rol).

### 1.2 Consulta (un solo formulario)
Fecha y lugar · peso y tensión arterial · motivo · síntomas actuales · examen físico · ecografía · colposcopia ·
imágenes (mamografía, densitometría…) · diagnóstico (texto) · tratamiento · indicaciones · exámenes solicitados ·
próxima cita (crea cita TENTATIVA sin hora) · observaciones · **control prenatal** (casilla «es prenatal», semanas,
FPP, altura uterina, FCF, presentación, edemas, laboratorio; todo manual) · **actualizar ficha** (FUR, fecha y
resultado de citología) · servicios cobrados y «pagado».

### 1.3 Otros
- Glosario de medicamentos: nombre + indicaciones por defecto (sin cálculo).
- PDF: récipe (horizontal, 2 columnas), referencia con antecedentes **seleccionables**, reposo, historia completa
  (con imágenes adjuntas), estadísticas.
- Procedimientos cobrables sin consulta; pagos pendientes.
- Estadísticas: citas por estado y mes, consultas (prenatales vs. ginecológicas), pacientes nuevas, edades
  (0-20…60+), métodos anticonceptivos, VIH, VPH, con/sin citología, antecedentes familiares, citas por día,
  prenatales por mes, semanas promedio, ingresos y servicios más usados. Gráficos con Chart.js (CDN).
- Offline Nivel 1 + 2A: ya portado a Ordo Salud (ADR-032).

## 2. Qué se trae y cómo (mapeo a Ordo Salud)
| Ginea | Ordo Salud |
|---|---|
| Datos personales | `Paciente` del núcleo (ya tiene estado civil, ocupación, seguro, contacto, grupo). Falta «nivel de instrucción» → sección de ficha |
| Antecedentes personales | `nucleo.antecedentes` + tabaquismo/alcohol/transfusiones en la ficha GO |
| Familiares GO | sección `go.familiares` (casillas + texto), contables en reportes |
| Gineco-obstétricos | `go.gineco` (menstrual, obstétricos con fórmula calculada, menopausia) y `go.citologia` (citología, VPH, VIH, ITS, sexualidad) |
| Planificación | `go.planificacion` |
| Consulta | plantilla «Consulta ginecológica» con el mismo orden de Ginea: `go.tipo` · signos (peso, TA) · motivo · examen físico · `go.estudios` (ecografía, colposcopia, imágenes, laboratorio) · diagnósticos · plan (+ próxima cita tentativa) · récipe · órdenes · `go.actualizar` (FUR y citología → ficha) |
| Control prenatal | sección `go.prenatal` con **EG y FPP calculadas** (FUR o ecografía) + modelo `ControlPrenatal` para seguir el embarazo |
| Glosario | glosario del núcleo (ADR-037) — modo «dosis fija» + plantilla de indicaciones cubre el de Ginea |
| Récipe, reposo, referencia | documentos del núcleo (ya existen) |
| Procedimientos y «pagado» | cargos y pagos del núcleo (ADR-025): cargo sin consulta = procedimiento |
| Estadísticas | reporte GO en `/esp/ginecologia/reportes/` con barras CSS (sin CDN) + Excel |

## 3. Mejoras sobre Ginea
- [x] EG (semanas + días) y FPP (Naegele) calculadas al escribir la FUR o la ecografía; EG por eco tiene prioridad.
- [x] Seguimiento del embarazo: panel con EG de hoy, FPP, trimestre y tabla de controles; alerta de TA ≥ 140/90.
- [x] Fórmula obstétrica calculada (G P C A E) y aviso si los números no cuadran.
- [x] Aviso de citología vencida (> 1 año, o sin registro) en la ficha.
- [x] Constancia de embarazo y carnet de control prenatal en PDF (Ginea no los tenía).
- [x] Reporte: embarazos en curso y FPP de los próximos 30 días, citologías vencidas.

## 4. Incompatibilidades y diferencias (decisiones)
1. **Modelo de datos**: Ginea guarda todo en columnas fijas; Ordo Salud en secciones (JSON) que la médica puede
   reordenar. Migrar consultorios de Ginea (Fase 18) necesita un script de mapeo columna → sección.
2. **Nombre en un solo campo** (`nombre_completo`) vs. `nombres` + `apellidos`: la migración tendrá que partirlo
   (heurística; revisar a mano los nombres compuestos).
3. **Cédula** con validador `V-12345678` vs. tipo + número normalizado: compatible al migrar.
4. **Cobro**: Ginea marca la consulta «pagada» (sí/no) y guarda servicios por consulta; Ordo Salud usa cargos,
   pagos, abonos y saldo a favor. No hay «pagado» por consulta: se ve en la cuenta del paciente.
5. **Procedimientos** como modelo aparte → en Ordo Salud son cargos sin consulta.
6. **Subdominio por médico** (`dra-x.ginea.app`) vs. ruta `/<consultorio>/`: al migrar cambian los enlaces y hay
   que reinstalar la app en los teléfonos.
7. **Glosario sin cálculo**: compatible (modo dosis fija); al migrar, `indicaciones` → plantilla de indicaciones.
8. **FUR única en la ficha** que se sobrescribe: en Ordo Salud la FUR queda en la ficha **y** en cada control
   prenatal (historial por embarazo).
9. **Chart.js por CDN** en estadísticas: no se trae (las barras CSS funcionan sin conexión, ADR-031).
10. **Adjuntos** en Cloudinary con campo `drive_file_id` (nombre heredado de Drive): Ordo Salud ya tiene adjuntos;
    al migrar se copian las referencias.
11. **Pacientes solo mujeres**: Ginea no guarda sexo. En Ordo Salud el sexo existe; en consultorios de GO la
    paciente nueva queda con sexo femenino por defecto.
12. **Datos sensibles** (VIH, ITS, vida sexual): se guardan como en Ginea, dentro de la historia (auditada); no
    salen en reportes con nombre, solo conteos.

## 5. Checklist
- [x] 14.1 Módulo `apps/especialidades/ginecologia`: secciones, cálculos, plantillas (predeterminada = Ginea)
- [x] 14.2 `ControlPrenatal` + gancho al guardar `go.prenatal` + panel de embarazo y panel GO en la ficha
- [x] 14.3 `go.actualizar` → actualiza la ficha (FUR, citología)
- [x] 14.4 Documentos: constancia de embarazo, carnet prenatal
- [x] 14.5 Reporte GO + Excel
- [x] 14.6 Sexo femenino por defecto en consultorios de GO
- [x] 14.7 Tests (12), capturas escritorio y móvil, docs
- [ ] 14.8 Revisión con una ginecóloga real (Dra. de Ginea) antes de cerrar

## 6. Notas de implementación
- Motivo y diagnóstico **opcionales** en las plantillas de GO (como Ginea): ajuste nuevo de plantilla `opcionales`.
- La plantilla «Control prenatal» abre con el tipo «Control prenatal» (ajuste `por_defecto`).
- Gancho nuevo del núcleo `registrar_inicial`: el control prenatal abre con la FUR y la eco del embarazo en curso.
- Un control prenatal se crea si el tipo es «Control prenatal», hay datos del feto (AU, FCF, presentación…), o
  hay FUR/eco en una plantilla sin sección de tipo. Peso y TA se leen de los signos vitales de la consulta.
- Pendiente: gráfico de altura uterina vs. EG; alertas de laboratorio prenatal; migración de datos de Ginea (Fase 18).

## 7. Ajuste 2026-10-21 — «la historia tal cual Ginea» (pedido de Darwin)
- La ficha GO quedó con **los mismos bloques, campos, etiquetas y orden** que la ficha clínica de Ginea:
  Antecedentes personales (tabaquismo, alcoholismo, transfusiones, instrucción) · Antecedentes familiares (4 casillas +
  autoinmunes, genéticas, otros) · **Historia gineco-obstétrica** en un solo bloque (menarquía, ciclo, FUR,
  características del sangrado, G P C A, último parto, citología con resultado en texto libre y «tiempo aproximado»,
  VPH, VIH, ITS, inicio de vida sexual, n.º de parejas, dispareunia, menopausia) · Planificación familiar (método en
  texto libre, DIU tipo y fecha, ligadura) · Observaciones generales. Sin campos ocultos condicionales.
- Se quitó lo que Ginea no tenía (ectópicos, complicaciones obstétricas, cáncer de ovario, listas cerradas de método y
  de citología). La fórmula obstétrica sigue calculada (en Ginea se mostraba en el encabezado).
- Consulta con los nombres de Ginea: «Motivo / notas adicionales», «Síntomas actuales», «Examen físico» (un solo
  campo), peso y tensión arterial, «Tratamiento», «Indicaciones», «Exámenes solicitados», «Próxima cita»,
  «Observaciones». Diferencias que se mantienen: diagnóstico en tabla (CIE-10 opcional) y récipe en tabla (para el
  PDF y la calculadora del glosario).
- Comando nuevo `refrescar_plantillas <especialidad> [--consultorio enlace]` para rehacer las plantillas del sistema
  de un consultorio existente (las de cada médico y las consultas ya abiertas no cambian).

