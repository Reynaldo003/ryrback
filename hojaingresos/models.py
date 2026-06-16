# hojaingresos/models.py
from django.db import models

from citas.models import ClienteComercial


class HojaIngresos(models.Model):
    cliente = models.ForeignKey(
        ClienteComercial,
        db_column="id_cliente",
        on_delete=models.PROTECT,
        related_name="hojas_ingresos",
    )

    agencia = models.CharField(max_length=120, blank=True, default="")

    no_orden = models.CharField(max_length=255, blank=True, default="")

    fecha_ingreso = models.DateTimeField(null=True, blank=True)

    asistencia = models.BooleanField(default=False)

    diss = models.CharField(max_length=120, blank=True, default="")

    pauta = models.TextField(blank=True, default="")

    indicador_resultados = models.CharField(max_length=120, blank=True, default="")
    alcance = models.CharField(max_length=120, blank=True, default="")
    citado = models.BooleanField(default=False)
    torre = models.CharField(max_length=120, blank=True, default="")
    asesor = models.CharField(max_length=120, blank=True, default="")

    agendado_por = models.CharField(max_length=120, blank=True, default="")

    nombre_cliente = models.CharField(max_length=200, blank=True, default="")

    tipo_cita = models.CharField(max_length=120, blank=True, default="")

    declaracion_textual_cliente = models.TextField(blank=True, default="")

    comentarios = models.TextField(blank=True, default="")

    vin = models.CharField(max_length=80, blank=True, default="")

    anio_vehiculo = models.CharField(max_length=10, blank=True, default="")

    modelo = models.CharField(max_length=120, blank=True, default="")

    medio_concertacion = models.CharField(max_length=120, blank=True, default="")

    pauta_origen = models.TextField(blank=True, default="")

    venta_mano_obra = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    # Campos opcionales que venían de tu estructura anterior.
    # Los dejo porque pueden servirte para trazabilidad interna.
    asesor_digital = models.CharField(max_length=200, blank=True, default="")
    asesor_piso = models.CharField(max_length=200, blank=True, default="")

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "hoja_ingresos"
        managed = True
        ordering = ["-fecha_ingreso", "-id"]
        indexes = [
            models.Index(fields=["fecha_ingreso"]),
            models.Index(fields=["agencia"]),
            models.Index(fields=["asesor"]),
            models.Index(fields=["asistencia"]),
            models.Index(fields=["vin"]),
            models.Index(fields=["no_orden"]),
        ]

    def __str__(self):
        telefono = getattr(self.cliente, "telefono", "") or "Sin teléfono"
        cliente = self.nombre_cliente or getattr(self.cliente, "nombre", "") or "Sin cliente"

        return f"Ingreso #{self.id} - {cliente} - {telefono}"