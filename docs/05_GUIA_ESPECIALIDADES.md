# 05 — Guía: cómo agregar una especialidad

> Objetivo de diseño: agregar una especialidad **no toca** `apps/clinica`, `apps/agenda`,
> `apps/cobros` ni `apps/reportes`. Si hace falta tocarlos, falta un punto de extensión:
> se agrega al núcleo con su ADR, no se parchea para una especialidad.

## 1. Pasos

1. Crear `apps/especialidades/<codigo>/` con la estructura de `02_ESTRUCTURA_PROYECTO.md`.
2. Declarar la especialidad en `especialidad.py`:

```python
# apps/especialidades/cardiologia/especialidad.py
from apps.clinica.registro import Especialidad, SeccionModulo, Documento, registrar

from . import calculos, documentos
from .secciones import ANTECEDENTES_CV, EXAMEN_CV, ECG, RIESGO_CV

registrar(Especialidad(
    codigo='cardiologia',
    nombre='Cardiología',
    prefijo='car',
    color='#C0392B',
    secciones=[
        SeccionModulo('car.antecedentes', 'Antecedentes cardiovasculares', ambito='PACIENTE',
                      esquema=ANTECEDENTES_CV, version=1),
        SeccionModulo('car.examen', 'Examen cardiovascular', ambito='CONSULTA',
                      esquema=EXAMEN_CV, version=1),
        SeccionModulo('car.ecg', 'Electrocardiograma', ambito='CONSULTA', esquema=ECG, version=1),
        SeccionModulo('car.riesgo', 'Riesgo cardiovascular', ambito='CONSULTA',
                      esquema=RIESGO_CV, version=1),
    ],
    calculos={'car.riesgo_cv': calculos.riesgo_cardiovascular},
    documentos=[Documento('car.informe_ecg', 'Informe de ECG', documentos.informe_ecg)],
    plantillas_iniciales=[
        ('Primera consulta', ['nucleo.motivo', 'car.antecedentes', 'nucleo.signos_vitales',
                              'car.examen', 'car.ecg', 'nucleo.diagnosticos', 'nucleo.plan',
                              'nucleo.prescripcion']),
        ('Control', ['nucleo.motivo', 'nucleo.signos_vitales', 'car.examen',
                     'nucleo.diagnosticos', 'nucleo.prescripcion']),
    ],
))
```

3. En `apps.py`, `ready()` importa `especialidad.py` (eso registra).
4. Agregar la app a `INSTALLED_APPS`.
5. `python manage.py sincronizar_especialidades` → crea/actualiza `Especialidad` y
   `SeccionClinica` (+ `SeccionClinicaVersion` si subió la versión).
6. Plataforma → tenant → habilitar la especialidad → se copian las plantillas iniciales.
7. Tests del módulo: esquemas válidos, cálculos con casos reales, PDF genera sin error.

## 2. Cambiar el esquema de una sección ya usada

- **Agregar** un campo opcional: subir `version`. Registros viejos siguen válidos.
- **Renombrar o quitar** un campo: subir `version` y escribir una función de migración de
  datos en `secciones.py` (`migrar_v1_a_v2(datos) -> datos`). Las consultas **cerradas** nunca
  se migran: se leen con su versión.
- Nunca cambiar el `tipo` de un campo existente en la misma clave.

## 3. Cuándo un módulo necesita modelos propios

Si el dato se **grafica**, se **cuenta** en reportes o tiene **muchas filas por paciente**
(vacunas aplicadas, controles domiciliarios, mediciones seriadas), va en un modelo del módulo
que hereda `TenantModel`. La sección del módulo solo lo edita/muestra.

## 4. Checklist de una especialidad nueva

- [ ] Secciones con esquemas válidos (`python manage.py validar_esquemas`)
- [ ] Cálculos con tests contra valores reales de referencia
- [ ] Plantillas iniciales razonables (revisadas con un médico de la especialidad)
- [ ] Documentos PDF propios con encabezado del tenant y firma del profesional
- [ ] Reportes propios registrados (si aplica)
- [ ] Las páginas del módulo requieren red. Solo sus recursos estáticos públicos pueden incluirse en la precarga de la PWA.
- [ ] Esquemas listos para el dictado (etiquetas claras, unidades declaradas)
- [ ] Entrada en `DECISIONES.md` y fase cerrada en `HISTORIAL.md`
