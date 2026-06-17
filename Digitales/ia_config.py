# Digitales/ia_config.py
from __future__ import annotations

from typing import Any

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from CrmConformidad.jwt_authentication import CRMJWTAuthentication
from citas.models import ClienteComercial, normaliza_tel_mx

from .models import (
    ConfiguracionIAWhatsApp,
    ConversacionIA,
    ExpedienteDigital,
)
from .sett import WHATSAPP_LINES


@api_view(["GET"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def ia_lineas_whatsapp(request):
    configs = {
        item.numero_asesor: item
        for item in ConfiguracionIAWhatsApp.objects.all()
    }

    items = []

    for numero, cfg in WHATSAPP_LINES.items():
        config = configs.get(numero)

        items.append({
            "numero": numero,
            "key": cfg.get("key", ""),
            "label": f"{cfg.get('asesor_digital', 'Sin asesor')} - {cfg.get('agencia', '')}",
            "asesor_digital": cfg.get("asesor_digital", ""),
            "agencia": cfg.get("agencia", ""),
            "business": cfg.get("business", ""),
            "phone_number_id": cfg.get("phone_number_id", ""),
            "ia_configurada": bool(config),
            "ia_activa": bool(config.activo) if config else False,
            "horarios": config.horarios if config else {},
        })

    return Response({
        "ok": True,
        "items": items,
    })

CONDICIONES_FIJAS_DEFAULT = """
[CONDICIONES NO NEGOCIABLES]
- No inventar precios, mensualidades, promociones ni disponibilidad.
- No compartir datos de otros clientes.
- No hablar de marcas fuera del catálogo configurado.
- Si el cliente pide cotización formal, marcar pendiente de cotización y canalizar a asesor.
- Si un asesor humano interviene, pausar la IA.
""".strip()


def _usuario_request(request) -> str:
    user = getattr(request, "user", None)

    if user and getattr(user, "is_authenticated", False):
        return (
            getattr(user, "usuario", "")
            or getattr(user, "username", "")
            or getattr(user, "email", "")
            or ""
        ).strip()

    return (
        request.data.get("usuario", "")
        if hasattr(request, "data")
        else ""
    ).strip()


def _numero_desde_request(request) -> str:
    numero = ""

    try:
        numero = request.data.get("numero_asesor", "")
    except Exception:
        numero = ""

    if not numero:
        numero = request.query_params.get("numero_asesor", "")

    return normaliza_tel_mx(numero)

def _serializar_config(item):
    return {
        "id": item.id,
        "numero_asesor": item.numero_asesor,
        "activo": item.activo,
        "horarios": item.horarios or {},
        "identidad": item.identidad or "",
        "precios": item.precios or "",
        "perfilamiento": item.perfilamiento or "",
        "limites": item.limites or "",
        "personalidad": item.personalidad or "",
        "condiciones_fijas": item.condiciones_fijas or "",
        "actualizado_por": item.actualizado_por or "",
    }

def _get_or_create_config(numero_asesor: str) -> ConfiguracionIAWhatsApp:
    numero_asesor = normaliza_tel_mx(numero_asesor)

    item, _ = ConfiguracionIAWhatsApp.objects.get_or_create(
        numero_asesor=numero_asesor,
        defaults={
            "activo": False,
            "horarios": {},
            "condiciones_fijas": CONDICIONES_FIJAS_DEFAULT,
        },
    )

    return item


def _aplicar_payload_config(
    item: ConfiguracionIAWhatsApp,
    data: dict[str, Any],
    actualizado_por: str = "",
) -> ConfiguracionIAWhatsApp:
    campos_texto = [
        "identidad",
        "precios",
        "perfilamiento",
        "limites",
        "personalidad",
        "condiciones_fijas",
    ]

    for campo in campos_texto:
        if campo in data:
            setattr(item, campo, str(data.get(campo) or ""))

    if "activo" in data:
        item.activo = bool(data.get("activo"))

    if "horarios" in data:
        horarios = data.get("horarios")
        item.horarios = horarios if isinstance(horarios, dict) else {}

    if actualizado_por:
        item.actualizado_por = actualizado_por

    return item


@api_view(["GET", "POST"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def ia_config_list(request):
    if request.method == "GET":
        qs = ConfiguracionIAWhatsApp.objects.all().order_by("numero_asesor")

        return Response(
            {
                "ok": True,
                "items": [_serializar_config(item) for item in qs],
            },
            status=status.HTTP_200_OK,
        )

    numero_asesor = normaliza_tel_mx(request.data.get("numero_asesor", ""))

    if not numero_asesor:
        return Response(
            {
                "ok": False,
                "error": "Falta numero_asesor.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    item = _get_or_create_config(numero_asesor)
    item = _aplicar_payload_config(
        item,
        request.data or {},
        actualizado_por=_usuario_request(request),
    )
    item.save()

    return Response(
        {
            "ok": True,
            "item": _serializar_config(item),
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET", "PATCH", "PUT"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def ia_config_detail(request, numero_asesor: str):
    numero_asesor = normaliza_tel_mx(numero_asesor)

    if not numero_asesor:
        return Response(
            {
                "ok": False,
                "error": "Número de asesor inválido.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    item = _get_or_create_config(numero_asesor)

    if request.method == "GET":
        return Response(
            {
                "ok": True,
                "item": _serializar_config(item),
            },
            status=status.HTTP_200_OK,
        )

    item = _aplicar_payload_config(
        item,
        request.data or {},
        actualizado_por=_usuario_request(request),
    )
    item.save()

    return Response(
        {
            "ok": True,
            "item": _serializar_config(item),
        },
        status=status.HTTP_200_OK,
    )

@api_view(["POST"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def ia_config_publicar(request, numero_asesor: str):
    numero_asesor = normaliza_tel_mx(numero_asesor)

    if not numero_asesor:
        return Response(
            {"ok": False, "error": "Número de asesor inválido."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    item = _get_or_create_config(numero_asesor)
    item.activo = True
    item.actualizado_por = _usuario_request(request)
    item.save(update_fields=["activo", "actualizado_por"])

    return Response({
        "ok": True,
        "item": _serializar_config(item),
    })

def _obtener_expediente_por_tel(tel: str):
    tel = normaliza_tel_mx(tel)

    if not tel:
        return None

    cliente = ClienteComercial.objects.filter(telefono=tel).first()

    if not cliente:
        return None

    return ExpedienteDigital.objects.filter(cliente=cliente).first()


@api_view(["POST"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def ia_pausar_conversacion(request):
    tel = normaliza_tel_mx(request.data.get("tel", ""))
    numero_asesor = _numero_desde_request(request)
    motivo = (request.data.get("motivo") or "manual").strip()[:120]

    if not tel:
        return Response(
            {
                "ok": False,
                "error": "Falta tel.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not numero_asesor:
        return Response(
            {
                "ok": False,
                "error": "Falta numero_asesor.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    expediente = _obtener_expediente_por_tel(tel)

    if not expediente:
        return Response(
            {
                "ok": False,
                "error": "No existe expediente para ese teléfono.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    expediente.ia_pausada = True
    expediente.ia_pausada_motivo = motivo
    expediente.ia_pausada_at = timezone.now()
    expediente.save(
        update_fields=[
            "ia_pausada",
            "ia_pausada_motivo",
            "ia_pausada_at",
            "actualizado",
        ]
    )

    conversacion, _ = ConversacionIA.objects.get_or_create(
        expediente=expediente,
        numero_asesor=numero_asesor,
    )
    conversacion.ia_activa = False
    conversacion.ia_pausada = True
    conversacion.motivo_pausa = motivo
    conversacion.estado_conversacion = "pausada"
    conversacion.save(
        update_fields=[
            "ia_activa",
            "ia_pausada",
            "motivo_pausa",
            "estado_conversacion",
        ]
    )

    return Response(
        {
            "ok": True,
            "mensaje": "IA pausada correctamente.",
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def ia_reactivar_conversacion(request):
    tel = normaliza_tel_mx(request.data.get("tel", ""))
    numero_asesor = _numero_desde_request(request)

    if not tel:
        return Response(
            {
                "ok": False,
                "error": "Falta tel.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not numero_asesor:
        return Response(
            {
                "ok": False,
                "error": "Falta numero_asesor.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    expediente = _obtener_expediente_por_tel(tel)

    if not expediente:
        return Response(
            {
                "ok": False,
                "error": "No existe expediente para ese teléfono.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    expediente.ia_pausada = False
    expediente.ia_pausada_motivo = ""
    expediente.ia_pausada_at = None
    expediente.save(
        update_fields=[
            "ia_pausada",
            "ia_pausada_motivo",
            "ia_pausada_at",
        ]
    )

    conversacion, _ = ConversacionIA.objects.get_or_create(
        expediente=expediente,
        numero_asesor=numero_asesor,
    )
    conversacion.ia_activa = True
    conversacion.ia_pausada = False
    conversacion.motivo_pausa = ""
    conversacion.estado_conversacion = "informando"
    conversacion.save(
        update_fields=[
            "ia_activa",
            "ia_pausada",
            "motivo_pausa",
            "estado_conversacion",
        ]
    )

    return Response(
        {
            "ok": True,
            "mensaje": "IA reactivada correctamente.",
        },
        status=status.HTTP_200_OK,
    )