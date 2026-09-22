# notificaciones/models.py
from django.db import models


class Notificacion(models.Model):
    """Notificación de WhatsApp persistida para la bandeja/campana.

    Se crea en el mismo flujo del push por WebSocket
    (notificar_mensaje_whatsapp) para que la notificación quede
    disponible en la campana aunque el navegador no esté abierto
    en ese momento o el WebSocket se haya caído.
    """

    usuario = models.ForeignKey(
        "CrmConformidad.Usuario",
        on_delete=models.CASCADE,
        related_name="notificaciones_whatsapp",
    )
    numero_asesor = models.CharField(max_length=20, db_index=True)
    telefono = models.CharField(max_length=20, blank=True, default="")
    nombre = models.CharField(max_length=255, blank=True, default="")
    mensaje = models.TextField(blank=True, default="")
    wa_message_id = models.CharField(max_length=100, blank=True, default="")
    expediente_id = models.CharField(max_length=50, blank=True, null=True)
    url = models.CharField(max_length=500, blank=True, default="")
    leida = models.BooleanField(default=False)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notificaciones_whatsapp_notificacion"
        ordering = ["-creado"]
        indexes = [
            models.Index(fields=["usuario", "leida", "creado"]),
        ]

    def __str__(self):
        return (
            f"Notificacion({self.usuario_id} · "
            f"{self.telefono} · leida={self.leida})"
        )