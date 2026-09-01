from django.db import models
from django.utils import timezone
from citas.models import ClienteComercial


class SolicitudCredito(models.Model):
    cliente = models.ForeignKey(
        ClienteComercial,
        db_column="id_cliente",
        on_delete=models.PROTECT,
        related_name="solicitud_credito",
    )

    agencia = models.CharField(max_length=120, default="", null=True)
    id_soli_cred = models.CharField(max_length=120, default="")
    producto_financiero = models.CharField(max_length=120, default="")
    plazo_meses = models.CharField(max_length=50, default="", null=True, blank=True)
    monto_financiero = models.CharField(max_length=120, default="", null=True, blank=True)
    auto_interes = models.CharField(max_length=255, default="")
    canal_origen = models.CharField(max_length=200, default="", blank=True)
    asesor_ventas = models.CharField(max_length=200, default="", null=True, blank=True)
    estado_financiamiento = models.CharField(max_length=200, default="")
    estado_compra = models.CharField(max_length=200, default="")
    fecha_respuesta = models.DateTimeField(null=True)
    comentarios = models.TextField(max_length=2000, default="", null=True, blank=True)

    creado = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "solicitud_credito"
        managed = True
        ordering = ["-creado"]

    def __str__(self):
        return f"{self.cliente.nombre or 'Cliente'} - {self.cliente.telefono}"


class LongDrive(models.Model):
    cliente = models.ForeignKey(
        ClienteComercial,
        db_column="id_cliente",
        on_delete=models.PROTECT,
        related_name="long_drive",
    )

    agencia = models.CharField(max_length=120, default="", null=True)
    chasis = models.CharField(max_length=120, default="")
    producto_long_drive = models.CharField(max_length=120, default="")
    tipo_venta = models.CharField(max_length=100, default="")
    fecha_entrega = models.DateTimeField(null=True)

    creado = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "long_drive"
        managed = True
        ordering = ["-creado"]

    def __str__(self):
        return f"{self.cliente.nombre or 'Cliente'} - {self.producto_long_drive}"