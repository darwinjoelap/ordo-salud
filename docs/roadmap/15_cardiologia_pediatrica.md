# Fase 15 — Cardiología pediátrica (modelo de la Dra. Lyna Sierra)

> Fuente: dos informes en Word que entregó la especialista (2026-10-22): «MODELO_HISTORIA.doc» (escolar con CIA) y
> «MODELO_COMPLEJO_DE_HISTORIA.docx» (Trisomía 21, Tetralogía de Fallot en POP tardío). Cardióloga pediatra,
> intensivista y ecocardiografista fetal, en Mérida.

## 1. Inventario del modelo (un «Informe médico» por consulta)
| Bloque | Contenido |
|---|---|
| Encabezado | Banner de la doctora · «Mérida dd/mm/aaaa» a la derecha · NOMBRE, EDAD («2 AÑOS + 11 MESES»), FN, TLF, MADRE, CI, procedencia |
| Título | INFORME MÉDICO (centrado, subrayado) |
| Enfermedad actual | Prosa |
| Antecedentes personales | Prosa armada siempre igual: «Producto de madre de 43 años, VG, I Mortinato. Embarazo simple a término 38 semanas. Complicado con … Nace a través de cesárea segmentaria por … Respiró y lloró espontáneamente al nacer. PAN: 2.740 grs, TAN: 48 cms. Egresó / Ingresó … Niega alergias, asma bronquial, eruptivas … I/Q … Esquema de inmunizaciones incompleto, documentado.» |
| Examen físico | Línea en negrita «FC: 72 lpm, Sat: 93 %. TA: 99/60 mmHg, Peso: 10.4 Kgs, Talla: 82 cm, SC: 0.48 m2SC» + prosa del examen (cardiovascular) |
| EKG | `RS/88/0.16/0.08/0.36/0.44/30°/80°` (ritmo/FC/PR/QRS/QT/QTc/eje P/eje QRS) + «Trazo: HVD…» |
| Ecocardiograma transtorácico | Prosa con medidas: situs, ápex, retornos (VCI y colapso), tabique interatrial (defecto, medidas, bordes, shunt, Qp:Qs), aurículas (área, volumen, volumen indexado), conexión AV, tricúspide y mitral (anillo, E, A, regurgitación, Vmáx, gradiente), tabique interventricular, VD (diámetros, TAPSE, s', áreas, CAF), VI (SIVd, DdVI, PPd, SIVs, DsVI, PPs, FEVI), TSVD, conexión VA, pulmonar (anillo y Z-score, Vmáx, Gp), TAP y ramas (mm, Z, Vmáx, Gp), ductus, aorta (valvas, anillo, SV, UST, arco, descendente), pericardio, trombos, vegetaciones |
| Comentario | Resumen + plan + «Se revalorará en N meses» (en negrita en un modelo) |
| Imágenes | Imágenes del eco al final |
| Evolución | Notas cortas con fecha al pie («05/10/2026 Se entrega Holter con resultado normal…») |
| Firma | «Dra. Lyna Sierra · Cardiólogo Pediatra – Intensivista» |

## 2. Decisiones de Darwin (2026-10-22)
- Nombre: **Cardiología pediátrica** (la de adultos será otro perfil). Código `cardiologia_pediatrica`.
- Ecocardiograma **todo estructurado** (un campo por medida, cálculos automáticos) y el informe arma la prosa.
- Antecedentes: **campos + párrafo automático**, en la ficha del paciente (se llenan una vez).
- Primera entrega: informe, **notas de evolución**, **imágenes del eco en el PDF** y **dictado por voz opcional**
  (apagado hasta que Darwin lo active para el consultorio: depende del acuerdo económico).
- Fuera: ecocardiografía fetal (necesita su modelo).

## 3. Cálculos
| Valor | Fórmula | Comprobado con el modelo |
|---|---|---|
| QTc | Bazett: QT / √(60/FC) | 0.36 s y 88 lpm → 0.44 ✔ · 0.34 s y 94 lpm → 0.43 ✔ |
| Gradiente | Bernoulli simplificado: 4·v² | 3.08 m/s → 37.9 (ella 38.2) · 2.51 → 25.2 (25) ✔ |
| Volumen indexado | volumen / SC | 16 / 0.48 → 33.3 ✔ · 18.9 / 0.85 → 22.2 ✔ |
| CAF del VD | (área diástole − área sístole) / área diástole | 12.8 y 6.5 → 49.2 % ✔ |
| FEVI (Teichholz) | VFD = 7/(2.4+D)·D³ con D en cm; FE = (VFD − VFS)/VFD | 25.8 y 15.1 mm → 74 % ✔ (en el otro modelo escribe «> 60 %»: se puede poner a mano) |
| FA | (DdVI − DsVI) / DdVI | — |
| SC | Del núcleo (Mosteller). **Pendiente con la doctora**: sus SC no coinciden con una sola fórmula (0.48 ≈ Mosteller truncado; 0.85 = DuBois) | — |
| Z-score | **Pendiente**: hay que saber qué calculadora usa (Detroit/Pettersen, Boston, PHN/Lopez, Cantinotti). Mientras, se escribe a mano. Sus casos sirven para validar: anillo pulmonar 7 mm con SC 0.48 → Z −4.15; TAP 7 mm → −3.81; RD 7 mm → −0.68; RI 6 mm → −0.84 | — |

## 4. Mapeo a Ordo Salud
| Modelo | Ordo Salud |
|---|---|
| Datos del encabezado | Paciente + representante principal (madre, CI) + ciudad del paciente |
| Enfermedad actual | `nucleo.motivo` (motivo opcional, «Enfermedad actual») |
| Antecedentes personales | Sección de ficha `cp.antecedentes` (perinatales + patológicos + inmunizaciones) con «Así sale en el informe» |
| Examen físico | `nucleo.signos_vitales` (FC, Sat, TA, peso, talla, SC) + `nucleo.examen_fisico` (examen físico y cardiovascular) |
| EKG | `cp.ekg` con QTc y la línea calculados |
| Eco | `cp.eco` (≈100 campos en subtítulos) con cálculos y prosa del informe |
| Comentario | `nucleo.plan` («Comentario» + «Próximo control» → cita tentativa) |
| Diagnóstico, récipe, órdenes (Holter…) | Núcleo (diagnóstico opcional) |
| Informe médico | Documento `cp_informe` con su formato exacto, imágenes y notas de evolución |
| Notas de evolución | Núcleo: `clinica.NotaEvolucion` (cualquier especialidad; también en la consulta cerrada) |
| Dictado por voz | Núcleo: botón de micrófono en los textos si `ConfiguracionTenant.dictado_activo` (lo activa la plataforma) |

## 5. Checklist
- [x] 15.1 Módulo `apps/especialidades/cardiologia_pediatrica` (secciones, cálculos, plantilla en su orden)
- [x] 15.2 Antecedentes con párrafo automático (ficha)
- [x] 15.3 EKG y eco estructurados con cálculos y prosa
- [x] 15.4 Informe médico PDF tal cual el modelo + imágenes + notas de evolución
- [x] 15.5 Panel «Resumen cardiológico» y reporte de la especialidad
- [x] 15.6 Dictado por voz opcional (apagado por defecto)
- [x] 15.7 Tests, capturas, comparación con su Word
- [ ] 15.8 Pendientes con la doctora: fórmula de SC, calculadora de Z-score, abreviaturas de ritmo, revisión del informe
