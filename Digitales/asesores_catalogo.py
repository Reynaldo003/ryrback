import hashlib
import json
import logging
import time

from django.core.cache import cache
from django.db import transaction
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from CrmConformidad.permissions import IsAdminRole
from .models import Asesor

logger = logging.getLogger(__name__)
CACHE_VERSION_KEY = "digitales:asesores:version"
CACHE_TTL_SEGUNDOS = 300


def _clave_cache_asesores(filtros):
    try:
        version = str(cache.get(CACHE_VERSION_KEY) or "1")
    except Exception:
        logger.warning("No se pudo consultar la versión de caché de asesores", exc_info=True)
        return None
    filtros_json = json.dumps(filtros, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(filtros_json.encode("utf-8")).hexdigest()[:24]
    return f"digitales:asesores:list:{version}:{digest}"


def _invalidar_cache_asesores():
    try:
        cache.set(CACHE_VERSION_KEY, str(time.time_ns()), timeout=None)
    except Exception:
        # Una falla de Redis no debe revertir una creación/edición exitosa.
        logger.warning("No se pudo invalidar la caché de asesores", exc_info=True)


class AsesorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Asesor
        fields = ["id", "nombre", "telefono", "tipo_asesor", "area", "agencia", "activo", "creado", "actualizado"]
        read_only_fields = ["id", "creado", "actualizado"]

    def validate_nombre(self, value):
        nombre = str(value or "").strip()
        if not nombre:
            raise serializers.ValidationError("El nombre del asesor es obligatorio.")
        return nombre

    def validate_telefono(self, value):
        return str(value or "").strip()

    def validate_tipo_asesor(self, value):
        return str(value or "").strip()

    def validate_area(self, value):
        return str(value or "").strip()

    def validate_agencia(self, value):
        return str(value or "").strip()


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def asesores_list(request):
    activo = str(request.query_params.get("activo", "true")).strip().lower()
    tipo_asesor = str(request.query_params.get("tipo_asesor", "")).strip()
    area = str(request.query_params.get("area", "")).strip()
    agencia = str(request.query_params.get("agencia", "")).strip()

    filtros = {"activo": activo, "tipo_asesor": tipo_asesor.casefold(), "area": area.casefold(), "agencia": agencia.casefold()}
    clave = _clave_cache_asesores(filtros)
    if clave:
        try:
            datos_cache = cache.get(clave)
            if datos_cache is not None:
                return Response(datos_cache)
        except Exception:
            logger.warning("No se pudo leer la caché de asesores", exc_info=True)

    queryset = Asesor.objects.all()
    if activo in {"true", "1", "si", "sí"}:
        queryset = queryset.filter(activo=True)
    elif activo in {"false", "0", "no"}:
        queryset = queryset.filter(activo=False)
    if tipo_asesor:
        queryset = queryset.filter(tipo_asesor__iexact=tipo_asesor)
    if area:
        queryset = queryset.filter(area__iexact=area)
    if agencia:
        queryset = queryset.filter(agencia__iexact=agencia)

    datos = [dict(registro) for registro in AsesorSerializer(queryset, many=True).data]
    if clave:
        try:
            cache.set(clave, datos, timeout=CACHE_TTL_SEGUNDOS)
        except Exception:
            logger.warning("No se pudo escribir la caché de asesores", exc_info=True)
    return Response(datos)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated, IsAdminRole])
def asesores_admin_list_create(request):
    if request.method == "GET":
        queryset = Asesor.objects.all()
        return Response(AsesorSerializer(queryset, many=True).data)

    serializer = AsesorSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    asesor = serializer.save()
    transaction.on_commit(_invalidar_cache_asesores)
    return Response(AsesorSerializer(asesor).data, status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH", "PUT"])
@permission_classes([IsAuthenticated, IsAdminRole])
def asesor_admin_detail(request, asesor_id):
    try:
        asesor = Asesor.objects.get(pk=asesor_id)
    except Asesor.DoesNotExist:
        return Response({"detail": "Asesor no encontrado."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        return Response(AsesorSerializer(asesor).data)

    serializer = AsesorSerializer(asesor, data=request.data, partial=request.method == "PATCH")
    serializer.is_valid(raise_exception=True)
    asesor = serializer.save()
    transaction.on_commit(_invalidar_cache_asesores)
    return Response(AsesorSerializer(asesor).data)
