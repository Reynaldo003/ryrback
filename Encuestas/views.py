# Encuestas/views.py
from django.core.exceptions import ValidationError

from rest_framework import generics, status, viewsets
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from CrmConformidad.jwt_authentication import CRMJWTAuthentication

from .QR import generar_qr_permanente, obtener_capacidades_qr
from .models import EncuestaSatisfaccion, EncuestaServicio, EncuestaPiso
from .serializers import (
    EncuestaSatisfaccionSerializer,
    EncuestaServicioSerializer,
    EncuestaPisoSerializer,
)

from trafico_piso.models import TraficoPiso


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

class EncuestaPisoViewSet(viewsets.ReadOnlyModelViewSet):
    authentication_classes = []
    permission_classes = [AllowAny]

    serializer_class = EncuestaPisoSerializer
    queryset = EncuestaPiso.objects.all().order_by("-creado_en")

    def get_queryset(self):
        qs = super().get_queryset()

        id_trafico = self.request.query_params.get("id_trafico")
        telefono = self.request.query_params.get("telefono")
        flow_token = self.request.query_params.get("flow_token")
        agencia = self.request.query_params.get("agencia")

        if id_trafico:
            qs = qs.filter(id_trafico=id_trafico)

        if flow_token:
            qs = qs.filter(flow_token=flow_token)

        if telefono:
            digitos = "".join(ch for ch in telefono if ch.isdigit())
            ultimos_10 = digitos[-10:] if len(digitos) >= 10 else digitos
            if ultimos_10:
                qs = qs.filter(telefono__endswith=ultimos_10)

        if agencia:
            qs = qs.filter(agencia__iexact=agencia)

        return qs
    
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
        
class RespuestasEncuestaPorClienteView(APIView):
    """
    Obtiene las respuestas de encuesta para un cliente específico
    usando su ID de tráfico de piso
    """
    authentication_classes = []
    permission_classes = [AllowAny]
    
    def get(self, request, cliente_id):
        try:
            # Primero, verifica que el cliente existe en tráfico_piso
            # Ajusta el nombre del modelo según tu app trafico_piso
            from trafico_piso.models import RegistroTraficoPiso  # Cambia por el nombre correcto
            
            try:
                cliente = RegistroTraficoPiso.objects.get(id=cliente_id)
            except RegistroTraficoPiso.DoesNotExist:
                return Response(
                    {"error": "Cliente no encontrado en tráfico de piso"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Busca encuestas asociadas a este cliente
            # Puedes buscar por id_trafico o por teléfono
            encuestas = EncuestaSatisfaccion.objects.filter(
                id_trafico=cliente_id
            ).order_by('-creado')
            
            # Si no hay encuestas con id_trafico, intenta por teléfono
            if not encuestas.exists() and cliente.telefono:
                encuestas = EncuestaSatisfaccion.objects.filter(
                    telefono=cliente.telefono
                ).order_by('-creado')
            
            serializer = EncuestaSatisfaccionSerializer(encuestas, many=True)
            
            return Response({
                "cliente": {
                    "id": cliente.id,
                    "nombre": cliente.nombre or cliente.nombre_cliente,
                    "telefono": cliente.telefono
                },
                "encuestas": serializer.data,
                "total": encuestas.count()
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )