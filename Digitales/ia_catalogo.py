#Volkswagen
# Digitales/ia_catalogo.py
from __future__ import annotations

from typing import Any

import logging
import os
from django.core.files.base import ContentFile

from django.core.exceptions import ValidationError
from django.db import IntegrityError, DatabaseError
from django.utils.dateparse import parse_date
from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.utils.text import slugify as django_slugify
from django.core.files.storage import default_storage
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.decorators import parser_classes

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
        "url_ficha_tecnica": item.url_ficha_tecnica,
        "ficha_tecnica_thumbnail": item.ficha_tecnica_thumbnail,
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

@api_view(["GET", "POST"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def catalogo_vehiculos_list(request):
    if request.method == "GET":
        modelo = (request.query_params.get("modelo") or "").strip()
        marca = (request.query_params.get("marca") or "").strip()
        activo_param = request.query_params.get("activo", "true").strip().lower()

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

    try:
        item = _aplicar_payload_vehiculo(item, data)
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
    except (ValueError, TypeError, ValidationError) as exc:
        logger.exception(
            "ERROR VALIDANDO CATÁLOGO VEHÍCULO CREATE | payload=%s | error=%s",
            dict(data),
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
            "ERROR DB CATÁLOGO VEHÍCULO CREATE | payload=%s | error=%s",
            dict(data),
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
            "ERROR GENERAL CATÁLOGO VEHÍCULO CREATE | payload=%s | error=%s",
            dict(data),
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
def _slug_vehiculo(modelo: str, ano) -> str:
    base = django_slugify(str(modelo or "").strip()).replace("-", "_") or "vehiculo"
    ano_txt = str(ano or "").strip()
    return f"{base}_{ano_txt}" if ano_txt else base


def _guardar_archivo_catalogo(file_obj, *, slug: str, subcarpeta: str) -> str:
    original_name = getattr(file_obj, "name", "archivo") or "archivo"
    nombre_limpio = original_name.replace(" ", "_")
    path = f"catalogo/{slug}/{subcarpeta}/{nombre_limpio}"

    try:
        file_obj.seek(0)
    except Exception:
        pass

    # default_storage.save agrega un sufijo aleatorio si ya existe ese nombre,
    # así que nunca pisa un archivo existente.
    return default_storage.save(path, file_obj)
 
def _generar_thumbnail_pdf(saved_pdf_path: str, *, slug: str) -> str:
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.warning("PyMuPDF no instalado, no se genera miniatura de PDF.")
        return ""

    try:
        with default_storage.open(saved_pdf_path, "rb") as f:
            pdf_bytes = f.read()

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=fitz.Matrix(0.6, 0.6))
        png_bytes = pix.tobytes("png")
        doc.close()

        base_name = os.path.splitext(os.path.basename(saved_pdf_path))[0]
        thumb_path = f"catalogo/{slug}/ficha/{base_name}_thumb.png"

        return default_storage.save(thumb_path, ContentFile(png_bytes))
    except Exception as exc:
        logger.warning("NO SE PUDO GENERAR MINIATURA PDF | path=%s error=%s", saved_pdf_path, str(exc))
        return "" 

@api_view(["POST"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def catalogo_vehiculo_upload_media(request, vehiculo_id: int):
    item = CatalogoVehiculos.objects.filter(id=vehiculo_id).first()

    if not item:
        return Response({"ok": False, "error": "Vehículo no encontrado."}, status=status.HTTP_404_NOT_FOUND)

    tipo = str(request.data.get("tipo") or "").strip().lower()

    if tipo not in ("ficha", "imagenes", "videos"):
        return Response(
            {"ok": False, "error": "tipo debe ser 'ficha', 'imagenes' o 'videos'."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not item.modelo or not item.ano:
        return Response(
            {"ok": False, "error": "Guarda modelo y año del vehículo antes de subir archivos."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    files = request.FILES.getlist("files")

    if not files:
        return Response({"ok": False, "error": "Faltan archivos."}, status=status.HTTP_400_BAD_REQUEST)

    slug = _slug_vehiculo(item.modelo, item.ano)

    try:
        if tipo == "ficha":
            saved_path = _guardar_archivo_catalogo(files[0], slug=slug, subcarpeta="ficha")

            thumb_anterior = item.ficha_tecnica_thumbnail
            if thumb_anterior:
                try:
                    if default_storage.exists(thumb_anterior):
                        default_storage.delete(thumb_anterior)
                except Exception:
                    pass

            item.url_ficha_tecnica = saved_path
            item.ficha_tecnica_thumbnail = _generar_thumbnail_pdf(saved_path, slug=slug)

            item.save(update_fields=["url_ficha_tecnica", "ficha_tecnica_thumbnail"])

        elif tipo == "imagenes":
            actuales = list(item.imagenes or [])
            for f in files:
                actuales.append(_guardar_archivo_catalogo(f, slug=slug, subcarpeta="imagenes"))
            item.imagenes = actuales
            item.save(update_fields=["imagenes"])

        else:  # videos
            actuales = list(item.videos or [])
            for f in files:
                actuales.append(_guardar_archivo_catalogo(f, slug=slug, subcarpeta="videos"))
            item.videos = actuales
            item.save(update_fields=["videos"])

    except Exception as exc:
        logger.exception(
            "ERROR SUBIENDO MEDIA CATALOGO | vehiculo_id=%s tipo=%s error=%s",
            vehiculo_id, tipo, str(exc),
        )
        return Response(
            {"ok": False, "error": "No se pudo guardar el archivo.", "detalle": str(exc)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response({"ok": True, "item": _serializar_vehiculo(item)}, status=status.HTTP_200_OK)

@api_view(["DELETE"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def catalogo_vehiculo_eliminar_media(request, vehiculo_id: int):
    item = CatalogoVehiculos.objects.filter(id=vehiculo_id).first()

    if not item:
        return Response({"ok": False, "error": "Vehículo no encontrado."}, status=status.HTTP_404_NOT_FOUND)

    tipo = str(request.query_params.get("tipo") or "").strip().lower()
    ruta = str(request.query_params.get("ruta") or "").strip()

    if tipo not in ("ficha", "imagenes", "videos") or not ruta:
        return Response(
            {"ok": False, "error": "Faltan parámetros tipo y ruta."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if tipo == "ficha":
        if item.url_ficha_tecnica == ruta:
            thumb_a_borrar = item.ficha_tecnica_thumbnail
            item.url_ficha_tecnica = ""
            item.ficha_tecnica_thumbnail = ""
            item.save(update_fields=["url_ficha_tecnica", "ficha_tecnica_thumbnail"])

            if thumb_a_borrar:
                try:
                    if default_storage.exists(thumb_a_borrar):
                        default_storage.delete(thumb_a_borrar)
                except Exception:
                    pass
    elif tipo == "imagenes":
        item.imagenes = [x for x in (item.imagenes or []) if x != ruta]
        item.save(update_fields=["imagenes"])
    else:
        item.videos = [x for x in (item.videos or []) if x != ruta]
        item.save(update_fields=["videos"])

    try:
        if default_storage.exists(ruta):
            default_storage.delete(ruta)
    except Exception as exc:
        logger.warning("NO SE PUDO BORRAR ARCHIVO FISICO | ruta=%s error=%s", ruta, str(exc))

    return Response({"ok": True, "item": _serializar_vehiculo(item)}, status=status.HTTP_200_OK)        