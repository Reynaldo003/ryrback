#usados/models.py
from pathlib import Path
import uuid

from django.db import models
from citas.models import ClienteComercial


def avaluo_evidencia_upload_to(instance, filename):
    ext = Path(filename).suffix.lower()
    return f"avaluos/evidencias/{instance.avaluo_id}/{uuid.uuid4().hex}{ext}"


class AvaluoUsado(models.Model):
    cliente = models.ForeignKey(
        ClienteComercial,
        db_column="id_cliente",
        on_delete=models.PROTECT,
        related_name="avaluos_usados",
    )

    agencia = models.CharField(max_length=120, default="", null=True, blank=True)
    fecha_avaluo = models.DateTimeField(null=True, blank=True)
    asesor_ventas = models.CharField(max_length=200, default="", null=True, blank=True)

    marca_auto = models.CharField(max_length=120, default="", null=True, blank=True)
    modelo = models.CharField(max_length=120, default="", null=True, blank=True)
    anio_modelo = models.CharField(max_length=10, default="", null=True, blank=True)
    serie = models.CharField(max_length=120, default="", null=True, blank=True)
    kilometraje = models.CharField(max_length=50, default="", null=True, blank=True)

    precio_guia = models.CharField(max_length=120, default="", null=True, blank=True)
    costo_reparacion = models.CharField(max_length=120, default="", null=True, blank=True)
    costo_estimado = models.CharField(max_length=120, default="", null=True, blank=True)
    oferta_economica = models.CharField(max_length=120, default="", null=True, blank=True)

    color = models.CharField(max_length=120, default="", null=True, blank=True)
    descripcion = models.TextField(max_length=4000, default="", null=True, blank=True)

    ganador_subasta = models.CharField(max_length=200, default="", null=True, blank=True)
    etapa_proceso = models.CharField(max_length=200, default="", null=True, blank=True)
    tipo_toma = models.CharField(max_length=100, default="", null=True, blank=True)
    comentarios = models.TextField(max_length=2000, default="", null=True, blank=True)

    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "avaluos"
        managed = True
        ordering = ["-creado"]

    def __str__(self):
        nombre = self.cliente.nombre or "Cliente"
        telefono = self.cliente.telefono or "Sin teléfono"
        return f"{nombre} - {self.marca_auto or ''} {self.modelo or ''} - {telefono}".strip()


class AvaluoUsadoEvidencia(models.Model):
    TIPO_IMAGEN = "imagen"
    TIPO_VIDEO = "video"
    TIPO_ARCHIVO = "archivo"

    TIPOS = (
        (TIPO_IMAGEN, "Imagen"),
        (TIPO_VIDEO, "Video"),
        (TIPO_ARCHIVO, "Archivo"),
    )

    avaluo = models.ForeignKey(
        AvaluoUsado,
        db_column="id_avaluo",
        on_delete=models.CASCADE,
        related_name="evidencias",
    )
    archivo = models.FileField(upload_to=avaluo_evidencia_upload_to)
    nombre = models.CharField(max_length=255, default="", blank=True)
    tipo = models.CharField(max_length=20, choices=TIPOS, default=TIPO_ARCHIVO)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "avaluos_evidencias"
        managed = True
        ordering = ["-creado"]

    def __str__(self):
        return self.nombre or f"Evidencia {self.pk}"


class ConceptoAvaluo(models.Model):
    avaluo = models.ForeignKey(
        AvaluoUsado,
        db_column="id_avaluo",
        on_delete=models.CASCADE,
        related_name="conceptos",
    )
    descripcion = models.TextField(max_length=4000, default="", blank=True)
    costo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "conceptos_avaluos"
        managed = True
        ordering = ["id"]

    def __str__(self):
        return self.descripcion or f"Concepto {self.pk}"
 