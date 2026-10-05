# usados/views.py
from django.db.models import Q
from django.utils.dateparse import parse_date
from rest_framework import permissions, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from CrmConformidad.jwt_authentication import CRMJWTAuthentication
from .models import AvaluoUsado
from .pagination import AvaluoPagination
from .serializers import AvaluoUsadoSerializer
def normalizar_texto(valor):
    return str(valor or "").strip()
def es_administrador(usuario):
    """
    Retorna True únicamente cuando el usuario tiene rol Administrador.
    """
    rol = getattr(usuario, "rol", None)
    nombre_rol = getattr(rol, "nombre", "")
    return normalizar_texto(nombre_rol).lower() == "administrador"

def obtener_agencias_usuario(usuario):
    """
    Convierte:
        "VW Cordoba"
    o:
        "VW Cordoba|VW Orizaba"

    en:
        ["VW Cordoba"]

    o:
        ["VW Cordoba", "VW Orizaba"]
    """
    agencia = getattr(usuario, "agencia", "")
    return [
        item.strip()
        for item in str(agencia or "").split("|")
        if item.strip()
    ]

def obtener_agencia_permitida(usuario, agencia):
    """
    Valida que una agencia pertenezca al usuario.

    Devuelve el nombre original de la agencia asignada al usuario
    para mantener un valor uniforme en la base de datos.

    Administradores pueden usar cualquier agencia.
    """
    agencia = normalizar_texto(agencia)
    if es_administrador(usuario):
        return agencia
    agencias_permitidas = obtener_agencias_usuario(usuario)
    if not agencias_permitidas:
        raise PermissionDenied(
            "Tu usuario no tiene una agencia asignada."
        )
    # Si solo tiene una agencia y no llegó ninguna agencia,
    # usamos automáticamente la agencia del usuario.
    if not agencia and len(agencias_permitidas) == 1:
        return agencias_permitidas[0]

    for agencia_permitida in agencias_permitidas:
        if agencia_permitida.lower() == agencia.lower():
            return agencia_permitida

    raise PermissionDenied(
        "No tienes permisos para registrar información de esta agencia."
    )

class AvaluoUsadoViewSet(viewsets.ModelViewSet):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser,FormParser,JSONParser,]
    serializer_class = AvaluoUsadoSerializer
    pagination_class = AvaluoPagination

    filter_backends = [OrderingFilter,SearchFilter,]
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
        "tipo_valuacion",
        "vendedor",
        "origen_valuacion",
        "observaciones",
        "comentario_ticket",
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
        "tipo_valuacion",
        "vendedor",
        "origen_valuacion",
        "observaciones",
        "comentario_ticket",
        "conceptos__descripcion",
        "cliente__nombre",
        "cliente__telefono",
        "cliente__correo",
    ]

    def get_queryset(self):
        """
        Regla principal:

        - Administrador:
            puede ver registros de todas las agencias.

        - Cualquier otro usuario:
            solamente puede ver registros de las agencias
            que tenga asignadas.

        Después de aplicar la seguridad por usuario,
        aplicamos los filtros normales de la interfaz.
        """

        usuario = self.request.user
        queryset = (AvaluoUsado.objects.select_related("cliente").prefetch_related("evidencias","conceptos",).all())

        # =====================================================
        # SEGURIDAD POR AGENCIA
        # =====================================================

        if not es_administrador(usuario):
            agencias_usuario = obtener_agencias_usuario(usuario)

            # Usuario sin agencia:
            # no debe ver absolutamente ningún registro.
            if not agencias_usuario:
                return queryset.none()

            filtro_agencias = Q(
                agencia__iexact=agencias_usuario[0]
            )

            for agencia in agencias_usuario[1:]:
                filtro_agencias |= Q(
                    agencia__iexact=agencia
                )

            queryset = queryset.filter(
                filtro_agencias
            )

        # =====================================================
        # FILTRO DE AGENCIA SOLICITADO DESDE FRONTEND
        # =====================================================

        agencia = normalizar_texto(
            self.request.query_params.get("agencia")
        )

        if agencia and agencia.lower() != "todos":

            # Para usuarios normales hacemos una segunda validación.
            #
            # Esto evita que alguien cambie manualmente la URL:
            #
            # ?agencia=VW Orizaba
            #
            # siendo usuario de VW Cordoba.
            if not es_administrador(usuario):
                agencias_usuario = obtener_agencias_usuario(
                    usuario
                )

                pertenece = any(
                    item.lower() == agencia.lower()
                    for item in agencias_usuario
                )

                if not pertenece:
                    return queryset.none()

            queryset = queryset.filter(
                agencia__iexact=agencia
            )

        # =====================================================
        # FILTRO DE FECHAS
        # =====================================================

        desde = parse_date(
            normalizar_texto(
                self.request.query_params.get("desde")
            )
        )

        hasta = parse_date(
            normalizar_texto(
                self.request.query_params.get("hasta")
            )
        )

        if desde:
            queryset = queryset.filter(
                fecha_avaluo__date__gte=desde
            )

        if hasta:
            queryset = queryset.filter(
                fecha_avaluo__date__lte=hasta
            )

        return queryset.distinct()

    def perform_create(self, serializer):
        """
        Evita que un usuario cree un avalúo para otra agencia
        manipulando manualmente el request.
        """

        usuario = self.request.user

        agencia = serializer.validated_data.get(
            "agencia",
            "",
        )

        agencia_permitida = obtener_agencia_permitida(
            usuario,
            agencia,
        )

        serializer.save(
            agencia=agencia_permitida
        )

    def perform_update(self, serializer):
        """
        Evita cambiar un avalúo a una agencia que el usuario
        no tiene asignada.
        """
        usuario = self.request.user
        agencia = serializer.validated_data.get("agencia",serializer.instance.agencia,)
        agencia_permitida = obtener_agencia_permitida(usuario,agencia,)
        serializer.save(
            agencia=agencia_permitida
        )