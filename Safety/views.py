# Safety/views.py
import json
import re

from django.db import transaction

from rest_framework import generics, status, mixins, viewsets
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from CrmConformidad.jwt_authentication import CRMJWTAuthentication

from .models import ReporteSafety, AdjuntoReporteSafety
from .serializers import ReporteSafetySerializer


def detectar_tipo_adjunto(archivo):
    tipo_mime = (getattr(archivo, "content_type", "") or "").lower()

    if tipo_mime.startswith("image/"):
        return "foto"

    if tipo_mime.startswith("video/"):
        return "video"

    return "archivo"


def crear_adjunto(reporte, archivo, punto_checklist_id="", tipo_adjunto=None):
    tipo_final = tipo_adjunto or detectar_tipo_adjunto(archivo)

    AdjuntoReporteSafety.objects.create(
        reporte=reporte,
        punto_checklist_id=str(punto_checklist_id or "").strip(),
        tipo_adjunto=tipo_final,
        archivo=archivo,
        nombre_original=getattr(archivo, "name", "") or "",
        tipo_mime=getattr(archivo, "content_type", "") or "",
        tamano_bytes=getattr(archivo, "size", 0) or 0,
    )


def obtener_ids_validos_checklist(checklist):
    ids = set()

    for item in checklist or []:
        item_id = str(item.get("id", "")).strip()
        if item_id:
            ids.add(item_id)

    return ids


def guardar_adjuntos_desde_request(request, reporte, ids_validos_checklist=None):
    for archivo in request.FILES.getlist("adjuntos_generales"):
        crear_adjunto(
            reporte=reporte,
            archivo=archivo,
            punto_checklist_id="",
            tipo_adjunto=detectar_tipo_adjunto(archivo),
        )

    patron = re.compile(r"^item_(?P<item_id>.+)_(?P<grupo>fotos|videos|archivos)$")

    tipo_por_grupo = {
        "fotos": "foto",
        "videos": "video",
        "archivos": "archivo",
    }

    for clave in request.FILES.keys():
        coincidencia = patron.match(clave)
        if not coincidencia:
            continue

        item_id = str(coincidencia.group("item_id") or "").strip()
        grupo = coincidencia.group("grupo")

        if not item_id:
            continue

        if ids_validos_checklist is not None and item_id not in ids_validos_checklist:
            continue

        for archivo in request.FILES.getlist(clave):
            crear_adjunto(
                reporte=reporte,
                archivo=archivo,
                punto_checklist_id=item_id,
                tipo_adjunto=tipo_por_grupo[grupo],
            )


class PublicReporteSafetyCreateView(generics.CreateAPIView):
    """
    Vista pública para crear reportes desde formularios externos.
    No requiere JWT.
    """
    authentication_classes = []
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    http_method_names = ["post", "options", "head"]

    queryset = ReporteSafety.objects.all().order_by("-creado", "-id_reporte")
    serializer_class = ReporteSafetySerializer

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        checklist_raw = request.data.get("checklist", "[]")

        try:
            checklist = json.loads(checklist_raw) if isinstance(checklist_raw, str) else checklist_raw
        except json.JSONDecodeError:
            return Response(
                {"checklist": ["El checklist debe enviarse en formato JSON válido."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        datos = {
            "fecha_reporte": request.data.get("fecha_reporte"),
            "reportante": request.data.get("reportante", ""),
            "agencia": request.data.get("agencia", ""),
            "nombre_cliente": request.data.get("nombre_cliente", ""),
            "orden_servicio": request.data.get("orden_servicio", ""),
            "tecnico_reparo": request.data.get("tecnico_reparo", ""),
            "valido_control_calidad": request.data.get("valido_control_calidad", ""),
            "comentarios_finales": request.data.get("comentarios_finales", ""),
            "checklist": checklist,
        }

        serializer = self.get_serializer(data=datos)
        serializer.is_valid(raise_exception=True)

        reporte = serializer.save()

        ids_validos_checklist = obtener_ids_validos_checklist(
            serializer.validated_data.get("checklist", [])
        )

        guardar_adjuntos_desde_request(
            request,
            reporte,
            ids_validos_checklist=ids_validos_checklist,
        )

        reporte = (
            ReporteSafety.objects
            .prefetch_related("adjuntos")
            .get(pk=reporte.pk)
        )

        salida = self.get_serializer(reporte, context={"request": request})

        return Response(
            {
                "message": "Reporte registrado correctamente.",
                "data": salida.data,
            },
            status=status.HTTP_201_CREATED,
        )


class ReporteSafetyViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    Vista interna del CRM para consultar/eliminar reportes.
    Requiere JWT.
    """
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    serializer_class = ReporteSafetySerializer
    queryset = (
        ReporteSafety.objects
        .prefetch_related("adjuntos")
        .all()
        .order_by("-creado", "-id_reporte")
    )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context