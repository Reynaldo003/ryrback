# logs/models.py
from django.db import models


class LogActividad(models.Model):
    """Registro de una acción/modificación hecha por un usuario.

    Solo se loggean eventos de modificación (CREAR/EDITAR/ELIMINAR) y
    LOGIN/LOGIN_FALLIDO. Nunca se guarda el payload completo de la
    petición ni datos sensibles.
    """

    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey(
        "CrmConformidad.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logs_actividad",
    )
    modulo = models.CharField(max_length=100, db_index=True)
    tipo = models.CharField(max_length=30, db_index=True)
    entidad = models.CharField(max_length=250, blank=True, default="")
    cambio = models.TextField(blank=True, default="")
    datos = models.JSONField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    fecha = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "logs_actividad"
        ordering = ["-fecha"]
        indexes = [
            models.Index(fields=["usuario", "fecha"]),
            models.Index(fields=["modulo", "fecha"]),
            models.Index(fields=["tipo", "fecha"]),
        ]

    def __str__(self):
        return f"{self.fecha} · {self.usuario_id} · {self.tipo} · {self.modulo}"