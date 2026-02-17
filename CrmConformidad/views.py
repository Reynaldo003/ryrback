#crmConformidad/views.py
from rest_framework import generics
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework import status
from .models import ExpedienteConformidad, ExpedienteDocumento
from .serializers import CasoSerializer, ExpedienteDocumentoSerializer
from django.shortcuts import get_object_or_404
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from .serializers import UsuarioRegisterSerializer,UsuarioLoginSerializer, generar_token_usuario, AdminUsuarioCreateSerializer
from .models import Usuario, Rol
from .authentication import SignedUserAuthentication
from .permissions import IsAdminRole

class CasoListCreateView(generics.ListCreateAPIView):
    queryset = ExpedienteConformidad.objects.select_related("cliente").prefetch_related("documentos").order_by("-id_exp")
    serializer_class = CasoSerializer

class CasoDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = ExpedienteConformidad.objects.select_related("cliente").prefetch_related("documentos")
    serializer_class = CasoSerializer
    @transaction.atomic
    def perform_destroy(self, instance: ExpedienteConformidad):
        cliente = instance.cliente
        for doc in instance.documentos.all():
            if doc.archivo:
                doc.archivo.delete(save=False)  # elimina archivo físico
            doc.delete()  # elimina registro

        instance.delete()

        if not cliente.expedientes.exists():
            cliente.delete()

class CasoUploadDocsView(generics.GenericAPIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, id_exp):
        exp = get_object_or_404(ExpedienteConformidad, id_exp=id_exp)
        files = request.FILES.getlist("files")
        created = []
        for f in files:
            doc = ExpedienteDocumento.objects.create(
                expediente=exp,
                archivo=f,
                nombre_original=f.name,
                mime=getattr(f, "content_type", None),
                size=f.size,
            )
            created.append(doc)

        ser = ExpedienteDocumentoSerializer(created, many=True, context={"request": request})
        return Response(ser.data, status=status.HTTP_201_CREATED)
class DocDeleteView(generics.DestroyAPIView):
    queryset = ExpedienteDocumento.objects.all()

class AuthRegisterView(APIView):
    def post(self, request):
        ser = UsuarioRegisterSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        user = ser.save()
        return Response(
            {
                "id_usuario": user.id_usuario,
                "usuario": user.usuario,
                "correo": user.correo,
                "rol": user.rol.nombre,
                "agencia": user.agencia,
            },
            status=status.HTTP_201_CREATED,
        )


class AuthLoginView(APIView):
    def permisos_por_rol(self, nombre_rol: str):
        r = (nombre_rol or "").strip().lower()

        # tu tabla real
        if r == "administrador":
            return ["ALL", "USUARIOS_ADMIN", "CRM_RECLAMACIONES", "CRM_DIGITALES", "CRM_VENTAS"]

        if r == "asesor general":
            return ["CRM_RECLAMACIONES", "CRM_DIGITALES"]

        if r == "hostess":
            return ["CRM_VENTAS"]

        if r == "asesor conformidad":
            return ["CRM_RECLAMACIONES"]

        if r == "asesor digital":
            return ["CRM_DIGITALES"]

        return []

    def post(self, request):
        ser = UsuarioLoginSerializer(data=request.data)
        if not ser.is_valid():
            return Response({"detail": "Credenciales inválidas."}, status=status.HTTP_401_UNAUTHORIZED)

        user = ser.validated_data["user"]
        token = generar_token_usuario(user.id_usuario)

        return Response(
            {
                "token": token,
                "user": {
                    "id_usuario": user.id_usuario,
                    "nombre": user.nombre,
                    "apellidos": user.apellidos,
                    "usuario": user.usuario,
                    "correo": user.correo,
                    "rol": user.rol.nombre,
                    "agencia": user.agencia,
                    "permisos": self.permisos_por_rol(user.rol.nombre),
                },
            },
            status=status.HTTP_200_OK,
        )

class AuthMeView(APIView):
    authentication_classes = [SignedUserAuthentication]
    permission_classes = [IsAuthenticated]

    def permisos_por_rol(self, nombre_rol: str):
        # reutiliza misma lógica
        r = (nombre_rol or "").strip().lower()
        if r == "administrador":
            return ["ALL", "USUARIOS_ADMIN", "CRM_RECLAMACIONES", "CRM_DIGITALES", "CRM_VENTAS"]
        if r == "asesor general":
            return ["CRM_RECLAMACIONES", "CRM_DIGITALES"]
        if r == "hostess":
            return ["CRM_VENTAS"]
        if r == "asesor conformidad":
            return ["CRM_RECLAMACIONES"]
        if r == "asesor digital":
            return ["CRM_DIGITALES"]
        return []

    def get(self, request):
        u = request.user
        return Response(
            {
                "id_usuario": u.id_usuario,
                "nombre": u.nombre,
                "apellidos": u.apellidos,
                "usuario": u.usuario,
                "correo": u.correo,
                "rol": u.rol.nombre,
                "agencia": u.agencia,
                "permisos": self.permisos_por_rol(u.rol.nombre),
            }
        )


# ====== ADMIN ======

class AdminRolesView(APIView):
    authentication_classes = [SignedUserAuthentication]
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        roles = Rol.objects.all().order_by("id_rol")
        data = [{"id_rol": r.id_rol, "nombre": r.nombre, "descripcion": r.descripcion} for r in roles]
        return Response(data)


class AdminPermisosCatalogView(APIView):
    """
    Catálogo simple (si aún no tienes tabla permisos).
    Si luego creas tabla permisos, aquí lo cambias a query.
    """
    authentication_classes = [SignedUserAuthentication]
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        data = [
            {"clave": "CRM_RECLAMACIONES", "descripcion": "Acceso al CRM de Reclamaciones/Conformidad"},
            {"clave": "CRM_DIGITALES", "descripcion": "Acceso al CRM de Digitales"},
            {"clave": "CRM_VENTAS", "descripcion": "Acceso al CRM de Ventas"},
            {"clave": "USUARIOS_ADMIN", "descripcion": "Administración de usuarios/configuración"},
            {"clave": "ALL", "descripcion": "Superusuario (solo Administrador)"},
        ]
        return Response(data)


class AdminUsuariosCreateView(APIView):
    authentication_classes = [SignedUserAuthentication]
    permission_classes = [IsAuthenticated, IsAdminRole]

    def post(self, request):
        ser = AdminUsuarioCreateSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        u = ser.save()
        return Response(
            {
                "id_usuario": u.id_usuario,
                "usuario": u.usuario,
                "correo": u.correo,
                "rol": u.rol.nombre,
                "agencia": u.agencia,
            },
            status=status.HTTP_201_CREATED,
        )
