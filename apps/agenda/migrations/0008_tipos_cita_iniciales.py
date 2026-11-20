"""Tipos iniciales de cita para consultorios existentes; no altera los personalizados."""
from django.db import migrations


TIPOS = (
    ('PRIMERA', 'Primera consulta'),
    ('CONTROL', 'Control'),
    ('EMERGENCIA', 'Emergencia'),
    ('OTRA', 'Otra'),
)


def poblar_tipos(apps, schema_editor):
    TipoCita = apps.get_model('agenda', 'TipoCita')
    Tenant = apps.get_model('plataforma', 'Tenant')
    alias = schema_editor.connection.alias
    for tenant_id in Tenant._base_manager.using(alias).values_list('pk', flat=True).iterator():
        for codigo, nombre in TIPOS:
            TipoCita._base_manager.db_manager(alias).get_or_create(
                tenant_id=tenant_id, nombre=nombre,
                defaults={'tipo_consulta': codigo, 'duracion_min': 30, 'activo': True},
            )


class Migration(migrations.Migration):
    dependencies = [('agenda', '0007_servicios_previstos_cita')]
    operations = [migrations.RunPython(poblar_tipos, migrations.RunPython.noop)]
