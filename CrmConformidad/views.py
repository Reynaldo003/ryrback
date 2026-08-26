# CrmConformidad/views.py
from django.db import transaction
from django.shortcuts import get_object_or_404

from rest_framework import generics, status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .jwt_authentication import CRMJWTAuthentication
from .models import ExpedienteConformidad, ExpedienteDocumento, Usuario, Rol
from .permissions import IsAdminRole
from .serializers import CasoSerializer, ExpedienteDocumentoSerializer, UsuarioRegisterSerializer, UsuarioLoginSerializer, AdminUsuarioCreateSerializer, AdminUsuarioUpdateSerializer


# ============================================================
# HELPERS DE USUARIO / PERMISOS / JWT
# ============================================================

def permisos_por_rol(nombre_rol: str):
    r = (nombre_rol or "").strip().lower()

    if r == "administrador":
        return [
            "ALL",
            "USUARIOS_ADMIN",
            "CRM_RECLAMACIONES",
            "CRM_DIGITALES",
            "CRM_FINANCIEROS",
            "CRM_VENTAS",
            "CRM_POSTVENTA",
            "CRM_RRHH",
            "CRM_CALIDAD",
            "CRM_CALL_CENTER",
            "CRM_COORDINADOR_DIGITAL",
            "CRM_ASESOR_PISO",
        ]

    if r == "asesor general":
        return ["CRM_RECLAMACIONES", "CRM_DIGITALES"]

    if r == "hostess":
        return ["CRM_VENTAS"]

    if r == "asesor conformidad":
        return ["CRM_RECLAMACIONES"]

    if r == "coordinador digital":
        return ["CRM_COORDINADOR_DIGITAL"]
    
    if r == "asesor digital":
        return ["CRM_DIGITALES"]

    if r == "contador":
        return ["CRM_FINANCIEROS"]

    if r == "postventa":
        return ["CRM_POSTVENTA"]

    if r == "recursos humanos":
        return ["CRM_RRHH"]

    if r == "calidad":
        return ["CRM_CALIDAD"]
    
    if r == "contacto":
        return ["CRM_CALL_CENTER"]

    if r == "asesor_piso":
        return ["CRM_ASESOR_PISO"]
    
    return []


def serialize_usuario(user):
    rol_nombre = user.rol.nombre if getattr(user, "rol", None) else ""

    return {
        "id_usuario": user.id_usuario,
        "nombre": user.nombre,
        "apellidos": user.apellidos,
        "usuario": user.usuario,
        "correo": user.correo,
        "rol": rol_nombre,
        "agencia": user.agencia,
        "telefono": user.telefono,
        "permisos": permisos_por_rol(rol_nombre),
    }


def generar_jwt_usuario(user):
    """
    Genera JWT usando SimpleJWT, pero con claims personalizados para tu modelo Usuario.

    El claim importante es id_usuario, porque CRMJWTAuthentication lo usa para
    resolver request.user contra CrmConformidad.models.Usuario.
    """
    rol_nombre = user.rol.nombre if getattr(user, "rol", None) else ""

    refresh = RefreshToken()

    refresh["id_usuario"] = user.id_usuario
    refresh["usuario"] = user.usuario
    refresh["rol"] = rol_nombre
    refresh["agencia"] = user.agencia
    refresh["telefono"] = user.telefono or ""
    refresh["permisos"] = permisos_por_rol(rol_nombre)

    access = refresh.access_token

    return {
        "access": str(access),
        "refresh": str(refresh),
    }


# ============================================================
# CASOS CONFORMIDAD - PROTEGIDO CON JWT
# ============================================================

class CasoListCreateView(generics.ListCreateAPIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    queryset = (
        ExpedienteConformidad.objects
        .select_related("cliente")
        .prefetch_related("documentos")
        .order_by("-id_exp")
    )
    serializer_class = CasoSerializer


class CasoDetailView(generics.RetrieveUpdateDestroyAPIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    queryset = (
        ExpedienteConformidad.objects
        .select_related("cliente")
        .prefetch_related("documentos")
    )
    serializer_class = CasoSerializer

    @transaction.atomic
    def perform_destroy(self, instance: ExpedienteConformidad):
        cliente = instance.cliente

        for doc in instance.documentos.all():
            if doc.archivo:
                doc.archivo.delete(save=False)
            doc.delete()

        instance.delete()

        if cliente and not cliente.expedientes.exists():
            cliente.delete()


class CasoUploadDocsView(generics.GenericAPIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]
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

        ser = ExpedienteDocumentoSerializer(
            created,
            many=True,
            context={"request": request},
        )

        return Response(ser.data, status=status.HTTP_201_CREATED)


class DocDeleteView(generics.DestroyAPIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    queryset = ExpedienteDocumento.objects.all()


# ============================================================
# AUTH PÚBLICO
# ============================================================

class AuthRegisterView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

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
                "rol": user.rol.nombre if user.rol else "",
                "agencia": user.agencia,
            },
            status=status.HTTP_201_CREATED,
        )


class AuthLoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        ser = UsuarioLoginSerializer(data=request.data)

        if not ser.is_valid():
            return Response(
                {"detail": "Credenciales inválidas."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        user = ser.validated_data["user"]
        jwt = generar_jwt_usuario(user)
        user_data = serialize_usuario(user)

        return Response(
            {
                # Compatibilidad con frontend viejo:
                # token ahora también es JWT access.
                "token": jwt["access"],

                # JWT real:
                "access": jwt["access"],
                "refresh": jwt["refresh"],

                "user": user_data,
            },
            status=status.HTTP_200_OK,
        )


class AuthMeView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(serialize_usuario(request.user))


# ============================================================
# ADMIN - PROTEGIDO CON JWT + ROL ADMIN
# ============================================================

class AdminRolesView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        roles = Rol.objects.all().order_by("id_rol")

        data = [
            {
                "id_rol": rol.id_rol,
                "nombre": rol.nombre,
                "descripcion": rol.descripcion,
            }
            for rol in roles
        ]

        return Response(data)

    def post(self, request):
        nombre = str(request.data.get("nombre", "")).strip()
        descripcion = str(request.data.get("descripcion", "")).strip()

        if not nombre:
            return Response(
                {"detail": "El nombre es requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if Rol.objects.filter(nombre__iexact=nombre).exists():
            return Response(
                {"detail": "Ya existe un rol con ese nombre."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        rol = Rol.objects.create(
            nombre=nombre,
            descripcion=descripcion or "Sin descripción",
        )

        return Response(
            {
                "id_rol": rol.id_rol,
                "nombre": rol.nombre,
                "descripcion": rol.descripcion,
            },
            status=status.HTTP_201_CREATED,
        )
    
class AdminPermisosCatalogView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        data = [
            {
                "clave": "CRM_FINANCIEROS",
                "descripcion": "Acceso al CRM de Servicios Financieros",
            },
            {
                "clave": "CRM_RECLAMACIONES",
                "descripcion": "Acceso al CRM de Reclamaciones/Conformidad",
            },
            {
                "clave": "CRM_DIGITALES",
                "descripcion": "Acceso al CRM de Digitales",
            },
            {
                "clave": "CRM_VENTAS",
                "descripcion": "Acceso al CRM de Ventas",
            },
            {
                "clave": "USUARIOS_ADMIN",
                "descripcion": "Administración de usuarios/configuración",
            },
            {
                "clave": "ALL",
                "descripcion": "Superusuario",
            },
            {
                "clave": "CRM_POSTVENTA",
                "descripcion": "Acceso a pedidos de piezas",
            },
            {
                "clave": "CRM_RRHH",
                "descripcion": "Administrador de procesos de reclutamiento",
            },
            {
                "clave": "CRM_CALIDAD",
                "descripcion": "Acceso completo al CRM solo a la agencia que pertenece.",
            },
            {
                "clave": "CRM_CALL_CENTER",
                "descripcion": "Contacto PostVenta.",
            },
            {
                "clave": "CRM_COORDINADOR_DIGITAL",
                "descripcion": "Coordinacion de asesores digitales.",
            },
            {
                "clave": "CRM_ASESOR_PISO",
                "descripcion": "CRM ASESOR PISO",
            },
        ]

        return Response(data)

def serializar_usuario_admin(u):
    return {
        "id": u.id_usuario,
        "id_usuario": u.id_usuario,
        "nombre": u.nombre,
        "apellidos": u.apellidos,
        "usuario": u.usuario,
        "correo": u.correo,
        "estado": "Activo",
        "agencia": u.agencia,
        "telefono": u.telefono or "",
        "id_rol": u.rol.id_rol if u.rol else None,
        "nombre_rol": u.rol.nombre if u.rol else "",
    }

class AdminUsuariosCreateView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated, IsAdminRole]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        usuarios = Usuario.objects.select_related("rol").all().order_by("id_usuario")
        return Response([serializar_usuario_admin(u) for u in usuarios])

    def post(self, request):
        ser = AdminUsuarioCreateSerializer(data=request.data)
        if not ser.is_valid(): return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        usuario = ser.save()
        return Response(serializar_usuario_admin(usuario), status=status.HTTP_201_CREATED)

class AdminUsuarioDetailView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated, IsAdminRole]
    parser_classes = [MultiPartParser, FormParser]

    def get_object(self, pk):
        return get_object_or_404(Usuario.objects.select_related("rol"), id_usuario=pk)

    def get(self, request, pk):
        return Response(serializar_usuario_admin(self.get_object(pk)))

    @transaction.atomic
    def patch(self, request, pk):
        usuario = self.get_object(pk)
        ser = AdminUsuarioUpdateSerializer(usuario, data=request.data, partial=True)

        if not ser.is_valid(): return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        usuario = ser.save()
        usuario.refresh_from_db()
        usuario = Usuario.objects.select_related("rol").get(id_usuario=usuario.id_usuario)

        return Response(serializar_usuario_admin(usuario), status=status.HTTP_200_OK)
    
class PerfilUsuarioView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def patch(self, request):
        usuario = request.user  # ajustar según tu modelo
        for field in ['nombre', 'apellidos', 'usuario', 'correo', 'telefono']:
            if field in request.data:
                setattr(usuario, field, request.data[field])
        if 'foto' in request.FILES:
            usuario.foto = request.FILES['foto']
        usuario.save()
        return Response({'detail': 'Perfil actualizado'})