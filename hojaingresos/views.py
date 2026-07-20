# hojaingresos/views.py
import re
import unicodedata

from django.db.models import Q
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from CrmConformidad.jwt_authentication import CRMJWTAuthentication

from .models import HojaIngresos
from .serializers import HojaIngresosSerializer


ADMIN_PERMISSIONS = {
    "ALL",
    "USUARIOS_ADMIN",
    "CRM_DIGITALES",
    "TALLER_ADMIN",
}


def normalizar_texto(value):
    texto = str(value or "").strip()
    texto = unicodedata.normalize("NFD", texto)
    return "".join(
        caracter
        for caracter in texto
        if unicodedata.category(caracter) != "Mn"
    ).lower()


def obtener_agencias_usuario(user):
    valor = getattr(user, "agencia", "") or ""
    return [
        agencia.strip()
        for agencia in str(valor).split("|")
        if agencia.strip()
    ]


def obtener_permisos_usuario(user):
    permisos = getattr(user, "permisos", []) or []

    if hasattr(permisos, "values_list"):
        try:
            return {
                str(codigo).strip().upper()
                for codigo in permisos.values_list("codigo", flat=True)
            }
        except Exception:
            return set()

    if isinstance(permisos, str):
        return {
            item.strip().upper()
            for item in re.split(r"[|,]", permisos)
            if item.strip()
        }

    resultado = set()
    if isinstance(permisos, (list, tuple, set)):
        for permiso in permisos:
            if isinstance(permiso, dict):
                valor = permiso.get("codigo") or permiso.get("permiso") or ""
            else:
                valor = getattr(permiso, "codigo", permiso)

            if str(valor).strip():
                resultado.add(str(valor).strip().upper())

    return resultado


def es_administrador_taller(user):
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True

    if normalizar_texto(getattr(user, "rol", "")) == "administrador":
        return True

    return bool(obtener_permisos_usuario(user) & ADMIN_PERMISSIONS)


class HojaIngresosViewSet(ModelViewSet):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = HojaIngresosSerializer

    # Taller.jsx espera un arreglo directo, no {count, results}.
    pagination_class = None

    def get_permissions(self):
       
        if self.action in ("list", "retrieve", "update", "partial_update"):
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_queryset(self):
        queryset = (
            HojaIngresos.objects
            .select_related("cliente", "taller")
            .all()
            .order_by("-fecha_ingreso", "-id")
        )

        user = self.request.user

        if not getattr(user, "is_authenticated", False):
            # Visitante público (sin login): solo ve VW Córdoba.
            queryset = queryset.filter(agencia__iexact="VW Cordoba")
        elif not es_administrador_taller(user):
            agencias_usuario = obtener_agencias_usuario(user)
            if not agencias_usuario:
                return queryset.none()

            filtro_agencias = Q()
            for agencia_usuario in agencias_usuario:
                filtro_agencias |= Q(agencia__iexact=agencia_usuario)

            queryset = queryset.filter(filtro_agencias)

        params = self.request.query_params

        busqueda = (params.get("q") or "").strip()
        agencia = (params.get("agencia") or "").strip()
        asesor = (params.get("asesor") or "").strip()
        asistencia = (params.get("asistencia") or "").strip().lower()
        desde = (params.get("desde") or "").strip()
        hasta = (params.get("hasta") or "").strip()

        tecnico = (params.get("tecnico") or "").strip()
        fecha = (params.get("fecha") or "").strip()
        etapa = (params.get("etapa") or "").strip()
        estatus_agenda = (params.get("estatus_agenda") or "").strip()
        tipo_bloque = (params.get("tipo_bloque") or "").strip()

        if agencia and agencia not in {"Todos", "Todas"}:
            queryset = queryset.filter(agencia__iexact=agencia)

        if asesor and asesor not in {"Todos", "Todas"}:
            queryset = queryset.filter(asesor__icontains=asesor)

        if asistencia in {"true", "false"}:
            queryset = queryset.filter(asistencia=asistencia == "true")

        if desde:
            queryset = queryset.filter(fecha_ingreso__date__gte=desde)

        if hasta:
            queryset = queryset.filter(fecha_ingreso__date__lte=hasta)

        if tecnico and tecnico not in {"Todos", "Todas"}:
            queryset = queryset.filter(taller__tecnico__iexact=tecnico)

        if fecha:
            queryset = queryset.filter(taller__fecha_programada=fecha)

        if etapa:
            queryset = queryset.filter(taller__etapa__iexact=etapa)

        if estatus_agenda:
            queryset = queryset.filter(
                taller__estatus_agenda__iexact=estatus_agenda
            )

        if tipo_bloque:
            queryset = queryset.filter(taller__tipo_bloque__iexact=tipo_bloque)

        if busqueda:
            queryset = queryset.filter(
                Q(agencia__icontains=busqueda)
                | Q(no_orden__icontains=busqueda)
                | Q(diss__icontains=busqueda)
                | Q(pauta__icontains=busqueda)
                | Q(indicador_resultados__icontains=busqueda)
                | Q(alcance__icontains=busqueda)
                | Q(torre__icontains=busqueda)
                | Q(asesor__icontains=busqueda)
                | Q(agendado_por__icontains=busqueda)
                | Q(nombre_cliente__icontains=busqueda)
                | Q(tipo_cita__icontains=busqueda)
                | Q(declaracion_textual_cliente__icontains=busqueda)
                | Q(comentarios__icontains=busqueda)
                | Q(vin__icontains=busqueda)
                | Q(anio_vehiculo__icontains=busqueda)
                | Q(modelo__icontains=busqueda)
                | Q(medio_concertacion__icontains=busqueda)
                | Q(pauta_origen__icontains=busqueda)
                | Q(cliente__nombre__icontains=busqueda)
                | Q(cliente__telefono__icontains=busqueda)
                | Q(taller__tecnico__icontains=busqueda)
                | Q(taller__etapa__icontains=busqueda)
                | Q(taller__tipo_servicio__icontains=busqueda)
                | Q(taller__comentarios_taller__icontains=busqueda)
            ).distinct()

        return queryset

    def _validar_agencia(self, agencia):
        user = self.request.user

        if not getattr(user, "is_authenticated", False):
            # Visitante público: solo puede modificar VW Córdoba.
            if normalizar_texto(agencia) != normalizar_texto("VW Cordoba"):
                raise PermissionDenied(
                    "No tienes permiso para trabajar con esa agencia."
                )
            return

        if es_administrador_taller(user):
            return

        permitidas = {
            normalizar_texto(item)
            for item in obtener_agencias_usuario(user)
        }

        if not permitidas or normalizar_texto(agencia) not in permitidas:
            raise PermissionDenied(
                "No tienes permiso para trabajar con esa agencia."
            )

    def perform_create(self, serializer):
        agencia = serializer.validated_data.get("agencia", "")
        self._validar_agencia(agencia)
        serializer.save()

    def perform_update(self, serializer):
        agencia = serializer.validated_data.get(
            "agencia",
            serializer.instance.agencia,
        )
        self._validar_agencia(agencia)
        serializer.save()