# clickup/views.py
from django.db import transaction
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import (
    Team, TeamMember, TeamInvite,
    Project, List, Task, TaskAssignee
)
from .serializers import (
    TeamSerializer, TeamMemberSerializer, TeamInviteSerializer,
    ProjectSerializer, ListSerializer, TaskSerializer
)
from .permissions import IsTeamMember, IsTeamAdminOrOwner


class TeamViewSet(viewsets.ModelViewSet):
    serializer_class = TeamSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        uid = self.request.user.id_usuario
        return Team.objects.filter(memberships__user_id=uid, memberships__is_active=True).distinct()

    def perform_create(self, serializer):
        team = serializer.save(owner=self.request.user)
        TeamMember.objects.create(team=team, user=self.request.user, role="OWNER", is_active=True)

    @action(detail=True, methods=["get"], permission_classes=[IsAuthenticated, IsTeamMember])
    def members(self, request, pk=None):
        qs = TeamMember.objects.filter(team_id=pk, is_active=True).select_related("user")
        return Response(TeamMemberSerializer(qs, many=True).data)

    @action(detail=True, methods=["get"], permission_classes=[IsAuthenticated, IsTeamAdminOrOwner])
    def invites(self, request, pk=None):
        qs = TeamInvite.objects.filter(team_id=pk).order_by("-created_at")
        return Response(TeamInviteSerializer(qs, many=True).data)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsTeamAdminOrOwner])
    def invite(self, request, pk=None):
        email = str(request.data.get("email", "")).strip().lower()
        role = str(request.data.get("role", "MEMBER")).strip().upper()
        expires_days = int(request.data.get("expires_days", 7))

        if not email:
            return Response({"detail": "email es requerido."}, status=400)

        inv = TeamInvite.objects.create(
            team_id=pk,
            email=email,
            role=role if role in ["ADMIN", "MEMBER", "VIEWER"] else "MEMBER",
            invited_by=request.user,
            expires_at=timezone.now() + timezone.timedelta(days=expires_days),
        )

        # Front: /clickup/accept?token=...
        base_url = request.headers.get("Origin", "").strip() or "http://localhost:5173"
        invite_url = f"{base_url}/clickup/accept?token={inv.token}"

        # Si luego quieres enviar email real, lo conectamos aquí.
        return Response({**TeamInviteSerializer(inv).data, "invite_url": invite_url}, status=201)

    @action(detail=True, methods=["post"], url_path="invites/(?P<invite_id>[^/.]+)/revoke",
            permission_classes=[IsAuthenticated, IsTeamAdminOrOwner])
    def revoke_invite(self, request, pk=None, invite_id=None):
        inv = TeamInvite.objects.filter(team_id=pk, id=invite_id).first()
        if not inv:
            return Response({"detail": "Invitación no encontrada."}, status=404)
        if inv.status != "PENDING":
            return Response({"detail": "Solo PENDING se puede revocar."}, status=400)
        inv.status = "REVOKED"
        inv.save(update_fields=["status"])
        return Response({"ok": True})

    @action(detail=False, methods=["post"], url_path="accept", permission_classes=[IsAuthenticated])
    def accept(self, request):
        token = str(request.data.get("token", "")).strip()
        if not token:
            return Response({"detail": "token es requerido."}, status=400)

        inv = TeamInvite.objects.filter(token=token).select_related("team").first()
        if not inv:
            return Response({"detail": "Invitación inválida."}, status=404)

        if inv.status != "PENDING":
            return Response({"detail": f"Invitación no disponible: {inv.status}."}, status=400)

        if inv.is_expired():
            inv.status = "EXPIRED"
            inv.save(update_fields=["status"])
            return Response({"detail": "Invitación expirada."}, status=400)

        # Validación por correo (tu Usuario tiene campo correo). :contentReference[oaicite:3]{index=3}
        if (request.user.correo or "").strip().lower() != inv.email:
            return Response({"detail": "Tu correo no coincide con la invitación."}, status=403)

        TeamMember.objects.update_or_create(
            team=inv.team,
            user=request.user,
            defaults={"role": inv.role, "is_active": True},
        )

        inv.status = "ACCEPTED"
        inv.accepted_at = timezone.now()
        inv.accepted_by = request.user
        inv.save(update_fields=["status", "accepted_at", "accepted_by"])

        return Response({"ok": True, "team_id": inv.team_id})


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated, IsTeamMember]

    def get_queryset(self):
        return Project.objects.filter(team_id=self.kwargs["team_id"]).order_by("-created_at")

    def perform_create(self, serializer):
        serializer.save(team_id=self.kwargs["team_id"])

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsTeamMember])
    def bootstrap(self, request, team_id=None, pk=None):
        """
        Crea listas default para kanban:
        - Por hacer
        - En proceso
        - Hecho
        """
        defaults = ["Por hacer", "En proceso", "Hecho"]
        created = []
        for idx, name in enumerate(defaults):
            obj, _ = List.objects.get_or_create(project_id=pk, name=name, defaults={"order": idx})
            created.append(obj)
        return Response(ListSerializer(created, many=True).data)


class BoardViewSet(viewsets.ViewSet):
    """
    Tablero Kanban por Team + Project
    """
    permission_classes = [IsAuthenticated, IsTeamMember]

    def list(self, request, team_id=None):
        project_id = request.query_params.get("project_id")
        if not project_id:
            return Response({"detail": "project_id es requerido."}, status=400)

        # valida que el proyecto sea de ese team
        pr = Project.objects.filter(id=project_id, team_id=team_id).first()
        if not pr:
            return Response({"detail": "Proyecto no encontrado."}, status=404)

        lists = List.objects.filter(project_id=project_id).order_by("order", "id")
        tasks = Task.objects.filter(list__project_id=project_id).select_related("list").order_by("order", "id")

        # serialización simple
        lists_data = ListSerializer(lists, many=True).data

        tasks_by_list = {}
        for t in tasks:
            tasks_by_list.setdefault(t.list_id, []).append(TaskSerializer(t).data)

        return Response({
            "project": ProjectSerializer(pr).data,
            "lists": lists_data,
            "tasks_by_list": tasks_by_list,
        })

    @action(detail=False, methods=["post"])
    @transaction.atomic
    def move_task(self, request, team_id=None):
        """
        body:
        {
          "task_id": 1,
          "to_list_id": 2,
          "to_order": 0
        }
        """
        task_id = request.data.get("task_id")
        to_list_id = request.data.get("to_list_id")
        to_order = int(request.data.get("to_order", 0))

        if not task_id or not to_list_id:
            return Response({"detail": "task_id y to_list_id son requeridos."}, status=400)

        task = Task.objects.select_related("list__project").filter(
            id=task_id, list__project__team_id=team_id
        ).first()
        if not task:
            return Response({"detail": "Tarea no encontrada."}, status=404)

        to_list = List.objects.select_related("project").filter(
            id=to_list_id, project__team_id=team_id
        ).first()
        if not to_list:
            return Response({"detail": "Lista destino no encontrada."}, status=404)

        # compacta órdenes en la lista origen
        origin_list_id = task.list_id
        Task.objects.filter(list_id=origin_list_id, order__gt=task.order).update(order=models.F("order") - 1)

        # abre hueco en la lista destino
        Task.objects.filter(list_id=to_list_id, order__gte=to_order).update(order=models.F("order") + 1)

        task.list = to_list
        task.order = to_order
        task.save(update_fields=["list", "order"])

        return Response({"ok": True})