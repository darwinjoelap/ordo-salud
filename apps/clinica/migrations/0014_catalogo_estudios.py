"""Catálogo de exámenes por consultorio y nombres congelados en estudios preoperatorios."""
import django.db.models.deletion
import django.db.models.manager
from django.conf import settings
from django.db import migrations, models




INICIALES = (
    ('LAB', 'Hemograma completo'),
    ('LAB', 'Glicemia'),
    ('LAB', 'Urea'),
    ('LAB', 'Creatinina sérica'),
    ('LAB', 'Electrolitos séricos'),
    ('LAB', 'Tiempo de protrombina (TP / INR)'),
    ('LAB', 'Tiempo parcial de tromboplastina (TTPa)'),
    ('LAB', 'Examen general de orina'),
    ('LAB', 'Hemoglobina glicosilada (HbA1c)'),
    ('LAB', 'Grupo sanguíneo y factor Rh'),
    ('ECG', 'Electrocardiograma de 12 derivaciones'),
    ('RX', 'Radiografía de tórax'),
)


def crear_sugerencias(apps, schema_editor):
    import unicodedata

    Tenant = apps.get_model('plataforma', 'Tenant')
    Catalogo = apps.get_model('clinica', 'EstudioCatalogo')
    alias = schema_editor.connection.alias
    for tenant_id in Tenant._base_manager.using(alias).values_list('pk', flat=True).iterator():
        for categoria, nombre in INICIALES:
            texto = unicodedata.normalize('NFKD', nombre.casefold())
            normalizado = ''.join(ch for ch in texto if not unicodedata.combining(ch))
            Catalogo._base_manager.db_manager(alias).get_or_create(
                tenant_id=tenant_id, nombre_normalizado=normalizado,
                defaults={'nombre': nombre, 'categoria': categoria, 'activo': True},
            )


class Migration(migrations.Migration):
    dependencies = [
        ('clinica', '0013_preoperatorio_valoracion_informe'),
        ('plataforma', '0006_excedente_dictado'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='EstudioCatalogo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('creado_en', models.DateTimeField(auto_now_add=True, verbose_name='Creado')),
                ('actualizado_en', models.DateTimeField(auto_now=True, verbose_name='Actualizado')),
                ('nombre', models.CharField(max_length=200)),
                ('nombre_normalizado', models.CharField(editable=False, max_length=220)),
                ('categoria', models.CharField(choices=[('LAB', 'Laboratorio'), ('ECG', 'Electrocardiograma'),
                                                        ('RX', 'Radiografía / imágenes'), ('OTRO', 'Otros estudios')],
                                               max_length=4)),
                ('descripcion', models.CharField(blank=True, max_length=500)),
                ('activo', models.BooleanField(default=True)),
                ('creado_por', models.ForeignKey(blank=True, editable=False, null=True,
                    on_delete=django.db.models.deletion.SET_NULL, related_name='+',
                    to=settings.AUTH_USER_MODEL, verbose_name='Creado por')),
                ('tenant', models.ForeignKey(editable=False, on_delete=django.db.models.deletion.PROTECT,
                    related_name='+', to='plataforma.tenant', verbose_name='Tenant')),
            ],
            options={
                'ordering': ['categoria', 'nombre'],
                'base_manager_name': 'todos',
                'constraints': [models.UniqueConstraint(fields=('tenant', 'nombre_normalizado'),
                    name='estudio_catalogo_tenant_nombre_unico')],
            },
            managers=[
                ('objects', django.db.models.manager.Manager()),
                ('todos', django.db.models.manager.Manager()),
            ],
        ),
        migrations.AddField(
            model_name='estudiopreoperatorio', name='catalogo',
            field=models.ForeignKey(blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT, related_name='registros_preoperatorios',
                to='clinica.estudiocatalogo'),
        ),
        migrations.AddField(
            model_name='estudiopreoperatorio', name='nombre',
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name='estudiopreoperatorio', name='unidad',
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AlterField(
            model_name='estudiopreoperatorio', name='resultado',
            field=models.TextField(blank=True, default='', max_length=3000),
        ),
        migrations.RunPython(crear_sugerencias, migrations.RunPython.noop),
    ]
