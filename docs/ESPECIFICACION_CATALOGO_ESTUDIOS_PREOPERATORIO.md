# Catálogo compartido de exámenes, órdenes y resultados

## Decisión funcional

Un mismo catálogo de exámenes se utiliza en **consultas** (para emitir órdenes) y en
**Evaluación Preoperatoria** (para registrar estudios y resultados). No se confunde con
`cobros.Servicio`: ordenar un examen no crea un cargo ni significa que se haya realizado.

Cada consultorio administra sus propias entradas; los demás consultorios no pueden
leerlas ni modificarlas. Los profesionales autorizados pueden dar de alta un examen
faltante desde el selector mediante un formulario breve, con nombre, categoría,
descripción opcional y estado activo. Los nombres duplicados deben rechazarse sin
perder el formulario que el médico estuviera completando.

## Pantallas y comportamiento

**Orden de exámenes desde consulta.** El profesional abre «Orden de exámenes» desde
los documentos de la consulta. Ve un selector por categorías (laboratorio, ECG,
radiografía/imagen, otros). Al marcar cada examen aparece debajo un campo de
observaciones/indicaciones para ese examen. Puede agregar un examen al catálogo
sin salir del flujo y seleccionarlo. La emisión genera un PDF con paciente,
profesional, fecha, lista exacta de exámenes y sus observaciones, utilizando
`DocumentoEmitido` y conservando una instantánea de nombres e indicaciones.
Las órdenes anteriores permanecen legibles si se modifica el catálogo. Una
orden no contiene resultados ni genera cargos de cobro.

**Estudios en Evaluación Preoperatoria.** Se presenta el mismo catálogo, con casillas
de selección. Al marcar un estudio se despliegan fecha de realización, resultado o
hallazgos, unidades cuando corresponda, observación e identificación opcional de
adjuntos existentes autorizados. Puede registrarse como pendiente sin inventar
resultados. Los registros se incorporan a la versión de `ValoracionPreoperatoria`
y al informe preoperatorio; una enmienda conserva los registros previos y los
PDF originales. El histórico `EstudioPreoperatorio` existente se sigue leyendo.

**Alta de un examen ausente.** El botón «+ Agregar examen» abre un formulario dentro
de la misma pantalla, no un campo libre que cree estudios silenciosamente. Requiere
nombre y categoría; las entradas se crean mediante POST, con CSRF, validación de
permisos, validación por tenant y control de duplicados. Después de crear, se
incorpora a la lista y puede marcarse, sin descartar el trabajo en curso.

**Valores ya disponibles.** La edad de las escalas preoperatorias se obtiene de la
fecha de nacimiento y fecha de valoración en el servidor; jamás se acepta la edad
enviada por el navegador. Otros valores existentes, por ejemplo SpO₂ o hemoglobina,
solo podrán sugerirse indicando fuente, fecha y unidad, y cuando correspondan las
condiciones de medición; el médico debe confirmar su aplicabilidad antes de
incorporarlos al puntaje. «Desconocido» nunca equivale a «No».

## Persistencia y permisos

- `EstudioCatalogo`: `TenantModel`, nombre único normalizado por consultorio,
  categoría, descripción, activo y autoría; catálogos independientes de los servicios
  facturables.
- `EstudioPreoperatorio`: referencia opcional al catálogo más nombre instantáneo
  para lectura histórica, categoría, fecha, resultado, observación, adjuntos.
  Preservar compatibilidad con las filas de tipo LAB/ECG/RX/OTRO ya guardadas.
- `DocumentoEmitido` tipo `orden_estudios`: guardar lista de estudios,
  indicaciones y nombre al emitir; el PDF nunca consulta el catálogo vigente
  para reconstruir una orden histórica.
- Validar pertenencia a tenant, paciente, autoría, acceso a consulta y adjuntos
  tanto en escrituras como en descargas. Cero cambio en datos clínicos existentes
  por una migración de relleno.

## Criterios de aceptación

1. Lista de exámenes por categoría en la orden y en preoperatorio, con observaciones
   bajo cada casilla seleccionada y una ruta para registrar exámenes nuevos.
2. La orden se imprime en PDF con nombres, observaciones y firma de acuerdo con la
   regla del generador; no genera cobros ni escribe resultados clínicos.
3. El preoperatorio permite registrar resultados individuales y adjuntos, guardando
   revisiones y manteniendo PDF históricos.
4. Consultorio ajeno, examen inactivo, adjunto no visible y POST manipulado son
   rechazados sin guardar datos ni revelar información.
5. Reenvíos de formularios, concurrencia y catálogos editados no generan duplicados
   ni cambian órdenes ya emitidas.
6. Migración reversible del esquema (sin eliminar información), tests sobre PostgreSQL
   aislado y datos sintéticos; pruebas del PDF y del historial anterior.

## Índice previsto para implementar este bloque (18 archivos)

```text
apps/clinica/models/consulta.py
apps/clinica/migrations/0014_catalogo_estudios.py (nuevo)
apps/clinica/estudios.py (nuevo)
apps/clinica/forms_estudios.py (nuevo)
apps/clinica/views_estudios.py (nuevo)
apps/clinica/urls.py
apps/clinica/preoperatorio.py
apps/clinica/views_preoperatorio.py
templates/clinica/preoperatorio_form.html
templates/clinica/_catalogo_estudios.html (nuevo)
apps/documentos/comunes.py
apps/documentos/forms.py
apps/documentos/generadores/orden_estudios.py (nuevo)
templates/documentos/emitir.html
static/js/estudios.js (nuevo)
tests/test_catalogo_estudios.py (nuevo)
tests/test_orden_estudios.py (nuevo)
tests/test_preoperatorio_estudios_catalogo.py (nuevo)
```

Este índice se presenta para aprobación antes de editar esos archivos, conforme
a `docs/03_CONVENCIONES.md`. La parte de ocultar DASI y precalcular la edad
se desarrolló por separado, sin migraciones ni despliegue.
