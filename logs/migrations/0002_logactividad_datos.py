# Snapshot restaurable de eliminaciones (campo datos)
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("logs", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="logactividad",
            name="datos",
            field=models.JSONField(blank=True, null=True),
        ),
    ]
