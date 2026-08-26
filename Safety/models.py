#Safety/models.py
from django.db import models
from django.utils import timezone


class ReporteSafety(models.Model):
    id_reporte = models.AutoField(primary_key=True)
    creado = models.DateTimeField(auto_now_add=True)
    fecha_reporte = models.DateField(default=timezone.localdate)

    reportante = models.CharField(max_length=200)
    agencia = models.CharField(max_length=200)

    nombre_cliente = models.CharField(max_length=200)
    orden_servicio = models.CharField(max_length=100)
    tecnico_reparo = models.CharField(max_length=200)
    valido_control_calidad = models.CharField(max_length=200)

    checklist = models.JSONField(default=list, blank=True)

    comentarios_finales = models.TextField(blank=True, default="")

    class Meta:
        db_table = "safety_reportes"
        managed = True
        ordering = ["-creado", "-id_reporte"]

    def __str__(self):
        return f"{self.orden_servicio} - {self.nombre_cliente}"


class AdjuntoReporteSafety(models.Model):
    TIPO_ADJUNTO_CHOICES = [
        ("foto", "Foto"),
        ("video", "Video"),
        ("archivo", "Archivo"),
    ]

    id_adjunto = models.AutoField(primary_key=True)

    reporte = models.ForeignKey(
        ReporteSafety,
        on_delete=models.CASCADE,
        related_name="adjuntos",
    )

    # Vacío = adjunto general del reporte
    # Con valor = ligado al id del punto del checklist
    punto_checklist_id = models.CharField(
        max_length=100,
        blank=True,
        default="",
        db_index=True,
    )

    tipo_adjunto = models.CharField(
        max_length=20,
        choices=TIPO_ADJUNTO_CHOICES,
        default="archivo",
    )

    archivo = models.FileField(upload_to="safety/reportes/%Y/%m/%d/")
    nombre_original = models.CharField(max_length=255, blank=True, default="")
    tipo_mime = models.CharField(max_length=200, blank=True, default="")
    tamano_bytes = models.PositiveBigIntegerField(default=0)

    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "safety_reportes_adjuntos"
        managed = True
        ordering = ["id_adjunto"]
        indexes = [
            models.Index(fields=["reporte", "punto_checklist_id"], name="safety_rep_punto_idx"),
            models.Index(fields=["reporte", "tipo_adjunto"], name="safety_rep_tipo_idx"),
        ]

    def __str__(self):
        return self.nombre_original or f"Adjunto {self.id_adjunto}"