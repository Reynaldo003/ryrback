
from django.db import migrations, models
class Migration(migrations.Migration):

    dependencies = [
        ('citas', '0011_cita_citas_fecha_asesor_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='cita',
            name='vin',
            field=models.CharField(blank=True, default='', max_length=32),
        ),
        migrations.AddField(
            model_name='cita',
            name='avaluo_cerrado',
            field=models.BooleanField(default=False),
        ),
    ]
