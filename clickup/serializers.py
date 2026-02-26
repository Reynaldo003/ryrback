# clickup/serializers.py
from rest_framework import serializers
from django.utils import timezone
from .models import Team, TeamMember, TeamInvite, Project, List, Task, TaskAssignee
from CrmConformidad.models import Usuario  # AJUSTA


class UsuarioMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        fields = ("id_usuario", "nombre", "apellidos", "correo")


class TeamSerializer(serializers.ModelSerializer):
    owner = UsuarioMiniSerializer(read_only=True)

    class Meta:
        model = Team
        fields = ("id", "name", "descripcion", "owner", "created_at")


class TeamMemberSerializer(serializers.ModelSerializer):
    user = UsuarioMiniSerializer(read_only=True)

    class Meta:
        model = TeamMember
        fields = ("id", "team", "user", "role", "joined_at", "is_active")
        read_only_fields = ("id", "joined_at")


class TeamInviteSerializer(serializers.ModelSerializer):
    invited_by = UsuarioMiniSerializer(read_only=True)
    is_expired = serializers.SerializerMethodField()

    class Meta:
        model = TeamInvite
        fields = (
            "id", "team", "email", "role", "token",
            "status", "invited_by", "created_at", "expires_at",
            "is_expired", "accepted_at", "accepted_by"
        )
        read_only_fields = ("id", "token", "status", "created_at", "accepted_at", "accepted_by")

    def get_is_expired(self, obj):
        return obj.is_expired()

    def validate_email(self, value):
        return value.strip().lower()

    def validate_expires_at(self, value):
        if value and value <= timezone.now():
            raise serializers.ValidationError("expires_at debe ser futura.")
        return value


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ("id", "team", "name", "descripcion", "created_at")
        read_only_fields = ("id", "created_at")


class ListSerializer(serializers.ModelSerializer):
    class Meta:
        model = List
        fields = ("id", "project", "name", "order")
        read_only_fields = ("id",)


class TaskAssigneeSerializer(serializers.ModelSerializer):
    user = UsuarioMiniSerializer(read_only=True)

    class Meta:
        model = TaskAssignee
        fields = ("id", "user")


class TaskSerializer(serializers.ModelSerializer):
    assignees = TaskAssigneeSerializer(many=True, read_only=True)

    class Meta:
        model = Task
        fields = (
            "id", "list", "title", "description",
            "priority", "due_date", "order",
            "created_by", "created_at", "assignees",
        )
        read_only_fields = ("id", "created_by", "created_at")