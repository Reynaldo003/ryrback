# documentacion/views.py
import unicodedata

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404

from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from CrmConformidad.jwt_authentication import CRMJWTAuthentication

from .models import Expediente, DocumentoExpediente
from .serializers import ExpedienteSerializer, DocumentoExpedienteSerializer, DocumentoUploadSerializer
from .requisitos import obtener_requisitos, obtener_requisito


def normalizar(valor):
    valor = unicodedata.normalize("NFD", str(valor or "").strip().lower())
    return "".join(caracter for caracter in valor if unicodedata.category(caracter) != "Mn")


def obtener_rol(usuario): return normalizar(getattr(usuario, "rol", ""))


def obtener_agencias_usuario(usuario):
    return [agencia.strip() for agencia in str(getattr(usuario, "agencia", "") or "").split("|") if agencia.strip()]


def nombre_usuario_crm(usuario):
    return str(
        getattr(usuario, "nombre_completo", "")
        or getattr(usuario, "nombre", "")
        or getattr(usuario, "username", "")
        or getattr(usuario, "usuario", "")
        or getattr(usuario, "email", "")
        or usuario
        or ""
    ).strip()


def es_admin(usuario):
    if getattr(usuario, "is_superuser", False): return True
    return obtener_rol(usuario) == "administrador"


def es_gerente_servicios_financieros(usuario):
    rol = obtener_rol(usuario)
    return "gerente" in rol and "servicios" in rol and "financieros" in rol


def queryset_expedientes_usuario(usuario):
    """
    Actualmente los asesores de piso NO tienen cuentas en el CRM.

    Por lo tanto:
    - Administrador: ve todos los expedientes.
    - Resto de usuarios: ve expedientes de las agencias que tenga asignadas.
    - El asesor responsable se guarda como texto en asesor_nombre.
    """
    queryset = Expediente.objects.prefetch_related("documentos").all()

    if es_admin(usuario): return queryset

    agencias = obtener_agencias_usuario(usuario)
    return queryset.filter(agencia__in=agencias) if agencias else queryset.none()


def puede_editar_expediente(usuario, expediente):
    """
    Mientras los asesores no tengan cuentas:
    - Administrador puede editar cualquier expediente.
    - Usuarios internos pueden editar expedientes de sus Dealers asignados.

    Más adelante, cuando cada asesor tenga Login, aquí podremos restringir
    nuevamente por usuario/asesor.
    """
    if es_admin(usuario): return True

    agencias = obtener_agencias_usuario(usuario)
    return expediente.agencia in agencias


class ExpedienteViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    serializer_class = ExpedienteSerializer

    def get_queryset(self): return queryset_expedientes_usuario(self.request.user)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        agencia = serializer.validated_data["agencia"]

        if not es_admin(request.user):
            agencias_permitidas = obtener_agencias_usuario(request.user)

            if agencia not in agencias_permitidas:
                return Response(
                    {"agencia": ["No puedes crear expedientes para este Dealer."]},
                    status=status.HTTP_403_FORBIDDEN,
                )

        expediente = serializer.save(creado_por=nombre_usuario_crm(request.user))

        expediente = (
            Expediente.objects
            .prefetch_related("documentos")
            .get(pk=expediente.pk)
        )

        salida = self.get_serializer(expediente)

        return Response(
            {
                "message": "Expediente creado correctamente.",
                "data": salida.data,
            },
            status=status.HTTP_201_CREATED,
        )


class RequisitosView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tipo_persona = str(request.query_params.get("tipo_persona", "") or "").strip()
        financiamiento = str(request.query_params.get("financiamiento", "") or "").strip()

        if not tipo_persona:
            return Response(
                {"tipo_persona": ["Este parámetro es obligatorio."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not financiamiento:
            return Response(
                {"financiamiento": ["Este parámetro es obligatorio."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        requisitos = obtener_requisitos(tipo_persona, financiamiento)

        return Response({
            "disponible": requisitos is not None,
            "requisitos": requisitos or [],
        })


class DocumentoUploadView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @transaction.atomic
    def post(self, request, expediente_id):
        expediente = get_object_or_404(
            queryset_expedientes_usuario(request.user),
            pk=expediente_id,
        )

        if not puede_editar_expediente(request.user, expediente):
            raise PermissionDenied("No tienes permisos para modificar este expediente.")

        requisito_id = str(request.data.get("requisito_id", "") or "").strip()

        if not requisito_id:
            return Response(
                {"requisito_id": ["Este campo es obligatorio."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        requisito = obtener_requisito(
            expediente.tipo_persona,
            expediente.financiamiento,
            requisito_id,
        )

        if not requisito:
            return Response(
                {"requisito_id": ["Este requisito no pertenece al expediente."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if expediente.documentos.filter(requisito_id=requisito_id).exists():
            return Response(
                {
                    "archivo": [
                        "Este requisito ya tiene un documento. Elimínalo antes de cargar uno nuevo."
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = DocumentoUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        archivo = serializer.validated_data["archivo"]

        try:
            documento = DocumentoExpediente.objects.create(
                expediente=expediente,
                requisito_id=requisito_id,
                requisito_nombre=requisito["nombre"],
                archivo=archivo,
                nombre_original=getattr(archivo, "name", "") or "",
                tipo_mime=getattr(archivo, "content_type", "") or "application/pdf",
                tamano_bytes=getattr(archivo, "size", 0) or 0,
            )
        except IntegrityError:
            return Response(
                {"archivo": ["Este requisito ya tiene un documento."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        salida = DocumentoExpedienteSerializer(
            documento,
            context={"request": request},
        )

        return Response(
            {
                "message": "Documento cargado correctamente.",
                "data": salida.data,
            },
            status=status.HTTP_201_CREATED,
        )


class DocumentoDeleteView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def delete(self, request, pk):
        documento = get_object_or_404(
            DocumentoExpediente.objects.select_related("expediente"),
            pk=pk,
        )

        expediente = documento.expediente

        if not queryset_expedientes_usuario(request.user).filter(pk=expediente.pk).exists():
            raise PermissionDenied("No tienes acceso a este expediente.")

        if not puede_editar_expediente(request.user, expediente):
            raise PermissionDenied("No tienes permisos para eliminar documentos de este expediente.")

        documento.delete()

        return Response(
            {"message": "Documento eliminado correctamente."},
            status=status.HTTP_200_OK,
        )