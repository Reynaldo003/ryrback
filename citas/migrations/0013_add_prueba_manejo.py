
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('citas', '0012_add_vin_avaluo_cerrado'),
    ]

    operations = [
        migrations.AddField(
            model_name='cita',
            name='prueba_manejo',
            field=models.BooleanField(default=False),
        ),
    ]
