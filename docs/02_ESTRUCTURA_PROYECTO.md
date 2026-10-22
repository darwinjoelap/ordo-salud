# 02 — Estructura del proyecto

```
ordo-salud/
├── CLAUDE.md                      ← contexto permanente (raíz)
├── README.md
├── .env.example
├── .gitignore  .dockerignore  .gitattributes
├── Dockerfile                     ← de Ordo
├── railway.json                   ← web: preDeploy migrate, healthcheck /salud/
├── railway.cron.json              ← cron: tareas_programadas
├── requirements.txt               ← producción
├── requirements-dev.txt           ← -r requirements.txt + ruff, coverage, factory-boy
├── pyproject.toml                 ← ruff
├── manage.py                      ← DJANGO_SETTINGS_MODULE=config.settings.dev
│
├── config/
│   ├── settings/{base,dev,prod}.py
│   ├── urls.py                    ← rutas; /<slug>/ de entrada AL FINAL
│   ├── wsgi.py  asgi.py
│
├── apps/
│   ├── core/
│   │   ├── tenancy.py             ← TenantModel, tenant_actual(), usando_tenant()
│   │   ├── middleware.py          ← TenantActivoMiddleware
│   │   ├── permisos.py            ← PERMISOS rol → acciones, @requiere
│   │   ├── forms.py               ← FormBase, validar_unico_en_tenant
│   │   ├── modelos.py             ← Auditable (creado_en, actualizado_en, creado_por)
│   │   ├── auditoria.py           ← Auditoria + registrar()
│   │   ├── excepciones.py         ← ErrorDeNegocio + middleware que lo muestra como mensaje
│   │   ├── fechas.py              ← edad exacta, edad en meses/días, formato 12 h
│   │   ├── pdf.py                 ← encabezado_tenant(), pie_tenant(), firma_profesional()
│   │   ├── secuencias.py          ← siguiente_numero('REC')
│   │   ├── pwa.py                 ← manifest, sw.js, /offline/, /instalar/, /visor/
│   │   ├── context_processors.py
│   │   ├── templatetags/ordo.py  ← hora12, usd, bs, edad, icon
│   │   └── management/commands/tareas_programadas.py
│   ├── plataforma/                ← Tenant, Plan, Suscripcion, TenantEspecialidad, panel
│   ├── usuarios/                  ← Usuario, backends.py, Mi perfil, cambio de clave
│   ├── equipo/                    ← Membresia, PerfilProfesional, Especialidad, gestión del equipo
│   ├── configuracion/             ← ConfiguracionTenant, Lugar
│   ├── tasas/                     ← copia de Ordo
│   ├── pacientes/                 ← Paciente, Representante, AntecedenteBase
│   ├── agenda/
│   ├── clinica/
│   │   ├── models/                ← paquete: secciones.py, plantillas.py, consulta.py, prescripcion.py…
│   │   ├── registro.py            ← registro de especialidades, secciones y cálculos
│   │   ├── esquemas.py            ← validador del esquema de campos
│   │   ├── formularios.py         ← construye el form Django desde un esquema
│   │   ├── services.py  selectors.py
│   │   └── templates/clinica/secciones/  ← parciales por tipo de campo
│   ├── cobros/
│   ├── documentos/
│   ├── reportes/
│   ├── offline/                   ← de Pediae
│   ├── dictado/                   ← Fase 17
│   └── especialidades/
│       ├── __init__.py
│       ├── general/
│       ├── pediatria/
│       │   ├── apps.py            ← ready(): registrar especialidad
│       │   ├── especialidad.py    ← declaración (secciones, cálculos, documentos, plantillas)
│       │   ├── secciones.py       ← esquemas de las secciones del módulo
│       │   ├── calculos.py        ← percentiles OMS, dosis por kg
│       │   ├── models.py          ← VacunaAplicada, PesquisaRealizada…
│       │   ├── documentos.py      ← constancia niño sano, lactancia
│       │   ├── fixtures/          ← esquema PAI, curvas OMS
│       │   └── templates/pediatria/
│       ├── ginecologia/
│       └── cardiologia/
│
├── templates/                     ← base.html, parciales comunes, errores
├── static/
│   ├── vendor/                    ← bootstrap, bootstrap-icons, htmx (sin sourceMappingURL)
│   ├── css/ordo-salud.css
│   ├── js/{pwa.js, offline.js, secciones.js}
│   └── img/marca/                 ← logo, iconos PWA (incl. maskable y apple-touch-icon)
├── tests/                         ← python manage.py test tests
│   ├── test_aislamiento.py        ← obligatorio desde la Fase 02
│   └── …
├── scripts/                       ← utilidades fuera de Django (migración desde Ginea/Pediae)
└── docs/
    ├── README.md
    ├── 00_ARQUITECTURA.md  01_MODELO_DATOS.md  02_ESTRUCTURA_PROYECTO.md
    ├── 03_CONVENCIONES.md  04_REUTILIZACION.md  05_GUIA_ESPECIALIDADES.md
    ├── DECISIONES.md  ESTADO.md  HISTORIAL.md
    ├── DESPLIEGUE_RAILWAY.md      ← se escribe en la Fase 01
    └── roadmap/
        ├── 00_INDICE.md
        ├── _PLANTILLA_FASE.md
        └── NN_nombre.md
```

Notas:
- `config/` y no `ordo_salud/` como paquete del proyecto (evita choque de nombres; igual que Ordo y Biolife).
- `apps/clinica/models/` es paquete porque el motor tendrá varios archivos; el resto de apps usa `models.py`.
- Las especialidades viven todas bajo `apps/especialidades/`; `INSTALLED_APPS` las lista una por una
  (habilitar = instalar app + `sincronizar_especialidades` + habilitar en el tenant).
