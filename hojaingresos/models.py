from decimal import Decimal

from django.db import models

from citas.models import ClienteComercial


class HojaIngresos(models.Model):
    cliente = models.ForeignKey(
        ClienteComercial,
        db_column="id_cliente",
        on_delete=models.PROTECT,
        related_name="hojas_ingresos",
        null=True,
        blank=True,
    )

    agencia = models.CharField(max_length=120, blank=True, default="")
    no_orden = models.CharField(max_length=255, blank=True, default="")
    fecha_ingreso = models.DateTimeField(null=True, blank=True)
    asistencia = models.BooleanField(null=True,blank=True,default=None,)
    diss = models.CharField(max_length=120, blank=True, default="")
    pauta = models.TextField(blank=True, default="")
    indicador_resultados = models.CharField(max_length=120, blank=True, default="")
    alcance = models.CharField(max_length=120, blank=True, default="")
    citado = models.BooleanField(required=False default=None)
    torre = models.CharField(max_length=120, blank=True, default="")
    asesor = models.CharField(max_length=120, blank=True, default="")
    agendado_por = models.CharField(max_length=120, blank=True, default="")
    nombre_cliente = models.CharField(max_length=200, blank=True, default="")
    tipo_cita = models.TextField(blank=True,default="",)
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
    long_drive = models.BooleanField(required=False,allow_null=True,blank=True,)

    hora_promesa = models.DateTimeField(
        null=True,
        blank=True,
    )

    pre_picking_hecho = models.BooleanField(
        default=False,
    )

    pre_picking_notas = models.TextField(
        blank=True,
        default="",
    )
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
        nombre = (
            getattr(self.cliente, "nombre", "")
            or self.nombre_cliente
            or "Sin cliente"
        )
        return f"Ingreso #{self.pk} - {nombre} - {telefono}"


class TallerActividad(models.Model):
    ingreso = models.OneToOneField(HojaIngresos, on_delete=models.CASCADE, related_name="taller", db_column="id_ingreso",)

    tecnico = models.CharField(max_length=160, blank=True, default="", db_index=True,)
    etapa = models.CharField(max_length=80, blank=True, default="Ingreso con Cita", db_index=True,)
    estatus_agenda = models.CharField(max_length=40, blank=True, default="Programado", db_index=True,)
    fecha_programada = models.DateField(null=True,blank=True,db_index=True,)
    hora_inicio = models.TimeField(null=True, blank=True)
    hora_fin = models.TimeField(null=True, blank=True)
    tipo_bloque = models.CharField(max_length=40, blank=True, default="trabajo", db_index=True,)
    tipo_servicio = models.TextField(blank=True,default="",)
    comentarios_taller = models.TextField(blank=True, default="")
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "taller_actividad"
        ordering = ["fecha_programada", "hora_inicio", "tecnico", "id"]
        indexes = [
            models.Index(fields=["fecha_programada", "tecnico"]),
            models.Index(fields=["etapa", "fecha_programada"]),
        ]

    def __str__(self):
        referencia = self.ingreso.no_orden or f"Ingreso {self.ingreso_id}"
        tecnico = self.tecnico or "Sin técnico"
        return f"{referencia} - {tecnico}"

    @property
    def horas_agenda(self):
        if not self.hora_inicio or not self.hora_fin:
            return Decimal("0.00")

        inicio = self.hora_inicio.hour * 60 + self.hora_inicio.minute
        fin = self.hora_fin.hour * 60 + self.hora_fin.minute

        if fin <= inicio:
            return Decimal("0.00")

        return Decimal(fin - inicio) / Decimal("60")

    def save(self, *args, **kwargs):
        self.tecnico = (self.tecnico or "").strip().upper()
        self.etapa = (self.etapa or "Ingreso con Cita").strip()
        self.estatus_agenda = (self.estatus_agenda or "Programado").strip()
        self.tipo_bloque = (self.tipo_bloque or "trabajo").strip().lower()
        self.tipo_servicio = (self.tipo_servicio or "").strip()
        self.comentarios_taller = (self.comentarios_taller or "").strip()
        super().save(*args, **kwargs)