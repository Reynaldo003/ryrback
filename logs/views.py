# logs/views.py
import datetime

from django.core.cache import cache
from django.db.models import Q
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from CrmConformidad.jwt_authentication import CRMJWTAuthentication
from CrmConformidad.permissions import IsAdminRole
from CrmConformidad.models import Usuario

from .helpers import (
    MODULOS_ETIQUETAS,
    TIPOS_DISPONIBLES,
    etiqueta_modulo,
    modulos_disponibles,
    esperar_cola,
    registrar_log,
)
from .models import LogActividad
from .serializers import LogActividadSerializer
from .snapshots import restaurar_snapshot

RESUMEN_CACHE_KEY = "logs:resumen:7d:v1"
RESUMEN_DIAS = 7
ESTADO_COUNT_CACHE_KEY = "logs:estado:count:v1"

class LogEstadoView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        ultimo_id = (
            LogActividad.objects
            .order_by("-id")
            .values_list("id", flat=True)
            .first()
        ) or 0

        total = cache.get(ESTADO_COUNT_CACHE_KEY)
        if total is None:
            total = LogActividad.objects.count()
            cache.set(ESTADO_COUNT_CACHE_KEY, total, 30)

        return Response(
            {
                "ultimo_id": ultimo_id,
                "total": total,
                "cola": esperar_cola(),
            },
            status=status.HTTP_200_OK,
        )


class LogsPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 200


class LogListView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        queryset = (
            LogActividad.objects
            .select_related("usuario")
            .order_by("-fecha")
        )

        usuario_id = request.query_params.get("usuario_id")
        if usuario_id:
            queryset = queryset.filter(usuario_id=usuario_id)

        modulo = request.query_params.get("modulo")
        if modulo:
            queryset = queryset.filter(modulo=modulo)

        tipo = request.query_params.get("tipo")
        if tipo:
            queryset = queryset.filter(tipo=tipo)

        desde = request.query_params.get("desde")
        if desde:
            try:
                queryset = queryset.filter(
                    fecha__gte=datetime.datetime.strptime(desde, "%Y-%m-%d")
                )
            except ValueError:
                pass

        hasta = request.query_params.get("hasta")
        if hasta:
            try:
                queryset = queryset.filter(
                    fecha__lte=datetime.datetime.strptime(hasta, "%Y-%m-%d")
                    + datetime.timedelta(days=1)
                )
            except ValueError:
                pass

        buscar = (request.query_params.get("buscar") or "").strip()
        if buscar:
            queryset = queryset.filter(
                Q(entidad__icontains=buscar) | Q(cambio__icontains=buscar)
            )

        paginator = LogsPagination()
        pagina = paginator.paginate_queryset(queryset, request, view=self)

        items = []
        for obj in pagina or []:
            data = LogActividadSerializer(obj).data
            data["modulo_etiqueta"] = etiqueta_modulo(obj.modulo)
            items.append(data)

        return paginator.get_paginated_response(items)


class LogCatalogoView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        usuarios = list(
            Usuario.objects
            .order_by("nombre", "apellidos")
            .values("id_usuario", "nombre", "apellidos", "usuario")
        )
        for u in usuarios:
            u["label"] = f"{u['nombre']} {u['apellidos'] or ''}".strip() or u["usuario"]

        return Response(
            {
                "modulos": modulos_disponibles(),
                "tipos": TIPOS_DISPONIBLES,
                "usuarios": usuarios,
                "cola": esperar_cola(),
            },
            status=status.HTTP_200_OK,
        )


class LogResumenView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        datos = cache.get(RESUMEN_CACHE_KEY)
        if datos is None:
            datos = _calcular_resumen()
            cache.set(RESUMEN_CACHE_KEY, datos, 60)

        datos["cola"] = esperar_cola()
        return Response(datos, status=status.HTTP_200_OK)


def _calcular_resumen():
    desde = datetime.datetime.now() - datetime.timedelta(days=RESUMEN_DIAS)

    logs = (
        LogActividad.objects
        .filter(fecha__gte=desde)
        .select_related("usuario")
    )

    por_dia = {}
    por_tipo = {}
    por_modulo = {}
    por_usuario = {}

    for log in logs.iterator(chunk_size=2000):
        dia = log.fecha.strftime("%Y-%m-%d")
        por_dia[dia] = por_dia.get(dia, 0) + 1
        por_tipo[log.tipo] = por_tipo.get(log.tipo, 0) + 1
        por_modulo[log.modulo] = por_modulo.get(log.modulo, 0) + 1

        clave_usuario = log.usuario_id or 0
        nombre = "Anónimo"
        if log.usuario is not None:
            nombre = f"{log.usuario.nombre} {log.usuario.apellidos or ''}".strip()
        if clave_usuario not in por_usuario:
            por_usuario[clave_usuario] = {"nombre": nombre, "total": 0}
        por_usuario[clave_usuario]["total"] += 1

    return {
        "desde": desde.strftime("%Y-%m-%d"),
        "hasta": datetime.datetime.now().strftime("%Y-%m-%d"),
        "total": sum(por_dia.values()),
        "por_dia": [{"fecha": k, "total": v} for k, v in sorted(por_dia.items())],
        "por_tipo": [{"tipo": k, "total": v} for k, v in sorted(por_tipo.items(), key=lambda x: -x[1])],
        "por_modulo": [
            {"modulo": k, "label": MODULOS_ETIQUETAS.get(k, k), "total": v}
            for k, v in sorted(por_modulo.items(), key=lambda x: -x[1])
        ],
        "por_usuario": sorted(por_usuario.values(), key=lambda x: -x["total"])[:20],
    }


class LogRestaurarView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated, IsAdminRole]

    def post(self, request, log_id):
        try:
            log = LogActividad.objects.get(pk=log_id)
        except LogActividad.DoesNotExist:
            return Response(
                {"detail": f"No existe el log #{log_id}."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if log.tipo != "ELIMINAR":
            return Response(
                {"detail": f"El log #{log_id} es tipo {log.tipo}, no ELIMINAR."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not (isinstance(log.datos, dict) and log.datos.get("modelo")):
            return Response(
                {"detail": "Este log no tiene snapshot restaurable."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ip = request.META.get("REMOTE_ADDR")
        ok, mensajes = restaurar_snapshot(log.datos)

        # Auditoría de la restauración: deja constancia de quién la hizo y
        # desde qué log, para poder rastrear el origen de cada restauración.
        registrar_log(
            usuario=request.user,
            tipo="EDITAR",
            modulo=log.modulo,
            entidad=log.entidad,
            cambio=(
                f"Restauró lo eliminado en el log #{log.id} "
                f"({'; '.join(mensajes) if mensajes else 'sin detalle'})"
            ),
            ip=ip,
            datos={"log_origen": log.id, "resultado": ok},
        )

        return Response(
            {"ok": ok, "mensajes": mensajes},
            status=status.HTTP_200_OK if ok else status.HTTP_400_BAD_REQUEST,
        )