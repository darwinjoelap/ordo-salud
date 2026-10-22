# Ordo Salud — documentación

Sistema SaaS de consultas médicas multiespecialidad. Esta carpeta es la **fuente de verdad**
del proyecto: si algo no está escrito aquí, no está acordado.

## Mapa de archivos

| Archivo | Qué contiene | Cuándo leerlo |
|---|---|---|
| `../CLAUDE.md` | Contexto permanente: stack, reglas, forma de trabajo | Siempre (automático) |
| `ESTADO.md` | Dónde estamos, qué sigue, qué quedó roto | Al abrir y cerrar cada sesión |
| `DECISIONES.md` | ADR append-only | Antes de proponer un cambio estructural |
| `HISTORIAL.md` | Fases cerradas | Cuando se necesite saber qué se hizo |
| `00_ARQUITECTURA.md` | Visión, tenancy, capas, motor de historia, agenda, tasa, PWA, dictado | Antes de cada fase nueva |
| `01_MODELO_DATOS.md` | Entidades, relaciones, esquema de campos, constraints | Fases 02–14 |
| `02_ESTRUCTURA_PROYECTO.md` | Árbol de carpetas | Fase 01 y al crear apps |
| `03_CONVENCIONES.md` | Nombres, services/selectors, tests, formato de entrega | Siempre que se escriba código |
| `04_REUTILIZACION.md` | Qué se toma de Ordo, Pediae, Ginea y Biolife (archivo por archivo) | Al iniciar cada fase |
| `05_GUIA_ESPECIALIDADES.md` | Cómo agregar una especialidad | Fases 13, 14, 16 y siguientes |
| `roadmap/00_INDICE.md` | 19 fases, dependencias, criterios de salida | Al planificar |
| `roadmap/_PLANTILLA_FASE.md` | Estructura obligatoria de una fase | Al redactar una fase |
| `roadmap/NN_*.md` | Fase ejecutable | En su sesión |

## Protocolo de sesión

**Apertura** (primer mensaje):
```
Lee CLAUDE.md, docs/ESTADO.md y docs/roadmap/NN_nombre.md.
Confirma en 5 líneas: fase actual, qué quedó pendiente y la primera tarea de hoy.
No escribas código todavía.
```

**Si la fase aún no tiene su .md:**
```
Lee CLAUDE.md, docs/ESTADO.md, docs/00_ARQUITECTURA.md, docs/01_MODELO_DATOS.md y
docs/04_REUTILIZACION.md. Redacta docs/roadmap/NN_nombre.md con _PLANTILLA_FASE.md.
Expón las decisiones abiertas con opciones antes de cerrarlo.
```

**Cierre** (último mensaje, sin excepción):
```
Actualiza docs/ESTADO.md (fase, hecho, pendiente, próximo paso, lo roto o a medias).
Si hubo decisión estructural, agrégala a docs/DECISIONES.md.
Si la fase cerró, pásala a docs/HISTORIAL.md.
```

## Señales de que se perdió el contexto
- Se propone otra estructura de carpetas o volver a columnas por especialidad en `Paciente`.
- Se filtra por tenant a mano en una vista.
- Se sugiere un ZIP o reescribir archivos enteros.
- Se mezclan fases.

Recarga: `Lee CLAUDE.md y docs/ESTADO.md. Reinicia desde ahí.`

## Sugerencia de organización en Claude
- Un **proyecto propio** "Ordo Salud" (no mezclarlo con Ginea/Pediae/Ordo: comparten vocabulario
  y el modelo confunde convenciones).
- Instrucciones del proyecto: 5–10 líneas que apunten a `CLAUDE.md`; no duplicarlo.
