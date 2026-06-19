# Digitales/models.py
from django.db import models
from django.utils import timezone

from citas.models import ClienteComercial, normaliza_tel_mx

class ExpedienteDigital(models.Model):
    cliente = models.OneToOneField(
        ClienteComercial,
        db_column="id_cliente",
        on_delete=models.PROTECT,
        related_name="expediente_digital",
    )

    agencia = models.CharField(max_length=120, blank=True, default="")
    business = models.CharField(max_length=120, blank=True, default="")
    canal_contacto = models.CharField(max_length=120, blank=True, default="")
    pauta = models.TextField(blank=True, default="")
    estado = models.CharField(max_length=120, blank=True, default="")
    auto_interes = models.CharField(max_length=255, blank=True, default="")
    asesor_digital = models.CharField(max_length=200, blank=True, default="")
    asesor_ventas = models.CharField(max_length=200, blank=True, default="")
    comentarios = models.TextField(max_length=2000, blank=True, default="")

    enganche_monto = models.PositiveIntegerField(null=True, blank=True)
    presupuesto_mensual = models.PositiveIntegerField(null=True, blank=True)
    buro_estado = models.CharField(max_length=30,blank=True,default="",)  # bueno | regular | iniciando | desconocido
    forma_pago = models.CharField(max_length=30,blank=True,default="",)  # contado | credito | arrendamiento | desconocido
    tipo_cliente = models.CharField(max_length=30,blank=True,default="",)  # persona_fisica | persona_moral | desconocido
    uso_vehiculo = models.CharField(max_length=255, blank=True, default="")
    plazo_compra = models.CharField(max_length=120, blank=True, default="")
    comprobacion_ingresos = models.CharField(max_length=200, blank=True, default="")

    # Control operativo de IA
    ia_pausada = models.BooleanField(default=False)
    ia_pausada_motivo = models.CharField(max_length=120, blank=True, default="")
    ia_pausada_at = models.DateTimeField(null=True, blank=True)

    requiere_asesor = models.BooleanField(default=False)
    motivo_requiere_asesor = models.CharField(max_length=120, blank=True, default="")

    cotizacion_pendiente = models.BooleanField(default=False)
    cotizacion_solicitada_at = models.DateTimeField(null=True, blank=True)

    primer_mensaje_cliente = models.DateTimeField(null=True, blank=True, db_index=True)
    primer_contacto_asesor = models.DateTimeField(null=True, blank=True, db_index=True)
    ultimo_contacto_asesor = models.DateTimeField(null=True, blank=True, db_index=True)

    last_read_at = models.DateTimeField(null=True, blank=True)

    resumen = models.TextField(blank=True, default="")
    resumen_actualizado_at = models.DateTimeField(null=True, blank=True)
    resumen_fuente = models.CharField(max_length=30,blank=True,default="",)  # auto_6 | auto_1h | manual

    ultima_cita = models.ForeignKey(
        "citas.Cita",
        db_column="id_ultima_cita",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    ultima_cita_agendada = models.DateTimeField(null=True, blank=True)
    asistencia = models.BooleanField(default=False)

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "expediente_digital"
        managed = True

    def touch_mensaje_cliente(self, when=None, save_now=False):
        """
        Marca cuándo escribió el cliente por primera vez.

        Este campo sirve para saber desde qué momento empezó
        el tiempo de respuesta comercial.
        """
        when = when or timezone.now()

        campos = []

        if not self.primer_mensaje_cliente:
            self.primer_mensaje_cliente = when
            campos.append("primer_mensaje_cliente")

        if save_now and campos:
            campos.append("actualizado")
            self.save(update_fields=campos)


    def touch_contacto_asesor(self, when=None, save_now=False):
        """
        Marca cuándo respondió el asesor humano.

        primer_contacto_asesor:
            Se llena una sola vez.

        ultimo_contacto_asesor:
            Se actualiza cada vez que el asesor responde.
        """
        when = when or timezone.now()

        campos = []

        if not self.primer_contacto_asesor:
            self.primer_contacto_asesor = when
            campos.append("primer_contacto_asesor")

        self.ultimo_contacto_asesor = when
        campos.append("ultimo_contacto_asesor")

        if save_now:
            campos.append("actualizado")
            self.save(update_fields=list(dict.fromkeys(campos)))

    def mark_read(self, when=None):
        when = when or timezone.now()
        self.last_read_at = when
        self.save(update_fields=["last_read_at", "actualizado"])

    def __str__(self):
        return f"ExpedienteDigital #{self.cliente_id} - {self.cliente.telefono}"

class ConversacionIA(models.Model):
    expediente = models.ForeignKey(
        ExpedienteDigital,
        on_delete=models.CASCADE,
        related_name="conversaciones_ia",
    )

    numero_asesor = models.CharField(max_length=15, db_index=True)

    ia_activa = models.BooleanField(default=True)
    ia_pausada = models.BooleanField(default=False)
    motivo_pausa = models.CharField(max_length=120, blank=True, default="")

    estado_conversacion = models.CharField(max_length=50,blank=True,default="sin_iniciar",)
    # sin_iniciar | perfilando | informando | pendiente_cotizacion | pausada

    pregunta_pendiente = models.CharField(max_length=80, blank=True, default="")
    pregunta_pendiente_intentos = models.PositiveSmallIntegerField(default=0)

    ultima_intencion = models.CharField(max_length=80, blank=True, default="")
    ultimo_modelo_mencionado = models.CharField(max_length=120, blank=True, default="")

    resumen_conversacion = models.TextField(blank=True, default="")
    datos_extra = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "conversacion_ia"
        unique_together = [("expediente", "numero_asesor")]
        indexes = [
            models.Index(fields=["numero_asesor", "ia_activa", "ia_pausada"]),
            models.Index(fields=["estado_conversacion"]),
        ]

    def __str__(self):
        return f"IA {self.numero_asesor} | expediente {self.expediente_id}"

class InteresVehiculoProspecto(models.Model):
    expediente = models.ForeignKey(
        ExpedienteDigital,
        on_delete=models.CASCADE,
        related_name="intereses_vehiculos",
    )

    modelo = models.CharField(max_length=120)
    version = models.CharField(max_length=120, blank=True, default="")
    origen = models.CharField(max_length=50, blank=True, default="ia")
    activo = models.BooleanField(default=True)
    prioridad = models.PositiveSmallIntegerField(default=1)

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "intereses_vehiculos_prospectos"
        indexes = [
            models.Index(fields=["expediente", "activo"]),
            models.Index(fields=["modelo"]),
        ]

    def __str__(self):
        version = f" {self.version}" if self.version else ""
        return f"{self.modelo}{version} | expediente {self.expediente_id}"


class MensajeWhatsApp(models.Model):
    class Direccion(models.TextChoices):
        IN = "in", "Entrante"
        OUT = "out", "Saliente"

    telefono = models.CharField(max_length=32, db_index=True)
    numero_asesor = models.CharField(max_length=15)

    cliente = models.ForeignKey(
        ClienteComercial,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mensajes_whatsapp",
    )

    direction = models.CharField(max_length=3, choices=Direccion.choices)
    body = models.TextField(blank=True, default="")
    wa_message_id = models.CharField(max_length=120, blank=True, default="", db_index=True)
    status = models.CharField(max_length=30, blank=True, default="sent")

    raw = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "digitales_mensajes"
        managed = True
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(
                fields=["telefono", "numero_asesor", "created_at", "id"],
                name="dig_msg_tel_line_dt_idx",
            ),
            models.Index(
                fields=["telefono", "numero_asesor", "-created_at", "-id"],
                name="dig_msg_tel_line_desc_idx",
            ),
            models.Index(fields=["numero_asesor", "created_at"]),
            models.Index(fields=["wa_message_id"]),
        ]

    def save(self, *args, **kwargs):
        self.telefono = normaliza_tel_mx(self.telefono)
        self.numero_asesor = normaliza_tel_mx(self.numero_asesor)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.direction} {self.telefono} {self.numero_asesor} {self.created_at:%Y-%m-%d %H:%M}"


class LecturaWhatsApp(models.Model):
    expediente = models.ForeignKey(
        ExpedienteDigital,
        on_delete=models.CASCADE,
        related_name="lecturas_whatsapp",
    )
    numero_asesor = models.CharField(max_length=15, db_index=True)
    last_read_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "digitales_lecturas_whatsapp"
        managed = True
        unique_together = [("expediente", "numero_asesor")]
        indexes = [
            models.Index(fields=["expediente", "numero_asesor"]),
            models.Index(fields=["numero_asesor", "last_read_at"]),
        ]

    def touch(self, when=None):
        self.last_read_at = when or timezone.now()
        self.save(update_fields=["last_read_at", "updated_at"])


class CampanaMeta(models.Model):
    id_campana = models.BigIntegerField(primary_key=True)
    id_concesionaria = models.IntegerField()
    sucursal = models.CharField(max_length=100)
    nombre_campana = models.CharField(max_length=500)
    inicio_campana = models.DateField(null=True, blank=True)
    fin_campana = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "campanas_meta"
        managed = False


class MapeoFuenteMeta(models.Model):
    id_fuente = models.CharField(
        max_length=120,
        primary_key=True,
        db_column="id_fuente",
    )
    tipo_fuente = models.CharField(max_length=30)
    id_campana = models.BigIntegerField(null=True, blank=True)
    nombre_campana = models.CharField(max_length=500, blank=True, default="")
    id_anuncio = models.BigIntegerField(null=True, blank=True)
    nombre_anuncio = models.CharField(max_length=500, blank=True, default="")
    id_conjunto = models.BigIntegerField(null=True, blank=True)
    nombre_conjunto = models.CharField(max_length=500, blank=True, default="")
    sucursal = models.CharField(max_length=100, blank=True, default="")
    respuesta_meta = models.TextField(blank=True, default="")
    creado_en = models.DateTimeField(null=True, blank=True)
    actualizado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "mapeo_fuentes_meta"
        managed = False

class CatalogoVehiculos(models.Model):
    marca = models.CharField(max_length=80, default="Volkswagen")
    modelo = models.CharField(max_length=120)
    ano = models.PositiveSmallIntegerField()
    version = models.CharField(max_length=120, blank=True, default="")

    precio_lista = models.PositiveIntegerField(null=True, blank=True)
    precio_contado = models.PositiveIntegerField(null=True, blank=True)
    precio_financiado = models.PositiveIntegerField(null=True, blank=True)

    resumen = models.TextField(blank=True, default="")
    ficha_tecnica = models.JSONField(default=dict, blank=True)

    url_ficha_tecnica = models.CharField(max_length=800, blank=True, default="")
    imagenes = models.JSONField(default=list, blank=True)
    ultima_actualizacion = models.DateField(null=True, blank=True)

    activo = models.BooleanField(default=True)

    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "catalogo_vehiculos"
        ordering = ["marca", "modelo", "ano", "version"]
        indexes = [
            models.Index(fields=["marca", "modelo", "ano"]),
            models.Index(fields=["activo"]),
            models.Index(fields=["modelo"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["marca", "modelo", "ano", "version"],
                name="uniq_catalogo_vehiculos_modelo_version",
            )
        ]

    def __str__(self):
        partes = [self.marca, self.modelo, str(self.ano), self.version]
        return " ".join([p for p in partes if p]).strip()
    
class ConfiguracionIAWhatsApp(models.Model):
    numero_asesor = models.CharField(max_length=15, unique=True)

    activo = models.BooleanField(default=False)
    horarios = models.JSONField(default=dict, blank=True)

    identidad = models.TextField(blank=True, default="")
    precios = models.TextField(blank=True, default="")
    perfilamiento = models.TextField(blank=True, default="")
    limites = models.TextField(blank=True, default="")
    personalidad = models.TextField(blank=True, default="")
    condiciones_fijas = models.TextField(blank=True, default="")
    actualizado_por = models.CharField(max_length=120, blank=True, default="")

    class Meta:
        db_table = "configuracion_ia_whatsapp"
        ordering = ["numero_asesor"]

    def save(self, *args, **kwargs):
        self.numero_asesor = normaliza_tel_mx(self.numero_asesor)
        super().save(*args, **kwargs)

    def __str__(self):
        estado = "activa" if self.activo else "inactiva"
        return f"IA WhatsApp {self.numero_asesor} | {estado}"