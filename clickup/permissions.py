from rest_framework.permissions import BasePermission
from .models import Equipo, MiembroEquipo, Proyecto, Lista, Tarea

class EsMiembroEquipo(BasePermission):
    def has_permission(self, request, view):
        uid = getattr(request.user, "id_usuario", None)
        if not uid:
            return False

        equipo_id = self._resolver_equipo_id(view)
        if not equipo_id:
            return False

        if Equipo.objects.filter(id=equipo_id, propietario_id=uid).exists():
            return True

        return MiembroEquipo.objects.filter(
            equipo_id=equipo_id,
            usuario_id=uid,
            activo=True,
        ).exists()

    def _resolver_equipo_id(self, view):
        equipo_id = view.kwargs.get("equipo_id")
        if equipo_id:
            return equipo_id

        pk = view.kwargs.get("pk")
        if not pk:
            return None

        proyecto = Proyecto.objects.filter(id=pk).only("equipo_id").first()
        if proyecto:
            return proyecto.equipo_id

        lista = Lista.objects.filter(id=pk).select_related("proyecto").first()
        if lista:
            return lista.proyecto.equipo_id

        tarea = Tarea.objects.filter(id=pk).select_related("lista__proyecto").first()
        if tarea:
            return tarea.lista.proyecto.equipo_id

        return None


class EsAdminOPropietarioEquipo(BasePermission):
    def has_permission(self, request, view):
        uid = getattr(request.user, "id_usuario", None)
        if not uid:
            return False

        equipo_id = self._resolver_equipo_id(view)
        if not equipo_id:
            return False

        if Equipo.objects.filter(id=equipo_id, propietario_id=uid).exists():
            return True

        return MiembroEquipo.objects.filter(
            equipo_id=equipo_id,
            usuario_id=uid,
            activo=True,
            rol__in=["OWNER", "ADMIN"],
        ).exists()

    def _resolver_equipo_id(self, view):
        equipo_id = view.kwargs.get("equipo_id")
        if equipo_id:
            return equipo_id

        pk = view.kwargs.get("pk")
        if not pk:
            return None

        equipo = Equipo.objects.filter(id=pk).only("id").first()
        if equipo:
            return equipo.id

        proyecto = Proyecto.objects.filter(id=pk).only("equipo_id").first()
        if proyecto:
            return proyecto.equipo_id

        return None