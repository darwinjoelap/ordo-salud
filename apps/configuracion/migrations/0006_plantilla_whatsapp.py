"""ADR-058: el recordatorio de WhatsApp pasa a ser una plantilla editable completa.

El «mensaje adicional» que ya tuviera un consultorio se conserva: queda al final del mensaje estándar.
"""
from django.db import migrations, models

ESTANDAR = ('Hola {saludo}, le recordamos la cita {de_paciente}con {profesional} ({consultorio}) el {fecha} '
            'a las {hora} en {lugar}.')


def pasar_mensaje(apps, schema_editor):
    Config = apps.get_model('configuracion', 'ConfiguracionTenant')
    for c in Config.objects.exclude(mensaje_whatsapp=''):
        extra = (c.mensaje_whatsapp or '').strip()
        if extra:
            # llaves en el texto libre: se cambian por paréntesis para que no parezcan marcadores
            c.plantilla_whatsapp = f'{ESTANDAR}\n\n{extra.replace("{", "(").replace("}", ")")}'
            c.save(update_fields=['plantilla_whatsapp'])


def volver(apps, schema_editor):
    Config = apps.get_model('configuracion', 'ConfiguracionTenant')
    for c in Config.objects.exclude(plantilla_whatsapp=''):
        texto = c.plantilla_whatsapp
        c.mensaje_whatsapp = texto.split('\n\n', 1)[1] if texto.startswith(ESTANDAR) and '\n\n' in texto else ''
        c.save(update_fields=['mensaje_whatsapp'])


class Migration(migrations.Migration):

    dependencies = [
        ('configuracion', '0005_formula_sc'),
    ]

    operations = [
        migrations.AddField(
            model_name='configuraciontenant',
            name='plantilla_whatsapp',
            field=models.TextField(
                blank=True, verbose_name='Mensaje del recordatorio por WhatsApp',
                help_text='Marcadores: {saludo} {paciente} {de_paciente} {profesional} {consultorio} {fecha} {hora} '
                          '{lugar}. Vacío = mensaje estándar.'),
        ),
        migrations.RunPython(pasar_mensaje, volver),
        migrations.RemoveField(model_name='configuraciontenant', name='mensaje_whatsapp'),
    ]
