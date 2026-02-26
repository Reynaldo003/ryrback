# clickup/models.py
import uuid
from django.db import models
from django.utils import timezone

from CrmConformidad.models import Usuario


class Equipo(models.Model):
    id = models.BigAutoField(primary_key=True)
    nombre = models.CharField(max_length=120)
    descripcion = models.CharField(max_length=255, blank=True, null=True)

    propietario = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name="equipos_propios",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "clickup_equipo"

    def __str__(self):
        return self.nombre


class MiembroEquipo(models.Model):
    ROLES = (
        ("OWNER", "Propietario"),
        ("ADMIN", "Administrador"),
        ("MEMBER", "Miembro"),
        ("VIEWER", "Lector"),
    )

    id = models.BigAutoField(primary_key=True)
    equipo = models.ForeignKey(
        Equipo,
        on_delete=models.CASCADE,
        related_name="miembros",
    )
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name="membresias_equipo",
    )
    rol = models.CharField(max_length=12, choices=ROLES, default="MEMBER")
    unido_en = models.DateTimeField(auto_now_add=True)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "clickup_miembro_equipo"
        constraints = [
            models.UniqueConstraint(fields=["equipo", "usuario"], name="uq_clickup_miembro_equipo_usuario")
        ]


class InvitacionEquipo(models.Model):
    ESTADOS = (
        ("PENDING", "Pendiente"),
        ("ACCEPTED", "Aceptada"),
        ("REVOKED", "Revocada"),
        ("EXPIRED", "Expirada"),
    )

    id = models.BigAutoField(primary_key=True)
    equipo = models.ForeignKey(
        Equipo,
        on_delete=models.CASCADE,
        related_name="invitaciones",
    )
    correo = models.EmailField(max_length=255)
    rol = models.CharField(max_length=12, default="MEMBER")
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    invitado_por = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name="invitaciones_equipo_enviadas",
    )
    estado = models.CharField(max_length=10, choices=ESTADOS, default="PENDING")

    creado_en = models.DateTimeField(auto_now_add=True)
    expira_en = models.DateTimeField(blank=True, null=True)

    aceptado_en = models.DateTimeField(blank=True, null=True)
    aceptado_por = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="invitaciones_equipo_aceptadas",
    )

    class Meta:
        db_table = "clickup_invitacion_equipo"
        indexes = [
            models.Index(fields=["equipo", "correo"]),
            models.Index(fields=["token"]),
            models.Index(fields=["estado"]),
        ]

    def save(self, *args, **kwargs):
        if not self.expira_en:
            self.expira_en = timezone.now() + timezone.timedelta(days=7)
        super().save(*args, **kwargs)

    def esta_expirada(self):
        return timezone.now() >= self.expira_en


# ========= Proyectos por equipo =========

class Proyecto(models.Model):
    id = models.BigAutoField(primary_key=True)
    equipo = models.ForeignKey(
        Equipo,
        on_delete=models.CASCADE,
        related_name="proyectos",
    )
    nombre = models.CharField(max_length=140)
    descripcion = models.CharField(max_length=255, blank=True, null=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "clickup_proyectos"
        constraints = [
            models.UniqueConstraint(fields=["equipo", "nombre"], name="uq_clickup_proyecto_equipo_nombre")
        ]


class Lista(models.Model):
    id = models.BigAutoField(primary_key=True)
    proyecto = models.ForeignKey(
        Proyecto,
        on_delete=models.CASCADE,
        related_name="listas",
    )
    nombre = models.CharField(max_length=120)
    orden = models.IntegerField(default=0)

    class Meta:
        db_table = "clickup_listas"
        ordering = ["orden", "id"]
        constraints = [
            models.UniqueConstraint(fields=["proyecto", "nombre"], name="uq_clickup_lista_proyecto_nombre")
        ]


class Tarea(models.Model):
    PRIORIDADES = (
        ("LOW", "Baja"),
        ("MEDIUM", "Media"),
        ("HIGH", "Alta"),
        ("URGENT", "Urgente"),
    )

    id = models.BigAutoField(primary_key=True)
    lista = models.ForeignKey(
        Lista,
        on_delete=models.CASCADE,
        related_name="tareas",
    )

    titulo = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True, null=True)

    prioridad = models.CharField(max_length=10, choices=PRIORIDADES, default="MEDIUM")
    vence_en = models.DateTimeField(blank=True, null=True)

    # orden dentro de la lista (para kanban)
    orden = models.IntegerField(default=0)

    creado_por = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name="tareas_clickup_creadas",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "clickup_tareas"
        ordering = ["orden", "id"]


class TareaAsignada(models.Model):
    id = models.BigAutoField(primary_key=True)
    tarea = models.ForeignKey(
        Tarea,
        on_delete=models.CASCADE,
        related_name="asignados",
    )
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name="tareas_clickup_asignadas",
    )

    class Meta:
        db_table = "clickup_tarea_asignada"
        constraints = [
            models.UniqueConstraint(fields=["tarea", "usuario"], name="uq_clickup_tarea_asignada_tarea_usuario")
        ]