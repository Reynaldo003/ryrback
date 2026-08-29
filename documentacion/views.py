# documentacion/views.py
import json
import unicodedata

from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from CrmConformidad.jwt_authentication import CRMJWTAuthentication

from .models import Expediente, DocumentoExpediente
from .serializers import ExpedienteSerializer, DocumentoExpedienteSerializer, DocumentoUploadSerializer
from .requisitos import obtener_requisitos, obtener_requisito, obtener_plantilla_solicitud

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

def requisitos_obligatorios_faltantes(expediente):
    requisitos = obtener_requisitos(expediente.tipo_persona, expediente.financiamiento,) or []

    obligatorios = [requisito for requisito in requisitos if requisito.get("obligatorio")]

    cargados = set(expediente.documentos.values_list("requisito_id",flat=True,))

    return [requisito for requisito in obligatorios if requisito["id"] not in cargados]

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
    @action(detail=True,methods=["post"],url_path="formato-pdf",parser_classes=[MultiPartParser,FormParser,],)
    @transaction.atomic
    def guardar_formato_pdf(self, request, pk=None):
        expediente = self.get_object()

        if not puede_editar_expediente(request.user,expediente,):
            raise PermissionDenied("No tienes permisos para modificar este expediente.")
        
        faltantes = requisitos_obligatorios_faltantes(expediente)

        if faltantes:
            return Response(
                {
                    "detail":
                        "Debes completar todos los documentos obligatorios antes de guardar la solicitud.",
                    "faltantes": [
                        {
                            "id": requisito["id"],
                            "nombre": requisito["nombre"],
                        }
                        for requisito in faltantes
                    ],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        plantilla_configurada = obtener_plantilla_solicitud(expediente.tipo_persona, expediente.financiamiento,)

        if not plantilla_configurada:
            return Response(
                {
                    "detail":
                        "Este expediente no tiene una plantilla PDF configurada."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        plantilla_enviada = str(request.data.get("plantilla", "") or "").strip()
        plantilla_esperada = plantilla_configurada["value"]

        if plantilla_enviada != plantilla_esperada:
            return Response(
                {
                    "plantilla": [
                        "La plantilla enviada no corresponde al tipo de persona y financiamiento del expediente."
                    ],
                    "esperada": plantilla_esperada,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        archivo = request.FILES.get("archivo")
        if not archivo:
            return Response(
                {
                    "archivo": [
                        "Debes enviar el PDF modificado."
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        nombre = str(getattr(archivo, "name", "") or "").lower()
        mime = str(getattr(archivo, "content_type", "") or "").lower()

        if not nombre.endswith(".pdf"):
            return Response(
                {
                    "archivo": [
                        "Solo se permiten archivos PDF."
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if mime and mime != "application/pdf":
            return Response(
                {
                    "archivo": [
                        "El archivo enviado no tiene formato PDF."
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        posicion = archivo.tell()
        cabecera = archivo.read(5)
        archivo.seek(posicion)

        if cabecera != b"%PDF-":
            return Response(
                {
                    "archivo": [
                        "El archivo enviado no es un PDF válido."
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ---------------------------------------------------------
        # CAMPOS ACROFORM
        # ---------------------------------------------------------

        campos_raw = request.data.get("campos","{}",)

        try:
            campos = (
                json.loads(campos_raw)
                if isinstance(campos_raw, str)
                else campos_raw
            )
        except json.JSONDecodeError:
            return Response(
                {
                    "campos": [
                        "Los campos enviados no contienen JSON válido."
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not isinstance(campos, dict):
            return Response(
                {
                    "campos": [
                        "Los campos deben enviarse como un objeto JSON."
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ---------------------------------------------------------
        # NOMBRE DEL PDF GENERADO
        # ---------------------------------------------------------

        nombre_plantilla = plantilla_configurada["archivo"]

        nombre_final = (
            f"{expediente.folio}-"
            f"{nombre_plantilla}"
        )

        archivo_anterior = (
            expediente.solicitud_pdf.name
            if expediente.solicitud_pdf
            else ""
        )

        # ---------------------------------------------------------
        # GUARDAR NUEVA COPIA
        # ---------------------------------------------------------

        expediente.solicitud_pdf.save(nombre_final,archivo,save=False,)
        expediente.solicitud_pdf_plantilla = (plantilla_esperada)
        expediente.solicitud_pdf_campos = campos
        expediente.solicitud_pdf_actualizado = (timezone.now())

        expediente.save(
            update_fields=[
                "solicitud_pdf",
                "solicitud_pdf_plantilla",
                "solicitud_pdf_campos",
                "solicitud_pdf_actualizado",
                "actualizado",
            ]
        )

        # Eliminamos la versión anterior después
        # de haber guardado correctamente la nueva.
        if (archivo_anterior and archivo_anterior != expediente.solicitud_pdf.name):
            try:
                default_storage.delete(archivo_anterior)
            except Exception:
                pass

        salida = self.get_serializer(expediente)

        return Response(
            {
                "message":
                    "Solicitud PDF guardada correctamente.",
                "data": salida.data,
            },
            status=status.HTTP_200_OK,
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