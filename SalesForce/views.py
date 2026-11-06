from datetime import date
import logging
from zipfile import BadZipFile

from django.db.models.deletion import ProtectedError
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import action

logger = logging.getLogger(__name__)

from CrmConformidad.jwt_authentication import CRMJWTAuthentication

from .importador import TABLAS, importar_archivo, validar_archivo
from .models import (
    ActividadProceso, ActividadProspecto, EntregaComercial, FacturaComercial,
    ImportacionComercial, ProcesoComercial, ProcesoComercialDetalle, Prospecto,
)
from .serializers import (
    ActividadProcesoSerializer, ActividadProspectoSerializer, ArchivoImportacionSerializer,
    EntregaComercialSerializer, FacturaComercialSerializer, ImportacionComercialSerializer,
    ProcesoComercialSerializer, ProcesoDetalleSerializer, ProspectoSerializer,
)


class EsAdministradorCRM(permissions.BasePermission):
    """Ajusta esta condición al catálogo oficial de roles de CrmConformidad."""
    message = "Solo los administradores pueden modificar datos de Salesforce."

    def has_permission(self, request, view):
        usuario = request.user
        if not usuario or not usuario.is_authenticated:
            return False
        if getattr(usuario, "is_superuser", False) or getattr(usuario, "is_staff", False):
            return True
        rol = getattr(usuario, "rol", "")
        if hasattr(rol, "nombre"):
            rol = rol.nombre
        return str(rol or "").strip().casefold() in {"administrador", "admin"}


class PaginacionSalesforce(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


class SalesforceViewSet(viewsets.ModelViewSet):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [permissions.IsAuthenticated, EsAdministradorCRM]
    pagination_class = PaginacionSalesforce
    search_fields = ()
    fecha_field = None
    agencia_field = "numero_concesionaria"

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params
        agencia = (params.get("agencia") or "").strip()
        busqueda = (params.get("search") or "").strip()
        if agencia and self.agencia_field:
            queryset = queryset.filter(**{self.agencia_field: agencia})
        if busqueda and self.search_fields:
            from django.db.models import Q
            filtro = Q()
            for campo in self.search_fields:
                filtro |= Q(**{f"{campo}__icontains": busqueda})
            queryset = queryset.filter(filtro)
        if self.fecha_field:
            for parametro, sufijo in (("fecha_desde", "gte"), ("fecha_hasta", "lte")):
                valor = params.get(parametro)
                if not valor:
                    continue
                try:
                    fecha = date.fromisoformat(valor)
                except ValueError as exc:
                    raise ValidationError({parametro: "Usa YYYY-MM-DD."}) from exc
                queryset = queryset.filter(**{f"{self.fecha_field}__{sufijo}": fecha})
        return queryset

    def perform_create(self, serializer):
        serializer.save(sincronizado_en=timezone.now())

    def perform_update(self, serializer):
        serializer.save(sincronizado_en=timezone.now())

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response({"detail": "No se puede eliminar porque hay registros relacionados."}, status=409)


class ProspectoViewSet(SalesforceViewSet):
    queryset = Prospecto.objects.all().order_by("-fecha_creacion", "id_prospecto")
    serializer_class = ProspectoSerializer
    search_fields = ("nombre", "apellido_paterno", "modelo_interes", "id_prospecto")
    fecha_field = "fecha_creacion"


class ProcesoComercialViewSet(SalesforceViewSet):
    queryset = ProcesoComercial.objects.select_related("prospecto").all().order_by("-fecha_creacion", "id_proceso_comercial")
    serializer_class = ProcesoComercialSerializer
    search_fields = ("nombre_proceso", "nombre_cuenta", "id_proceso_comercial")
    fecha_field = "fecha_creacion"


class ProcesoDetalleViewSet(SalesforceViewSet):
    queryset = ProcesoComercialDetalle.objects.select_related("proceso").all().order_by("proceso_id")
    serializer_class = ProcesoDetalleSerializer
    agencia_field = "proceso__numero_concesionaria"
    search_fields = ("proceso__nombre_proceso", "proceso_id", "rfc")


class ActividadProspectoViewSet(SalesforceViewSet):
    queryset = ActividadProspecto.objects.all().order_by("-fecha", "id_actividad")
    serializer_class = ActividadProspectoSerializer
    search_fields = ("asunto", "id_actividad", "id_prospecto_original")
    fecha_field = "fecha"


class ActividadProcesoViewSet(SalesforceViewSet):
    queryset = ActividadProceso.objects.all().order_by("-fecha", "id_actividad")
    serializer_class = ActividadProcesoSerializer
    search_fields = ("asunto", "id_actividad", "nombre_proceso", "id_proceso_original")
    fecha_field = "fecha"


class FacturaComercialViewSet(SalesforceViewSet):
    queryset = FacturaComercial.objects.all().order_by("-fecha_facturacion", "id_factura")
    serializer_class = FacturaComercialSerializer
    search_fields = ("nombre_factura", "nombre_proceso", "vin", "id_factura")
    fecha_field = "fecha_facturacion"


class EntregaComercialViewSet(SalesforceViewSet):
    queryset = EntregaComercial.objects.all().order_by("-fecha_entrega", "id_factura")
    serializer_class = EntregaComercialSerializer
    search_fields = ("nombre_factura", "nombre_proceso", "vin", "id_factura")
    fecha_field = "fecha_entrega"


class TablasView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [permissions.IsAuthenticated, EsAdministradorCRM]

    def get(self, request):
        ultimas = {}
        for registro in ImportacionComercial.objects.filter(estado="completada").order_by("-finalizado_en"):
            if registro.tabla not in ultimas:
                ultimas[registro.tabla] = registro.finalizado_en
            if len(ultimas) == len(TABLAS):
                break
        tablas = []
        for clave, config in TABLAS.items():
            fecha = ultimas.get(clave)
            tablas.append({
                "id": clave,
                "name": config["nombre"],
                "records": config["modelo"].objects.count(),
                "updatedAt": fecha.isoformat() if fecha else None,
                "status": "Lista para actualización",
            })
        return Response(tablas)


class ImportacionComercialViewSet(viewsets.ReadOnlyModelViewSet):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [permissions.IsAuthenticated, EsAdministradorCRM]
    serializer_class = ImportacionComercialSerializer
    pagination_class = PaginacionSalesforce
    queryset = ImportacionComercial.objects.all().order_by("-iniciado_en")

    def get_queryset(self):
        queryset = super().get_queryset()
        tabla = (self.request.query_params.get("tabla") or "").strip()
        return queryset.filter(tabla=tabla) if tabla else queryset

    @action(detail=False, methods=["post"], parser_classes=[MultiPartParser, FormParser], url_path="validar")
    def validar(self, request):
        entrada = ArchivoImportacionSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            resultado = validar_archivo(entrada.validated_data["archivo"], entrada.validated_data["tabla"])
        except (ValueError, OSError, KeyError, BadZipFile) as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response(resultado)

    @action(detail=False, methods=["post"], parser_classes=[MultiPartParser, FormParser], url_path="importar")
    def importar(self, request):
        entrada = ArchivoImportacionSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        datos = entrada.validated_data
        if not datos.get("huella"):
            raise ValidationError({"huella": "Primero valida este archivo."})
        usuario = request.user
        nombre_usuario = usuario.get_username() if hasattr(usuario, "get_username") else str(usuario)
        registro = ImportacionComercial.objects.create(
            tabla=datos["tabla"], nombre_archivo=datos["archivo"].name[:255], realizada_por=nombre_usuario[:200],
            estado=ImportacionComercial.Estado.PENDIENTE,
        )
        try:
            resultado = importar_archivo(datos["archivo"], datos["tabla"], datos["huella"])
            registro.registros_leidos = resultado["encontrados"]
            registro.registros_creados = resultado["nuevos"] if resultado["valido"] else 0
            registro.registros_actualizados = resultado["actualizar"] if resultado["valido"] else 0
            registro.registros_sin_cambios = resultado["sin_cambios"] if resultado["valido"] else 0
            registro.registros_error = resultado["errores"]
            registro.detalle_errores = resultado["detalle_errores"]
            registro.estado = ImportacionComercial.Estado.COMPLETADA if resultado["valido"] else ImportacionComercial.Estado.ERROR
            registro.finalizado_en = timezone.now()
            registro.save()
            if not resultado["valido"]:
                return Response(resultado, status=status.HTTP_400_BAD_REQUEST)
            return Response({**resultado, "importacion_id": registro.pk})
        except Exception as exc:
            registro.estado = ImportacionComercial.Estado.ERROR
            registro.detalle_errores = [{"error": str(exc)[:400]}]
            registro.registros_error = 1
            registro.finalizado_en = timezone.now()
            registro.save(update_fields=["estado", "detalle_errores", "registros_error", "finalizado_en"])
            if isinstance(exc, (ValueError, OSError, KeyError, BadZipFile)):
                raise ValidationError({"detail": str(exc)}) from exc
            logger.exception("Falló la importación Salesforce %s", registro.pk)
            raise
