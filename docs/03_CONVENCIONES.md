# 03 — Convenciones

## Idioma (ADR-016)
- Modelos, campos, funciones, variables, URLs y plantillas: **español**, sin tildes ni ñ en
  identificadores (`numero_documento`, `anio`). Igual que Ginea, Pediae y Ordo.
- Términos técnicos de Django se dejan como son (`objects`, `save`, `clean`, `Meta`).
- Commits en español, formato convencional: `feat(agenda): bloqueo por vacaciones`.

## Nomenclatura

| Elemento | Convención | Ejemplo |
|---|---|---|
| Modelo | PascalCase singular | `PlantillaHistoria` |
| Booleano | `es_` / `tiene_` / `requiere_` / adjetivo | `es_predeterminada`, `activa` |
| Fecha y hora | sufijo `_en` | `cerrada_en` |
| Solo fecha | `fecha` o prefijo `fecha_` | `fecha_nacimiento` |
| Service (escribe) | verbo_sustantivo | `crear_cita`, `cerrar_consulta` |
| Selector (lee) | sustantivo descriptivo | `citas_del_dia`, `historia_visible` |
| Choices | `models.TextChoices` dentro del modelo | `class Estado(models.TextChoices)` |
| Permiso | `area.accion` | `historia.ver`, `agenda.gestionar` |
| Código de sección | `prefijo.nombre` | `ped.antropometria`, `gin.control_prenatal` |
| Test | `test_<qué>_<condición>` | `test_cita_solapada_falla` |

## Reglas de código
1. **Vistas**: validan entrada, llaman service/selector, responden. Sin ORM complejo ni escrituras en GET.
2. **Services**: argumentos solo por nombre (`def crear_cita(*, paciente, profesional, ...)`),
   type hints, `transaction.atomic()` si escriben más de un modelo, lanzan `ErrorDeNegocio`.
3. **Selectors**: `select_related` / `prefetch_related` aquí, nunca en plantillas.
4. Validaciones de integridad en `clean()` y constraints de BD; reglas de negocio en services.
5. `DecimalField` para montos y medidas clínicas. Nunca `float`.
6. `CharField`/`TextField` con `blank=True, default=''`, no `null=True`.
7. Una migración por cambio lógico con nombre descriptivo. Nunca editar una ya aplicada en producción.
8. Fuera de un request: `with usando_tenant(t): ...` o `Modelo.todos`.
9. Archivos en Cloudflare R2 privado (ADR-051): adjuntos clínicos siempre por una vista con permisos; `.url` solo para marca (logo, banner, firma, sello) y da un enlace firmado que vence. Nunca `public` ni rutas con nombre o cédula del paciente.
10. Los JS/CSS de `static/vendor/` sin `sourceMappingURL` (rompe `collectstatic` con manifest).

## Interfaz
- Django Templates + HTMX. JavaScript propio pequeño y sin build.
- Pantallas densas y móviles primero: el médico usa el teléfono en consulta.
- Hora siempre `{{ valor|hora12 }}`; montos `{{ x|usd }}` y `{{ x|bs:tasa }}`.
- Color del tenant en `--marca` desde `ConfiguracionTenant.color_primario`.
- Formularios que generan PDF o no deben encolarse offline: `target="_blank"` o `data-offline="off"`.
  Enlaces a PDF con `data-pdf` (se abren en el visor de la PWA).

## Tests
- `python manage.py test tests` en SQLite **y** en PostgreSQL antes de cerrar fase:
  `$env:DATABASE_URL="postgres://..."; python manage.py test tests`
- Mínimo por fase: reglas de negocio nuevas y sus casos borde.
- Toda fase que cree modelos [T] agrega su caso a `tests/test_aislamiento.py`.

## Formato de entrega en sesión
- Un bloque de código por archivo, precedido de su ruta completa.
- Archivo existente: solo el fragmento que cambia, con 2–3 líneas de contexto.
- Más de 5 archivos: índice primero, esperar confirmación.
- Nunca ZIP ni "descarga todo".
- Cierre: checklist de verificación + lista de lo que **no** quedó implementado.
