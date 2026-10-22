from django.apps import AppConfig


class GinecologiaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.especialidades.ginecologia'
    label = 'esp_ginecologia'
    verbose_name = 'Especialidad: Ginecología y obstetricia'

    def ready(self):
        from . import especialidad  # noqa: F401  (registra la especialidad, sus secciones y ganchos)
