# clickup/views.py
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
import os
import requests as http_requests  

from .authentication import UsuarioJWTAuthentication
from .models import (
    Equipo,
    MiembroEquipo,
    InvitacionEquipo,
    Proyecto,
    Lista,
    Tarea,
    TareaAsignada,
    NotificacionClickup,
    ReporteIncidencia,
    EvidenciaTarea,
)
from .permissions import EsMiembroEquipo, EsAdminOPropietarioEquipo
from .serializers import (
    EquipoSerializer,
    MiembroEquipoSerializer,
    InvitacionEquipoSerializer,
    ProyectoSerializer,
    ListaSerializer,
    TareaSerializer,
    TareaCreateSerializer,
    TareaUpdateSerializer,
    UsuarioSearchSerializer,
    NotificacionClickupSerializer,
    ReporteIncidenciaCreateSerializer,
    ReporteIncidenciaDetailSerializer,
    EvidenciaTareaSerializer,
)
from CrmConformidad.models import Usuario


def crear_notificacion(
    *,
    usuario,
    tipo,
    titulo,
    mensaje="",
    equipo=None,
    proyecto=None,
    tarea=None,
    invitacion=None,
    estado="PENDING",
):
    return NotificacionClickup.objects.create(
        usuario=usuario,
        tipo=tipo,
        titulo=titulo,
        mensaje=mensaje or "",
        equipo=equipo,
        proyecto=proyecto,
        tarea=tarea,
        invitacion=invitacion,
        estado=estado,
    )


def sincronizar_asignados_y_notificar(tarea, usuarios_ids, actor=None):
    usuarios_ids = list(set([int(x) for x in (usuarios_ids or []) if x]))
    actuales = set(TareaAsignada.objects.filter(tarea=tarea).values_list("usuario_id", flat=True))
    nuevos = set(usuarios_ids) - actuales
    eliminados = actuales - set(usuarios_ids)

    if eliminados:
        TareaAsignada.objects.filter(tarea=tarea, usuario_id__in=eliminados).delete()

    for uid in nuevos:
        TareaAsignada.objects.get_or_create(tarea=tarea, usuario_id=uid)

    if nuevos:
        usuarios_nuevos = Usuario.objects.filter(id_usuario__in=nuevos)
        proyecto = tarea.lista.proyecto
        equipo = proyecto.equipo
        actor_nombre = ""
        if actor:
            actor_nombre = f"{actor.nombre or ''} {actor.apellidos or ''}".strip() or actor.correo or "Alguien"

        for usuario in usuarios_nuevos:
            crear_notificacion(
                usuario=usuario,
                tipo="TASK_ASSIGNED",
                titulo="Se te asignó una tarea",
                mensaje=f"{actor_nombre} te asignó la tarea '{tarea.titulo}'.",
                equipo=equipo,
                proyecto=proyecto,
                tarea=tarea,
                estado="PENDING",
            )


def buscar_configuracion_default_reportes():
    equipo = Equipo.objects.filter(nombre__iexact="Desarrollo Software").first()
    if not equipo:
        raise ValueError("No existe el equipo 'Desarrollo Software'.")

    proyecto = Proyecto.objects.filter(equipo=equipo, nombre__iexact="CRM").first()
    if not proyecto:
        raise ValueError("No existe el proyecto 'CRM' dentro del equipo 'Desarrollo Software'.")

    lista = Lista.objects.filter(proyecto=proyecto, nombre__iexact="Por hacer").first()
    if not lista:
        raise ValueError("No existe la lista 'Por hacer' dentro del proyecto 'CRM'.")

    usuario = Usuario.objects.filter(
        Q(nombre__iexact="Reynaldo") & Q(apellidos__icontains="Vallejo")
    ).first()

    if not usuario:
        usuario = Usuario.objects.filter(
            Q(correo__iexact="reynaldo.vallejo@correo.com")
            | Q(usuario__iexact="reynaldovallejo")
        ).first()

    if not usuario:
        raise ValueError("No existe el usuario 'Reynaldo Vallejo'.")

    MiembroEquipo.objects.update_or_create(
        equipo=equipo,
        usuario=usuario,
        defaults={"rol": "MEMBER", "activo": True},
    )

    return equipo, proyecto, lista, usuario


class UsuarioSearchView(APIView):
    authentication_classes = [UsuarioJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        q = str(request.query_params.get("q", "")).strip()
        limit_raw = request.query_params.get("limit", 10)

        try:
            limit = max(1, min(int(limit_raw), 20))
        except (TypeError, ValueError):
            limit = 10

        qs = Usuario.objects.all().order_by("nombre", "apellidos", "correo")

        if q:
            qs = qs.filter(
                Q(nombre__icontains=q)
                | Q(apellidos__icontains=q)
                | Q(correo__icontains=q)
                | Q(usuario__icontains=q)
            )

        return Response(UsuarioSearchSerializer(qs[:limit], many=True).data)


class EquipoViewSet(viewsets.ModelViewSet):
    serializer_class = EquipoSerializer
    authentication_classes = [UsuarioJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        uid = self.request.user.id_usuario
        return (
            Equipo.objects.filter(
                Q(propietario_id=uid)
                | Q(miembros__usuario_id=uid, miembros__activo=True)
            )
            .distinct()
            .order_by("-creado_en")
        )

    def perform_create(self, serializer):
        equipo = serializer.save(propietario=self.request.user)
        MiembroEquipo.objects.update_or_create(
            equipo=equipo,
            usuario=self.request.user,
            defaults={"rol": "OWNER", "activo": True},
        )

    @action(detail=True, methods=["get"], permission_classes=[IsAuthenticated, EsMiembroEquipo])
    def miembros(self, request, pk=None):
        qs = (
            MiembroEquipo.objects.filter(equipo_id=pk, activo=True)
            .select_related("usuario")
            .order_by("id")
        )
        return Response(MiembroEquipoSerializer(qs, many=True).data)

    @action(detail=True, methods=["get"], permission_classes=[IsAuthenticated, EsAdminOPropietarioEquipo])
    def invitaciones(self, request, pk=None):
        qs = (
            InvitacionEquipo.objects.filter(equipo_id=pk)
            .select_related("usuario_invitado", "invitado_por", "aceptado_por")
            .order_by("-creado_en")
        )
        return Response(InvitacionEquipoSerializer(qs, many=True).data)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, EsAdminOPropietarioEquipo])
    @transaction.atomic
    def invitar(self, request, pk=None):
        usuario_id = request.data.get("usuario_id")
        rol = str(request.data.get("rol", "MEMBER")).strip().upper()

        if rol not in ["ADMIN", "MEMBER", "VIEWER"]:
            rol = "MEMBER"

        if not usuario_id:
            return Response({"detail": "usuario_id es requerido."}, status=status.HTTP_400_BAD_REQUEST)

        usuario = Usuario.objects.filter(id_usuario=usuario_id).first()
        if not usuario:
            return Response({"detail": "Usuario no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        equipo = Equipo.objects.filter(id=pk).first()
        if not equipo:
            return Response({"detail": "Equipo no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        ya_es_miembro = MiembroEquipo.objects.filter(
            equipo_id=pk,
            usuario_id=usuario.id_usuario,
            activo=True,
        ).exists()
        if ya_es_miembro:
            return Response({"detail": "Ese usuario ya pertenece al equipo."}, status=status.HTTP_400_BAD_REQUEST)

        invitacion_activa = InvitacionEquipo.objects.filter(
            equipo_id=pk,
            usuario_invitado_id=usuario.id_usuario,
            estado="PENDING",
        ).first()
        if invitacion_activa:
            return Response({"detail": "Ese usuario ya tiene una invitación pendiente."}, status=status.HTTP_400_BAD_REQUEST)

        inv = InvitacionEquipo.objects.create(
            equipo_id=pk,
            usuario_invitado=usuario,
            correo=(usuario.correo or "").strip().lower() or None,
            rol=rol,
            invitado_por=request.user,
        )

        crear_notificacion(
            usuario=usuario,
            tipo="TEAM_INVITE",
            titulo="Invitación a equipo",
            mensaje=f"Te invitaron al equipo '{equipo.nombre}' con rol {rol}.",
            equipo=equipo,
            invitacion=inv,
            estado="PENDING",
        )

        return Response(InvitacionEquipoSerializer(inv).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="aceptar", permission_classes=[IsAuthenticated])
    @transaction.atomic
    def aceptar(self, request):
        invitacion_id = request.data.get("invitacion_id")
        inv = InvitacionEquipo.objects.filter(id=invitacion_id).select_related("equipo", "usuario_invitado").first()

        if not inv:
            return Response({"detail": "Invitación inválida."}, status=status.HTTP_404_NOT_FOUND)

        if inv.estado != "PENDING":
            return Response({"detail": f"Invitación no disponible: {inv.estado}."}, status=status.HTTP_400_BAD_REQUEST)

        if inv.esta_expirada():
            inv.estado = "EXPIRED"
            inv.save(update_fields=["estado"])
            return Response({"detail": "Invitación expirada."}, status=status.HTTP_400_BAD_REQUEST)

        if inv.usuario_invitado_id and inv.usuario_invitado_id != request.user.id_usuario:
            return Response({"detail": "Esta invitación no te pertenece."}, status=status.HTTP_403_FORBIDDEN)

        MiembroEquipo.objects.update_or_create(
            equipo=inv.equipo,
            usuario=request.user,
            defaults={"rol": inv.rol, "activo": True},
        )

        inv.estado = "ACCEPTED"
        inv.aceptado_en = timezone.now()
        inv.aceptado_por = request.user
        inv.save(update_fields=["estado", "aceptado_en", "aceptado_por"])

        NotificacionClickup.objects.filter(
            invitacion=inv,
            usuario=request.user,
            estado="PENDING",
        ).update(estado="ACCEPTED", leido_en=timezone.now())

        return Response({"ok": True, "equipo_id": inv.equipo_id})


class ProyectoViewSet(viewsets.ModelViewSet):
    serializer_class = ProyectoSerializer
    authentication_classes = [UsuarioJWTAuthentication]
    permission_classes = [IsAuthenticated, EsMiembroEquipo]

    def get_queryset(self):
        return Proyecto.objects.filter(equipo_id=self.kwargs["equipo_id"]).order_by("-creado_en", "-id")

    def perform_create(self, serializer):
        serializer.save(equipo_id=self.kwargs["equipo_id"])

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, EsMiembroEquipo])
    def bootstrap(self, request, equipo_id=None, pk=None):
        defaults = ["Por hacer", "En proceso", "Hecho"]
        creadas = []

        for idx, nombre in enumerate(defaults):
            obj, _ = Lista.objects.get_or_create(
                proyecto_id=pk,
                nombre=nombre,
                defaults={"orden": idx},
            )
            creadas.append(obj)

        creadas = sorted(creadas, key=lambda x: (x.orden, x.id))
        return Response(ListaSerializer(creadas, many=True).data)


class TableroViewSet(viewsets.ViewSet):
    authentication_classes = [UsuarioJWTAuthentication]
    permission_classes = [IsAuthenticated, EsMiembroEquipo]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def list(self, request, equipo_id=None):
        proyecto_id = request.query_params.get("proyecto_id")
        if not proyecto_id:
            return Response({"detail": "proyecto_id es requerido."}, status=status.HTTP_400_BAD_REQUEST)

        pr = Proyecto.objects.filter(id=proyecto_id, equipo_id=equipo_id).first()
        if not pr:
            return Response({"detail": "Proyecto no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        listas = Lista.objects.filter(proyecto_id=proyecto_id).order_by("orden", "id")
        tareas = (
            Tarea.objects.filter(
                lista__proyecto_id=proyecto_id,
                tarea_padre__isnull=True,
            )
           .prefetch_related(
            "asignados__usuario",
            "evidencias__subido_por",
            "subtareas",
        )                         
        .order_by("orden", "id")
        )

        listas_data = ListaSerializer(listas, many=True).data
        tareas_por_lista = {}

        for t in tareas:
            tareas_por_lista.setdefault(t.lista_id, []).append(TareaSerializer(t, context={"request": request}).data)

        return Response(
            {
                "proyecto": ProyectoSerializer(pr).data,
                "listas": listas_data,
                "tareas_por_lista": tareas_por_lista,
            }
        )

    @action(detail=False, methods=["post"], url_path="mover-tarea")
    @transaction.atomic
    def mover_tarea(self, request, equipo_id=None):
        tarea_id = request.data.get("tarea_id")
        lista_destino_id = request.data.get("lista_destino_id")
        orden_destino = request.data.get("orden_destino", 0)

        try:
            tarea_id = int(tarea_id)
            lista_destino_id = int(lista_destino_id)
            orden_destino = int(orden_destino)
        except (TypeError, ValueError):
            return Response(
                {"detail": "tarea_id, lista_destino_id y orden_destino deben ser numéricos."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        tarea = (
            Tarea.objects.select_related("lista__proyecto")
            .filter(id=tarea_id, lista__proyecto__equipo_id=equipo_id)
            .first()
        )
        if not tarea:
            return Response({"detail": "Tarea no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        lista_destino = (
            Lista.objects.select_related("proyecto")
            .filter(id=lista_destino_id, proyecto__equipo_id=equipo_id)
            .first()
        )
        if not lista_destino:
            return Response({"detail": "Lista destino no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        if tarea.lista_id == lista_destino.id:
            total_destino = Tarea.objects.filter(lista_id=lista_destino.id).exclude(id=tarea.id).count()
            orden_destino = max(0, min(orden_destino, total_destino))
        else:
            total_destino = Tarea.objects.filter(lista_id=lista_destino.id).count()
            orden_destino = max(0, min(orden_destino, total_destino))

        lista_origen_id = tarea.lista_id
        orden_origen = tarea.orden

        if lista_origen_id == lista_destino_id:
            Tarea.objects.filter(
                lista_id=lista_origen_id,
                orden__gt=orden_origen,
                orden__lte=orden_destino,
            ).update(orden=models.F("orden") - 1)

            Tarea.objects.filter(
                lista_id=lista_origen_id,
                orden__lt=orden_origen,
                orden__gte=orden_destino,
            ).update(orden=models.F("orden") + 1)
        else:
            Tarea.objects.filter(
                lista_id=lista_origen_id,
                orden__gt=orden_origen,
            ).update(orden=models.F("orden") - 1)

            Tarea.objects.filter(
                lista_id=lista_destino_id,
                orden__gte=orden_destino,
            ).update(orden=models.F("orden") + 1)

        tarea.lista = lista_destino
        tarea.orden = orden_destino
        if lista_destino.nombre in ["Por hacer", "En proceso", "Hecho"]:
            tarea.estado = lista_destino.nombre
            tarea.save(update_fields=["lista", "orden", "estado"])
            tarea.subtareas.update(lista=lista_destino, estado=lista_destino.nombre)
        else:
            tarea.save(update_fields=["lista", "orden"])
            tarea.subtareas.update(lista=lista_destino)

        reporte = getattr(tarea, "reporte_incidencia", None)
        if reporte:
            nombre_lista = (lista_destino.nombre or "").strip().lower()
            if "hecho" in nombre_lista:
                reporte.estado = "RESOLVED"
                reporte.resuelto_en = timezone.now()
                reporte.save(update_fields=["estado", "resuelto_en", "actualizado_en"])
            elif "proceso" in nombre_lista:
                reporte.estado = "IN_PROGRESS"
                reporte.save(update_fields=["estado", "actualizado_en"])
            else:
                reporte.estado = "OPEN"
                reporte.resuelto_en = None
                reporte.save(update_fields=["estado", "resuelto_en", "actualizado_en"])

        return Response({"ok": True})

    @action(detail=False, methods=["post"], url_path="crear-tarea")
    @transaction.atomic
    def crear_tarea(self, request, equipo_id=None):
        ser = TareaCreateSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)

        lista = (
            Lista.objects.select_related("proyecto__equipo")
            .filter(id=ser.validated_data["lista"].id, proyecto__equipo_id=equipo_id)
            .first()
        )

        if not lista:
            return Response(
                {"detail": "Lista no encontrada o no pertenece al equipo."},
                status=status.HTTP_404_NOT_FOUND,
            )

        asignados_ids = list(ser.validated_data.get("asignados_ids") or [])

        last = (
            Tarea.objects.filter(lista=lista, tarea_padre__isnull=True)
            .aggregate(m=models.Max("orden"))["m"]
        )
        next_order = 0 if last is None else int(last) + 1

        estado = lista.nombre if lista.nombre in ["Por hacer", "En proceso", "Hecho"] else "Por hacer"

        tarea = ser.save(
            creado_por=request.user,
            orden=next_order,
            estado=estado,
        )

        if asignados_ids:
            sincronizar_asignados_y_notificar(tarea, asignados_ids, actor=request.user)

        tarea = (
            Tarea.objects.select_related("lista", "creado_por", "reporte_incidencia")
            .prefetch_related("asignados__usuario", "evidencias__subido_por", "subtareas")
            .get(id=tarea.id)
        )

        return Response(
            TareaSerializer(tarea, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["patch"], url_path=r"tareas/(?P<tarea_id>[^/.]+)")
    @transaction.atomic
    def editar_tarea(self, request, equipo_id=None, tarea_id=None):
        tarea = (
            Tarea.objects.select_related("lista__proyecto__equipo", "reporte_incidencia")
            .prefetch_related("asignados__usuario", "evidencias__subido_por", "subtareas")
            .filter(id=tarea_id, lista__proyecto__equipo_id=equipo_id)
            .first()
        )
        if not tarea:
            return Response({"detail": "Tarea no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        ser = TareaUpdateSerializer(tarea, data=request.data, partial=True, context={"request": request})
        ser.is_valid(raise_exception=True)
        
        tarea = ser.save()

        if "asignados_ids" in ser.validated_data:
            sincronizar_asignados_y_notificar(
                tarea,
                ser.validated_data["asignados_ids"],
                actor=request.user
            )

        reporte = getattr(tarea, "reporte_incidencia", None)
        if reporte and tarea.lista:
            nombre_lista = (tarea.lista.nombre or "").strip().lower()
            if "hecho" in nombre_lista:
                reporte.estado = "RESOLVED"
                reporte.resuelto_en = timezone.now()
                reporte.save(update_fields=["estado", "resuelto_en", "actualizado_en"])
            elif "proceso" in nombre_lista:
                reporte.estado = "IN_PROGRESS"
                reporte.save(update_fields=["estado", "actualizado_en"])
            else:
                reporte.estado = "OPEN"
                reporte.resuelto_en = None
                reporte.save(update_fields=["estado", "resuelto_en", "actualizado_en"])

        tarea = (
            Tarea.objects.select_related("lista", "creado_por")
            .prefetch_related("asignados__usuario", "evidencias__subido_por", "subtareas")
            .get(id=tarea.id)
        )

        return Response(TareaSerializer(tarea, context={"request": request}).data)

   
    @action(detail=False, methods=["delete"], url_path=r"tareas/(?P<tarea_id>[^/.]+)/eliminar")
    @transaction.atomic
    def eliminar_tarea(self, request, equipo_id=None, tarea_id=None):
        tarea = Tarea.objects.filter(id=tarea_id, lista__proyecto__equipo_id=equipo_id).first()
        if not tarea:
            return Response({"detail": "Tarea no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        tarea.delete()
        return Response({"ok": True}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path=r"tareas/(?P<tarea_id>[^/.]+)/detalle")
    def detalle_tarea(self, request, equipo_id=None, tarea_id=None):
        tarea = (
            Tarea.objects.select_related("lista__proyecto", "creado_por")
            .prefetch_related("asignados__usuario", "evidencias__subido_por")
            .filter(id=tarea_id, lista__proyecto__equipo_id=equipo_id)
            .first()
        )
        if not tarea:
            return Response({"detail": "Tarea no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        reporte = getattr(tarea, "reporte_incidencia", None)

        return Response({
            "tarea": TareaSerializer(tarea, context={"request": request}).data,
            "reporte": ReporteIncidenciaDetailSerializer(reporte, context={"request": request}).data if reporte else None,
        })

    @action(detail=False, methods=["post"], url_path=r"tareas/(?P<tarea_id>[^/.]+)/evidencias")
    @transaction.atomic
    def subir_evidencia(self, request, equipo_id=None, tarea_id=None):
        tarea = (
            Tarea.objects.select_related("lista__proyecto")
            .filter(id=tarea_id, lista__proyecto__equipo_id=equipo_id)
            .first()
        )
        if not tarea:
            return Response({"detail": "Tarea no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        tipo = str(request.data.get("tipo", "")).strip().upper()
        comentario = str(request.data.get("comentario", "")).strip()
        archivos = request.FILES.getlist("archivos")

        if tipo not in ["BUG", "RESOLUTION"]:
            return Response({"detail": "tipo inválido. Usa BUG o RESOLUTION."}, status=status.HTTP_400_BAD_REQUEST)

        if not archivos:
            return Response({"detail": "Debes adjuntar al menos un archivo."}, status=status.HTTP_400_BAD_REQUEST)

        reporte = getattr(tarea, "reporte_incidencia", None)
        creadas = []
        for archivo in archivos:
            evidencia = EvidenciaTarea.objects.create(
                tarea=tarea,
                reporte=reporte,
                tipo=tipo,
                comentario=comentario,
                archivo=archivo,
                subido_por=request.user,
            )
            creadas.append(evidencia)

        if reporte and tipo == "RESOLUTION":
            reporte.estado = "RESOLVED"
            reporte.resuelto_en = reporte.resuelto_en or timezone.now()
            reporte.save(update_fields=["estado", "resuelto_en", "actualizado_en"])

        return Response(
            EvidenciaTareaSerializer(creadas, many=True, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class ReporteIncidenciaViewSet(viewsets.ViewSet):
    authentication_classes = [UsuarioJWTAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @transaction.atomic
    def create(self, request):
        data = request.data.copy()
        imagenes = request.FILES.getlist("imagenes")
        data.setlist("imagenes", imagenes)

        ser = ReporteIncidenciaCreateSerializer(data=data)
        ser.is_valid(raise_exception=True)

        try:
            equipo, proyecto, lista, usuario_asignado = buscar_configuracion_default_reportes()
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        last = (
            Tarea.objects.filter(lista=lista, tarea_padre__isnull=True)
            .aggregate(m=models.Max("orden"))["m"]
        )
        next_order = 0 if last is None else int(last) + 1

        tipo = ser.validated_data["tipo"]
        titulo = ser.validated_data["titulo"].strip()
        descripcion = ser.validated_data["descripcion"].strip()

        prefijo = "[BUG]" if tipo == "BUG" else "[SUGERENCIA]"
        tarea = Tarea.objects.create(
            lista=lista,
            titulo=f"{prefijo} {titulo}",
            descripcion=descripcion,
            prioridad="HIGH" if tipo == "BUG" else "MEDIUM",
            creada=timezone.now(),
            orden=next_order,
            creado_por=request.user,
        )

        sincronizar_asignados_y_notificar(tarea, [usuario_asignado.id_usuario], actor=request.user)

        reporte = ReporteIncidencia.objects.create(
            tipo=tipo,
            titulo=titulo,
            descripcion=descripcion,
            estado="OPEN",
            reportado_por=request.user,
            equipo=equipo,
            proyecto=proyecto,
            tarea=tarea,
        )

        for archivo in ser.validated_data.get("imagenes") or []:
            EvidenciaTarea.objects.create(
                tarea=tarea,
                reporte=reporte,
                tipo="BUG",
                comentario="Evidencia inicial del reporte",
                archivo=archivo,
                subido_por=request.user,
            )

        crear_notificacion(
            usuario=usuario_asignado,
            tipo="BUG_REPORTED",
            titulo="Nuevo reporte enviado al CRM",
            mensaje=f"Se creó la tarea '{tarea.titulo}' automáticamente.",
            equipo=equipo,
            proyecto=proyecto,
            tarea=tarea,
            estado="PENDING",
        )

        tarea = (
            Tarea.objects.select_related("lista", "creado_por")
            .prefetch_related("asignados__usuario", "evidencias")
            .get(id=tarea.id)
        )

        return Response(
            {
                "ok": True,
                "equipo_id": equipo.id,
                "proyecto_id": proyecto.id,
                "tarea": TareaSerializer(tarea, context={"request": request}).data,
                "reporte": ReporteIncidenciaDetailSerializer(reporte, context={"request": request}).data,
            },
            status=status.HTTP_201_CREATED,
        )


class NotificacionViewSet(viewsets.ViewSet):
    authentication_classes = [UsuarioJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def list(self, request):
        desde = timezone.now() - timezone.timedelta(days=7)
        qs = (
            NotificacionClickup.objects.filter(usuario=request.user, creado_en__gte=desde)
            .select_related("equipo", "proyecto", "tarea", "invitacion")
            .order_by("-creado_en")
        )
        return Response(NotificacionClickupSerializer(qs, many=True).data)

    @action(detail=False, methods=["post"], url_path=r"(?P<notificacion_id>[^/.]+)/descartar")
    def descartar(self, request, notificacion_id=None):
        notif = NotificacionClickup.objects.filter(id=notificacion_id, usuario=request.user).first()
        if not notif:
            return Response({"detail": "Notificación no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        notif.estado = "DISMISSED"
        notif.leido_en = timezone.now()
        notif.save(update_fields=["estado", "leido_en"])
        return Response({"ok": True})

    @action(detail=False, methods=["post"], url_path=r"(?P<notificacion_id>[^/.]+)/leer")
    def marcar_leida(self, request, notificacion_id=None):
        notif = NotificacionClickup.objects.filter(id=notificacion_id, usuario=request.user).first()
        if not notif:
            return Response({"detail": "Notificación no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        notif.estado = "READ"
        notif.leido_en = timezone.now()
        notif.save(update_fields=["estado", "leido_en"])
        return Response({"ok": True})


class ResumenIAView(APIView):
    authentication_classes = [UsuarioJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        tareas = request.data.get("tareas", [])
        proyecto_nombre = request.data.get("proyecto_nombre", "Proyecto")
        equipo_nombre = request.data.get("equipo_nombre", "Grupo Automotriz R&R")
        total = request.data.get("total", 0)
        hecho = request.data.get("hecho", 0)

        problemas_texto = " | ".join([
            ". ".join(filter(None, [
                t.get("descripcion_problema"),
                t.get("desarrollo_estrategia"),
                t.get("resultados"),
            ]))
            for t in tareas[:8]
            if any([t.get("descripcion_problema"), t.get("desarrollo_estrategia"), t.get("resultados")])
        ])

        from django.conf import settings
        api_key = getattr(settings, "OPENAI_API_KEY", "")
        if not api_key:
            return Response({"detail": "API key no configurada."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        try:
            resp = http_requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                json={
                    "model": "gpt-4o-mini",
                    "max_tokens": 600,
                    "messages": [
                        {
                            "role": "system",
                            "content": "Eres un analista de mejora continua para una agencia Volkswagen. Generas resúmenes ejecutivos profesionales en español.",
                        },
                        {
                            "role": "user",
                            "content": (
                                f"Genera un resumen ejecutivo del siguiente proyecto de mejora continua.\n\n"
                                f"El resumen debe tener entre 6 y 8 oraciones, explicar los problemas identificados, "
                                f"describir las estrategias implementadas, mencionar los resultados esperados, "
                                f"ser un párrafo continuo sin listas y usar lenguaje profesional.\n\n"
                                f"Proyecto: {proyecto_nombre}\n"
                                f"Equipo: {equipo_nombre}\n"
                                f"Total de planes: {total}\n"
                                f"Completados: {hecho} de {total}\n\n"
                                f"Contenido:\n{problemas_texto[:3000]}"
                            ),
                        },
                    ],
                },
                timeout=30,
            )
            data = resp.json()
            resumen = data["choices"][0]["message"]["content"].strip()
            return Response({"resumen": resumen})

        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)