from django.utils.dateparse import parse_date
from rest_framework import permissions, viewsets
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser

from CrmConformidad.jwt_authentication import CRMJWTAuthentication

from .models import AvaluoUsado
from .pagination import AvaluoPagination
from .serializers import AvaluoUsadoSerializer


class AvaluoUsadoViewSet(viewsets.ModelViewSet):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    serializer_class = AvaluoUsadoSerializer
    pagination_class = AvaluoPagination
    filter_backends = [OrderingFilter, SearchFilter]

    ordering_fields = [
        "creado",
        "fecha_avaluo",
        "agencia",
        "asesor_ventas",
        "marca_auto",
        "modelo",
        "anio_modelo",
        "serie",
        "kilometraje",
        "precio_guia",
        "costo_reparacion",
        "costo_estimado",
        "oferta_economica",
        "color",
        "ganador_subasta",
        "etapa_proceso",
        "tipo_toma",
    ]
    ordering = ["-creado"]

    search_fields = [
        "agencia",
        "asesor_ventas",
        "marca_auto",
        "modelo",
        "anio_modelo",
        "serie",
        "kilometraje",
        "precio_guia",
        "costo_reparacion",
        "costo_estimado",
        "oferta_economica",
        "color",
        "descripcion",
        "ganador_subasta",
        "etapa_proceso",
        "tipo_toma",
        "comentarios",
        "conceptos__descripcion",
        "cliente__nombre",
        "cliente__telefono",
        "cliente__correo",
    ]

    def get_queryset(self):
        queryset = (
            AvaluoUsado.objects
            .select_related("cliente")
            .prefetch_related("evidencias", "conceptos")
            .all()
        )

        agencia = str(self.request.query_params.get("agencia", "")).strip()
        desde = parse_date(str(self.request.query_params.get("desde", "")).strip())
        hasta = parse_date(str(self.request.query_params.get("hasta", "")).strip())

        if agencia and agencia.lower() != "todos":
            queryset = queryset.filter(agencia__iexact=agencia)

        if desde:
            queryset = queryset.filter(fecha_avaluo__date__gte=desde)

        if hasta:
            queryset = queryset.filter(fecha_avaluo__date__lte=hasta)

        return queryset.distinct()
