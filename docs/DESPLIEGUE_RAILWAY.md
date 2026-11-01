# Despliegue en Railway (demo y producción)

> Estado al 2026-10-24: el código está listo y el proyecto de Railway **todavía no existe**.
> Hasta el ~31 de octubre **no se toca `ordove.com`**: Let's Encrypt tiene bloqueado ese dominio (ver el documento de Ordo Lab).
> El demo va primero en la dirección `…up.railway.app`, por ruta (`/dra-sierra/`).

## Fase A — Demo en la dirección de Railway (se puede hacer hoy)

### A1. Proyecto y base de datos
- [ ] Railway → **New Project** → *Deploy from GitHub repo* → `ordo-salud`, rama `main` (o `develop`).
- [ ] En el mismo proyecto: **+ New → Database → PostgreSQL**.
- [ ] Servicio web → **Settings → Networking → Generate Domain** (queda `ordo-salud-production.up.railway.app` o parecido).

### A2. Variables del servicio web
| Variable | Valor |
|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.prod` |
| `SECRET_KEY` | una clave larga nueva (no la de desarrollo) |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (referencia de Railway) |
| `ALLOWED_HOSTS` | `ordo-salud-production.up.railway.app,healthcheck.railway.app` |
| `CSRF_TRUSTED_ORIGINS` | `https://ordo-salud-production.up.railway.app` |
| `BASE_DOMAIN` | **vacío por ahora** (todo por ruta) |
| `R2_BUCKET` | `ordo-salud-media` |
| `R2_ACCOUNT_ID` | el ID de cuenta (lo que va antes de `.r2.cloudflarestorage.com` en el endpoint) |
| `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` | las del token **ordo-salud-prod**. Sin R2 los archivos se pierden en cada despliegue |
| `GEMINI_API_KEY` | la clave **con facturación activa** (el nivel gratis usa los datos para entrenar). Sin clave, el dictado funciona en modo de prueba |
| `SENTRY_DSN` | opcional |

`railway.json` ya trae: build con `Dockerfile`, `migrate` antes de desplegar y healthcheck en `/salud/`.

### A3. Primer arranque
Railway → servicio web → **⋯ → Shell** (o `railway run` desde tu PC):
```bash
python manage.py probar_almacenamiento     # debe terminar en «Almacenamiento OK.»
python manage.py sincronizar_especialidades
python manage.py importar_cie10            # catálogo de diagnósticos
python manage.py createsuperuser           # tu cuenta de plataforma
python manage.py demo_cardiologia --consultorio dra-sierra --crear --usuario lsierra --clave "UNA-CLAVE-PARA-ELLA"
```
- [ ] `https://…up.railway.app/salud/` responde `{"estado": "ok"}`.
- [ ] `https://…up.railway.app/dra-sierra/` muestra su login con su marca; entra con `lsierra`.
- [ ] Plataforma (`/cuenta/entrar/?plataforma=1`) → consultorio → **Dictado por voz** activado y plan con minutos.
- [ ] Configuración del consultorio: banner (membrete) y **Fórmula de SC = Haycock** (ya viene así por la especialidad).

### A4. Tareas programadas (opcional en el demo)
Segundo servicio con el mismo repo y **Config file path = `railway.cron.json`** (corre `tareas_programadas` a las 07:00 de Venezuela: cierra consultas vencidas, tasa del BCV, recordatorios).

### A5. Antes de pasarle el demo
- [ ] Los pacientes del demo son **ficticios** (marcados `[DEMO]`). Se borran con
  `python manage.py demo_cardiologia --consultorio dra-sierra --borrar` cuando empiece con pacientes reales.
- [ ] Prueba de dictado real con la clave de Gemini (una consulta de 2–3 minutos) y revisar el costo en Google AI Studio.

## Fase B — Subdominio por consultorio (después del ~31 de octubre)

Objetivo: `https://dra-sierra.salud.ordove.com` (cada consultorio el suyo) y `https://admin.salud.ordove.com` (plataforma).

### B1. Railway
- [ ] Servicio web → Settings → Networking → **Custom Domain** → `*.salud.ordove.com` (comodín: 1 de los 2 dominios del plan Hobby).
- [ ] Railway muestra los registros DNS que pide (el CNAME del comodín y el/los de verificación `_acme-challenge`).

### B2. Cloudflare (zona `ordove.com`)
- [ ] Crear los registros **exactamente** como los da Railway, con la nube en **gris (DNS only)**. Con la nube naranja el
  certificado comodín no se emite.
- [ ] Esperar a que Railway marque el dominio como verificado y con certificado.

### B3. Variables (cambiar y redesplegar)
| Variable | Valor |
|---|---|
| `BASE_DOMAIN` | `salud.ordove.com` |
| `ALLOWED_HOSTS` | `.salud.ordove.com,ordo-salud-production.up.railway.app,healthcheck.railway.app` |
| `CSRF_TRUSTED_ORIGINS` | `https://*.salud.ordove.com,https://ordo-salud-production.up.railway.app` |

**No** definir `SESSION_COOKIE_DOMAIN` ni `CSRF_COOKIE_DOMAIN`: cada subdominio guarda su propia sesión, así una
sesión de un consultorio nunca vale en otro.

### B4. Comprobar
- [ ] `https://dra-sierra.salud.ordove.com/` → login de la Dra. Sierra (sin escribir ruta).
- [ ] `https://admin.salud.ordove.com/` → login de plataforma; el panel funciona.
- [ ] `https://dra-sierra.salud.ordove.com/plataforma/` → 404 (la plataforma solo vive en `admin.`).
- [ ] La dirección vieja `…up.railway.app/dra-sierra/` sigue funcionando (respaldo).
- [ ] En el teléfono de la doctora: desinstalar la app vieja (si la instaló con la dirección de Railway) e instalarla
  desde `dra-sierra.salud.ordove.com`. Los borradores sin conexión de la dirección vieja no pasan solos: que sincronice antes.

### Notas
- El enlace de cada consultorio debe ser válido como subdominio: minúsculas, números y guiones (`dralyna`, `dra-sierra`).
  La plataforma ya no acepta otro formato. Reservados: `admin`, `www`, `app`, `api`, `mail`, etc.
- Si un consultorio cambia de enlace, cambia su subdominio: avisarle y reinstalar la app.
