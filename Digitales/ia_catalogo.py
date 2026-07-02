#Volkswagen
# Digitales/ia_catalogo.py
from __future__ import annotations

from typing import Any

import logging

from django.core.exceptions import ValidationError
from django.db import IntegrityError, DatabaseError
from django.utils.dateparse import parse_date
from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from CrmConformidad.jwt_authentication import CRMJWTAuthentication

from .models import CatalogoVehiculos

logger = logging.getLogger(__name__)

def _int_o_none(valor):
    if valor in (None, ""):
        return None

    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _serializar_vehiculo(item: CatalogoVehiculos) -> dict[str, Any]:
    return {
        "id": item.id,
        "marca": item.marca,
        "modelo": item.modelo,
        "ano": item.ano,
        "version": item.version,
        "precio_lista": item.precio_lista,
        "precio_contado": item.precio_contado,
        "precio_financiado": item.precio_financiado,
        "resumen": item.resumen,
        "ficha_tecnica": item.ficha_tecnica,
        "url_ficha_tecnica": item.url_ficha_tecnica,
        "imagenes": item.imagenes,
        "videos": getattr(item, "videos", []) or [],
        "ultima_actualizacion": item.ultima_actualizacion.isoformat() if item.ultima_actualizacion else None,
        "activo": item.activo,
        "creado": item.creado.isoformat() if item.creado else None,
    }


def obtener_catalogo_activo_para_ia(limite: int = 80) -> list[dict[str, Any]]:
    qs = (
        CatalogoVehiculos.objects
        .filter(activo=True)
        .order_by("modelo", "ano", "version")[:limite]
    )

    return [_serializar_vehiculo(item) for item in qs]


def buscar_vehiculos_para_ia(texto: str, limite: int = 10) -> list[dict[str, Any]]:
    texto = (texto or "").strip()

    if not texto:
        return []

    qs = (
        CatalogoVehiculos.objects
        .filter(activo=True)
        .filter(
            Q(modelo__icontains=texto)
            | Q(version__icontains=texto)
            | Q(marca__icontains=texto)
        )
        .order_by("modelo", "ano", "version")[:limite]
    )

    return [_serializar_vehiculo(item) for item in qs]


def _lista_texto_o_vacia(valor) -> list[str]:
    if valor in (None, ""):
        return []

    if isinstance(valor, list):
        return [
            str(item or "").strip()
            for item in valor
            if str(item or "").strip()
        ]

    if isinstance(valor, str):
        return [
            linea.strip()
            for linea in valor.splitlines()
            if linea.strip()
        ]

    return []


def _fecha_o_none(valor):
    if valor in (None, ""):
        return None

    if hasattr(valor, "year") and hasattr(valor, "month") and hasattr(valor, "day"):
        return valor

    texto = str(valor or "").strip()

    # Soporta valores tipo "2026-07-02" o "2026-07-02T00:00:00"
    fecha = parse_date(texto[:10])

    if not fecha:
        raise ValueError("ultima_actualizacion debe tener formato YYYY-MM-DD.")

    return fecha


def _aplicar_payload_vehiculo(item: CatalogoVehiculos, data: dict[str, Any]) -> CatalogoVehiculos:
    campos_texto = [
        "marca",
        "modelo",
        "version",
        "resumen",
        "url_ficha_tecnica",
    ]

    for campo in campos_texto:
        if campo in data:
            setattr(item, campo, str(data.get(campo) or "").strip())

    if "ano" in data:
        ano = _int_o_none(data.get("ano"))

        if not ano:
            raise ValueError("El año es obligatorio y debe ser numérico.")

        item.ano = ano

    for campo in ["precio_lista", "precio_contado", "precio_financiado"]:
        if campo in data:
            setattr(item, campo, _int_o_none(data.get(campo)))

    if "ficha_tecnica" in data:
        ficha = data.get("ficha_tecnica")

        if ficha in (None, ""):
            item.ficha_tecnica = {}
        elif isinstance(ficha, dict):
            item.ficha_tecnica = ficha
        else:
            raise ValueError("ficha_tecnica debe ser un objeto JSON válido.")

    if "imagenes" in data:
        item.imagenes = _lista_texto_o_vacia(data.get("imagenes"))

    if "videos" in data:
        if not hasattr(item, "videos"):
            raise ValueError("El modelo CatalogoVehiculos todavía no tiene el campo videos cargado en runtime.")

        item.videos = _lista_texto_o_vacia(data.get("videos"))

    if "ultima_actualizacion" in data:
        item.ultima_actualizacion = _fecha_o_none(data.get("ultima_actualizacion"))

    if "activo" in data:
        item.activo = bool(data.get("activo"))

    return item

@api_view(["GET", "PATCH", "PUT", "DELETE"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def catalogo_vehiculo_detail(request, vehiculo_id: int):
    try:
        item = CatalogoVehiculos.objects.filter(id=vehiculo_id).first()

        if not item:
            return Response(
                {
                    "ok": False,
                    "error": "Vehículo no encontrado.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if request.method == "GET":
            return Response({
                "ok": True,
                "item": _serializar_vehiculo(item),
            })

        if request.method in ("PATCH", "PUT"):
            item = _aplicar_payload_vehiculo(item, request.data or {})

            try:
                item.full_clean()
                item.save()
            except IntegrityError:
                return Response(
                    {
                        "ok": False,
                        "error": "Ya existe un vehículo con la misma marca, modelo, año y versión.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return Response({
                "ok": True,
                "item": _serializar_vehiculo(item),
            })

        item.activo = False
        item.save(update_fields=["activo"])

        return Response({
            "ok": True,
            "mensaje": "Vehículo desactivado correctamente.",
        })

    except (ValueError, TypeError, ValidationError) as exc:
        logger.exception(
            "ERROR VALIDANDO CATÁLOGO VEHÍCULO | id=%s | payload=%s | error=%s",
            vehiculo_id,
            dict(request.data or {}),
            str(exc),
        )

        return Response(
            {
                "ok": False,
                "error": str(exc),
                "tipo": exc.__class__.__name__,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    except DatabaseError as exc:
        logger.exception(
            "ERROR DB CATÁLOGO VEHÍCULO | id=%s | payload=%s | error=%s",
            vehiculo_id,
            dict(request.data or {}),
            str(exc),
        )

        return Response(
            {
                "ok": False,
                "error": "Error de base de datos al guardar el vehículo.",
                "detalle": str(exc),
                "tipo": exc.__class__.__name__,
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    except Exception as exc:
        logger.exception(
            "ERROR GENERAL CATÁLOGO VEHÍCULO | id=%s | payload=%s | error=%s",
            vehiculo_id,
            dict(request.data or {}),
            str(exc),
        )

        return Response(
            {
                "ok": False,
                "error": "Error inesperado al guardar el vehículo.",
                "detalle": str(exc),
                "tipo": exc.__class__.__name__,
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

@api_view(["GET", "PATCH", "PUT", "DELETE"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def catalogo_vehiculo_detail(request, vehiculo_id: int):
    item = CatalogoVehiculos.objects.filter(id=vehiculo_id).first()

    if not item:
        return Response(
            {"ok": False, "error": "Vehículo no encontrado."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "GET":
        return Response({
            "ok": True,
            "item": _serializar_vehiculo(item),
        })

    if request.method in ("PATCH", "PUT"):
        item = _aplicar_payload_vehiculo(item, request.data or {})

        try:
            item.save()
        except IntegrityError:
            return Response(
                {
                    "ok": False,
                    "error": "Ya existe un vehículo con la misma marca, modelo, año y versión.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({
            "ok": True,
            "item": _serializar_vehiculo(item),
        })

    item.activo = False
    item.save(update_fields=["activo"])

    return Response({
        "ok": True,
        "mensaje": "Vehículo desactivado correctamente.",
    })