from django.db import migrations


def cargar_personal_tuxtepec(apps, schema_editor):
    Asesor = apps.get_model("Digitales", "Asesor")
    Tecnico = apps.get_model("Digitales", "Tecnico")

    asesores = [
        "Isis Frutos",
        "Ana Andrade",
    ]

    for nombre in asesores:
        Asesor.objects.get_or_create(
            nombre=nombre,
            agencia="VW Tuxtepec",
            defaults={
                "telefono": "",
                "tipo_asesor": "Servicio",
                "area": "PostVenta",
                "activo": True,
            },
        )

    tecnicos = [
        "Lorenzo Bernardino",
        "Gustavo Ávalos",
        "Abel Jiménez",
    ]

    for nombre in tecnicos:
        Tecnico.objects.get_or_create(
            nombre=nombre,
            agencia="VW Tuxtepec",
            tipo_personal="Tecnico",
            defaults={
                "activo": True,
            },
        )

    refacciones = [
        "Itzel Lozano",
        "José Manuel Hernández",
        "Miguel Ángel Morales",
    ]

    for nombre in refacciones:
        Tecnico.objects.get_or_create(
            nombre=nombre,
            agencia="VW Tuxtepec",
            tipo_personal="Refacciones",
            defaults={
                "activo": True,
            },
        )


def eliminar_personal_tuxtepec(apps, schema_editor):
    Asesor = apps.get_model("Digitales", "Asesor")
    Tecnico = apps.get_model("Digitales", "Tecnico")

    Asesor.objects.filter(
        nombre__in=[
            "Isis Frutos",
            "Ana Andrade",
        ],
        agencia="VW Tuxtepec",
    ).delete()

    Tecnico.objects.filter(
        nombre__in=[
            "Lorenzo Bernardino",
            "Gustavo Ávalos",
            "Abel Jiménez",
            "Itzel Lozano",
            "José Manuel Hernández",
            "Miguel Ángel Morales",
        ],
        agencia="VW Tuxtepec",
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("Digitales", "0031_tecnico"),
    ]

    operations = [
        migrations.RunPython(
            cargar_personal_tuxtepec,
            eliminar_personal_tuxtepec,
        ),
    ]
