# clickup/models.py
import uuid
from django.db import models
from django.utils import timezone

from CrmConformidad.models import Usuario  # AJUSTA a tu app real donde está Usuario


class Team(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=120)
    descripcion = models.CharField(max_length=255, blank=True, null=True)

    owner = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name="owned_teams")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "clickup_teams"

    def __str__(self):
        return self.name


class TeamMember(models.Model):
    ROLE_CHOICES = (
        ("OWNER", "Owner"),
        ("ADMIN", "Admin"),
        ("MEMBER", "Member"),
        ("VIEWER", "Viewer"),
    )

    id = models.BigAutoField(primary_key=True)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="team_memberships")
    role = models.CharField(max_length=12, choices=ROLE_CHOICES, default="MEMBER")
    joined_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "clickup_team_members"
        unique_together = ("team", "user")


class TeamInvite(models.Model):
    STATUS_CHOICES = (
        ("PENDING", "Pending"),
        ("ACCEPTED", "Accepted"),
        ("REVOKED", "Revoked"),
        ("EXPIRED", "Expired"),
    )

    id = models.BigAutoField(primary_key=True)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="invites")
    email = models.EmailField(max_length=255)
    role = models.CharField(max_length=12, default="MEMBER")
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    invited_by = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name="sent_team_invites")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="PENDING")

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    accepted_at = models.DateTimeField(blank=True, null=True)
    accepted_by = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, null=True, blank=True, related_name="accepted_team_invites"
    )

    class Meta:
        db_table = "clickup_team_invites"
        indexes = [
            models.Index(fields=["team", "email"]),
            models.Index(fields=["token"]),
            models.Index(fields=["status"]),
        ]

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timezone.timedelta(days=7)
        super().save(*args, **kwargs)

    def is_expired(self):
        return timezone.now() >= self.expires_at


# ========= Proyectos por equipo =========

class Project(models.Model):
    id = models.BigAutoField(primary_key=True)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="projects")
    name = models.CharField(max_length=140)
    descripcion = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "clickup_projects"
        unique_together = ("team", "name")


class List(models.Model):
    id = models.BigAutoField(primary_key=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="lists")
    name = models.CharField(max_length=120)
    order = models.IntegerField(default=0)

    class Meta:
        db_table = "clickup_lists"
        ordering = ["order", "id"]
        unique_together = ("project", "name")


class Task(models.Model):
    PRIORITY_CHOICES = (
        ("LOW", "Low"),
        ("MEDIUM", "Medium"),
        ("HIGH", "High"),
        ("URGENT", "Urgent"),
    )

    id = models.BigAutoField(primary_key=True)
    list = models.ForeignKey(List, on_delete=models.CASCADE, related_name="tasks")

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)

    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default="MEDIUM")
    due_date = models.DateTimeField(blank=True, null=True)

    # orden dentro de la lista (para kanban)
    order = models.IntegerField(default=0)

    created_by = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name="created_clickup_tasks")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "clickup_tasks"
        ordering = ["order", "id"]


class TaskAssignee(models.Model):
    id = models.BigAutoField(primary_key=True)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="assignees")
    user = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="assigned_clickup_tasks")

    class Meta:
        db_table = "clickup_task_assignees"
        unique_together = ("task", "user")