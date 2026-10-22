# Fase 01 — Esqueleto y despliegue a staging

**Modelo sugerido:** Sonnet
**Depende de:** Fase 00 (ADR-002, 003, 004, 016 aceptados)
**ADR relacionados:** 002, 016
**Se apoya en:** `C:\proyectos\ordo` → `config/`, `Dockerfile`, `railway.json`, `apps/core/views.py` (`salud`),
`static/vendor/`, `templates/base.html`, `docs/DESPLIEGUE_RAILWAY.md`

## Objetivo
Proyecto Django vacío pero con la forma definitiva (settings por entorno, apps base, marca,
PWA mínima) corriendo en local y en **Railway staging**, con tests y `check --deploy` en verde.

## Fuera de alcance
Tenants, usuarios propios y permisos (Fase 02). Nada clínico. Cron de tasa (Fase 04).

## Decisiones previas a ejecutar
1. **Python**: confirmar `py -3.14 --version` en la máquina (Ordo ya usa 3.14). Si no está, usar
   3.13 y registrar ADR.
2. **Repositorio**: `github.com/darwinjoelap/ordo-salud` privado, ramas `main` y `develop`.
3. **Railway**: proyecto nuevo `ordo-salud` (no dentro del de Ordo) con servicios `web` y
   `Postgres`, entorno `staging` desde `develop`. El cron se agrega en la Fase 04.
4. **Marca**: ¿hay logo de Ordo Salud? (`C:\proyectos\marca`). Si no, marca de texto
   provisional y color primario provisional `#0F6E8C`; los iconos PWA se generan en la Fase 12.

## Tareas
- [ ] 1. Crear carpeta, venv y verificar intérprete
  ```powershell
  mkdir C:\proyectos\ordo-salud; cd C:\proyectos\ordo-salud
  py -3.14 -m venv venv
  .\venv\Scripts\Activate.ps1
  python -c "import sys; print(sys.executable)"   # ...\ordo-salud\venv\Scripts\python.exe
  ```
- [ ] 2. Copiar los `.md` de este paquete (ya están en `docs/` y `CLAUDE.md`) y `git init`.
- [ ] 3. `requirements.txt` = el de Ordo **sin** `beautifulsoup4`, `lxml` ni `cryptography` (entran en la
      Fase 04 con la tasa BCV); `openpyxl` se queda (reportes). `requirements-dev.txt` con debug-toolbar y ruff.
- [ ] 4. `django-admin startproject config .` y reemplazar por `config/settings/{base,dev,prod}.py` adaptados de Ordo:
  - `ORDO_VERSION` desde `RAILWAY_GIT_COMMIT_SHA`
  - `ORDO_APPS = ['apps.core']` (el resto se agrega en su fase)
  - Crear **desde ya** `apps.usuarios` con `Usuario(AbstractUser)` vacío y
    `AUTH_USER_MODEL = 'usuarios.Usuario'` (cambiarlo después obliga a rehacer migraciones)
  - Context processor `apps.core.context_processors.marca` (versión, nombre del producto)
  - `LANGUAGE_CODE='es-ve'`, `TIME_ZONE='America/Caracas'`
- [ ] 5. `apps/core`: `views.salud` (copiar de Ordo), `views.inicio` (placeholder con login requerido más adelante),
      `urls.py`, `templatetags/ordo.py` con `hora12` (h:mm a. m./p. m.) y su test.
- [ ] 6. `static/vendor/` copiado de Ordo (bootstrap, bootstrap-icons, htmx) y `static/css/ordo-salud.css` con variables
      `--marca`, `--lateral`.
- [ ] 7. `templates/base.html` adaptado de Ordo: barra superior, menú lateral, barra inferior móvil, bloque de mensajes,
      `<meta name="theme-color">`, `apple-mobile-web-app-capable`, área segura de iPhone (`env(safe-area-inset-*)`).
- [ ] 8. `Dockerfile`, `.dockerignore`, `railway.json` copiados de Ordo (healthcheck `/salud/`, preDeploy `migrate`).
- [ ] 9. `.env.example` adaptado; `.gitignore` (venv, .env, staticfiles, media, db.sqlite3, `__pycache__`).
- [ ] 10. `pyproject.toml` con ruff (line-length 110, py314).
- [ ] 11. `tests/test_basicos.py`: `/salud/` responde 200 `{"estado":"ok"}`; `hora12` convierte 13:05 → `1:05 p. m.`
- [ ] 12. Railway staging: variables (`DJANGO_SETTINGS_MODULE=config.settings.prod`, `SECRET_KEY`, `ALLOWED_HOSTS`,
      `CSRF_TRUSTED_ORIGINS`, `DATABASE_URL` referenciada de Postgres, Cloudinary, `SENTRY_DSN`) y primer deploy.
- [ ] 13. `docs/DESPLIEGUE_RAILWAY.md` adaptado de Ordo con los valores reales de Ordo Salud.

## Tests
- [ ] `python manage.py test tests` en SQLite
- [ ] Mismo comando contra PostgreSQL local (`$env:DATABASE_URL="postgres://..."`)
- [ ] `python manage.py check --deploy --settings=config.settings.prod` sin errores (con variables de prueba)
- [ ] `ruff check .` limpio

## Criterio de salida
- [ ] `https://<staging>.up.railway.app/salud/` → `{"estado": "ok"}`
- [ ] La página de inicio muestra la base visual en escritorio y en el teléfono
- [ ] Sentry recibe un error de prueba
- [ ] Commit en `develop`: `chore: esqueleto Ordo Salud y despliegue a staging`

## Verificación manual (Darwin)
1. Abrir staging en el iPhone y en Android: la barra inferior no queda debajo de la barra del sistema.
2. Railway → Deploy logs: se ven `migrate` y gunicorn arrancando.

## Cierre
- [ ] `docs/ESTADO.md` → Fase 01 cerrada, próximo: Fase 02
- [ ] ADR nuevos si cambió algo (versión de Python, nombre de servicios)
- [ ] `docs/HISTORIAL.md` con resumen
- [ ] Lista explícita de lo pendiente
