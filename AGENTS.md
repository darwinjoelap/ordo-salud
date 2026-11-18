# Instrucciones para agentes — Ordo Salud

## Producto y alcance

Ordo Salud integra distintas especialidades médicas en una plataforma multi-tenant.
Un tenant representa un consultorio o clínica y puede reunir varios profesionales
con diferentes especialidades.

Ordo Salud es la arquitectura de referencia para nuevas implementaciones.
Ginea y Pediae aportan conocimiento funcional e histórico.

Las solicitudes heredadas de Ginea y Pediae deben evaluarse como necesidades
funcionales, no como instrucciones para copiar su implementación o interfaz.
Antes de implementar una capacidad, determina si pertenece al núcleo compartido,
a un módulo de especialidad o a la configuración de un tenant.

Antes de actuar, identifica si la tarea autoriza análisis, edición o ejecución.
Una auditoría de solo lectura no autoriza cambios, pruebas con escrituras,
actualización de documentación ni operaciones externas.

## Contexto del repositorio

Lee las instrucciones aplicables y consulta:
- docs/ESTADO.md para contexto temporal.
- docs/DECISIONES.md para decisiones de arquitectura.
- docs/03_CONVENCIONES.md para convenciones.
- docs/05_GUIA_ESPECIALIDADES.md para extensiones.

Contrasta ejemplos y estados documentados con el código actual.
Si difieren, informa la discrepancia; no conviertas el comportamiento
existente en una decisión de producto sin evaluarlo.

No actualices documentación durante tareas de solo lectura.

## Repositorios de referencia

- Principal: C:\proyectos\ordo-salud
- Ginea: C:\proyectos\ginea-saas
- Pediae: C:\proyectos\pediae

Estas rutas son referencias de ubicación y no conceden permisos por sí mismas.
Verifica el acceso efectivo del entorno y respeta el alcance autorizado.
Si la lectura está bloqueada, informa la limitación; no solicites permisos de
escritura para consultar los repositorios heredados.

Consulta los legados únicamente en modo de lectura, salvo autorización
explícita para una tarea independiente sobre ellos.

Usa búsquedas dirigidas sobre código, esquemas y documentación técnica.
No ejecutes sus aplicaciones, comandos, migraciones ni dependencias para
resolver una duda que pueda aclararse leyendo el código.

Las instrucciones internas de los legados describen sus propios proyectos;
no autorizan cambios ni sincronizaciones entre repositorios.

No copies código heredado sin evaluar compatibilidad con:
tenancy, permisos, modelos, versiones, dependencias, seguridad y pruebas.

## Arquitectura multiespecialidad

Mantén el núcleo independiente de especialidades concretas.
Usa el registro actual de apps/clinica/registro.py para incorporar
secciones, cálculos, documentos, paneles y reportes.

Ubica capacidades comunes en el núcleo y reglas específicas en su módulo.
Si falta un punto de extensión, propón uno general con la decisión
documentada; evita condiciones particulares de especialidad en el núcleo.

Respeta servicios de escritura y selectors de lectura.
Usa los nombres y puntos de entrada existentes; el código emplea también
servicios.py y archivos de servicios especializados.

Mantén vistas delgadas y evita escrituras en GET.
Usa transacciones para operaciones relacionadas.

## Tenancy y permisos

Los nuevos modelos con datos de tenant deben usar TenantModel.
Los modelos globales o de alcance especial requieren una justificación
explícita y aislamiento equivalente.

Sin tenant activo, los accesos ordinarios deben fallar cerrado.
Modelo.todos es un acceso excepcional que exige alcance explícito.

Valida también las relaciones entre objetos: compartir una clave primaria
o recibirla desde el navegador no demuestra pertenencia al tenant.

Centraliza permisos en apps/core/permisos.py.
Respeta además el alcance de pacientes y agendas dentro del tenant.
No supongas que un usuario, un titular y un profesional son lo mismo.

No amplíes privilegios de soporte ni permisos clínicos como efecto
secundario de un cambio funcional.

## Compatibilidad y significado clínico

No equipares conceptos por similitud de nombre o apariencia.
Compara significado, ámbito, unidades, cardinalidad, autoría, fecha,
estados y reglas de validación.

Distingue dato ausente, negativo, cero, desconocido y no aplicable.
No deduzcas identidad de pacientes por nombre o representante.

Versiona los cambios de esquemas clínicos.
No renombres, elimines ni cambies el tipo de una clave usada sin una
estrategia explícita de compatibilidad.

Conserva la lectura de registros históricos con su versión.
Las consultas cerradas se corrigen mediante los mecanismos previstos
de enmienda o evolución, sin sobrescribir el registro original.

## Migración de clientes

Distingue migraciones de esquema Django e importación de datos de clientes.
La existencia de un importador no autoriza ejecutarlo.

Antes de una importación autorizada, documenta:
- Mapeo origen-destino y transformaciones.
- Datos excluidos, ambiguos o fuera de rango.
- Tratamiento de identidad, duplicados y autoría.
- Conciliación de conteos, cargos, pagos y tasas.
- Verificación de archivos, permisos y trazabilidad.
- Recuperación ante fallos de base de datos y almacenamiento externo.

No interpretes --ensayo como una operación de solo lectura.
No supongas que transaction.atomic revierte efectos externos.

No fusiones personas, recalcules resultados históricos ni interpretes
valores clínicos ambiguos sin criterios explícitos y aprobados.

Conserva la distinción entre valores originales y derivados.

## Seguridad y datos clínicos

No accedas a bases reales, respaldos, archivos clínicos, secretos ni
credenciales salvo autorización específica para esa tarea.

No abras .env ni imprimas variables de entorno o cadenas de conexión.
No reproduzcas información identificable encontrada en documentación.

Usa datos sintéticos en ejemplos y pruebas.
No envíes contenido clínico a servicios externos durante tareas de
desarrollo sin autorización específica.

Mantén adjuntos privados, rutas sin identificadores de pacientes y
descargas sujetas a permisos. Respeta R2 privado y enlaces temporales.

No borres físicamente información clínica ni alteres consultas cerradas
para acomodar una pantalla o una importación.

Conserva la auditoría de lecturas de historia clínica y de cambios clínicos,
con autoría y trazabilidad. No omitas los mecanismos existentes de auditoría
al incorporar servicios, importaciones o nuevas vías de acceso.

## Cálculos clínicos e IA

Toda modificación de cálculos debe indicar fuente, unidades, población,
rango válido, precisión y tratamiento de datos incompletos.

Verifica dosis, percentiles y cálculos obstétricos con casos sintéticos
y valores de referencia apropiados.

No completes hallazgos clínicos normales por defecto.
Las sugerencias de IA requieren revisión del profesional.
No presentes una sugerencia como dato observado o decisión confirmada.

## Pruebas

En auditorías de solo lectura, limita la verificación a inspección estática.

Para cambios autorizados, verifica primero el entorno virtual y utiliza
una configuración de pruebas aislada de bases y servicios reales.

Selecciona pruebas según el riesgo del cambio:
- Aislamiento entre tenants y alcance entre profesionales.
- Permisos, relaciones y accesos negativos.
- Versiones históricas y consultas cerradas.
- Unidades, límites y datos clínicos incompletos.
- Idempotencia y recuperación offline.
- Tasas congeladas y conciliación financiera.
- Importaciones y fallos parciales, incluidos archivos externos.

Para cambios de modelos o consultas, valida con PostgreSQL de pruebas.
SQLite por sí solo no acredita compatibilidad con PostgreSQL.

Informa qué verificaste, qué no ejecutaste y qué sigue pendiente.
No atribuyas a la sesión resultados históricos de la documentación.

## Solicitudes que comparan con Ginea o Pediae

1. Describe el objetivo del usuario y el escenario concreto.
2. Localiza el comportamiento heredado en código y documentación.
3. Localiza la capacidad equivalente en Ordo.
4. Clasifica la diferencia: configuración, descubrimiento de interfaz,
   regresión, brecha funcional, diferencia de modelo o limitación heredada.
5. Explica cualquier diferencia semántica o clínica.
6. Determina si la solución corresponde al núcleo, a una especialidad o
   a la configuración del tenant.
7. Propón la solución compatible con Ordo y sus criterios de aceptación.
8. Verifica otras especialidades, permisos e historia existente.
9. Comunica lo conservado, lo cambiado y las incertidumbres.

Pregunta solo cuando una ambigüedad afecte significado clínico, identidad,
datos, permisos o una decisión de producto que no pueda resolverse
con la evidencia disponible.

## Forma de trabajo y entrega

Trabaja con cambios incrementales dentro del alcance autorizado.
Respeta las convenciones españolas y el formato local de fechas,
horas y monedas.

En entregas manuales, presenta ruta y fragmentos con contexto.
Respeta el procedimiento vigente para cambios de más de cinco archivos.

Explica resultado, evidencia, verificaciones y trabajo incompleto.
No hagas commits, push, despliegues ni operaciones de migración sin
autorización expresa.
