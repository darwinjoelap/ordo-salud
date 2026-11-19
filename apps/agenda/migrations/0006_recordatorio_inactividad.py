from django.conf import settings
from django.db import migrations, models
from django.db.models import deletion, manager


class Migration(migrations.Migration):
    dependencies = [
        ('agenda', '0005_etiqueta_intento_recordatorio'),
        ('pacientes', '0005_whatsapp_seguimiento'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='RecordatorioInactividad',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('creado_en', models.DateTimeField(auto_now_add=True, verbose_name='Creado')),
                ('actualizado_en', models.DateTimeField(auto_now=True, verbose_name='Actualizado')),
                ('creado_por', models.ForeignKey(blank=True, editable=False, null=True, on_delete=deletion.SET_NULL,
                                                 related_name='+', to=settings.AUTH_USER_MODEL,
                                                 verbose_name='Creado por')),
                ('tenant', models.ForeignKey(editable=False, on_delete=deletion.PROTECT, related_name='+',
                                             to='plataforma.tenant', verbose_name='Tenant')),
                ('paciente', models.ForeignKey(on_delete=deletion.PROTECT, related_name='+', to='pacientes.paciente')),
                ('ultima_asistencia', models.DateField()),
                ('meses', models.PositiveSmallIntegerField()),
                ('canal', models.CharField(default='WHATSAPP', editable=False, max_length=10)),
                ('estado', models.CharField(choices=[('INTENTO', 'Intento registrado'),
                                                    ('ENVIADO', 'Envío declarado'),
                                                    ('IGNORADO', 'Ignorado')], max_length=10)),
                ('resuelto_por', models.ForeignKey(editable=False, null=True, on_delete=deletion.SET_NULL,
                                                    related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'constraints': [
                models.UniqueConstraint(fields=('tenant', 'paciente', 'ultima_asistencia'),
                                        name='recordatorio_inactividad_episodio_unico'),
            ]},
            managers=[('objects', manager.Manager()), ('todos', manager.Manager())],
        ),
    ]
