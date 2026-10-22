# CLAUDE.md — Contexto permanente de Ordo Salud

> Se lee al inicio de **cada** sesión. Mantenerlo corto (< 200 líneas).
> Lo que cambia seguido va en `docs/ESTADO.md`; las decisiones, en `docs/DECISIONES.md`.

## Qué es

SaaS multi-tenant para **gestión de consultas médicas de cualquier especialidad**.
Un *tenant* es un consultorio o una clínica; dentro de él trabajan uno o varios médicos,
**cada uno con su especialidad**. La base clínica es común y cada especialidad se agrega
como **módulo enchufable** (Pediatría y Ginecología se portan desde Pediae y Ginea;
Cardiología es la siguiente). El médico **arma su historia** eligiendo secciones.

Interfaz y datos en **español**. Producto de Darwin (Barquisimeto, Venezuela).

## Proyectos de referencia (NO se modifican desde aquí)

| Proyecto | Ruta | Qué se toma |
|---|---|---|
| Ordo | `C:\proyectos\ordo` | Esqueleto (config/settings, Dockerfile, railway.json), tenancy que falla cerrado, membresías y permisos, plataforma, **tasa BCV**, PWA y visor PDF |
| Pediae | `C:\proyectos\pediae` | Pacientes (menores y representantes, duplicados), agenda, consultas, PDFs, **modo offline**, módulo Pediatría |
| Ginea | `C:\proyectos\ginea-saas` | Módulo Ginecología/Obstetricia, PDFs, reportes |
| Biolife | `C:\proyectos\biolife` | Método de documentación, services/selectors, auditoría, rectificaciones |

Detalle archivo por archivo: `docs/04_REUTILIZACION.md`.

## Stack fijo (no renegociar sin ADR)

- Python 3.14 · Django 5.2 LTS · PostgreSQL 16 (psycopg 3) — esquema compartido con FK `tenant`
- Bootstrap 5.3 + Bootstrap Icons + HTMX 2 **servidos localmente** (sin CDN; la PWA debe cargar sin red)
- WhiteNoise · Cloudinary (media) · ReportLab (PDF) · Sentry · openpyxl (Excel)
- Railway Pro: servicio web + servicio cron + PostgreSQL; entornos `staging` (develop) y `production` (main)
- Zona horaria `America/Caracas`. Hora en pantalla y PDF en **12 h (h:mm a. m./p. m.)**

## Reglas de arquitectura (obligatorias)

1. **Todo modelo de un tenant hereda de `TenantModel`** (`apps/core/tenancy.py`).
   `Modelo.objects` sin tenant activo devuelve **nada** (falla cerrado). `Modelo.todos` solo
   en comandos, admin y migraciones.
2. **Vistas delgadas.** Escrituras en `services.py`, lecturas complejas en `selectors.py`.
   Una vista valida, llama a un service/selector y responde. Nada de escrituras en GET.
3. **El núcleo no conoce a las especialidades.** `apps/clinica` nunca importa
   `apps/especialidades/*`. Las especialidades se registran en `apps/clinica/registro.py`.
4. **Permisos solo en `apps/core/permisos.py`** (`@requiere('codigo')`). Nunca `if rol == ...`.
5. Formularios heredan `FormBase` (rehace querysets por tenant).
6. **Datos clínicos: nada de borrado físico.** Consulta cerrada = inmutable; se corrige con
   *enmienda* (ADR-010). Toda lectura de historia queda en la auditoría.
7. Montos: USD como moneda base; **la tasa se congela** en cada cargo y pago (ADR-011).
8. Adjuntos clínicos y PDFs **nunca** en URL pública permanente (Cloudinary `authenticated`
   o vista con login).

## Cómo trabajamos

- **Una sesión = una fase** de `docs/roadmap/`. No mezclar fases.
- El `.md` de una fase se redacta al **iniciar** esa fase (solo la 01 viene completa).
- **No entregar ZIP ni bundles.** Un bloque por archivo con su ruta; si el archivo existe,
  solo el fragmento que cambia con 2–3 líneas de contexto. Darwin aplica a mano.
- Más de 5 archivos → primero el índice de cambios y esperar confirmación.
- Si hay más de un camino razonable: **exponer opciones y esperar decisión**.
- Cerrar cada entrega con checklist de verificación y lista explícita de lo **incompleto/faltante**.
- Entorno: VS Code + PowerShell en Windows. **Verificar el venv como primer paso.**

## Comandos base (PowerShell)

```powershell
cd C:\proyectos\ordo-salud
.\venv\Scripts\Activate.ps1
python -c "import sys; print(sys.executable)"   # debe terminar en ...\ordo-salud\venv\...
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test tests
```

## Al cerrar cada sesión (sin excepción)

1. Actualizar `docs/ESTADO.md`: fase, hecho, pendiente, próximo paso, lo que quedó roto.
2. Decisión estructural → nueva entrada en `docs/DECISIONES.md` (append-only).
3. Fase cerrada → resumen a `docs/HISTORIAL.md` y quitar el detalle de `ESTADO.md`.
4. `TODO` en código siempre con fase: `# TODO(FASE 08): validar solapamiento`.
