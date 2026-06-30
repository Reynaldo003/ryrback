from django.db import models


class Bitacora(models.Model):
    folio = models.CharField(max_length=30, unique=True)

    chasis_vin = models.CharField(max_length=50)
    fecha_ingreso = models.DateField(null=True, blank=True)
    anio_modelo_color = models.CharField(max_length=100, blank=True)
    responsable = models.CharField(max_length=150)

    fecha_captura = models.DateTimeField()
    creado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.folio


class Reactivo(models.Model):
    ESTADO_CHOICES = [
        ("si", "Sí"),
        ("no", "No"),
        ("na", "N/A"),
    ]

    bitacora = models.ForeignKey(
        Bitacora, related_name="reactivos", on_delete=models.CASCADE
    )
    reactivo_id = models.PositiveIntegerField()  # id de la pregunta (1-12)
    titulo = models.CharField(max_length=200)
    estado = models.CharField(max_length=2, choices=ESTADO_CHOICES, null=True, blank=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        ordering = ["reactivo_id"]

    def __str__(self):
        return f"{self.bitacora.folio} - {self.titulo}"


def ruta_evidencia(instance, filename):
    return f"bitacora_mantenimiento/{instance.reactivo.bitacora.folio}/{instance.reactivo.reactivo_id}/{filename}"


class Evidencia(models.Model):
    reactivo = models.ForeignKey(
        Reactivo, related_name="evidencias", on_delete=models.CASCADE
    )
    archivo = models.FileField(upload_to=ruta_evidencia)
    subido_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.archivo.name