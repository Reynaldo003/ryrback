# Financieros/views.py
from rest_framework import viewsets, permissions
from rest_framework.filters import OrderingFilter, SearchFilter

from CrmConformidad.jwt_authentication import CRMJWTAuthentication

from .models import SolicitudCredito, LongDrive
from .serializers import SolicitudCreditoSerializer, LongDriveSerializer


class SolicitudCreditoViewSet(viewsets.ModelViewSet):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    queryset = (
        SolicitudCredito.objects
        .select_related("cliente")
        .all()
        .order_by("-creado")
    )
    serializer_class = SolicitudCreditoSerializer
    filter_backends = [OrderingFilter, SearchFilter]

    ordering_fields = [
        "creado",
        "fecha_respuesta",
        "agencia",
        "id_soli_cred",
        "producto_financiero",
        "asesor_ventas",
        "estado_financiamiento",
        "estado_compra",
    ]

    search_fields = [
        "agencia",
        "id_soli_cred",
        "producto_financiero",
        "plazo_meses",
        "monto_financiero",
        "auto_interes",
        "canal_origen",
        "asesor_ventas",
        "estado_financiamiento",
        "estado_compra",
        "comentarios",
        "cliente__nombre",
        "cliente__telefono",
        "cliente__correo",
    ]


class LongDriveViewSet(viewsets.ModelViewSet):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    queryset = (
        LongDrive.objects
        .select_related("cliente")
        .all()
        .order_by("-creado")
    )
    serializer_class = LongDriveSerializer
    filter_backends = [OrderingFilter, SearchFilter]

    ordering_fields = [
        "creado",
        "fecha_entrega",
        "agencia",
        "chasis",
        "producto_long_drive",
        "tipo_venta",
    ]

    search_fields = [
        "agencia",
        "chasis",
        "producto_long_drive",
        "tipo_venta",
        "cliente__nombre",
        "cliente__telefono",
        "cliente__correo",
    ]