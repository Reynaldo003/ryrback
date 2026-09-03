from django.db import migrations


def migrar_longdrive_formato_nuevo(apps, schema_editor):
    LongDrive = apps.get_model("Financieros", "LongDrive")

    concesionarios = {
        "vw cordoba": "2923",
        "vw córdoba": "2923",
        "vw orizaba": "2924",
    }

    for registro in LongDrive.objects.select_related("cliente").all():
        cliente = registro.cliente
        actualizaciones = {}

        if not registro.numero_serie and registro.chasis:
            actualizaciones["numero_serie"] = registro.chasis

        if not registro.cobertura and registro.producto_long_drive:
            actualizaciones["cobertura"] = registro.producto_long_drive

        if cliente:
            if not registro.nombre_razon_social and cliente.nombre:
                actualizaciones["nombre_razon_social"] = cliente.nombre

            if not registro.telefono_celular and cliente.telefono:
                actualizaciones["telefono_celular"] = cliente.telefono

            if not registro.correo_electronico and cliente.correo:
                actualizaciones["correo_electronico"] = cliente.correo

        agencia = (registro.agencia or "").strip()

        if agencia and not registro.concesionario:
            actualizaciones["concesionario"] = concesionarios.get(
                agencia.lower(),
                agencia,
            )

        if actualizaciones:
            LongDrive.objects.filter(pk=registro.pk).update(**actualizaciones)


class Migration(migrations.Migration):

    dependencies = [
        ("Financieros", "0007_longdrive_anio_and_more"),
    ]

    operations = [
        migrations.RunPython(
            migrar_longdrive_formato_nuevo,
            migrations.RunPython.noop,
        ),
    ]