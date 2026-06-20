# Digitales/ia_config.py
from __future__ import annotations

from typing import Any
from datetime import timedelta

from django.conf import settings
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

IA_CONFIG_GLOBAL_KEY = "GLOBAL"

def _normalizar_numero_config_ia(value: str, permitir_global: bool = True) -> str:
    raw = str(value or "").strip()

    if permitir_global and raw.upper() in ("GLOBAL", "TODOS", "ALL", "*"):
        return IA_CONFIG_GLOBAL_KEY

    return normaliza_tel_mx(raw)


def obtener_config_ia_para_numero(numero_asesor: str):
    numero_asesor = normaliza_tel_mx(numero_asesor or "")

    config_especifica = None

    if numero_asesor:
        config_especifica = ConfiguracionIAWhatsApp.objects.filter(
            numero_asesor=numero_asesor,
        ).first()

    if config_especifica:
        return config_especifica, "especifica"

    config_global = ConfiguracionIAWhatsApp.objects.filter(
        numero_asesor=IA_CONFIG_GLOBAL_KEY,
    ).first()

    if config_global:
        return config_global, "global"

    return None, ""

def _parse_hora_ia(value):
    try:
        return timezone.datetime.strptime(str(value or "").strip(), "%H:%M").time()
    except Exception:
        return None


def _aware_datetime_ia(fecha, hora):
    dt = timezone.datetime.combine(fecha, hora)

    if settings.USE_TZ and timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())

    return dt


def _ia_esta_en_horario(horarios: dict) -> bool:
    if not isinstance(horarios, dict) or not horarios:
        return True

    dias = ["lun", "mar", "mie", "jue", "vie", "sab", "dom"]
    ahora = timezone.now()

    if settings.USE_TZ and timezone.is_aware(ahora):
        ahora = timezone.localtime(ahora)

    hoy_idx = ahora.weekday()

    for inicio_idx, dia_key in enumerate(dias):
        config_dia = horarios.get(dia_key) or {}

        if not config_dia.get("activo", False):
            continue

        hora_inicio = _parse_hora_ia(config_dia.get("inicio"))
        hora_fin = _parse_hora_ia(config_dia.get("fin"))

        if not hora_inicio or not hora_fin:
            continue

        hasta_dia = config_dia.get("hastaDia")
        hasta_idx = dias.index(hasta_dia) if hasta_dia in dias else None
        base_delta = inicio_idx - hoy_idx

        for semana_offset in (0, -7):
            fecha_inicio = ahora.date() + timedelta(days=base_delta + semana_offset)

            if hasta_idx is not None:
                dias_duracion = (hasta_idx - inicio_idx) % 7
                fecha_fin = fecha_inicio + timedelta(days=dias_duracion)
            else:
                fecha_fin = fecha_inicio
                if hora_fin <= hora_inicio:
                    fecha_fin = fecha_fin + timedelta(days=1)

            inicio_dt = _aware_datetime_ia(fecha_inicio, hora_inicio)
            fin_dt = _aware_datetime_ia(fecha_fin, hora_fin)

            if inicio_dt <= ahora <= fin_dt:
                return True

    return False


def obtener_estado_ia_conversacion(*, numero_asesor: str, tel: str = "", expediente=None) -> dict[str, Any]:
    numero_asesor = normaliza_tel_mx(numero_asesor or "")
    tel = normaliza_tel_mx(tel or "")

    config, config_origen = obtener_config_ia_para_numero(numero_asesor)
    if expediente is None and tel:
        expediente = _obtener_expediente_por_tel(tel)

    conversacion = None
    if expediente and numero_asesor:
        conversacion = ConversacionIA.objects.filter(
            expediente=expediente,
            numero_asesor=numero_asesor,
        ).first()

    en_horario = _ia_esta_en_horario(config.horarios if config else {}) if config else False
    bloqueos: list[str] = []

    if not numero_asesor:
        bloqueos.append("numero_asesor_invalido")

    if not config:
        bloqueos.append("configuracion_ia_no_existe")
    else:
        if not config.activo:
            bloqueos.append("configuracion_ia_inactiva")
        if not en_horario:
            bloqueos.append("fuera_de_horario")

    if not expediente:
        bloqueos.append("expediente_no_encontrado")
    else:
        if expediente.ia_pausada:
            bloqueos.append("expediente_ia_pausada")

    if conversacion:
        if not conversacion.ia_activa:
            bloqueos.append("conversacion_ia_inactiva")
        if conversacion.ia_pausada:
            bloqueos.append("conversacion_ia_pausada")

    return {
        "numero_asesor": numero_asesor,
        "telefono": tel or (expediente.cliente.telefono if expediente and expediente.cliente_id else ""),
        "puede_responder": len(bloqueos) == 0,
        "bloqueos": bloqueos,
        "hora_servidor": timezone.now().isoformat(),
        "timezone": str(getattr(settings, "TIME_ZONE", "")),
        "use_tz": bool(getattr(settings, "USE_TZ", False)),
        "configuracion": {
            "existe": bool(config),
            "activo": bool(config.activo) if config else False,
            "en_horario": en_horario,
            "horarios": config.horarios if config else {},
            "origen": config_origen,
            "numero_config": config.numero_asesor if config else "",
        },
        "expediente": {
            "existe": bool(expediente),
            "id": expediente.id if expediente else None,
            "estado": expediente.estado if expediente else "",
            "ia_pausada": bool(expediente.ia_pausada) if expediente else False,
            "ia_pausada_motivo": expediente.ia_pausada_motivo if expediente else "",
            "ia_pausada_at": expediente.ia_pausada_at.isoformat() if expediente and expediente.ia_pausada_at else None,
            "requiere_asesor": bool(expediente.requiere_asesor) if expediente else False,
            "motivo_requiere_asesor": expediente.motivo_requiere_asesor if expediente else "",
            "cotizacion_pendiente": bool(expediente.cotizacion_pendiente) if expediente else False,
            "cotizacion_solicitada_at": expediente.cotizacion_solicitada_at.isoformat() if expediente and expediente.cotizacion_solicitada_at else None,
        },
        "conversacion": {
            "existe": bool(conversacion),
            "ia_activa": bool(conversacion.ia_activa) if conversacion else True,
            "ia_pausada": bool(conversacion.ia_pausada) if conversacion else False,
            "motivo_pausa": conversacion.motivo_pausa if conversacion else "",
            "estado_conversacion": conversacion.estado_conversacion if conversacion else "sin_iniciar",
            "ultima_intencion": conversacion.ultima_intencion if conversacion else "",
            "ultimo_modelo_mencionado": conversacion.ultimo_modelo_mencionado if conversacion else "",
            "pregunta_pendiente": conversacion.pregunta_pendiente if conversacion else "",
        },
    }


@api_view(["GET"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def ia_lineas_whatsapp(request):
    configs = {
        item.numero_asesor: item
        for item in ConfiguracionIAWhatsApp.objects.all()
    }
    config_global = configs.get(IA_CONFIG_GLOBAL_KEY)

    items = []

    for numero, cfg in WHATSAPP_LINES.items():
        config = configs.get(numero) or config_global
        config_origen = "especifica" if configs.get(numero) else ("global" if config_global else "")
        en_horario = _ia_esta_en_horario(config.horarios if config else {}) if config else False
        bloqueos = []

        if not config:
            bloqueos.append("configuracion_ia_no_existe")
        elif not config.activo:
            bloqueos.append("configuracion_ia_inactiva")
        elif not en_horario:
            bloqueos.append("fuera_de_horario")

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
            "en_horario": en_horario,
            "puede_responder_linea": bool(config and config.activo and en_horario),
            "bloqueos_linea": bloqueos,
            "horarios": config.horarios if config else {},
            "config_origen": config_origen,
            "numero_config": config.numero_asesor if config else "",
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
- La IA solo debe pausarse cuando un asesor lo haga manualmente desde el CRM.
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
        "promociones_eventos": item.promociones_eventos or "",
        "actualizado_por": item.actualizado_por or "",
    }

def _get_or_create_config(numero_asesor: str) -> ConfiguracionIAWhatsApp:
    numero_asesor = _normalizar_numero_config_ia(numero_asesor)

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
        "promociones_eventos",
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

    numero_asesor = _normalizar_numero_config_ia(request.data.get("numero_asesor", "GLOBAL"))

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
    numero_asesor = _normalizar_numero_config_ia(numero_asesor)

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
    numero_asesor = _normalizar_numero_config_ia(numero_asesor)

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


@api_view(["GET"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def ia_estado_conversacion(request):
    tel = normaliza_tel_mx(request.query_params.get("tel", ""))
    numero_asesor = _numero_desde_request(request)

    if not tel:
        return Response(
            {"ok": False, "error": "Falta tel."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not numero_asesor:
        return Response(
            {"ok": False, "error": "Falta numero_asesor."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(
        {
            "ok": True,
            "estado_ia": obtener_estado_ia_conversacion(
                tel=tel,
                numero_asesor=numero_asesor,
            ),
        },
        status=status.HTTP_200_OK,
    )


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
            "estado_ia": obtener_estado_ia_conversacion(
                tel=tel,
                numero_asesor=numero_asesor,
            ),
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
            "actualizado",
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
            "estado_ia": obtener_estado_ia_conversacion(
                tel=tel,
                numero_asesor=numero_asesor,
            ),
        },
        status=status.HTTP_200_OK,
    )