from django.db import models
from django.utils import timezone


class RegistroSalesforce(models.Model):
    # Conserva todas las columnas originales, incluso las no modeladas explícitamente.
    datos_origen = models.JSONField(default=dict, blank=True)
    sincronizado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        abstract = True


class Prospecto(RegistroSalesforce):
    # Archivo: TodosProspectos.csv
    id_prospecto = models.CharField(max_length=18, primary_key=True)
    numero_concesionaria = models.CharField(max_length=20, blank=True, default="", db_index=True)
    concesionaria = models.CharField(max_length=255, blank=True, default="")
    fecha_creacion = models.DateField(null=True, blank=True)
    nombre = models.CharField(max_length=200, blank=True, default="")
    apellido_paterno = models.CharField(max_length=200, blank=True, default="")
    modelo_interes = models.CharField(max_length=200, blank=True, default="")
    nombre_proceso_generado = models.CharField(max_length=500, blank=True, default="", db_index=True)
    telefono = models.CharField(max_length=50, blank=True, default="")
    email = models.CharField(max_length=254, blank=True, default="")
    ciudad = models.CharField(max_length=150, blank=True, default="")
    calle = models.CharField(max_length=255, blank=True, default="")
    fuente_primaria = models.CharField(max_length=150, blank=True, default="")
    propietario = models.CharField(max_length=200, blank=True, default="")
    alias_propietario = models.CharField(max_length=100, blank=True, default="")
    creado_por = models.CharField(max_length=200, blank=True, default="")
    modificado_por = models.CharField(max_length=200, blank=True, default="")
    tipo_registro = models.CharField(max_length=150, blank=True, default="")
    estado = models.CharField(max_length=100, blank=True, default="", db_index=True)
    calificado = models.BooleanField(null=True, blank=True)
    contactado = models.CharField(max_length=100, blank=True, default="")
    fecha_contacto = models.DateField(null=True, blank=True)
    ultima_actividad = models.DateField(null=True, blank=True)
    canal = models.CharField(max_length=100, blank=True, default="")
    medio_origen = models.CharField(max_length=200, blank=True, default="")
    periodo_compra = models.CharField(max_length=100, blank=True, default="")
    motivo_descalificacion = models.CharField(max_length=500, blank=True, default="")
    tipo_prospecto = models.CharField(max_length=100, blank=True, default="")
    permiso_marketing = models.BooleanField(null=True, blank=True)
    prospeccion = models.BooleanField(null=True, blank=True)
    prueba_manejo_antes_calificacion = models.BooleanField(null=True, blank=True)
    tiempo_atencion_horas = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    horas_primer_contacto = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    cotizaciones = models.IntegerField(null=True, blank=True)
    fecha_hora_descalificado = models.DateTimeField(null=True, blank=True)
    fecha_hora_nuevo = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "sf_prospectos"
        indexes = [models.Index(fields=["numero_concesionaria", "fecha_creacion"], name="sf_pros_agencia_fecha")]

    def construir_nombre_proceso(self):
        nombre = " ".join(parte.strip() for parte in [self.nombre, self.apellido_paterno] if parte.strip())
        modelo = self.modelo_interes.strip()
        return f"{nombre} - {modelo}" if nombre and modelo else ""

    def __str__(self):
        return f"{self.nombre} {self.apellido_paterno}".strip() or self.id_prospecto


class ProcesoComercial(RegistroSalesforce):
    # Archivo: TODOSProcesos Comerciales.xlsx
    id_proceso_comercial = models.CharField(max_length=18, primary_key=True)
    numero_concesionaria = models.CharField(max_length=20, blank=True, default="", db_index=True)
    concesionaria = models.CharField(max_length=255, blank=True, default="")
    fecha_creacion = models.DateField(null=True, blank=True)
    propietario = models.CharField(max_length=200, blank=True, default="")
    nombre_cuenta = models.CharField(max_length=255, blank=True, default="")
    nombre_proceso = models.CharField(max_length=500, blank=True, default="", db_index=True)
    etapa = models.CharField(max_length=120, blank=True, default="", db_index=True)
    periodo_fiscal = models.CharField(max_length=100, blank=True, default="")
    importe = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    ingresos_previstos = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    probabilidad = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    antiguedad = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    siguiente_paso = models.TextField(blank=True, default="")
    fuente_primaria = models.CharField(max_length=150, blank=True, default="")
    tipo = models.CharField(max_length=150, blank=True, default="")
    tipo_registro = models.CharField(max_length=200, blank=True, default="")
    id_cuenta = models.CharField(max_length=18, blank=True, default="", db_index=True)
    contact_id = models.CharField(max_length=18, blank=True, default="")
    id_cliente_sf_dms = models.CharField(max_length=100, blank=True, default="")
    id_cliente_dms = models.CharField(max_length=100, blank=True, default="")
    unidades_vendidas = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    ultima_actividad = models.DateField(null=True, blank=True)
    creado_por = models.CharField(max_length=200, blank=True, default="")
    modificado_por = models.CharField(max_length=200, blank=True, default="")
    cerrado = models.BooleanField(null=True, blank=True)
    fecha_cierre = models.DateField(null=True, blank=True)
    calificados = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    canal_cuenta = models.CharField(max_length=120, blank=True, default="")
    canal = models.CharField(max_length=120, blank=True, default="")
    estado_facturacion = models.CharField(max_length=120, blank=True, default="")
    prueba_manejo = models.BooleanField(null=True, blank=True)
    prueba_manejo_realizada = models.BooleanField(null=True, blank=True)
    email_titular = models.CharField(max_length=254, blank=True, default="")
    telefono = models.CharField(max_length=50, blank=True, default="")
    lead_id = models.CharField(max_length=18, blank=True, default="", db_index=True)
    prospecto = models.ForeignKey(Prospecto, null=True, blank=True, on_delete=models.SET_NULL, related_name="procesos")
    fecha_modificacion = models.DateField(null=True, blank=True)
    duracion_etapa = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = "sf_procesos_comerciales"
        indexes = [models.Index(fields=["numero_concesionaria", "fecha_creacion"], name="sf_proc_agencia_fecha")]

    def __str__(self):
        return self.nombre_proceso or self.id_proceso_comercial


class ProcesoComercialDetalle(RegistroSalesforce):
    # Archivo: Py-TODOSProcesos Comerciales.xlsx (información adicional de un proceso existente)
    proceso = models.OneToOneField(ProcesoComercial, primary_key=True, on_delete=models.PROTECT, related_name="detalle", db_column="id_proceso_comercial")
    forma_pago = models.CharField(max_length=100, blank=True, default="")
    direccion_facturacion_1 = models.CharField(max_length=255, blank=True, default="")
    direccion_facturacion_2 = models.CharField(max_length=255, blank=True, default="")
    direccion_facturacion_3 = models.CharField(max_length=255, blank=True, default="")
    colonia_facturacion = models.CharField(max_length=255, blank=True, default="")
    ciudad_facturacion = models.CharField(max_length=150, blank=True, default="")
    municipio_facturacion = models.CharField(max_length=150, blank=True, default="")
    sexo = models.CharField(max_length=50, blank=True, default="")
    profesion = models.CharField(max_length=150, blank=True, default="")
    ocupacion = models.CharField(max_length=150, blank=True, default="")
    estado_civil = models.CharField(max_length=100, blank=True, default="")
    nivel_estudios = models.CharField(max_length=100, blank=True, default="")
    numero_hijos = models.IntegerField(null=True, blank=True)
    modelo_interes_1 = models.CharField(max_length=200, blank=True, default="")
    modelo_interes_2 = models.CharField(max_length=200, blank=True, default="")
    fecha_nacimiento = models.DateField(null=True, blank=True)
    monto_financiar = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    producto_contrato = models.CharField(max_length=150, blank=True, default="")
    rfc = models.CharField(max_length=20, blank=True, default="")
    codigo_postal = models.CharField(max_length=12, blank=True, default="")
    consentimiento_contacto = models.CharField(max_length=100, blank=True, default="")
    tipo_financiamiento = models.CharField(max_length=150, blank=True, default="")
    periodo_compra = models.CharField(max_length=100, blank=True, default="")
    origen_venta = models.CharField(max_length=150, blank=True, default="")
    marca = models.CharField(max_length=100, blank=True, default="")
    modelo_auto = models.CharField(max_length=150, blank=True, default="")
    modelo_competencia = models.CharField(max_length=150, blank=True, default="")
    financiera = models.CharField(max_length=150, blank=True, default="")
    fuente_lead = models.CharField(max_length=150, blank=True, default="")
    fecha_hora_entrega = models.DateTimeField(null=True, blank=True)
    fecha_hora_venta = models.DateTimeField(null=True, blank=True)
    fecha_hora_facturacion = models.DateTimeField(null=True, blank=True)
    facturas = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    es_cerrada_ganada = models.BooleanField(null=True, blank=True)
    buy_back = models.BooleanField(null=True, blank=True)
    edad = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "sf_procesos_detalle"

    def __str__(self):
        return self.proceso_id


class ActividadBase(RegistroSalesforce):
    # Campos compartidos por los dos reportes de actividades.
    id_actividad = models.CharField(max_length=18, primary_key=True)
    numero_concesionaria = models.CharField(max_length=20, blank=True, default="", db_index=True)
    concesionaria = models.CharField(max_length=255, blank=True, default="")
    asignado = models.CharField(max_length=200, blank=True, default="")
    alias_asignado = models.CharField(max_length=100, blank=True, default="")
    tipo = models.CharField(max_length=120, blank=True, default="")
    subtipo_tarea = models.CharField(max_length=100, blank=True, default="")
    subtipo_evento = models.CharField(max_length=100, blank=True, default="")
    tipo_registro_actividad = models.CharField(max_length=150, blank=True, default="")
    asunto = models.CharField(max_length=500, blank=True, default="")
    fecha = models.DateField(null=True, blank=True, db_index=True)
    vencimiento = models.DateTimeField(null=True, blank=True)
    finalizacion = models.DateTimeField(null=True, blank=True)
    duracion_minutos = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    duracion_horas = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    duracion_llamada_segundos = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    duracion_llamada_minutos_original = models.CharField(max_length=50, blank=True, default="")
    tipo_llamada = models.CharField(max_length=100, blank=True, default="")
    resultado_llamada = models.CharField(max_length=150, blank=True, default="")
    identificador_llamada = models.CharField(max_length=150, blank=True, default="")
    prioridad = models.CharField(max_length=100, blank=True, default="")
    estado = models.CharField(max_length=100, blank=True, default="", db_index=True)
    ubicacion = models.CharField(max_length=255, blank=True, default="")
    es_tarea = models.BooleanField(null=True, blank=True)
    cerrado = models.BooleanField(null=True, blank=True)
    invitacion_eventos = models.BooleanField(null=True, blank=True)
    creado_por = models.CharField(max_length=200, blank=True, default="")
    modificado_por = models.CharField(max_length=200, blank=True, default="")
    comentarios = models.TextField(blank=True, default="")
    comentarios_completos = models.TextField(blank=True, default="")
    fecha_creacion = models.DateField(null=True, blank=True)
    fecha_modificacion = models.DateField(null=True, blank=True)

    class Meta:
        abstract = True

    def __str__(self):
        return self.asunto or self.id_actividad


class ActividadProspecto(ActividadBase):
    # Archivo: ActividadesProspectosTODAS.csv
    id_prospecto_original = models.CharField(max_length=18, blank=True, default="", db_index=True)
    prospecto = models.ForeignKey(Prospecto, null=True, blank=True, on_delete=models.SET_NULL, related_name="actividades")
    numero_concesionaria_virtual = models.CharField(max_length=20, blank=True, default="")
    marca = models.CharField(max_length=100, blank=True, default="")
    nombre_prospecto = models.CharField(max_length=200, blank=True, default="")
    apellido_paterno = models.CharField(max_length=200, blank=True, default="")
    propietario_prospecto = models.CharField(max_length=200, blank=True, default="")
    estado_prospecto = models.CharField(max_length=100, blank=True, default="")
    ultima_actividad_prospecto = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "sf_actividades_prospectos"
        indexes = [models.Index(fields=["id_prospecto_original", "fecha"], name="sf_actpros_id_fecha")]


class ActividadProceso(ActividadBase):
    # Archivo: ActividadesProcesosTODAS.xlsx
    id_proceso_original = models.CharField(max_length=18, blank=True, default="", db_index=True)
    proceso = models.ForeignKey(ProcesoComercial, null=True, blank=True, on_delete=models.SET_NULL, related_name="actividades")
    numero_concesionaria_interfaz = models.CharField(max_length=20, blank=True, default="")
    inicio = models.DateTimeField(null=True, blank=True)
    fin = models.DateTimeField(null=True, blank=True)
    nombre_proceso = models.CharField(max_length=500, blank=True, default="")
    propietario_proceso = models.CharField(max_length=200, blank=True, default="")
    tipo_proceso = models.CharField(max_length=150, blank=True, default="")
    etapa_proceso = models.CharField(max_length=150, blank=True, default="")
    importe_proceso = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    descripcion = models.TextField(blank=True, default="")

    class Meta:
        db_table = "sf_actividades_procesos"
        indexes = [models.Index(fields=["id_proceso_original", "fecha"], name="sf_actproc_id_fecha")]


class FacturaComercial(RegistroSalesforce):
    # Archivo: Facturadas.xlsx
    id_factura = models.CharField(max_length=18, primary_key=True)
    proceso = models.ForeignKey(ProcesoComercial, on_delete=models.PROTECT, related_name="facturas", db_column="id_proceso_comercial")
    numero_concesionaria = models.CharField(max_length=20, blank=True, default="", db_index=True)
    marca = models.CharField(max_length=100, blank=True, default="")
    fecha_facturacion = models.DateField(null=True, blank=True, db_index=True)
    nombre_proceso = models.CharField(max_length=500, blank=True, default="")
    nombre_cuenta = models.CharField(max_length=255, blank=True, default="")
    propietario_proceso = models.CharField(max_length=200, blank=True, default="")
    etapa = models.CharField(max_length=150, blank=True, default="")
    nombre_factura = models.CharField(max_length=255, blank=True, default="")
    fecha_entrega = models.DateField(null=True, blank=True)
    vin = models.CharField(max_length=50, blank=True, default="", db_index=True)
    fecha_modificacion_etapa = models.DateField(null=True, blank=True)
    importe = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    total = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    id_sales_dms = models.CharField(max_length=150, blank=True, default="")
    canal_cuenta = models.CharField(max_length=150, blank=True, default="")
    tipo_registro_proceso = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        db_table = "sf_facturas_comerciales"
        indexes = [models.Index(fields=["numero_concesionaria", "fecha_facturacion"], name="sf_fac_agencia_fecha")]

    def __str__(self):
        return self.nombre_factura or self.id_factura


class EntregaComercial(RegistroSalesforce):
    # Archivo: 100% EntregadosTotales.xlsx; 126 IDs de factura no existen en Facturadas.
    id_factura = models.CharField(max_length=18, primary_key=True)
    factura = models.OneToOneField(FacturaComercial, null=True, blank=True, on_delete=models.SET_NULL, related_name="entrega")
    proceso = models.ForeignKey(ProcesoComercial, on_delete=models.PROTECT, related_name="entregas", db_column="id_proceso_comercial")
    numero_concesionaria = models.CharField(max_length=20, blank=True, default="", db_index=True)
    marca = models.CharField(max_length=100, blank=True, default="")
    fecha_facturacion = models.DateField(null=True, blank=True)
    nombre_proceso = models.CharField(max_length=500, blank=True, default="")
    propietario_proceso = models.CharField(max_length=200, blank=True, default="")
    etapa = models.CharField(max_length=150, blank=True, default="")
    modelo_interes = models.CharField(max_length=200, blank=True, default="")
    modelo = models.CharField(max_length=200, blank=True, default="")
    nombre_factura = models.CharField(max_length=255, blank=True, default="")
    fecha_entrega = models.DateField(null=True, blank=True, db_index=True)
    cantidad_facturas_facturadas = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    estatus = models.CharField(max_length=150, blank=True, default="")
    calificados = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    forma_pago = models.CharField(max_length=100, blank=True, default="")
    metodo_pago = models.CharField(max_length=100, blank=True, default="")
    creado_por = models.CharField(max_length=200, blank=True, default="")
    nombre_cuenta = models.CharField(max_length=255, blank=True, default="")
    cliente_venta = models.CharField(max_length=255, blank=True, default="")
    cliente_facturacion = models.CharField(max_length=255, blank=True, default="")
    vin = models.CharField(max_length=50, blank=True, default="", db_index=True)
    importe = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    total = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    id_sales_dms = models.CharField(max_length=150, blank=True, default="")
    tipo_registro_proceso = models.CharField(max_length=200, blank=True, default="")
    fecha_modificacion = models.DateField(null=True, blank=True)
    fecha_modificacion_etapa = models.DateField(null=True, blank=True)
    tipo_proceso_venta = models.CharField(max_length=150, blank=True, default="")
    canal_cuenta = models.CharField(max_length=150, blank=True, default="")

    class Meta:
        db_table = "sf_entregas_comerciales"
        indexes = [models.Index(fields=["numero_concesionaria", "fecha_entrega"], name="sf_ent_agencia_fecha")]

    def __str__(self):
        return self.nombre_factura or self.id_factura


class ImportacionComercial(models.Model):
    # Historial de cargas que mostrará la interfaz de SalesForce.
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        VALIDADA = "validada", "Validada"
        COMPLETADA = "completada", "Completada"
        ERROR = "error", "Con errores"

    tabla = models.CharField(max_length=80, db_index=True)
    nombre_archivo = models.CharField(max_length=255)
    realizada_por = models.CharField(max_length=200, blank=True, default="")
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.PENDIENTE)
    registros_leidos = models.PositiveIntegerField(default=0)
    registros_creados = models.PositiveIntegerField(default=0)
    registros_actualizados = models.PositiveIntegerField(default=0)
    registros_sin_cambios = models.PositiveIntegerField(default=0)
    registros_error = models.PositiveIntegerField(default=0)
    detalle_errores = models.JSONField(default=list, blank=True)
    iniciado_en = models.DateTimeField(auto_now_add=True)
    finalizado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "sf_importaciones_comerciales"
        ordering = ["-iniciado_en"]

    def __str__(self):
        return f"{self.tabla} - {self.nombre_archivo}"
