#digitales/models.py
from django.db import models
from django.utils import timezone

def normaliza_tel_mx(raw: str) -> str:
    """
    Normaliza a '52' + 10 dígitos cuando aplica.
    - "2720000000" -> "522720000000"
    - "+52 2720000000" -> "522720000000"
    - "52 2720000000" -> "522720000000"
    """
    digits = "".join(c for c in str(raw or "") if c.isdigit())
    if not digits:
        return ""
    if len(digits) == 10:
        return "52" + digits
    if len(digits) == 12 and digits.startswith("52"):
        return digits
    return digits

class ClientesDigitales(models.Model):
    nombre = models.CharField(max_length=200, blank=True, default="")
    telefono = models.CharField(max_length=32, db_index=True, unique=True)
    correo = models.EmailField(blank=True, default="")

    agencia = models.CharField(max_length=120, blank=True, default="")
    business = models.CharField(max_length=120, blank=True, default="")
    canal_contacto = models.CharField(max_length=120, blank=True, default="")
    pauta = models.CharField(max_length=500, blank=True, default="")
    estado = models.CharField(max_length=120, blank=True, default="")

    # ✅ NUEVO: separa responsabilidades reales
    asesor_digital = models.CharField(max_length=200, blank=True, default="")
    asesor_ventas = models.CharField(max_length=200, blank=True, default="")

    # (si quieres mantenerlo por compatibilidad)
    responsable = models.CharField(max_length=200, blank=True, default="")

    auto_interes = models.CharField(max_length=255, blank=True, default="")
    comentarios = models.TextField(max_length=2000, blank=True, default="")

    cita_efectiva = models.BooleanField(default=False)
    cita_virtual = models.BooleanField(default=False)
    solicitud_credito = models.BooleanField(default=False)
    facturado = models.BooleanField(default=False)
    resultado_solicitud = models.CharField(max_length=120, blank=True, default="")
    tipo_venta = models.CharField(max_length=120, blank=True, default="")

    primer_contacto_at = models.DateTimeField(null=True, blank=True)
    ultimo_contacto_at = models.DateTimeField(null=True, blank=True)

    last_read_at = models.DateTimeField(null=True, blank=True)

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "clientes_digitales"
        managed = True

    def touch_ultimo_contacto(self, when=None, save_now=False):
        when = when or timezone.now()
        if not self.primer_contacto_at:
            self.primer_contacto_at = when
        self.ultimo_contacto_at = when
        if save_now:
            self.save(update_fields=["primer_contacto_at", "ultimo_contacto_at", "actualizado"])
    def mark_read(self, when=None):
            when = when or timezone.now()
            self.last_read_at = when
            self.save(update_fields=["last_read_at", "actualizado"])

    def save(self, *args, **kwargs):
        self.telefono = normaliza_tel_mx(self.telefono)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nombre} ({self.telefono})".strip()

class MensajeWhatsApp(models.Model):
    """
    Mensajes guardados (entrantes y salientes).
    """
    class Direccion(models.TextChoices):
        IN = "in", "Entrante"
        OUT = "out", "Saliente"

    telefono = models.CharField(max_length=32, db_index=True)
    cliente = models.ForeignKey(
        ClientesDigitales,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mensajes",
    )

    direction = models.CharField(max_length=3, choices=Direccion.choices)
    body = models.TextField(blank=True, default="")
    wa_message_id = models.CharField(max_length=120, blank=True, default="", db_index=True)
    status = models.CharField(max_length=30, blank=True, default="sent")  # sent/delivered/read/failed/received

    raw = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "digitales_mensajes"
        managed = True
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["telefono", "created_at"]),
            models.Index(fields=["wa_message_id"]),
        ]

    def __str__(self):
        return f"{self.direction} {self.telefono} {self.created_at:%Y-%m-%d %H:%M}"
