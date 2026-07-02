#Volkswagen
# Digitales/ia_catalogo.py
from __future__ import annotations

from typing import Any

from django.db import IntegrityError
from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from CrmConformidad.jwt_authentication import CRMJWTAuthentication

from .models import CatalogoVehiculos


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
        "videos": item.videos,
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
        if ano:
            item.ano = ano

    for campo in ["precio_lista", "precio_contado", "precio_financiado"]:
        if campo in data:
            setattr(item, campo, _int_o_none(data.get(campo)))

    if "ficha_tecnica" in data:
        ficha = data.get("ficha_tecnica")
        item.ficha_tecnica = ficha if isinstance(ficha, dict) else {}

    if "imagenes" in data:
        imagenes = data.get("imagenes")
        item.imagenes = imagenes if isinstance(imagenes, list) else []
    
    if "videos" in data:
        videos = data.get("videos")
        item.videos = videos if isinstance(videos, list) else []

    if "ultima_actualizacion" in data:
        item.ultima_actualizacion = data.get("ultima_actualizacion") or None

    if "activo" in data:
        item.activo = bool(data.get("activo"))

    return item


@api_view(["GET", "POST"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def catalogo_vehiculos_list(request):
    if request.method == "GET":
        modelo = (request.query_params.get("modelo") or "").strip()
        marca = (request.query_params.get("marca") or "").strip()
        activo_param = request.query_params.get("activo", "true").strip().lower()
        
        activo = activo_param not in ("0", "false", "no", "inactivo")

        try:
            limite = int(request.query_params.get("limit", 300))
        except (TypeError, ValueError):
            limite = 300

        limite = max(1, min(limite, 1000))

        qs = CatalogoVehiculos.objects.all()
        
        if activo_param not in ("todos", "all", "*", ""):
            activo = activo_param not in ("0", "false", "no", "inactivo")
            qs = qs.filter(activo=activo)

        if modelo:
            qs = qs.filter(modelo__icontains=modelo)

        if marca:
            qs = qs.filter(marca__icontains=marca)

        qs = qs.order_by("marca", "modelo", "ano", "version")[:limite]

        return Response({
            "ok": True,
            "items": [_serializar_vehiculo(item) for item in qs],
        })

    data = request.data or {}

    if not str(data.get("modelo") or "").strip():
        return Response(
            {"ok": False, "error": "Falta modelo."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not str(data.get("ano") or "").strip():
        return Response(
            {"ok": False, "error": "Falta año."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    item = CatalogoVehiculos()
    item.marca = "Volkswagen"
    item.modelo = ""
    item.ano = int(data.get("ano"))

    item = _aplicar_payload_vehiculo(item, data)

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

    return Response(
        {
            "ok": True,
            "item": _serializar_vehiculo(item),
        },
        status=status.HTTP_201_CREATED,
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