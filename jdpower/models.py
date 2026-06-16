# jdpower/models.py
from django.db import models


class EncuestaJDPower(models.Model):
    id_ventas = models.BigIntegerField(db_column="id_ventas", primary_key=True)

    id_muestra = models.CharField(db_column="id_muestra", max_length=50, blank=True, null=True)
    id_encuesta = models.CharField(db_column="id_encuesta", max_length=50, blank=True, null=True)
    tipo = models.CharField(db_column="tipo", max_length=50, blank=True, null=True)
    canal_envio = models.CharField(db_column="canal_envio", max_length=50, blank=True, null=True)
    estatus = models.CharField(db_column="estatus", max_length=50, blank=True, null=True)

    chasis = models.CharField(db_column="chasis", max_length=50, blank=True, null=True)
    modelo = models.CharField(db_column="modelo", max_length=250, blank=True, null=True)
    anio_vehiculo = models.IntegerField(db_column="anio_vehiculo", blank=True, null=True)

    region = models.CharField(db_column="region", max_length=50, blank=True, null=True)
    zona = models.CharField(db_column="zona", max_length=50, blank=True, null=True)
    estado = models.CharField(db_column="estado", max_length=50, blank=True, null=True)
    ciudad = models.CharField(db_column="ciudad", max_length=50, blank=True, null=True)

    codigo_concesionaria = models.CharField(
        db_column="codigo_concesionaria",
        max_length=50,
        blank=True,
        null=True,
    )
    concesionaria = models.CharField(
        db_column="concesionaria",
        max_length=100,
        blank=True,
        null=True,
    )

    id_asesor = models.CharField(db_column="id_asesor", max_length=50, blank=True, null=True)
    vwsf = models.CharField(db_column="vwsf", max_length=50, blank=True, null=True)

    s1_entrega_vehiculo = models.CharField(
        db_column="s1_entrega_vehiculo",
        max_length=50,
        blank=True,
        null=True,
    )
    pn1_forma_compra = models.CharField(
        db_column="pn1_forma_compra",
        max_length=50,
        blank=True,
        null=True,
    )
    pn2_empresa_financiamiento = models.CharField(
        db_column="pn2_empresa_financiamiento",
        max_length=100,
        blank=True,
        null=True,
    )

    q1_satisfaccion_general = models.IntegerField(
        db_column="Q1_satisfaccion_general",
        blank=True,
        null=True,
    )
    q1_1_razones_calificacion = models.TextField(
        db_column="Q1_1_razones_calificacion",
        blank=True,
        null=True,
    )

    qr_2_1_proceso_entrega = models.IntegerField(
        db_column="QR_2_1_proceso_entrega",
        blank=True,
        null=True,
    )
    qr_2_1_1_efectividad_explicacion = models.IntegerField(
        db_column="QR_2_1_1_efectividad_explicacion",
        blank=True,
        null=True,
    )
    qr_2_1_2_puntualidad_entrega = models.IntegerField(
        db_column="QR_2_1_2_puntualidad_entrega",
        blank=True,
        null=True,
    )
    qr_2_1_3_condiciones_vehiculo = models.IntegerField(
        db_column="QR_2_1_3_condiciones_vehiculo",
        blank=True,
        null=True,
    )
    qr_2_1_4_conexion_bluetooth = models.IntegerField(
        db_column="QR_2_1_4_conexion_bluetooth",
        blank=True,
        null=True,
    )

    qr_2_2_atencion_personal = models.IntegerField(
        db_column="QR_2_2_atencion_personal",
        blank=True,
        null=True,
    )
    qr_2_2_1_conocimiento_vehiculo = models.IntegerField(
        db_column="QR_2_2_1_conocimiento_vehiculo",
        blank=True,
        null=True,
    )
    qr_2_2_2_amabilidad = models.IntegerField(
        db_column="QR_2_2_2_amabilidad",
        blank=True,
        null=True,
    )
    qr_2_2_3_respuesta = models.IntegerField(
        db_column="QR_2_2_3_respuesta",
        blank=True,
        null=True,
    )
    qr_2_2_4_comunicacion_fuera = models.IntegerField(
        db_column="QR_2_2_4_comunicacion_fuera",
        blank=True,
        null=True,
    )
    qr_2_2_5_uso_tecnologia = models.IntegerField(
        db_column="QR_2_2_5_uso_tecnologia",
        blank=True,
        null=True,
    )
    qr_2_2_6_info_tiempo_entrega = models.IntegerField(
        db_column="QR_2_2_6_info_tiempo_entrega",
        blank=True,
        null=True,
    )

    qr_2_3_instalaciones = models.IntegerField(
        db_column="QR_2_3_instalaciones",
        blank=True,
        null=True,
    )
    qr_2_3_1_apariencia = models.IntegerField(
        db_column="QR_2_3_1_apariencia",
        blank=True,
        null=True,
    )
    qr_2_3_2_facilidad_inventario = models.IntegerField(
        db_column="QR_2_3_2_facilidad_inventario",
        blank=True,
        null=True,
    )
    qr_2_3_3_variedad_modelos = models.IntegerField(
        db_column="QR_2_3_3_variedad_modelos",
        blank=True,
        null=True,
    )
    qr_2_3_4_calidad_amenidades = models.IntegerField(
        db_column="QR_2_3_4_calidad_amenidades",
        blank=True,
        null=True,
    )
    qr_2_3_5_opciones_estacionamiento = models.IntegerField(
        db_column="QR_2_3_5_opciones_estacionamiento",
        blank=True,
        null=True,
    )

    qr_2_4_documentacion = models.IntegerField(
        db_column="QR_2_4_documentacion",
        blank=True,
        null=True,
    )
    qr_2_4_1_claridad_documentos = models.IntegerField(
        db_column="QR_2_4_1_claridad_documentos",
        blank=True,
        null=True,
    )
    qr_2_4_2_transparencia_papeleo = models.IntegerField(
        db_column="QR_2_4_2_transparencia_papeleo",
        blank=True,
        null=True,
    )
    qr_2_4_3_prontitud_papeleo = models.IntegerField(
        db_column="QR_2_4_3_prontitud_papeleo",
        blank=True,
        null=True,
    )

    qr_2_5_negociacion = models.IntegerField(
        db_column="QR_2_5_negociacion",
        blank=True,
        null=True,
    )
    qr_2_5_1_acuerdo_precio = models.IntegerField(
        db_column="QR_2_5_1_acuerdo_precio",
        blank=True,
        null=True,
    )
    qr_2_5_2_precio_justo = models.IntegerField(
        db_column="QR_2_5_2_precio_justo",
        blank=True,
        null=True,
    )
    qr_2_5_3_comodidad_negociacion = models.IntegerField(
        db_column="QR_2_5_3_comodidad_negociacion",
        blank=True,
        null=True,
    )

    q3_comentarios_adicionales = models.TextField(
        db_column="Q3_comentarios_adicionales",
        blank=True,
        null=True,
    )

    p1_satisfaccion_producto = models.IntegerField(
        db_column="P1_satisfaccion_producto",
        blank=True,
        null=True,
    )
    p1_1_comentarios_auto = models.TextField(
        db_column="P1_1_comentarios_auto",
        blank=True,
        null=True,
    )
    p3_recomendacion_distribuidor = models.IntegerField(
        db_column="P3_recomendacion_distribuidor",
        blank=True,
        null=True,
    )

    q8_transferencia_datos = models.CharField(
        db_column="Q8_transferencia_datos",
        max_length=50,
        blank=True,
        null=True,
    )
    q10_autoriza_publicacion = models.CharField(
        db_column="Q10_autoriza_publicacion",
        max_length=50,
        blank=True,
        null=True,
    )

    fecha_registro = models.DateField(db_column="fecha_registro", blank=True, null=True)
    fecha_entrega = models.DateField(db_column="fecha_entrega", blank=True, null=True)
    fecha_encuesta = models.DateTimeField(db_column="fecha_encuesta", blank=True, null=True)
    periodo = models.DateField(db_column="periodo", blank=True, null=True)

    class Meta:
        managed = False
        db_table = "encuesta_jdpowerv"
        verbose_name = "Encuesta JD Power"
        verbose_name_plural = "Encuestas JD Power"

    def __str__(self):
        return f"{self.id_ventas} - {self.concesionaria or 'Sin concesionaria'}"



#  SERVICIO 
class EncuestaJDPowerServicio(models.Model):
    id = models.AutoField(db_column="id", primary_key=True)

    id_servicio = models.CharField(db_column="id_servicio", max_length=20)
    id_muestra = models.IntegerField(db_column="id_muestra")
    id_encuesta = models.IntegerField(db_column="id_encuesta", unique=True)
    tipo = models.CharField(db_column="tipo", max_length=100)
    periodo = models.DateField(db_column="periodo")
    canal_envio = models.CharField(db_column="canal_envio", max_length=30, blank=True, null=True)
    estatus = models.CharField(db_column="estatus", max_length=40, blank=True, null=True)

    # Fechas
    fecha_registro_procesado = models.DateField(db_column="fecha_registro_procesado", blank=True, null=True)
    fecha_servicio = models.DateField(db_column="fecha_servicio", blank=True, null=True)
    fecha_completo_encuesta = models.DateTimeField(db_column="fecha_completo_encuesta", blank=True, null=True)

    # Vehículo
    tipo_servicio = models.CharField(db_column="tipo_servicio", max_length=10, blank=True, null=True)
    chasis = models.CharField(db_column="chasis", max_length=25, blank=True, null=True)
    modelo = models.CharField(db_column="modelo", max_length=60, blank=True, null=True)
    anio_vehiculo = models.IntegerField(db_column="anio_vehiculo", blank=True, null=True)

    # Concesionaria
    region = models.CharField(db_column="region", max_length=40, blank=True, null=True)
    zona = models.CharField(db_column="zona", max_length=20, blank=True, null=True)
    estado = models.CharField(db_column="estado", max_length=80, blank=True, null=True)
    codigo_concesionaria = models.CharField(db_column="codigo_concesionaria", max_length=20, blank=True, null=True)
    concesionaria = models.CharField(db_column="concesionaria", max_length=120, blank=True, null=True)
    id_asesor = models.CharField(db_column="id_asesor", max_length=20, blank=True, null=True)

    # Filtro
    s1_confirma_concesionario = models.CharField(db_column="s1_confirma_concesionario", max_length=20, blank=True, null=True)

    # Q1
    q1_satisfaccion_general = models.IntegerField(db_column="q1_satisfaccion_general", blank=True, null=True)
    q1_1_razones_calificacion = models.TextField(db_column="q1_1_razones_calificacion", blank=True, null=True)

    # Q2.1
    q2_1_calidad_servicio = models.IntegerField(db_column="q2_1_calidad_servicio", blank=True, null=True)
    q2_1a_problema_no_resuelto = models.CharField(db_column="q2_1a_problema_no_resuelto", max_length=10, blank=True, null=True)
    q2_1b_sin_refacciones = models.CharField(db_column="q2_1b_sin_refacciones", max_length=10, blank=True, null=True)
    q2_1c_condiciones_auto = models.CharField(db_column="q2_1c_condiciones_auto", max_length=10, blank=True, null=True)
    q2_1d_tiempo_taller = models.CharField(db_column="q2_1d_tiempo_taller", max_length=10, blank=True, null=True)

    # Q2.2
    q2_2_cita_servicio = models.IntegerField(db_column="q2_2_cita_servicio", blank=True, null=True)
    q2_2c_sin_cita = models.CharField(db_column="q2_2c_sin_cita", max_length=10, blank=True, null=True)

    # Q2.3
    q2_3_atendido_valorado = models.IntegerField(db_column="q2_3_atendido_valorado", blank=True, null=True)
    q2_3a_amabilidad_personal = models.CharField(db_column="q2_3a_amabilidad_personal", max_length=10, blank=True, null=True)
    q2_3b_recepcion_rapida = models.CharField(db_column="q2_3b_recepcion_rapida", max_length=10, blank=True, null=True)
    q2_3c_informado_estatus = models.CharField(db_column="q2_3c_informado_estatus", max_length=10, blank=True, null=True)
    q2_3d_transparencia = models.CharField(db_column="q2_3d_transparencia", max_length=10, blank=True, null=True)

    # Q2.4
    q2_4_explicacion_info = models.IntegerField(db_column="q2_4_explicacion_info", blank=True, null=True)
    q2_4a_explico_trabajos_costo = models.CharField(db_column="q2_4a_explico_trabajos_costo", max_length=10, blank=True, null=True)
    q2_4b_enfocado_necesidades = models.CharField(db_column="q2_4b_enfocado_necesidades", max_length=10, blank=True, null=True)
    q2_4c_conocimiento_respuesta = models.CharField(db_column="q2_4c_conocimiento_respuesta", max_length=10, blank=True, null=True)
    q2_4d_reviso_trabajos_entrega = models.CharField(db_column="q2_4d_reviso_trabajos_entrega", max_length=10, blank=True, null=True)
    q2_4e_monto_justo = models.CharField(db_column="q2_4e_monto_justo", max_length=10, blank=True, null=True)

    # Q2.5
    q2_5_entrega = models.IntegerField(db_column="q2_5_entrega", blank=True, null=True)
    q2_5a_atendido_inmediato = models.CharField(db_column="q2_5a_atendido_inmediato", max_length=10, blank=True, null=True)
    q2_5b_auto_listo_fecha = models.CharField(db_column="q2_5b_auto_listo_fecha", max_length=10, blank=True, null=True)
    q2_5c_tiempo_recoger_auto = models.CharField(db_column="q2_5c_tiempo_recoger_auto", max_length=10, blank=True, null=True)

    # Q2.6
    q2_6_instalaciones_amenidades = models.IntegerField(db_column="q2_6_instalaciones_amenidades", blank=True, null=True)
    q2_6a_entrada_salida = models.CharField(db_column="q2_6a_entrada_salida", max_length=10, blank=True, null=True)
    q2_6b_agencia_limpia = models.CharField(db_column="q2_6b_agencia_limpia", max_length=10, blank=True, null=True)
    q2_6c_sala_espera = models.CharField(db_column="q2_6c_sala_espera", max_length=10, blank=True, null=True)
    q2_6d_amenidades = models.CharField(db_column="q2_6d_amenidades", max_length=10, blank=True, null=True)

    # Q3 y Q4
    q3_recomendacion = models.IntegerField(db_column="q3_recomendacion", blank=True, null=True)
    q4_comentarios_servicio = models.TextField(db_column="q4_comentarios_servicio", blank=True, null=True)

    # Producto
    p1_satisfaccion_producto = models.SmallIntegerField(db_column="p1_satisfaccion_producto", blank=True, null=True)
    p1_1_comentarios_auto = models.TextField(db_column="p1_1_comentarios_auto", blank=True, null=True)

    # Autorizaciones
    ot1_autoriza_compartir_datos = models.CharField(db_column="ot1_autoriza_compartir_datos", max_length=10, blank=True, null=True)
    q9_autoriza_seguimiento = models.CharField(db_column="q9_autoriza_seguimiento", max_length=10, blank=True, null=True)
    q9a_autoriza_transferencia = models.CharField(db_column="q9a_autoriza_transferencia", max_length=10, blank=True, null=True)
    q10_autoriza_publicacion = models.CharField(db_column="q10_autoriza_publicacion", max_length=10, blank=True, null=True)

    # Índice
    indice_satisfaccion_general = models.FloatField(db_column="indice_satisfaccion_general", blank=True, null=True)

    # Auditoría
    fecha_carga = models.DateTimeField(db_column="fecha_carga", auto_now_add=True)

    class Meta:
        managed = False
        db_table = "encuesta_jdpowerservicio"
        verbose_name = "Encuesta JD Power Servicio"
        verbose_name_plural = "Encuestas JD Power Servicio"

    def __str__(self):
        return f"{self.id_encuesta} - {self.concesionaria or 'Sin concesionaria'}"