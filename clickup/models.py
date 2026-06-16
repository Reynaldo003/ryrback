# clickup/models.py
import os
import uuid
from django.db import models
from django.utils import timezone
from CrmConformidad.models import Usuario

def evidencia_upload_to(instance, filename):
    ext = os.path.splitext(filename or "")[1]
    ext = ext if ext else ".bin"
    return f"clickup/evidencias/{timezone.now().strftime('%Y/%m')}/{uuid.uuid4().hex}{ext}"

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
        managed = True
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
        managed = True
        db_table = "clickup_miembro_equipo"
        constraints = [
            models.UniqueConstraint(fields=["equipo", "usuario"], name="uq_clickup_miembro_equipo_usuario")
        ]

    def __str__(self):
        return f"{self.equipo_id} - {self.usuario_id} - {self.rol}"


class InvitacionEquipo(models.Model):
    ESTADOS = (
        ("PENDING", "Pendiente"),
        ("ACCEPTED", "Aceptada"),
        ("REJECTED", "Rechazada"),
        ("REVOKED", "Revocada"),
        ("EXPIRED", "Expirada"),
    )

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
        related_name="invitaciones",
    )
    correo = models.EmailField(max_length=255, blank=True, null=True)

    usuario_invitado = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="invitaciones_clickup_recibidas",
    )

    rol = models.CharField(max_length=12, choices=ROLES, default="MEMBER")
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
        managed = True
        db_table = "clickup_invitacion_equipo"
        indexes = [
            models.Index(fields=["equipo", "correo"]),
            models.Index(fields=["token"]),
            models.Index(fields=["estado"]),
            models.Index(fields=["usuario_invitado", "estado"]),
        ]

    def save(self, *args, **kwargs):
        if not self.expira_en:
            self.expira_en = timezone.now() + timezone.timedelta(days=7)
        super().save(*args, **kwargs)

    def esta_expirada(self):
        return bool(self.expira_en and timezone.now() >= self.expira_en)

    def __str__(self):
        destino = self.usuario_invitado_id or self.correo or "sin destino"
        return f"Invitación {self.id} -> {destino}"


class Proyecto(models.Model):
    id = models.BigAutoField(primary_key=True)
    equipo = models.ForeignKey(
        Equipo,
        on_delete=models.CASCADE,
        related_name="proyectos",
    )
    nombre = models.CharField(max_length=140)
    descripcion = models.CharField(max_length=255, blank=True, null=True)
    color = models.CharField(max_length=20, blank=True, null=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = True
        db_table = "clickup_proyectos"
        constraints = [
            models.UniqueConstraint(fields=["equipo", "nombre"], name="uq_clickup_proyecto_equipo_nombre")
        ]

    def __str__(self):
        return self.nombre


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
        managed = True
        db_table = "clickup_listas"
        ordering = ["orden", "id"]
        constraints = [
            models.UniqueConstraint(fields=["proyecto", "nombre"], name="uq_clickup_lista_proyecto_nombre")
        ]

    def __str__(self):
        return self.nombre


class Tarea(models.Model):
    PRIORIDADES = (
        ("LOW", "Baja"),
        ("MEDIUM", "Media"),
        ("HIGH", "Alta"),
        ("URGENT", "Urgente"),
    )

    ESTADOS = (
        ("Por hacer", "Por hacer"),
        ("En proceso", "En proceso"),
        ("Hecho", "Hecho"),
    )

    id = models.BigAutoField(primary_key=True)
    lista = models.ForeignKey(
        Lista,
        on_delete=models.CASCADE,
        related_name="tareas",
    )

    # Relación para subtareas (Autorreferencial)
    tarea_padre = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='subtareas'
    )

    titulo = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True, null=True, default="")
    estado = models.CharField(max_length=20, choices=ESTADOS, default="Por hacer")
    prioridad = models.CharField(max_length=10, choices=PRIORIDADES, default="MEDIUM")
    
    # Campos especializados del formulario "Time for Action"
    descripcion_problema = models.TextField(blank=True, null=True)
    causa = models.CharField(max_length=150, blank=True, null=True)
    raiz = models.CharField(max_length=150, blank=True, null=True)
    desarrollo_estrategia = models.TextField(blank=True, null=True)
    resultados = models.TextField(blank=True, null=True)

    # Fechas y control de orden
    inicio = models.DateTimeField(blank=True, null=True) 
    vence = models.DateTimeField(blank=True, null=True)   
    creada = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    orden = models.IntegerField(default=0)
    
    # Control para el check de las subtareas
    completada = models.BooleanField(default=False) 

    creado_por = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name="tareas_clickup_creadas",
    )

    class Meta:
        managed = True
        db_table = "clickup_tareas"
        ordering = ["orden", "id"]

    def __str__(self):
        if self.tarea_padre_id:
            return f"[Subtarea de {self.tarea_padre.titulo}] - {self.titulo}"
        return f"[Plan de Acción] - {self.titulo}"

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
        managed = True
        db_table = "clickup_tarea_asignada"
        constraints = [
            models.UniqueConstraint(fields=["tarea", "usuario"], name="uq_clickup_tarea_asignada_tarea_usuario")
        ]

    def __str__(self):
        return f"{self.tarea_id} -> {self.usuario_id}"


class NotificacionClickup(models.Model):
    TIPOS = (
        ("TEAM_INVITE", "Invitación a equipo"),
        ("TASK_ASSIGNED", "Tarea asignada"),
        ("TASK_UPDATED", "Tarea actualizada"),
        ("BUG_REPORTED", "Error reportado"),
    )

    ESTADOS = (
        ("PENDING", "Pendiente"),
        ("ACCEPTED", "Aceptada"),
        ("DISMISSED", "Descartada"),
        ("READ", "Leída"),
    )

    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name="notificaciones_clickup",
    )
    tipo = models.CharField(max_length=20, choices=TIPOS)
    titulo = models.CharField(max_length=180)
    mensaje = models.CharField(max_length=255, blank=True, null=True)

    equipo = models.ForeignKey(
        Equipo,
        on_delete=models.CASCADE,
        related_name="notificaciones",
        null=True,
        blank=True,
    )
    proyecto = models.ForeignKey(
        Proyecto,
        on_delete=models.CASCADE,
        related_name="notificaciones",
        null=True,
        blank=True,
    )
    tarea = models.ForeignKey(
        Tarea,
        on_delete=models.CASCADE,
        related_name="notificaciones",
        null=True,
        blank=True,
    )
    invitacion = models.ForeignKey(
        InvitacionEquipo,
        on_delete=models.CASCADE,
        related_name="notificaciones",
        null=True,
        blank=True,
    )

    estado = models.CharField(max_length=12, choices=ESTADOS, default="PENDING")
    creado_en = models.DateTimeField(auto_now_add=True)
    leido_en = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = True
        db_table = "clickup_notificacion"
        indexes = [
            models.Index(fields=["usuario", "creado_en"]),
            models.Index(fields=["usuario", "estado"]),
            models.Index(fields=["tipo"]),
        ]

    def __str__(self):
        return f"{self.usuario_id} - {self.tipo} - {self.estado}"


class ReporteIncidencia(models.Model):
    TIPOS = (
        ("BUG", "Error"),
        ("SUGGESTION", "Sugerencia"),
    )

    ESTADOS = (
        ("OPEN", "Abierto"),
        ("IN_PROGRESS", "En progreso"),
        ("RESOLVED", "Resuelto"),
        ("CLOSED", "Cerrado"),
    )

    id = models.BigAutoField(primary_key=True)
    tipo = models.CharField(max_length=20, choices=TIPOS, default="BUG")
    titulo = models.CharField(max_length=180)
    descripcion = models.TextField()
    estado = models.CharField(max_length=20, choices=ESTADOS, default="OPEN")

    reportado_por = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name="reportes_incidencia_creados",
    )

    equipo = models.ForeignKey(
        Equipo,
        on_delete=models.PROTECT,
        related_name="reportes_incidencia",
    )
    proyecto = models.ForeignKey(
        Proyecto,
        on_delete=models.PROTECT,
        related_name="reportes_incidencia",
    )
    tarea = models.OneToOneField(
        Tarea,
        on_delete=models.CASCADE,
        related_name="reporte_incidencia",
    )

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    resuelto_en = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = True
        db_table = "clickup_reporte_incidencia"
        indexes = [
            models.Index(fields=["tipo", "estado"]),
            models.Index(fields=["creado_en"]),
            models.Index(fields=["reportado_por"]),
        ]

    def __str__(self):
        return f"{self.id} - {self.titulo}"


class EvidenciaTarea(models.Model):
    TIPOS = (
        ("BUG", "Evidencia del bug"),
        ("RESOLUTION", "Evidencia de solución"),
    )

    id = models.BigAutoField(primary_key=True)
    tarea = models.ForeignKey(
        Tarea,
        on_delete=models.CASCADE,
        related_name="evidencias",
    )
    reporte = models.ForeignKey(
        ReporteIncidencia,
        on_delete=models.CASCADE,
        related_name="evidencias",
        null=True,
        blank=True,
    )
    tipo = models.CharField(max_length=20, choices=TIPOS)
    comentario = models.CharField(max_length=255, blank=True, null=True)
    archivo = models.FileField(upload_to=evidencia_upload_to)
    subido_por = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name="evidencias_clickup_subidas",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = True
        db_table = "clickup_evidencia_tarea"
        indexes = [
            models.Index(fields=["tarea", "tipo"]),
            models.Index(fields=["creado_en"]),
        ]

    def __str__(self):
        return f"{self.tarea_id} - {self.tipo} - {self.id}"