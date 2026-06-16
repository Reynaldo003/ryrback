# retencion/models.py
from django.db import models


class OrdenServicioVW(models.Model):
    chassi = models.TextField(db_column="Chassi", blank=True, null=True)
    cliente_veiculo = models.TextField(db_column="Cliente_Veiculo", blank=True, null=True)
    marca_auto = models.TextField(db_column="Marca_Auto", blank=True, null=True)
    modelo_auto = models.TextField(db_column="Modelo_Auto", blank=True, null=True)

    num_os = models.TextField(
        db_column="Num_OS",
        primary_key=True,
    )

    fecha_os = models.DateField(db_column="Fecha_OS", blank=True, null=True)
    fecha_emision = models.DateField(db_column="Fecha_Emision", blank=True, null=True)
    fecha_salida = models.DateField(db_column="Fecha_Salida", blank=True, null=True)

    estado = models.CharField(db_column="Estado", max_length=8, blank=True, null=True)
    dias_os_a_actual = models.IntegerField(
        db_column="Dias_OS_A_Actual",
        blank=True,
        null=True,
    )

    segmento = models.CharField(db_column="Segmento", max_length=10, blank=True, null=True)
    meses_actual_a_emision = models.IntegerField(
        db_column="Meses_Actual_A_Emision",
        blank=True,
        null=True,
    )

    num_nota = models.TextField(db_column="Num_Nota", blank=True, null=True)
    total_nota = models.TextField(db_column="Total_Nota", blank=True, null=True)
    subtipo_os = models.TextField(db_column="Subtipo_OS", blank=True, null=True)

    telefono = models.TextField(db_column="telefono", blank=True, null=True)
    correo = models.TextField(db_column="correo", blank=True, null=True)
    nombre = models.TextField(db_column="nombre", blank=True, null=True)
    serie = models.TextField(db_column="Serie", blank=True, null=True)

    total_servicio = models.TextField(db_column="Total_Servicio", blank=True, null=True)

    class Meta:
        managed = False
        db_table = "Ordenes_Servicio_VW"
        verbose_name = "Orden de Servicio Retención"
        verbose_name_plural = "Órdenes de Servicio Retención"

    def __str__(self):
        return f"{self.num_os} - {self.cliente_veiculo or self.nombre or 'Sin cliente'}"