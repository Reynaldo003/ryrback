# retencion/models.py
from django.db import models

class OrdenServicioVentaVW(models.Model):
    vin = models.TextField(db_column="VIN", primary_key=True)
    agencia_venta = models.TextField(db_column="Agencia_Venta", blank=True, null=True)
    agencia_servicio = models.TextField(db_column="Agencia_Servicio", blank=True, null=True)

    fecha_venta = models.DateField(db_column="FechaVenta", blank=True, null=True)
    fecha_salida = models.DateField(db_column="FechaSalida", blank=True, null=True)
    numero_nota = models.TextField(db_column="NumeroNota", blank=True, null=True)
    total_nota = models.DecimalField(db_column="TotalNota", max_digits=18, decimal_places=2, blank=True, null=True)

    marca = models.TextField(db_column="Marca", blank=True, null=True)
    modelo_codigo = models.TextField(db_column="ModeloCodigo", blank=True, null=True)
    modelo_nombre = models.TextField(db_column="ModeloNombre", blank=True, null=True)
    condicion_vehiculo = models.CharField(db_column="CondicionVehiculo", max_length=10, blank=True, null=True)

    nombre_cliente = models.TextField(db_column="NombreCliente", blank=True, null=True)
    telefono_cliente = models.TextField(db_column="TelefonoCliente", blank=True, null=True)
    correo_cliente = models.TextField(db_column="CorreoCliente", blank=True, null=True)
    cumpleaños = models.DateField(db_column="Cumpleaños", blank=True, null=True)
    rfc = models.TextField(db_column="RFC", blank=True, null=True)

    ultima_orden_servicio = models.TextField(db_column="UltimaOrdenServicio", blank=True, null=True)
    tipo_orden = models.CharField(db_column="TipoOrden", max_length=20, blank=True, null=True)
    subtipo_orden = models.CharField(db_column="SubtipoOrden", max_length=20, blank=True, null=True)
    fecha_ultima_os = models.DateField(db_column="FechaUltimaOS", blank=True, null=True)
    situacion_os = models.CharField(db_column="SituacionOS", max_length=20, blank=True, null=True)

    cliente_vehiculo = models.TextField(db_column="ClienteVeiculo", blank=True, null=True)
    placa_vehiculo = models.TextField(db_column="PlacaVeiculo", blank=True, null=True)
    kilometraje = models.TextField(db_column="Kilometraje", blank=True, null=True)

    medio_contacto = models.TextField(db_column="MedioContacto", blank=True, null=True)

    total_ultimo_servicio = models.DecimalField(
        db_column="TotalUltimoServicio",
        max_digits=18,
        decimal_places=2,
        blank=True,
        null=True,
    )

    estado_actividad = models.CharField(db_column="EstadoActividad", max_length=10, blank=True, null=True)
    meses_desde_venta = models.IntegerField(db_column="MesesDesdeVenta", blank=True, null=True)
    segmento = models.CharField(db_column="Segmento", max_length=20, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "Ordenes_Servicio_Ventas_VW_v2"
        verbose_name = "Orden Venta Retención"
        verbose_name_plural = "Órdenes Venta Retención"

    def __str__(self):
        return f"{self.vin} - {self.nombre_cliente or 'Sin cliente'}"

class OrdenServicioCompletaVW(models.Model):
    vin = models.TextField(db_column="VIN", blank=True, null=True, db_index=True)
    agencia = models.TextField(db_column="Agencia", blank=True, null=True)
    fecha_venta = models.DateField(db_column="FechaVenta", blank=True, null=True)
    fecha_salida = models.DateField(db_column="FechaSalida", blank=True, null=True)
    numero_nota = models.TextField(db_column="NumeroNota", blank=True, null=True)
    total_nota = models.DecimalField(
        db_column="TotalNota", max_digits=18, decimal_places=2, blank=True, null=True
    )
    marca = models.TextField(db_column="Marca", blank=True, null=True)
    modelo_codigo = models.TextField(db_column="ModeloCodigo", blank=True, null=True)
    modelo_nombre = models.TextField(db_column="ModeloNombre", blank=True, null=True)
    condicion_vehiculo = models.CharField(
        db_column="CondicionVehiculo", max_length=10, blank=True, null=True
    )
    nombre_cliente = models.TextField(db_column="NombreCliente", blank=True, null=True)
    telefono_cliente = models.TextField(db_column="TelefonoCliente", blank=True, null=True)
    correo_cliente = models.TextField(db_column="CorreoCliente", blank=True, null=True)

    numero_orden_servicio = models.TextField(
        db_column="NumeroOrdenServicio",
        primary_key=True,
    )

    tipo_orden = models.CharField(db_column="TipoOrden", max_length=20, blank=True, null=True)
    subtipo_orden = models.CharField(
        db_column="SubtipoOrden", max_length=20, blank=True, null=True
    )
    fecha_os = models.DateField(db_column="FechaOS", blank=True, null=True)
    situacion_os = models.CharField(
        db_column="SituacionOS", max_length=20, blank=True, null=True
    )
    cliente_vehiculo = models.TextField(db_column="ClienteVeiculo", blank=True, null=True)
    placa_vehiculo = models.TextField(db_column="PlacaVeiculo", blank=True, null=True)
    kilometraje = models.TextField(db_column="Quilometragem", blank=True, null=True)
    medio_contacto = models.TextField(db_column="MedioContacto", blank=True, null=True)
    total_servicio = models.DecimalField(
        db_column="TotalServicio", max_digits=18, decimal_places=2, blank=True, null=True
    )
    estado_actividad = models.CharField(
        db_column="EstadoActividad", max_length=20, blank=True, null=True
    )
    meses_desde_venta = models.IntegerField(
        db_column="MesesDesdeVenta", blank=True, null=True
    )
    segmento = models.CharField(db_column="Segmento", max_length=20, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "Ventas_Ordenes_Servicio_Completas_VW"
        verbose_name = "Orden Servicio Completa"
        verbose_name_plural = "Órdenes Servicio Completas"

    def __str__(self):
        return f"{self.numero_orden_servicio} - {self.vin}"

class TareaCliente(models.Model):
    ESTADO_PENDIENTE = "pendiente"
    ESTADO_EN_PROGRESO = "en_progreso"
    ESTADO_COMPLETADA = "completada"
    ESTADO_CANCELADA = "cancelada"

    ESTADO_CHOICES = [
        (ESTADO_PENDIENTE, "Pendiente"),
        (ESTADO_EN_PROGRESO, "En progreso"),
        (ESTADO_COMPLETADA, "Completada"),
        (ESTADO_CANCELADA, "Cancelada"),
    ]

    telefono_cliente = models.CharField(max_length=20, db_index=True)
    nombre_cliente = models.CharField(max_length=255, blank=True)
    titulo = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True)
    forma_contacto = models.CharField(max_length=100, blank=True)
    motivo_contacto = models.CharField(max_length=100, blank=True)
    resultado = models.CharField(max_length=100, blank=True)
    estado = models.CharField(
        max_length=20, choices=ESTADO_CHOICES, default=ESTADO_PENDIENTE
    )
    fecha_limite = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "retencion_tarea_cliente"
        ordering = ["-created_at"]
        verbose_name = "Tarea de cliente"
        verbose_name_plural = "Tareas de clientes"

    def __str__(self):
        return f"{self.titulo} ({self.telefono_cliente})"