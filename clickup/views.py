# clickup/views.py
from django.db import models, transaction
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import (
    Equipo, MiembroEquipo, InvitacionEquipo,
    Proyecto, Lista, Tarea
)
from .serializers import (
    EquipoSerializer, MiembroEquipoSerializer, InvitacionEquipoSerializer,
    ProyectoSerializer, ListaSerializer, TareaSerializer
)
from .permissions import EsMiembroEquipo, EsAdminOPropietarioEquipo


class EquipoViewSet(viewsets.ModelViewSet):
    serializer_class = EquipoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        uid = self.request.user.id_usuario
        return Equipo.objects.filter(miembros__usuario_id=uid, miembros__activo=True).distinct()

    def perform_create(self, serializer):
        equipo = serializer.save(propietario=self.request.user)
        MiembroEquipo.objects.create(equipo=equipo, usuario=self.request.user, rol="OWNER", activo=True)

    @action(detail=True, methods=["get"], permission_classes=[IsAuthenticated, EsMiembroEquipo])
    def miembros(self, request, pk=None):
        qs = MiembroEquipo.objects.filter(equipo_id=pk, activo=True).select_related("usuario")
        return Response(MiembroEquipoSerializer(qs, many=True).data)

    @action(detail=True, methods=["get"], permission_classes=[IsAuthenticated, EsAdminOPropietarioEquipo])
    def invitaciones(self, request, pk=None):
        qs = InvitacionEquipo.objects.filter(equipo_id=pk).order_by("-creado_en")
        return Response(InvitacionEquipoSerializer(qs, many=True).data)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, EsAdminOPropietarioEquipo])
    def invitar(self, request, pk=None):
        correo = str(request.data.get("correo", "")).strip().lower()
        rol = str(request.data.get("rol", "MEMBER")).strip().upper()
        dias_expira = int(request.data.get("dias_expira", 7))

        if not correo:
            return Response({"detail": "correo es requerido."}, status=400)

        inv = InvitacionEquipo.objects.create(
            equipo_id=pk,
            correo=correo,
            rol=rol if rol in ["ADMIN", "MEMBER", "VIEWER"] else "MEMBER",
            invitado_por=request.user,
            expira_en=timezone.now() + timezone.timedelta(days=dias_expira),
        )

        base_url = request.headers.get("Origin", "").strip() or "http://localhost:5173"
        url_aceptar = f"{base_url}/clickup/accept?token={inv.token}"

        return Response({**InvitacionEquipoSerializer(inv).data, "url_aceptar": url_aceptar}, status=201)

    @action(detail=True, methods=["post"], url_path="invitaciones/(?P<invitacion_id>[^/.]+)/revocar",
            permission_classes=[IsAuthenticated, EsAdminOPropietarioEquipo])
    def revocar_invitacion(self, request, pk=None, invitacion_id=None):
        inv = InvitacionEquipo.objects.filter(equipo_id=pk, id=invitacion_id).first()
        if not inv:
            return Response({"detail": "Invitación no encontrada."}, status=404)
        if inv.estado != "PENDING":
            return Response({"detail": "Solo PENDING se puede revocar."}, status=400)

        inv.estado = "REVOKED"
        inv.save(update_fields=["estado"])
        return Response({"ok": True})

    @action(detail=False, methods=["post"], url_path="aceptar", permission_classes=[IsAuthenticated])
    def aceptar(self, request):
        token = str(request.data.get("token", "")).strip()
        if not token:
            return Response({"detail": "token es requerido."}, status=400)

        inv = InvitacionEquipo.objects.filter(token=token).select_related("equipo").first()
        if not inv:
            return Response({"detail": "Invitación inválida."}, status=404)

        if inv.estado != "PENDING":
            return Response({"detail": f"Invitación no disponible: {inv.estado}."}, status=400)

        if inv.esta_expirada():
            inv.estado = "EXPIRED"
            inv.save(update_fields=["estado"])
            return Response({"detail": "Invitación expirada."}, status=400)

        if (request.user.correo or "").strip().lower() != inv.correo:
            return Response({"detail": "Tu correo no coincide con la invitación."}, status=403)

        MiembroEquipo.objects.update_or_create(
            equipo=inv.equipo,
            usuario=request.user,
            defaults={"rol": inv.rol, "activo": True},
        )

        inv.estado = "ACCEPTED"
        inv.aceptado_en = timezone.now()
        inv.aceptado_por = request.user
        inv.save(update_fields=["estado", "aceptado_en", "aceptado_por"])

        return Response({"ok": True, "equipo_id": inv.equipo_id})


class ProyectoViewSet(viewsets.ModelViewSet):
    serializer_class = ProyectoSerializer
    permission_classes = [IsAuthenticated, EsMiembroEquipo]

    def get_queryset(self):
        return Proyecto.objects.filter(equipo_id=self.kwargs["equipo_id"]).order_by("-creado_en")

    def perform_create(self, serializer):
        serializer.save(equipo_id=self.kwargs["equipo_id"])

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, EsMiembroEquipo])
    def bootstrap(self, request, equipo_id=None, pk=None):
        defaults = ["Por hacer", "En proceso", "Hecho"]
        creadas = []
        for idx, nombre in enumerate(defaults):
            obj, _ = Lista.objects.get_or_create(proyecto_id=pk, nombre=nombre, defaults={"orden": idx})
            creadas.append(obj)
        return Response(ListaSerializer(creadas, many=True).data)


class TableroViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, EsMiembroEquipo]

    def list(self, request, equipo_id=None):
        proyecto_id = request.query_params.get("proyecto_id")
        if not proyecto_id:
            return Response({"detail": "proyecto_id es requerido."}, status=400)

        pr = Proyecto.objects.filter(id=proyecto_id, equipo_id=equipo_id).first()
        if not pr:
            return Response({"detail": "Proyecto no encontrado."}, status=404)

        listas = Lista.objects.filter(proyecto_id=proyecto_id).order_by("orden", "id")
        tareas = Tarea.objects.filter(lista__proyecto_id=proyecto_id).select_related("lista").order_by("orden", "id")

        listas_data = ListaSerializer(listas, many=True).data

        tareas_por_lista = {}
        for t in tareas:
            tareas_por_lista.setdefault(t.lista_id, []).append(TareaSerializer(t).data)

        return Response({
            "proyecto": ProyectoSerializer(pr).data,
            "listas": listas_data,
            "tareas_por_lista": tareas_por_lista,
        })

    @action(detail=False, methods=["post"])
    @transaction.atomic
    def mover_tarea(self, request, equipo_id=None):
        tarea_id = request.data.get("tarea_id")
        lista_destino_id = request.data.get("lista_destino_id")
        orden_destino = int(request.data.get("orden_destino", 0))

        if not tarea_id or not lista_destino_id:
            return Response({"detail": "tarea_id y lista_destino_id son requeridos."}, status=400)

        tarea = Tarea.objects.select_related("lista__proyecto").filter(
            id=tarea_id, lista__proyecto__equipo_id=equipo_id
        ).first()
        if not tarea:
            return Response({"detail": "Tarea no encontrada."}, status=404)

        lista_destino = Lista.objects.select_related("proyecto").filter(
            id=lista_destino_id, proyecto__equipo_id=equipo_id
        ).first()
        if not lista_destino:
            return Response({"detail": "Lista destino no encontrada."}, status=404)

        lista_origen_id = tarea.lista_id

        # compacta órdenes en la lista origen
        Tarea.objects.filter(lista_id=lista_origen_id, orden__gt=tarea.orden).update(orden=models.F("orden") - 1)

        # abre hueco en la lista destino
        Tarea.objects.filter(lista_id=lista_destino_id, orden__gte=orden_destino).update(orden=models.F("orden") + 1)

        tarea.lista = lista_destino
        tarea.orden = orden_destino
        tarea.save(update_fields=["lista", "orden"])

        return Response({"ok": True})