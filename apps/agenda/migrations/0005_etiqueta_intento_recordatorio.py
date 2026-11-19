from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('agenda', '0004_paleta_ordo_salud')]

    operations = [
        migrations.AlterField(
            model_name='cita',
            name='recordatorio_en',
            field=models.DateTimeField('Intento de recordatorio', null=True, blank=True),
        ),
    ]
