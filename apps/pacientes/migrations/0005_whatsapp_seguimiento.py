from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('pacientes', '0004_nivel_instruccion')]

    operations = [
        migrations.AddField(
            model_name=modelo,
            name='whatsapp_seguimiento',
            field=models.CharField(blank=True, editable=False, max_length=15),
        )
        for modelo in ('paciente', 'representante')
    ]
