# clickup/permissions.py
from rest_framework.permissions import BasePermission
from .models import TeamMember

class IsTeamMember(BasePermission):
    def has_permission(self, request, view):
        team_id = view.kwargs.get("team_id")
        if not team_id:
            return True
        return TeamMember.objects.filter(
            team_id=team_id,
            user_id=request.user.id_usuario,
            is_active=True
        ).exists()

class IsTeamAdminOrOwner(BasePermission):
    def has_permission(self, request, view):
        team_id = view.kwargs.get("team_id")
        if not team_id:
            return False
        return TeamMember.objects.filter(
            team_id=team_id,
            user_id=request.user.id_usuario,
            is_active=True,
            role__in=["OWNER", "ADMIN"]
        ).exists()