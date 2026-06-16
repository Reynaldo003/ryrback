# CrmConformidad/migrations/0012_auto_20260605_1030.py
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('CrmConformidad', '0011_alter_usuario_agencia'),
    ]

    operations = [
        migrations.CreateModel(
            name='FirebaseToken',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token', models.TextField(unique=True)),
                ('creado', models.DateTimeField(auto_now_add=True)),
                ('usuario', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='firebase_tokens', to='CrmConformidad.usuario')),
            ],
            options={
                'db_table': 'firebase_tokens',
                'managed': True,
            },
        ),
    ]