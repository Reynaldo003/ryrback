# Encuestas/views.py
from django.core.exceptions import ValidationError

from rest_framework import generics, status, viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from CrmConformidad.jwt_authentication import CRMJWTAuthentication

from .QR import generar_qr_permanente, obtener_capacidades_qr
from .models import EncuestaSatisfaccion, EncuestaServicio
from .serializers import (
    EncuestaSatisfaccionSerializer,
    EncuestaServicioSerializer,
)


# ============================================================
# VISTAS PÚBLICAS
# ============================================================

class PublicEncuestaSatisfaccionCreateView(generics.CreateAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    queryset = EncuestaSatisfaccion.objects.all().order_by("-id_encuesta")
    serializer_class = EncuestaSatisfaccionSerializer
    http_method_names = ["post", "options", "head"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        encuesta = serializer.save()

        return Response(
            {
                "message": "Encuesta registrada correctamente.",
                "data": self.get_serializer(encuesta).data,
            },
            status=status.HTTP_201_CREATED,
        )


class PublicEncuestaServicioCreateView(generics.CreateAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    queryset = EncuestaServicio.objects.all().order_by("-id_encuesta")
    serializer_class = EncuestaServicioSerializer
    http_method_names = ["post", "options", "head"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        encuesta = serializer.save()

        return Response(
            {
                "message": "Encuesta registrada correctamente.",
                "data": self.get_serializer(encuesta).data,
            },
            status=status.HTTP_201_CREATED,
        )


class QRInfoView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(obtener_capacidades_qr())


# ============================================================
# VISTAS PROTEGIDAS CRM
# ============================================================

class EncuestaSatisfaccionViewSet(viewsets.ReadOnlyModelViewSet):
    authentication_classes = []
    permission_classes = [AllowAny]

    serializer_class = EncuestaSatisfaccionSerializer
    queryset = EncuestaSatisfaccion.objects.all().order_by("-creado")


class EncuestaServicioViewSet(viewsets.ReadOnlyModelViewSet):
    authentication_classes = []
    permission_classes = [AllowAny]

    serializer_class = EncuestaServicioSerializer
    queryset = EncuestaServicio.objects.all().order_by("-creado")


def mensaje_error(exc):
    if hasattr(exc, "messages") and exc.messages:
        return exc.messages[0]
    return str(exc)


class GenerarQRPermanenteView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        try:
            resultado = generar_qr_permanente(
                data=request.data,
                files=request.FILES,
                request=request,
            )

            status_code = (
                status.HTTP_200_OK
                if resultado.get("ya_existia")
                else status.HTTP_201_CREATED
            )

            return Response(resultado, status=status_code)

        except ValidationError as exc:
            return Response(
                {"detail": mensaje_error(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception as exc:
            return Response(
                {"detail": f"Error generando QR: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )