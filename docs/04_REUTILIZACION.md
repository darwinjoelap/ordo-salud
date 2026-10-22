# 04 — Qué se reutiliza y de dónde

> Revisado el 2026-10-19 sobre las copias locales en `C:\proyectos`.
> Acción: **Copiar** (casi tal cual, renombrar empresa→tenant) · **Adaptar** (la lógica sirve,
> el modelo cambia) · **Referencia** (leer para no olvidar casos, reescribir) · **No portar**.
> Los proyectos de origen **no se modifican** desde Ordo Salud.

## 1. Desde Ordo (`C:\proyectos\ordo`) — esqueleto y plataforma

| Origen | Destino | Acción | Nota |
|---|---|---|---|
| `config/settings/{base,dev,prod}.py` | `config/settings/` | Adaptar | Quitar apps de ventas; agregar apps de Ordo Salud |
| `Dockerfile`, `railway.json`, `railway.cron.json`, `.dockerignore` | raíz | Copiar | Cambiar nombre de módulo si aplica |
| `docs/DESPLIEGUE_RAILWAY.md` | `docs/` | Adaptar | Variables y servicios de Ordo Salud |
| `apps/core/tenancy.py` | `apps/core/tenancy.py` | Copiar | `empresa` → `tenant`, `EmpresaModel` → `TenantModel` |
| `apps/core/middleware.py` | `apps/core/middleware.py` | Adaptar | Membresía virtual de soporte incluida |
| `apps/core/permisos.py` | `apps/core/permisos.py` | Adaptar | Nueva tabla de roles y permisos clínicos |
| `apps/core/forms.py` (`FormBootstrap`) | `apps/core/forms.py` (`FormBase`) | Copiar | Imprescindible: rehace querysets por tenant |
| `apps/core/pdf.py` | `apps/core/pdf.py` | Adaptar | + firma/sello del profesional |
| `apps/core/secuencias.py` | igual | Copiar | |
| `apps/core/pwa.py` + `static/js/pwa.js` | igual | Adaptar | Manifest, `/instalar/`, **`/visor/` de PDF** |
| `apps/core/management/commands/tareas_programadas.py` | igual | Adaptar | Tasa + limpieza idempotencia + cierre automático de consultas |
| `apps/usuarios/` (models, backends, middleware de cambio de clave) | `apps/usuarios/` | Adaptar | Login por usuario único por tenant |
| `apps/empresas/models.py` (`Empresa`, `Membresia`, `Rol`) | `apps/plataforma/`, `apps/equipo/` | Adaptar | Roles clínicos |
| `apps/empresas/equipo.py`, `views_equipo.py` | `apps/equipo/` | Adaptar | Alta con clave temporal; + perfil profesional |
| `apps/empresas/plataforma.py`, `views_plataforma.py`, `views_entrada.py` | `apps/plataforma/` | Adaptar | Panel `/plataforma/`, entrada `/<slug>/`, `RESERVADOS` |
| `apps/empresas/management/commands/crear_empresa.py` | `crear_tenant` | Adaptar | |
| **`apps/tasas/`** (models, servicios, comando `actualizar_tasa_bcv`) | `apps/tasas/` | **Copiar** | `TasaEmpresa` → `TasaTenant`. Incluye el arreglo del certificado del BCV |
| `static/vendor/` (bootstrap, icons, htmx) | igual | Copiar | Sin CDN |
| `tests/` (estructura y tests de tenancy) | `tests/` | Adaptar | Base de `test_aislamiento.py` |

## 2. Desde Pediae (`C:\proyectos\pediae`) — dominio clínico y offline

| Origen | Destino | Acción | Nota |
|---|---|---|---|
| `pacientes/models.py` → `Paciente.clean()` (duplicados, `_duplicado`) | `apps/pacientes/` | Adaptar | Mantener aviso "ya está registrado" + "Abrir su ficha" |
| `pacientes/models.py` → bloque perinatal, alimentación, desarrollo, hábitos | `especialidades/pediatria/secciones.py` | Adaptar | Pasan a secciones de ámbito PACIENTE |
| `pacientes/models.py` → `Vacuna`, `VacunaAplicada`, `Pesquisa`, `PesquisaRealizada` | `especialidades/pediatria/models.py` | Copiar | Heredan `TenantModel` |
| `pacientes/oms_data.py`, `consultas/oms.py` | `especialidades/pediatria/calculos.py` | Copiar | Percentiles OMS |
| `pacientes/constancias_pdf.py`, `vacunas_pdf.py`, `curvas_pdf.py` | `especialidades/pediatria/documentos.py` | Adaptar | Usar `core/pdf.py` para encabezado |
| `pacientes/informe_referencia_pdf.py` | `apps/documentos/referencia.py` | Adaptar | Es común a todas las especialidades |
| `consultas/models.py` → `Consulta` (campos pediátricos) | secciones de Pediatría + `SignosVitales` | Adaptar | |
| `consultas/models.py` → `Medicamento` (dosis mg/kg, rangos de edad/peso) | `Medicamento` común + extensión en Pediatría | Adaptar | Cálculo de dosis = función registrada del módulo |
| `consultas/models.py` → `ConsultaServicio`, `Procedimiento*` | `apps/cobros/` (`Cargo`) | Adaptar | Se agrega `Pago` real; hoy solo hay `pagado` |
| `consultas/recipe_pdf.py` | `apps/documentos/recipe.py` | Adaptar | |
| `templates/consultas/imprimir_consulta.html` | `apps/documentos/` (impresión HTML) | Adaptar | Diseño moderno ya probado; renderiza secciones dinámicas |
| `agenda/models.py` (`LugarConsulta`, `Cita`, WhatsApp a representante, hora tentativa) | `apps/agenda/`, `apps/configuracion/` | Adaptar | + profesional, tipo de cita, horario |
| `configuracion/models.py` (`ConfigConsultorio`) | `ConfiguracionTenant` | Adaptar | |
| `accounts/models.py` (firma, sello, banner, MPPS) | `PerfilProfesional` | Adaptar | Cloudinary por public_id → `CloudinaryField`/storage |
| `servicios/models.py` (`Servicio`) | `apps/cobros/` | Adaptar | `TasaCambio` manual de aquí **no** se porta (se usa la de Ordo) |
| `reportes/views.py` (`estadisticas`, `estadisticas_pdf`, `pagos_pendientes`, `generar_pdf_historial`) | `apps/reportes/`, `apps/documentos/` | Referencia | Partir en selectors; hoy es un archivo de 38 KB |
| **`offline/`** (`IdempotenciaMiddleware`, `SolicitudIdempotente`, ping, precache) | `apps/offline/` | **Copiar** | Ya en producción |
| **`static/js/offline.js`, `static/js/sw.js`** | `static/js/` | Adaptar | Unificar con el SW de Ordo; regex de páginas offline nuevas |
| `tenant/subscription_middleware.py` | `apps/plataforma/` | Referencia | Aviso de vencimiento a 5 días se conserva |

## 3. Desde Ginea (`C:\proyectos\ginea-saas`) — módulo Ginecología

| Origen | Destino | Acción |
|---|---|---|
| `pacientes/models.py` → menarquia, ciclo, FUR, gestas/partos/cesáreas/abortos, citología, VPH, VIH, ITS, vida sexual, menopausia, anticoncepción | `especialidades/ginecologia/secciones.py` (ámbito PACIENTE) | Adaptar |
| `consultas/models.py` → ecografía, colposcopia, imágenes, control prenatal (FPP, semanas, altura uterina, FCF, presentación, edemas) | secciones de ámbito CONSULTA + `calculos.py` (FPP, edad gestacional) | Adaptar |
| `consultas/reposo_pdf.py` | `apps/documentos/reposo.py` | Adaptar (común) |
| `consultas/referencia_pdf.py`, `recipe_pdf.py` | comparar con los de Pediae y quedarse con el mejor | Referencia |
| `templates/consultas/glosario_medicamentos.html` | catálogo `Medicamento` | Referencia |
| `reportes/views.py` | `apps/reportes/` | Referencia |

## 4. Desde Biolife (`C:\proyectos\biolife`) — método

| Origen | Uso |
|---|---|
| `docs/COWORK_Y_CONTEXTO.md` | Protocolo de sesión (apertura/cierre) — resumido en `docs/README.md` |
| `docs/03_CONVENCIONES.md` | Services/selectors, excepciones de dominio, formato de entrega |
| `docs/roadmap/` (formato de fase, criterio de salida, modelo por fase) | `docs/roadmap/_PLANTILLA_FASE.md` |
| Fase 15 (rectificaciones) | Idea de `Enmienda` sobre consulta cerrada |
| Auditoría (Fase 02) | `core.Auditoria` |

## 5. No portar (y por qué)

| Qué | Por qué |
|---|---|
| FK `tenant` con `null=True` y filtro manual en cada vista (Ginea/Pediae) | Riesgo de fuga de datos; se reemplaza por `TenantModel` |
| Ruteo `/t/<slug>/...` en todas las URLs + `StripTenantSlugMiddleware` | Se usa el esquema de Ordo (enlace de entrada + sesión) |
| `settings.py` único con `TENANT_SLUG` (modo instancia dedicada) | Una sola instancia SaaS |
| `consultas/drive.py`, `drive_file_id` (Google Drive) | Adjuntos en Cloudinary privado |
| `servicios.TasaCambio` manual por tenant | Se reemplaza por `apps/tasas` de Ordo |
| Campos de especialidad como columnas de `Paciente`/`Consulta` | Pasan a secciones |
| Unicidad de `cedula_representante` | Bloquea registrar hermanos |
| `models-1.py` y archivos de respaldo | Ruido |

## 6. Errores conocidos a no repetir

- Pediae: constancias no abren en el móvil (POST con `target="_blank"` + PDF inline) → usar el
  visor de PDF de Ordo y enlaces GET firmados.
- Pediae/Ginea: plantillas que preguntaban por un campo inexistente (`request.user.firma`) →
  propiedades únicas en `PerfilProfesional` (`tiene_firma`, `url_firma`) y tests de PDF con/sin firma.
- Ginea/Pediae: `IntegrityError` 500 al validar sin tenant en la instancia del form →
  `FormBase` + crear la instancia con tenant antes de validar.
- Ordo: `sourceMappingURL` en vendor rompe `collectstatic`.
- Ordo: related managers vacíos fuera de request → `usando_tenant()` en comandos y tests.
