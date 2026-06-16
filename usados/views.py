# usados/views.py
from rest_framework import viewsets, permissions
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.parsers import JSONParser, FormParser, MultiPartParser

from CrmConformidad.jwt_authentication import CRMJWTAuthentication

from .models import AvaluoUsado
from .serializers import AvaluoUsadoSerializer


class AvaluoUsadoViewSet(viewsets.ModelViewSet):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    queryset = (
        AvaluoUsado.objects
        .select_related("cliente")
        .prefetch_related("evidencias", "conceptos")
        .all()
        .order_by("-creado")
    )
    serializer_class = AvaluoUsadoSerializer
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