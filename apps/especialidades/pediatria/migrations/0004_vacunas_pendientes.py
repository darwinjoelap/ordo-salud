from django.db import migrations
from django.db.models import Max


def agregar_seccion(apps, schema_editor):
    db = schema_editor.connection.alias
    especialidad = apps.get_model('plataforma', 'Especialidad').objects.using(db).filter(codigo='pediatria').first()
    if especialidad is None:
        # En una instalación nueva, post_migrate crea el catálogo y las plantillas con la definición actual.
        return
    secciones = apps.get_model('clinica', 'SeccionClinica').objects.using(db)
    plantillas = apps.get_model('clinica', 'PlantillaHistoria').objects.using(db)
    items = apps.get_model('clinica', 'PlantillaSeccion').objects.using(db)
    seccion, _ = secciones.get_or_create(
        codigo='ped.vacunas_pendientes', tenant_id=None,
        defaults={
            'nombre': 'Vacunas pendientes', 'especialidad_id': especialidad.pk, 'orden': 95,
            'tipo': 'MODULO', 'ambito': 'CONSULTA', 'version': 1,
            'esquema': {'campos': [{'clave': 'notas', 'tipo': 'texto_largo', 'etiqueta': 'Anotaciones', 'filas': 3}]},
        },
    )
    vigentes = plantillas.filter(especialidad_id=especialidad.pk, activa=True)
    for plantilla in vigentes.annotate(ultimo_orden=Max('items__orden')).iterator(chunk_size=500):
        items.get_or_create(
            plantilla_id=plantilla.pk, seccion_id=seccion.pk,
            defaults={'tenant_id': plantilla.tenant_id, 'orden': (plantilla.ultimo_orden or 0) + 10},
        )


class Migration(migrations.Migration):
    dependencies = [
        ('clinica', '0015_exoneracion_atencion'),
        ('esp_pediatria', '0003_catalogo_inicial'),
    ]
    operations = [migrations.RunPython(agregar_seccion, migrations.RunPython.noop)]
