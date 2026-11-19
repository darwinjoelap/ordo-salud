from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('clinica', '0010_observacion_importante')]

    operations = [
        migrations.AddField(
            model_name='consulta',
            name='inicio_independiente',
            field=models.UUIDField(null=True, unique=True, editable=False),
        ),
    ]
