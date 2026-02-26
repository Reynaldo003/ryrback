# clickup/permissions.py
from rest_framework.permissions import BasePermission
from .models import MiembroEquipo


class EsMiembroEquipo(BasePermission):
    def has_permission(self, request, view):
        equipo_id = view.kwargs.get("equipo_id") or view.kwargs.get("team_id")
        if not equipo_id:
            return True

        return MiembroEquipo.objects.filter(
            equipo_id=equipo_id,
            usuario_id=request.user.id_usuario,
            activo=True
        ).exists()


class EsAdminOPropietarioEquipo(BasePermission):
    def has_permission(self, request, view):
        equipo_id = view.kwargs.get("equipo_id") or view.kwargs.get("team_id")
        if not equipo_id:
            return False

        return MiembroEquipo.objects.filter(
            equipo_id=equipo_id,
            usuario_id=request.user.id_usuario,
            activo=True,
            rol__in=["OWNER", "ADMIN"]
        ).exists()