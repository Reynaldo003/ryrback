#PedidosPiezas/models.py
from django.db import models
from django.utils import timezone


class PedidosPiezas(models.Model):
    id_pedido = models.AutoField(primary_key=True)
    numero_pedido = models.CharField(max_length=200, unique=True)
    creado = models.DateTimeField(auto_now_add=True)
    fecha_pedido = models.DateField(default=timezone.localdate)
    fecha_programada_llegada = models.DateField(null=True, blank=True)

    dealer = models.CharField(max_length=200, blank=True, default="")
    nombre_cliente = models.CharField(max_length=200, blank=True, default="")
    asesor = models.CharField(max_length=200, blank=True, default="")
    orden_servicio = models.CharField(max_length=50, blank=True, default="")
    ticket_sar = models.CharField(max_length=100, blank=True, default="")
    canal = models.CharField(max_length=100, blank=True, default="")
    estatus = models.CharField(max_length=50, blank=True, default="")

    class Meta:
        db_table = "pedidos_piezas"
        managed = True
        ordering = ["-creado"]

    def __str__(self):
        return f"{self.numero_pedido} - {self.nombre_cliente}"

    def save(self, *args, **kwargs):
        if not self.fecha_pedido:
            self.fecha_pedido = timezone.localdate()
        super().save(*args, **kwargs)


class Piezas(models.Model):
    id_pieza = models.AutoField(primary_key=True)
    codigo = models.CharField(max_length=100, unique=True, blank=True, default="")
    nombre = models.CharField(max_length=300, blank=True, default="")
    costo = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        db_table = "piezas"
        managed = True
        ordering = ["codigo"]

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"


class PedidoPiezaDetalle(models.Model):
    id_detalle = models.AutoField(primary_key=True)
    pedido = models.ForeignKey(
        PedidosPiezas,
        related_name="piezas",
        on_delete=models.CASCADE,
    )
    pieza = models.ForeignKey(
        Piezas,
        related_name="detalles_pedido",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    numero_parte = models.CharField(max_length=100, blank=True, default="")
    descripcion = models.CharField(max_length=300, blank=True, default="")
    cantidad = models.PositiveIntegerField(default=1)
    tipo_pedido = models.CharField(max_length=20, blank=True, default="")
    estatus = models.CharField(max_length=50, blank=True, default="")
    costo_unitario = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    fecha_llegada = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "pedidos_piezas_detalle"
        managed = True
        ordering = ["id_detalle"]

    def __str__(self):
        return f"{self.numero_parte} x {self.cantidad}"