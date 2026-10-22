from django.apps import AppConfig


class CardiologiaPediatricaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.especialidades.cardiologia_pediatrica'
    label = 'esp_cardiologia_pediatrica'
    verbose_name = 'Especialidad: Cardiología pediátrica'

    def ready(self):
        from . import especialidad  # noqa: F401  (registra la especialidad, sus secciones y cálculos)
