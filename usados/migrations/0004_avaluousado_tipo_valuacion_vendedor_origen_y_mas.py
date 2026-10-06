# Generated on 2026-10-05 - campos Seguimiento + solicitud estilo Chevrolet

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('usados', '0003_avaluousado_color_avaluousado_costo_estimado_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='avaluousado',
            name='tipo_valuacion',
            field=models.CharField(blank=True, default='Valoración', max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='avaluousado',
            name='vendedor',
            field=models.CharField(blank=True, default='', max_length=200, null=True),
        ),
        migrations.AddField(
            model_name='avaluousado',
            name='agenda_valuacion',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='avaluousado',
            name='origen_valuacion',
            field=models.CharField(blank=True, default='', max_length=120, null=True),
        ),
        migrations.AddField(
            model_name='avaluousado',
            name='fecha_toma_cuenta',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='avaluousado',
            name='fecha_finalizacion',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='avaluousado',
            name='observaciones',
            field=models.TextField(blank=True, default='', max_length=4000, null=True),
        ),
        migrations.AddField(
            model_name='avaluousado',
            name='comentario_ticket',
            field=models.TextField(blank=True, default='Valuación', max_length=2000, null=True),
        ),
    ]
