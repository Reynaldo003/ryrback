
# retencion/models_postgres.py
# Modelos independientes para probar PostgreSQL.
# No modifican los modelos originales de SQL Server.

from django.db import models


class OrdenServicioVentaPostgres(models.Model):
    """Listado unificado de Retencion en PostgreSQL."""

    vin = models.TextField(db_column="VIN", primary_key=True)
    agencia_venta = models.TextField(
        db_column="Agencia_Venta", null=True, blank=True
    )
    agencia_servicio = models.TextField(
        db_column="Agencia_Servicio", null=True, blank=True
    )
    fecha_venta = models.DateField(
        db_column="FechaVenta", null=True, blank=True
    )
    fecha_salida = models.DateField(
        db_column="FechaSalida", null=True, blank=True
    )
    numero_nota = models.TextField(
        db_column="NumeroNota", null=True, blank=True
    )
    total_nota = models.DecimalField(
        db_column="TotalNota", max_digits=18,
        decimal_places=2, null=True, blank=True
    )
    marca = models.TextField(
        db_column="Marca", null=True, blank=True
    )
    modelo_codigo = models.TextField(
        db_column="ModeloCodigo", null=True, blank=True
    )
    modelo_nombre = models.TextField(
        db_column="ModeloNombre", null=True, blank=True
    )
    condicion_vehiculo = models.CharField(
        db_column="CondicionVehiculo", max_length=10,
        null=True, blank=True
    )
    nombre_cliente = models.TextField(
        db_column="NombreCliente", null=True, blank=True
    )
    telefono_cliente = models.TextField(
        db_column="TelefonoCliente", null=True, blank=True
    )
    correo_cliente = models.TextField(
        db_column="CorreoCliente", null=True, blank=True
    )
    cumpleaños = models.DateField(
        db_column="Cumpleaños", null=True, blank=True
    )
    rfc = models.TextField(
        db_column="RFC", null=True, blank=True
    )
    ultima_orden_servicio = models.TextField(
        db_column="UltimaOrdenServicio", null=True, blank=True
    )
    tipo_orden = models.CharField(
        db_column="TipoOrden", max_length=20,
        null=True, blank=True
    )
    subtipo_orden = models.CharField(
        db_column="SubtipoOrden", max_length=20,
        null=True, blank=True
    )
    fecha_ultima_os = models.DateField(
        db_column="FechaUltimaOS", null=True, blank=True
    )
    situacion_os = models.CharField(
        db_column="SituacionOS", max_length=20,
        null=True, blank=True
    )
    cliente_vehiculo = models.TextField(
        db_column="ClienteVeiculo", null=True, blank=True
    )
    placa_vehiculo = models.TextField(
        db_column="PlacaVeiculo", null=True, blank=True
    )
    kilometraje = models.TextField(
        db_column="Kilometraje", null=True, blank=True
    )
    medio_contacto = models.TextField(
        db_column="MedioContacto", null=True, blank=True
    )
    total_ultimo_servicio = models.DecimalField(
        db_column="TotalUltimoServicio", max_digits=18,
        decimal_places=2, null=True, blank=True
    )
    estado_actividad = models.CharField(
        db_column="EstadoActividad", max_length=10,
        null=True, blank=True
    )
    meses_desde_venta = models.IntegerField(
        db_column="MesesDesdeVenta", null=True, blank=True
    )
    segmento = models.CharField(
        db_column="Segmento", max_length=20,
        null=True, blank=True
    )

    # Campos nuevos para Retencion
    asesor_venta = models.TextField(
        db_column="AsesorVenta", null=True, blank=True
    )
    concepto_orden_servicio = models.TextField(
        db_column="ConceptoOrdenServicio", null=True, blank=True
    )

    class Meta:
        managed = False
        app_label = "retencion"
        db_table = "retencion_unificada_clientes_prueba_vw"


class OrdenServicioHistorialPostgres(models.Model):
    """Historial de OS, con identificador unico por agencia."""

    identificador_os = models.TextField(
        db_column="IdentificadorOS", primary_key=True
    )

    vin = models.TextField(db_column="VIN")
    agencia = models.TextField(
        db_column="Agencia", null=True, blank=True
    )
    fecha_venta = models.DateField(
        db_column="FechaVenta", null=True, blank=True
    )
    fecha_salida = models.DateField(
        db_column="FechaSalida", null=True, blank=True
    )
    numero_nota = models.TextField(
        db_column="NumeroNota", null=True, blank=True
    )
    total_nota = models.DecimalField(
        db_column="TotalNota", max_digits=18,
        decimal_places=2, null=True, blank=True
    )
    marca = models.TextField(
        db_column="Marca", null=True, blank=True
    )
    modelo_codigo = models.TextField(
        db_column="ModeloCodigo", null=True, blank=True
    )
    modelo_nombre = models.TextField(
        db_column="ModeloNombre", null=True, blank=True
    )
    condicion_vehiculo = models.CharField(
        db_column="CondicionVehiculo", max_length=10,
        null=True, blank=True
    )
    nombre_cliente = models.TextField(
        db_column="NombreCliente", null=True, blank=True
    )
    telefono_cliente = models.TextField(
        db_column="TelefonoCliente", null=True, blank=True
    )
    correo_cliente = models.TextField(
        db_column="CorreoCliente", null=True, blank=True
    )

    # Numero original que se muestra en el frontend
    numero_orden_servicio = models.TextField(
        db_column="NumeroOrdenServicio", null=True, blank=True
    )
    tipo_orden = models.CharField(
        db_column="TipoOrden", max_length=20,
        null=True, blank=True
    )
    subtipo_orden = models.CharField(
        db_column="SubtipoOrden", max_length=20,
        null=True, blank=True
    )
    fecha_os = models.DateField(
        db_column="FechaOS", null=True, blank=True
    )
    situacion_os = models.CharField(
        db_column="SituacionOS", max_length=20,
        null=True, blank=True
    )
    cliente_vehiculo = models.TextField(
        db_column="ClienteVeiculo", null=True, blank=True
    )
    placa_vehiculo = models.TextField(
        db_column="PlacaVeiculo", null=True, blank=True
    )
    kilometraje = models.TextField(
        db_column="Quilometragem", null=True, blank=True
    )
    medio_contacto = models.TextField(
        db_column="MedioContacto", null=True, blank=True
    )
    total_servicio = models.DecimalField(
        db_column="TotalServicio", max_digits=18,
        decimal_places=2, null=True, blank=True
    )
    estado_actividad = models.CharField(
        db_column="EstadoActividad", max_length=10,
        null=True, blank=True
    )
    meses_desde_venta = models.IntegerField(
        db_column="MesesDesdeVenta", null=True, blank=True
    )
    segmento = models.CharField(
        db_column="Segmento", max_length=20,
        null=True, blank=True
    )

    class Meta:
        managed = False
        app_label = "retencion"
        db_table = "retencion_historial_unificado_prueba_vw"
