from __future__ import annotations

import re
from bisect import bisect_left
from datetime import datetime, time, timedelta
from statistics import median
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Max, OuterRef, Q, Subquery
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from CrmConformidad.jwt_authentication import CRMJWTAuthentication
from citas.models import normaliza_tel_mx

from .models import (
    BitacoraAsesorDigital,
    ConfiguracionIAWhatsApp,
    ConversacionIA,
    ExpedienteDigital,
    MensajeWhatsApp,
)
from .resumen_ia import generar_resumen_atencion_con_gemini
from .sett import WHATSAPP_LINES

HORAS_SIN_RESPUESTA = 48

TIPO_MENSAJE = "mensaje"
TIPO_PLANTILLA = "plantilla"
TIPO_MEDIA = "media"
TIPO_ACTUALIZACION = "actualizacion"
TIPO_BLOQUEO = "bloqueo"
TIPO_LLAMADA = "llamada"
TIPO_IA = "ia"
TIPO_OTRO = "otro"

RESULTADO_PENDIENTE = "pendiente"
RESULTADO_POSITIVO = "respuesta_positiva"
RESULTADO_NEUTRAL = "respuesta_neutral"
RESULTADO_NEGATIVO = "respuesta_negativa"
RESULTADO_SIN_RESPUESTA = "sin_respuesta"
RESULTADO_FALLIDO = "fallido"
RESULTADO_NO_APLICA = "no_aplica"

GRUPO_POSITIVO = "positivo"
GRUPO_NEUTRAL = "neutral"
GRUPO_NEGATIVO = "negativo"
GRUPO_PENDIENTE = "pendiente"
GRUPO_SIN_RESPUESTA = "sin_respuesta"
GRUPO_FALLIDO = "fallido"
GRUPO_NO_APLICA = "no_aplica"

GRUPO_TIPO_CONTACTO = "contacto"
GRUPO_TIPO_OPERATIVO = "operativo"

TIPOS_CONTACTO = (
    TIPO_MENSAJE,
    TIPO_PLANTILLA,
    TIPO_MEDIA,
)

RESULTADOS_RESPUESTA = (
    RESULTADO_POSITIVO,
    RESULTADO_NEUTRAL,
    RESULTADO_NEGATIVO,
)

GRUPOS_RESPUESTA = (
    GRUPO_POSITIVO,
    GRUPO_NEUTRAL,
    GRUPO_NEGATIVO,
)

GRUPOS_RESULTADO_VALIDOS = {
    GRUPO_POSITIVO,
    GRUPO_NEUTRAL,
    GRUPO_NEGATIVO,
    GRUPO_PENDIENTE,
    GRUPO_SIN_RESPUESTA,
    GRUPO_FALLIDO,
    GRUPO_NO_APLICA,
}

LABELS_TIPO_BASE = {
    TIPO_MENSAJE: "Mensaje de texto",
    TIPO_PLANTILLA: "Plantilla",
    TIPO_MEDIA: "Archivo o multimedia",
    TIPO_ACTUALIZACION: "Actualización de prospecto",
    TIPO_BLOQUEO: "Bloqueo o desbloqueo",
    TIPO_LLAMADA: "Llamada",
    TIPO_IA: "Control de IA",
    TIPO_OTRO: "Otra acción",
}

LABELS_RESULTADO_BASE = {
    RESULTADO_PENDIENTE: "Esperando respuesta",
    RESULTADO_POSITIVO: "Respondió con interés",
    RESULTADO_NEUTRAL: "Respondió",
    RESULTADO_NEGATIVO: "Respondió negativamente",
    RESULTADO_SIN_RESPUESTA: "No respondió",
    RESULTADO_FALLIDO: "Falló el envío",
    RESULTADO_NO_APLICA: "No aplica",
}

GRUPO_RESULTADO_BASE = {
    RESULTADO_PENDIENTE: GRUPO_PENDIENTE,
    RESULTADO_POSITIVO: GRUPO_POSITIVO,
    RESULTADO_NEUTRAL: GRUPO_NEUTRAL,
    RESULTADO_NEGATIVO: GRUPO_NEGATIVO,
    RESULTADO_SIN_RESPUESTA: GRUPO_SIN_RESPUESTA,
    RESULTADO_FALLIDO: GRUPO_FALLIDO,
    RESULTADO_NO_APLICA: GRUPO_NO_APLICA,
}

POSITIVAS = (
    "me interesa",
    "estoy interesado",
    "estoy interesada",
    "quiero cotizacion",
    "quiero cotización",
    "mandame cotizacion",
    "mándame cotización",
    "quiero comprar",
    "quiero adquirir",
    "quiero apartar",
    "agendar cita",
    "agendamos",
    "quiero una cita",
    "puedo visitar",
    "quiero visitar",
    "quiero financiamiento",
    "quiero credito",
    "quiero crédito",
    "quiero mensualidades",
    "marcame",
    "márcame",
    "llamame",
    "llámame",
    "hay disponibilidad",
    "tienen disponible",
)


NEGATIVAS = (
    "no me interesa",
    "ya no",
    "ya compre",
    "ya compré",
    "no gracias",
    "deja de escribir",
    "no me contactes",
    "equivocado",
    "numero equivocado",
    "número equivocado",
    "cancelar",
    "cancela",
    "bloquear",
    "baja",
)

CAMPOS_AUDITABLES = {
    "estado": "Estado",
    "motivo_descalificacion": "Motivo de descalificación",
    "asesor_digital": "Asesor digital",
    "asesor_ventas": "Asesor de ventas",
    "auto_interes": "Vehículo de interés",
    "forma_pago": "Forma de pago",
    "buro_estado": "Buró",
    "plazo_compra": "Plazo de compra",
    "requiere_asesor": "Requiere asesor",
    "cotizacion_pendiente": "Cotización pendiente",
    "whatsapp_bloqueado": "Bloqueo de WhatsApp",
}


# -----------------------------------------------------------------------------
# Helpers de fecha, normalización y etiquetas
# -----------------------------------------------------------------------------

def _ahora():
    """
    Devuelve un datetime compatible con la configuración actual de Django.

    - USE_TZ=False: datetime naive, apto para los campos DateTimeField del proyecto.
    - USE_TZ=True: datetime aware.
    """
    return timezone.now()


def _fecha_local_actual():
    """Obtiene la fecha actual sin llamar localdate() cuando USE_TZ=False."""
    ahora = _ahora()

    if settings.USE_TZ and timezone.is_aware(ahora):
        return timezone.localtime(ahora, timezone.get_current_timezone()).date()

    return ahora.date()


def _datetime_para_configuracion(value):
    """
    Normaliza un datetime para evitar mezclas entre valores aware y naive.
    Es útil al restar fechas y al trabajar con registros históricos.
    """
    if value is None:
        return None

    if settings.USE_TZ:
        if timezone.is_naive(value):
            return timezone.make_aware(value, timezone.get_current_timezone())
        return value

    if timezone.is_aware(value):
        return timezone.make_naive(value, timezone.get_current_timezone())

    return value


def _iso_datetime(value):
    """Serializa datetimes respetando USE_TZ=False y USE_TZ=True."""
    value = _datetime_para_configuracion(value)
    return value.isoformat() if value else None


def _dict_seguro(value) -> dict:
    return dict(value) if isinstance(value, dict) else {}


def _texto_normalizado(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _clave_abierta(value: Any, default: str, max_length: int = 80) -> str:
    value = str(value or "").strip()
    return (value or default)[:max_length]


def _label_abierto(value: str, known: dict[str, str] | None = None) -> str:
    value = str(value or "").strip()

    if not value:
        return "Sin definir"

    if known and value in known:
        return known[value]

    return value.replace("_", " ").replace("-", " ").strip().title()


def _inferir_grupo_resultado(resultado: str) -> str:
    resultado = _clave_abierta(resultado, RESULTADO_PENDIENTE)

    if resultado in GRUPO_RESULTADO_BASE:
        return GRUPO_RESULTADO_BASE[resultado]

    normalizado = _texto_normalizado(resultado).replace(" ", "_")

    if any(token in normalizado for token in ("sin_respuesta", "no_respond", "no_contesto")):
        return GRUPO_SIN_RESPUESTA

    if any(token in normalizado for token in ("fall", "error", "rechazado_meta")):
        return GRUPO_FALLIDO

    if any(token in normalizado for token in ("pendiente", "esperando")):
        return GRUPO_PENDIENTE

    if any(token in normalizado for token in ("no_aplica", "informativo", "operativo")):
        return GRUPO_NO_APLICA

    if any(token in normalizado for token in ("negativ", "rechaz", "descalific", "cancel", "no_interes")):
        return GRUPO_NEGATIVO

    if any(
        token in normalizado
        for token in (
            "positiv",
            "interes",
            "cita",
            "cotizacion",
            "venta",
            "apartado",
            "credito_autorizado",
            "visita_agendada",
        )
    ):
        return GRUPO_POSITIVO

    return GRUPO_NEUTRAL


def _grupo_resultado_evento(item: BitacoraAsesorDigital) -> str:
    metadata = item.metadata if isinstance(item.metadata, dict) else {}
    grupo = str(metadata.get("grupo_resultado") or "").strip().lower()

    if grupo in GRUPOS_RESULTADO_VALIDOS:
        return grupo

    return _inferir_grupo_resultado(item.resultado)


def _label_resultado_evento(item: BitacoraAsesorDigital) -> str:
    metadata = item.metadata if isinstance(item.metadata, dict) else {}
    label = str(metadata.get("resultado_label") or "").strip()
    return label or _label_abierto(item.resultado, LABELS_RESULTADO_BASE)


def _label_tipo_evento(item: BitacoraAsesorDigital) -> str:
    metadata = item.metadata if isinstance(item.metadata, dict) else {}
    label = str(metadata.get("tipo_label") or "").strip()
    return label or _label_abierto(item.tipo, LABELS_TIPO_BASE)


def clasificar_respuesta_cliente(texto: str) -> str:
    value = _texto_normalizado(texto)

    if any(frase in value for frase in NEGATIVAS):
        return RESULTADO_NEGATIVO

    if any(frase in value for frase in POSITIVAS):
        return RESULTADO_POSITIVO

    return RESULTADO_NEUTRAL


def _usuario_crm(request=None) -> str:
    user = getattr(request, "user", None) if request is not None else None

    if user and getattr(user, "is_authenticated", False):
        return str(
            getattr(user, "usuario", "")
            or getattr(user, "username", "")
            or getattr(user, "email", "")
            or user
        ).strip()[:120]

    return ""


def _asesor_linea(numero_asesor: str) -> str:
    cfg = WHATSAPP_LINES.get(normaliza_tel_mx(numero_asesor or ""), {})
    return str(cfg.get("asesor_digital") or "").strip()[:200]


def _expediente_de_mensaje(mensaje: MensajeWhatsApp):
    if mensaje.cliente_id:
        return ExpedienteDigital.objects.filter(cliente_id=mensaje.cliente_id).first()

    return (
        ExpedienteDigital.objects
        .select_related("cliente")
        .filter(cliente__telefono=normaliza_tel_mx(mensaje.telefono))
        .first()
    )


def _tipo_desde_mensaje(mensaje: MensajeWhatsApp, tipo: str = "") -> str:
    tipo = str(tipo or "").strip()

    # Si otro proceso manda un tipo nuevo, lo respetamos sin validar choices.
    if tipo:
        return tipo[:80]

    raw = mensaje.raw if isinstance(mensaje.raw, dict) else {}

    if raw.get("template_name") or str(mensaje.body or "").startswith("[TEMPLATE:"):
        return TIPO_PLANTILLA

    if raw.get("meta_type") or str(mensaje.body or "").startswith("[FILE:"):
        return TIPO_MEDIA

    return TIPO_MENSAJE


def _accion_mensaje(mensaje: MensajeWhatsApp, tipo: str) -> tuple[str, str]:
    raw = mensaje.raw if isinstance(mensaje.raw, dict) else {}

    if tipo == TIPO_PLANTILLA:
        plantilla = str(raw.get("template_name") or "").strip()

        if not plantilla:
            match = re.match(r"^\[TEMPLATE:([^\]]+)\]", str(mensaje.body or ""))
            plantilla = match.group(1).strip() if match else "sin_nombre"

        return f"Usó plantilla {plantilla}", plantilla

    if tipo == TIPO_MEDIA:
        media_type = str(raw.get("meta_type") or "archivo").strip().lower()
        labels = {
            "audio": "Envió una nota de voz",
            "image": "Envió una imagen",
            "video": "Envió un video",
            "document": "Envió un documento",
            "sticker": "Envió un sticker",
        }
        return labels.get(media_type, "Envió un archivo"), ""

    return "Envió un mensaje", ""




def _es_mensaje_ia_raw(raw) -> bool:
    raw = raw if isinstance(raw, dict) else {}
    return bool(
        raw.get("ia_provider")
        or raw.get("ia_model")
        or raw.get("openai_model")
        or raw.get("gemini_model")
        or raw.get("decision")
        or raw.get("origen") == "ia"
    )


def _estado_ia_chat(
    *,
    expediente: ExpedienteDigital | None,
    numero_asesor: str,
    fuente: str = "estado_actual",
) -> dict[str, Any]:
    numero = normaliza_tel_mx(numero_asesor or "")
    config = (
        ConfiguracionIAWhatsApp.objects
        .filter(numero_asesor=numero)
        .only("activo")
        .first()
        if numero
        else None
    )
    conversacion = (
        ConversacionIA.objects
        .filter(expediente=expediente, numero_asesor=numero)
        .only("ia_activa", "ia_pausada", "motivo_pausa", "estado_conversacion")
        .first()
        if expediente and numero
        else None
    )

    configurada = bool(config)
    config_activa = bool(config.activo) if config else False
    conversacion_activa = bool(conversacion.ia_activa) if conversacion else True
    pausada_expediente = bool(expediente.ia_pausada) if expediente else False
    pausada_conversacion = bool(conversacion.ia_pausada) if conversacion else False
    pausada = pausada_expediente or pausada_conversacion

    if not configurada:
        estado = "no_configurada"
    elif not config_activa:
        estado = "inactiva_linea"
    elif pausada:
        estado = "pausada"
    elif not conversacion_activa:
        estado = "inactiva_chat"
    else:
        estado = "activa"

    motivo = ""
    if pausada_expediente and expediente:
        motivo = expediente.ia_pausada_motivo or "Pausada en el expediente"
    elif pausada_conversacion and conversacion:
        motivo = conversacion.motivo_pausa or "Pausada en la conversación"

    return {
        "estado": estado,
        "activa": estado == "activa",
        "configurada": configurada,
        "config_activa": config_activa,
        "conversacion_activa": conversacion_activa,
        "pausada": pausada,
        "motivo": motivo,
        "estado_conversacion": (
            conversacion.estado_conversacion
            if conversacion
            else "sin_iniciar"
        ),
        "fuente": fuente,
    }


def _estado_ia_desde_filas(
    *,
    numero_asesor: str,
    expediente_pausado: bool,
    expediente_motivo: str,
    config_activa: bool | None,
    conversacion: dict | None,
) -> dict[str, Any]:
    conversacion = conversacion or {}
    configurada = config_activa is not None
    chat_activo = bool(conversacion.get("ia_activa", True))
    pausada_chat = bool(conversacion.get("ia_pausada", False))
    pausada = bool(expediente_pausado or pausada_chat)

    if not configurada:
        estado = "no_configurada"
    elif not config_activa:
        estado = "inactiva_linea"
    elif pausada:
        estado = "pausada"
    elif not chat_activo:
        estado = "inactiva_chat"
    else:
        estado = "activa"

    return {
        "estado": estado,
        "activa": estado == "activa",
        "configurada": configurada,
        "config_activa": bool(config_activa),
        "conversacion_activa": chat_activo,
        "pausada": pausada,
        "motivo": (
            expediente_motivo
            if expediente_pausado
            else str(conversacion.get("motivo_pausa") or "")
        ),
        "estado_conversacion": str(
            conversacion.get("estado_conversacion") or "sin_iniciar"
        ),
        "fuente": "estado_actual",
        "numero_asesor": numero_asesor,
    }


# -----------------------------------------------------------------------------
# Registro y resolución de eventos
# -----------------------------------------------------------------------------

def registrar_evento_mensaje(
    mensaje: MensajeWhatsApp,
    *,
    request=None,
    expediente=None,
    tipo: str = "",
) -> BitacoraAsesorDigital | None:
    if not mensaje or mensaje.direction != MensajeWhatsApp.Direccion.OUT:
        return None

    raw = mensaje.raw if isinstance(mensaje.raw, dict) else {}

    # No atribuimos respuestas automáticas de IA a un asesor humano.
    if _es_mensaje_ia_raw(raw):
        return None

    expediente = expediente or _expediente_de_mensaje(mensaje)
    tipo = _tipo_desde_mensaje(mensaje, tipo)
    accion, plantilla = _accion_mensaje(mensaje, tipo)

    resultado = RESULTADO_FALLIDO if mensaje.status == "failed" else RESULTADO_PENDIENTE
    grupo_resultado = _inferir_grupo_resultado(resultado)

    metadata = {
        "wa_message_id": mensaje.wa_message_id,
        "meta_type": raw.get("meta_type", ""),
        "reply_to": raw.get("reply_to", ""),
        "origen": raw.get("origen", "asesor_humano"),
        "grupo_tipo": GRUPO_TIPO_CONTACTO,
        "grupo_resultado": grupo_resultado,
        "resultado_label": LABELS_RESULTADO_BASE.get(resultado, ""),
        "tipo_label": LABELS_TIPO_BASE.get(tipo, ""),
        # Se captura el estado en el momento del evento. Para registros antiguos
        # el frontend recibirá el estado actual como respaldo, claramente marcado.
        "ia_estado": _estado_ia_chat(
            expediente=expediente,
            numero_asesor=mensaje.numero_asesor,
            fuente="capturado_en_evento",
        ) if expediente else {},
    }

    defaults = {
        "expediente": expediente,
        "cliente": mensaje.cliente,
        "numero_asesor": mensaje.numero_asesor,
        "asesor_digital": _asesor_linea(mensaje.numero_asesor),
        "usuario_crm": _usuario_crm(request),
        "tipo": tipo,
        "accion": accion,
        "detalle": str(mensaje.body or "")[:1000],
        "plantilla_nombre": plantilla,
        "resultado": resultado,
        "estado_entrega": str(mensaje.status or "")[:50],
        "metadata": metadata,
    }

    evento, creado = BitacoraAsesorDigital.objects.get_or_create(
        mensaje=mensaje,
        defaults=defaults,
    )

    if creado:
        return evento

    # No borramos una corrección manual ni una respuesta ya asociada durante
    # backfills o llamadas repetidas.
    metadata_actual = _dict_seguro(evento.metadata)
    metadata_nueva = {**metadata, **metadata_actual}
    campos = []

    for campo in (
        "expediente",
        "cliente",
        "numero_asesor",
        "asesor_digital",
        "usuario_crm",
        "tipo",
        "accion",
        "detalle",
        "plantilla_nombre",
        "estado_entrega",
    ):
        valor = defaults[campo]

        if campo == "usuario_crm" and not valor:
            continue

        if getattr(evento, campo) != valor:
            setattr(evento, campo, valor)
            campos.append(campo)

    if evento.metadata != metadata_nueva:
        evento.metadata = metadata_nueva
        campos.append("metadata")

    if resultado == RESULTADO_FALLIDO and evento.resultado != RESULTADO_FALLIDO:
        evento.resultado = RESULTADO_FALLIDO
        evento.metadata["grupo_resultado"] = GRUPO_FALLIDO
        evento.metadata["resultado_label"] = LABELS_RESULTADO_BASE[RESULTADO_FALLIDO]
        campos.extend(["resultado", "metadata"])

    if campos:
        campos.append("actualizado")
        evento.save(update_fields=list(dict.fromkeys(campos)))

    return evento


def resolver_evento_por_respuesta(
    mensaje_entrante: MensajeWhatsApp,
    *,
    expediente=None,
) -> BitacoraAsesorDigital | None:
    if not mensaje_entrante or mensaje_entrante.direction != MensajeWhatsApp.Direccion.IN:
        return None

    raw = mensaje_entrante.raw if isinstance(mensaje_entrante.raw, dict) else {}

    if raw.get("is_reaction_event"):
        return None

    expediente = expediente or _expediente_de_mensaje(mensaje_entrante)

    if not expediente:
        return None

    evento = (
        BitacoraAsesorDigital.objects
        .filter(
            expediente=expediente,
            numero_asesor=mensaje_entrante.numero_asesor,
            resultado=RESULTADO_PENDIENTE,
            creado__lte=mensaje_entrante.created_at,
        )
        .filter(
            Q(tipo__in=TIPOS_CONTACTO)
            | Q(metadata__grupo_tipo=GRUPO_TIPO_CONTACTO)
        )
        .order_by("-creado", "-id")
        .first()
    )

    if not evento:
        return None

    creado_evento = _datetime_para_configuracion(evento.creado)
    creado_respuesta = _datetime_para_configuracion(mensaje_entrante.created_at)

    segundos = max(
        0,
        int((creado_respuesta - creado_evento).total_seconds()),
    )

    resultado = clasificar_respuesta_cliente(mensaje_entrante.body)
    metadata = _dict_seguro(evento.metadata)
    metadata["grupo_resultado"] = _inferir_grupo_resultado(resultado)
    metadata["resultado_label"] = LABELS_RESULTADO_BASE.get(resultado, "")
    metadata["clasificacion_automatica"] = True
    metadata["clasificado_at"] = _ahora().isoformat()

    evento.resultado = resultado
    evento.respuesta_mensaje = mensaje_entrante
    evento.respuesta_texto = str(mensaje_entrante.body or "")[:1000]
    evento.respondido_at = mensaje_entrante.created_at
    evento.tiempo_respuesta_segundos = segundos
    evento.metadata = metadata
    evento.save(
        update_fields=[
            "resultado",
            "respuesta_mensaje",
            "respuesta_texto",
            "respondido_at",
            "tiempo_respuesta_segundos",
            "metadata",
            "actualizado",
        ]
    )

    return evento


def actualizar_estado_entrega(
    mensaje: MensajeWhatsApp,
    estado: str,
    errors=None,
) -> None:
    if not mensaje:
        return

    evento = BitacoraAsesorDigital.objects.filter(mensaje=mensaje).first()

    if not evento:
        return

    evento.estado_entrega = str(estado or "")[:50]
    metadata = _dict_seguro(evento.metadata)

    if errors:
        metadata["errors"] = errors

    update_fields = ["estado_entrega", "metadata", "actualizado"]

    if estado == "failed":
        evento.resultado = RESULTADO_FALLIDO
        metadata["grupo_resultado"] = GRUPO_FALLIDO
        metadata["resultado_label"] = LABELS_RESULTADO_BASE[RESULTADO_FALLIDO]
        update_fields.append("resultado")

    evento.metadata = metadata
    evento.save(update_fields=list(dict.fromkeys(update_fields)))


def marcar_eventos_sin_respuesta(*, horas: int = HORAS_SIN_RESPUESTA) -> int:
    limite = _ahora() - timedelta(hours=max(1, int(horas)))

    eventos = (
        BitacoraAsesorDigital.objects
        .filter(
            resultado=RESULTADO_PENDIENTE,
            creado__lt=limite,
        )
        .filter(
            Q(tipo__in=TIPOS_CONTACTO)
            | Q(metadata__grupo_tipo=GRUPO_TIPO_CONTACTO)
        )
    )

    ids = list(eventos.values_list("id", flat=True))

    if not ids:
        return 0

    now = _ahora()
    actualizados = 0

    # Se actualiza por evento para conservar el grupo y la etiqueta en metadata.
    for evento in BitacoraAsesorDigital.objects.filter(id__in=ids).iterator(chunk_size=500):
        metadata = _dict_seguro(evento.metadata)
        metadata["grupo_resultado"] = GRUPO_SIN_RESPUESTA
        metadata["resultado_label"] = LABELS_RESULTADO_BASE[RESULTADO_SIN_RESPUESTA]
        evento.resultado = RESULTADO_SIN_RESPUESTA
        evento.metadata = metadata
        evento.actualizado = now
        evento.save(update_fields=["resultado", "metadata", "actualizado"])
        actualizados += 1

    return actualizados


def registrar_evento_operativo(
    *,
    expediente: ExpedienteDigital | None,
    numero_asesor: str,
    tipo: str,
    accion: str,
    detalle: str = "",
    request=None,
    resultado: str = RESULTADO_NO_APLICA,
    metadata: dict | None = None,
) -> BitacoraAsesorDigital:
    numero_asesor = normaliza_tel_mx(numero_asesor or "")
    tipo = _clave_abierta(tipo, TIPO_OTRO)
    resultado = _clave_abierta(resultado, RESULTADO_NO_APLICA)

    metadata_final = _dict_seguro(metadata)
    metadata_final.setdefault("grupo_tipo", GRUPO_TIPO_OPERATIVO)
    metadata_final.setdefault("grupo_resultado", _inferir_grupo_resultado(resultado))
    metadata_final.setdefault("tipo_label", LABELS_TIPO_BASE.get(tipo, ""))
    metadata_final.setdefault("resultado_label", LABELS_RESULTADO_BASE.get(resultado, ""))

    return BitacoraAsesorDigital.objects.create(
        expediente=expediente,
        cliente=expediente.cliente if expediente else None,
        numero_asesor=numero_asesor,
        asesor_digital=(
            _asesor_linea(numero_asesor)
            or (expediente.asesor_digital if expediente else "")
        ),
        usuario_crm=_usuario_crm(request),
        tipo=tipo,
        accion=str(accion or "Acción operativa").strip()[:255],
        detalle=str(detalle or "").strip()[:1000],
        resultado=resultado,
        metadata=metadata_final,
    )


def registrar_cambios_expediente(
    *,
    expediente: ExpedienteDigital,
    antes: dict[str, Any],
    request=None,
) -> BitacoraAsesorDigital | None:
    cambios = {}

    for campo, etiqueta in CAMPOS_AUDITABLES.items():
        anterior = antes.get(campo)
        nuevo = getattr(expediente, campo, None)

        if anterior != nuevo:
            cambios[campo] = {
                "etiqueta": etiqueta,
                "antes": anterior,
                "despues": nuevo,
            }

    if not cambios:
        return None

    numero = ""

    try:
        numero = normaliza_tel_mx(
            request.data.get("numero_asesor", "")
            or request.query_params.get("numero_asesor", "")
        )
    except Exception:
        numero = ""

    if not numero:
        numeros = _numeros_usuario(getattr(request, "user", None))
        numero = numeros[0] if numeros else ""

    descripciones = [
        f"{item['etiqueta']}: {item['antes'] or '—'} → {item['despues'] or '—'}"
        for item in cambios.values()
    ]

    return registrar_evento_operativo(
        expediente=expediente,
        numero_asesor=numero,
        tipo=TIPO_ACTUALIZACION,
        accion="Actualizó la información del prospecto",
        detalle="; ".join(descripciones)[:1000],
        request=request,
        resultado=RESULTADO_NO_APLICA,
        metadata={"cambios": cambios},
    )


# -----------------------------------------------------------------------------
# Permisos y filtros
# -----------------------------------------------------------------------------

def _usuario_es_admin(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False

    if bool(getattr(user, "is_superuser", False)):
        return True

    rol_obj = getattr(user, "rol", None)
    rol = str(
        getattr(rol_obj, "nombre", "")
        or getattr(rol_obj, "name", "")
        or (rol_obj if isinstance(rol_obj, str) else "")
        or ""
    ).strip().lower()

    if rol in ("administrador", "admin"):
        return True

    permisos = getattr(user, "permisos", None)

    if hasattr(permisos, "all"):
        permisos = permisos.all()

    valores = set()

    for permiso in permisos or []:
        valor = (
            permiso
            if isinstance(permiso, str)
            else (
                getattr(permiso, "codigo", "")
                or getattr(permiso, "nombre", "")
                or getattr(permiso, "name", "")
                or permiso
            )
        )
        valores.add(str(valor).strip().upper())

    return bool({"ALL", "USUARIOS_ADMIN", "CRM_COORDINADOR_DIGITAL"} & valores)


def _numeros_usuario(user) -> list[str]:
    raw = str(getattr(user, "telefono", "") or "")
    numeros = []

    for value in re.split(r"[|,;\n]+", raw):
        numero = normaliza_tel_mx(value)

        if numero in WHATSAPP_LINES and numero not in numeros:
            numeros.append(numero)

    return numeros


def _lineas_permitidas(request) -> tuple[list[str], Response | None]:
    user = getattr(request, "user", None)
    asignadas = _numeros_usuario(user)
    todas = list(WHATSAPP_LINES.keys())
    permitidas = todas if _usuario_es_admin(user) else asignadas

    if not permitidas:
        return [], Response(
            {
                "ok": False,
                "error": "Tu usuario no tiene líneas de WhatsApp disponibles.",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    solicitada = normaliza_tel_mx(request.query_params.get("numero_asesor", ""))

    if solicitada:
        if solicitada not in permitidas:
            return [], Response(
                {
                    "ok": False,
                    "error": "No tienes permiso para consultar esa línea.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        return [solicitada], None

    return permitidas, None


def _rango_fechas(request):
    """
    Construye el rango de consulta de forma compatible con USE_TZ=False.

    Con USE_TZ=False se generan límites naive. Con USE_TZ=True se convierten
    a datetimes aware en TIME_ZONE.
    """
    hoy = _fecha_local_actual()

    desde = (
        parse_date(request.query_params.get("fecha_desde", ""))
        or (hoy - timedelta(days=29))
    )
    hasta = (
        parse_date(request.query_params.get("fecha_hasta", ""))
        or hoy
    )

    if desde > hasta:
        desde, hasta = hasta, desde

    if (hasta - desde).days > 366:
        desde = hasta - timedelta(days=366)

    inicio = datetime.combine(desde, time.min)
    fin = datetime.combine(hasta + timedelta(days=1), time.min)

    if settings.USE_TZ:
        zona = timezone.get_current_timezone()
        inicio = timezone.make_aware(inicio, zona)
        fin = timezone.make_aware(fin, zona)

    return desde, hasta, inicio, fin


def _porcentaje(numerador: int, denominador: int) -> float:
    return round((numerador / denominador) * 100, 1) if denominador else 0.0


def _segundos_label(value) -> str:
    if value in (None, ""):
        return "—"

    segundos = max(0, int(value))
    minutos = segundos // 60

    if minutos < 60:
        return f"{minutos} min"

    horas, mins = divmod(minutos, 60)

    if horas < 24:
        return f"{horas}h {mins}m" if mins else f"{horas}h"

    dias, hrs = divmod(horas, 24)
    return f"{dias}d {hrs}h" if hrs else f"{dias}d"


def _q_contacto() -> Q:
    return Q(tipo__in=TIPOS_CONTACTO) | Q(metadata__grupo_tipo=GRUPO_TIPO_CONTACTO)


def _q_respuesta() -> Q:
    return _q_contacto() & (
        Q(resultado__in=RESULTADOS_RESPUESTA)
        | Q(metadata__grupo_resultado__in=GRUPOS_RESPUESTA)
    )


def _q_positivo() -> Q:
    return _q_contacto() & (
        Q(resultado=RESULTADO_POSITIVO)
        | Q(metadata__grupo_resultado=GRUPO_POSITIVO)
    )


def _q_negativo() -> Q:
    return _q_contacto() & (
        Q(resultado=RESULTADO_NEGATIVO)
        | Q(metadata__grupo_resultado=GRUPO_NEGATIVO)
    )


def _q_sin_respuesta() -> Q:
    return _q_contacto() & (
        Q(resultado=RESULTADO_SIN_RESPUESTA)
        | Q(metadata__grupo_resultado=GRUPO_SIN_RESPUESTA)
    )


def _q_fallido() -> Q:
    return _q_contacto() & (
        Q(resultado=RESULTADO_FALLIDO)
        | Q(metadata__grupo_resultado=GRUPO_FALLIDO)
    )


# -----------------------------------------------------------------------------
# Serialización y catálogos dinámicos
# -----------------------------------------------------------------------------

def _serializar_evento(
    item: BitacoraAsesorDigital,
    *,
    ia_fallback: dict | None = None,
) -> dict[str, Any]:
    metadata = item.metadata if isinstance(item.metadata, dict) else {}
    ia_estado = metadata.get("ia_estado") if isinstance(metadata.get("ia_estado"), dict) else {}

    if not ia_estado and ia_fallback:
        ia_estado = {**ia_fallback, "fuente": "estado_actual_para_registro_historico"}

    return {
        "id": str(item.evento_id),
        "expediente_id": item.expediente_id,
        "cliente_id": item.cliente_id,
        "numero_asesor": item.numero_asesor,
        "asesor_digital": item.asesor_digital,
        "usuario_crm": item.usuario_crm,
        "tipo": item.tipo,
        "tipo_label": _label_tipo_evento(item),
        "tipo_grupo": str(metadata.get("grupo_tipo") or "").strip(),
        "accion": item.accion,
        "detalle": item.detalle,
        "plantilla_nombre": item.plantilla_nombre,
        "resultado": item.resultado,
        "resultado_label": _label_resultado_evento(item),
        "resultado_grupo": _grupo_resultado_evento(item),
        "estado_entrega": item.estado_entrega,
        "respuesta_texto": item.respuesta_texto,
        "respondido_at": _iso_datetime(item.respondido_at),
        "tiempo_respuesta_segundos": item.tiempo_respuesta_segundos,
        "tiempo_respuesta_label": _segundos_label(item.tiempo_respuesta_segundos),
        "ia_estado": ia_estado,
        "metadata": metadata,
        "creado": _iso_datetime(item.creado),
        "actualizado": _iso_datetime(item.actualizado),
    }


def _catalogos_dinamicos(lineas: list[str]) -> dict[str, list[dict[str, str]]]:
    resultados: dict[str, dict[str, str]] = {
        value: {
            "value": value,
            "label": label,
            "grupo": GRUPO_RESULTADO_BASE.get(value, _inferir_grupo_resultado(value)),
        }
        for value, label in LABELS_RESULTADO_BASE.items()
    }

    tipos: dict[str, dict[str, str]] = {
        value: {
            "value": value,
            "label": label,
            "grupo": (
                GRUPO_TIPO_CONTACTO
                if value in TIPOS_CONTACTO
                else GRUPO_TIPO_OPERATIVO
            ),
        }
        for value, label in LABELS_TIPO_BASE.items()
    }

    rows = (
        BitacoraAsesorDigital.objects
        .filter(numero_asesor__in=lineas)
        .values("resultado", "tipo", "metadata")
        .order_by("-actualizado")[:5000]
    )

    for row in rows:
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        resultado = str(row.get("resultado") or "").strip()
        tipo = str(row.get("tipo") or "").strip()

        if resultado and resultado not in resultados:
            grupo = str(metadata.get("grupo_resultado") or "").strip()
            resultados[resultado] = {
                "value": resultado,
                "label": str(metadata.get("resultado_label") or "").strip()
                or _label_abierto(resultado),
                "grupo": grupo if grupo in GRUPOS_RESULTADO_VALIDOS else _inferir_grupo_resultado(resultado),
            }

        if tipo and tipo not in tipos:
            tipos[tipo] = {
                "value": tipo,
                "label": str(metadata.get("tipo_label") or "").strip()
                or _label_abierto(tipo),
                "grupo": str(metadata.get("grupo_tipo") or "").strip()
                or GRUPO_TIPO_OPERATIVO,
            }

    return {
        "resultados": sorted(resultados.values(), key=lambda item: item["label"].lower()),
        "tipos": sorted(tipos.values(), key=lambda item: item["label"].lower()),
        "grupos_resultado": [
            {"value": GRUPO_POSITIVO, "label": "Positivo"},
            {"value": GRUPO_NEUTRAL, "label": "Neutral"},
            {"value": GRUPO_NEGATIVO, "label": "Negativo"},
            {"value": GRUPO_PENDIENTE, "label": "Pendiente"},
            {"value": GRUPO_SIN_RESPUESTA, "label": "Sin respuesta"},
            {"value": GRUPO_FALLIDO, "label": "Fallido"},
            {"value": GRUPO_NO_APLICA, "label": "No aplica"},
        ],
    }


# -----------------------------------------------------------------------------
# Métricas explicables
# -----------------------------------------------------------------------------

def _aplicar_metricas_contacto(row: dict[str, Any]) -> dict[str, Any]:
    intentos = int(row.get("mensajes") or 0)
    respuestas = int(row.get("respuestas") or 0)
    positivas = int(row.get("positivas") or row.get("respuestas_positivas") or 0)
    sin_respuesta = int(row.get("sin_respuesta") or 0)
    fallidos = int(row.get("fallidos") or 0)

    contactos_validos = max(intentos - fallidos, 0)
    pendientes = max(contactos_validos - respuestas - sin_respuesta, 0)

    row["mensajes"] = intentos
    row["intentos_contacto"] = intentos
    row["contactos_validos"] = contactos_validos
    row["respuestas"] = respuestas
    row["positivas"] = positivas
    row["sin_respuesta"] = sin_respuesta
    row["fallidos"] = fallidos
    row["pendientes"] = pendientes
    row["abiertas"] = pendientes

    # Respuestas obtenidas sobre intentos realmente enviados; los fallidos no
    # forman parte del denominador.
    row["tasa_respuesta_cliente"] = _porcentaje(respuestas, contactos_validos)
    # Señales de interés sobre las respuestas recibidas, no sobre todos los envíos.
    row["tasa_interes_respuestas"] = _porcentaje(positivas, respuestas)
    row["tasa_interes_contactos"] = _porcentaje(positivas, contactos_validos)
    row["tasa_sin_respuesta_48h"] = _porcentaje(sin_respuesta, contactos_validos)

    # Alias temporal para no romper clientes antiguos.
    row["tasa_respuesta"] = row["tasa_respuesta_cliente"]
    row["tasa_positiva"] = row["tasa_interes_respuestas"]
    return row


def _resumen_operativo_cliente(row: dict[str, Any]) -> str:
    intentos = int(row.get("mensajes") or 0)
    respuestas = int(row.get("respuestas") or 0)
    positivas = int(row.get("positivas") or 0)
    sin_respuesta = int(row.get("sin_respuesta") or 0)
    pendientes = int(row.get("pendientes") or 0)
    ultima_accion = str(row.get("ultima_accion") or "").strip()

    if intentos == 0:
        return "No existe contacto humano registrado en el periodo."
    if positivas:
        return "El cliente respondió con interés; el asesor debe convertirlo en cita, llamada o cotización."
    if respuestas:
        return "El cliente respondió, pero aún no hay una señal comercial concluyente."
    if sin_respuesta and not pendientes:
        return "El asesor realizó contacto; el cliente no respondió después de 48 horas."
    if pendientes:
        return "El asesor inició seguimiento y la respuesta del cliente continúa pendiente dentro de 48 horas."
    return ultima_accion or "Existe actividad registrada, pero falta información para interpretar el resultado."


def _calcular_primera_atencion(
    *,
    lineas: list[str],
    inicio,
    fin,
) -> dict[str, Any]:
    """
    Calcula la primera respuesta HUMANA por conversación en el periodo.

    Inicio: primer mensaje entrante del cliente para teléfono + línea.
    Fin: primer mensaje saliente humano posterior, máximo 48 horas después.
    Mensajes de IA y envíos fallidos quedan fuera.
    """
    entradas = list(
        MensajeWhatsApp.objects
        .filter(
            numero_asesor__in=lineas,
            direction=MensajeWhatsApp.Direccion.IN,
            created_at__gte=inicio,
            created_at__lt=fin,
        )
        .values("telefono", "numero_asesor", "created_at")
        .order_by("created_at", "id")
    )

    primeras: dict[tuple[str, str], Any] = {}
    for row in entradas:
        key = (row["telefono"], row["numero_asesor"])
        primeras.setdefault(key, _datetime_para_configuracion(row["created_at"]))

    salidas_por_chat: dict[tuple[str, str], list[Any]] = {}
    if primeras:
        salidas = (
            MensajeWhatsApp.objects
            .filter(
                numero_asesor__in=lineas,
                direction=MensajeWhatsApp.Direccion.OUT,
                created_at__gte=inicio,
                created_at__lt=fin + timedelta(hours=HORAS_SIN_RESPUESTA),
            )
            .exclude(status="failed")
            .values("telefono", "numero_asesor", "created_at", "raw")
            .order_by("created_at", "id")
        )

        for row in salidas:
            if _es_mensaje_ia_raw(row.get("raw")):
                continue
            key = (row["telefono"], row["numero_asesor"])
            salidas_por_chat.setdefault(key, []).append(
                _datetime_para_configuracion(row["created_at"])
            )

    referencia = _datetime_para_configuracion(_ahora())
    por_chat: dict[tuple[str, str], dict[str, Any]] = {}
    por_linea_segundos: dict[str, list[int]] = {numero: [] for numero in lineas}
    por_linea_totales: dict[str, dict[str, int]] = {
        numero: {"recibidas": 0, "atendidas": 0, "vencidas": 0, "pendientes": 0}
        for numero in lineas
    }

    for key, entrada in primeras.items():
        telefono, numero = key
        por_linea_totales[numero]["recibidas"] += 1
        salidas = salidas_por_chat.get(key, [])
        index = bisect_left(salidas, entrada)
        salida = salidas[index] if index < len(salidas) else None
        segundos = None

        if salida:
            delta = int((salida - entrada).total_seconds())
            if 0 <= delta <= HORAS_SIN_RESPUESTA * 3600:
                segundos = delta

        if segundos is not None:
            estado = "atendida"
            por_linea_totales[numero]["atendidas"] += 1
            por_linea_segundos[numero].append(segundos)
        elif referencia >= entrada + timedelta(hours=HORAS_SIN_RESPUESTA):
            estado = "vencida_sin_atender"
            por_linea_totales[numero]["vencidas"] += 1
        else:
            estado = "pendiente"
            por_linea_totales[numero]["pendientes"] += 1

        por_chat[key] = {
            "estado": estado,
            "inicio": _iso_datetime(entrada),
            "respuesta_humana": _iso_datetime(salida) if segundos is not None else None,
            "segundos": segundos,
            "label": _segundos_label(segundos),
        }

    def construir(numero: str | None = None) -> dict[str, Any]:
        numeros = [numero] if numero else lineas
        segundos = [
            value
            for n in numeros
            for value in por_linea_segundos.get(n, [])
        ]
        recibidas = sum(por_linea_totales[n]["recibidas"] for n in numeros)
        atendidas = sum(por_linea_totales[n]["atendidas"] for n in numeros)
        vencidas = sum(por_linea_totales[n]["vencidas"] for n in numeros)
        pendientes = sum(por_linea_totales[n]["pendientes"] for n in numeros)
        promedio = round(sum(segundos) / len(segundos)) if segundos else None
        mediana_valor = round(median(segundos)) if segundos else None

        return {
            "conversaciones_recibidas": recibidas,
            "conversaciones_atendidas": atendidas,
            "sin_atencion_48h": vencidas,
            "pendientes_menos_48h": pendientes,
            "cobertura_atencion_pct": _porcentaje(atendidas, recibidas),
            "promedio_segundos": promedio,
            "promedio_label": _segundos_label(promedio),
            "mediana_segundos": mediana_valor,
            "mediana_label": _segundos_label(mediana_valor),
            "ventana_horas": HORAS_SIN_RESPUESTA,
        }

    return {
        "general": construir(),
        "por_linea": {numero: construir(numero) for numero in lineas},
        "por_chat": por_chat,
    }


def _completar_actividad_diaria(*, qs, desde, hasta) -> list[dict[str, Any]]:
    dias: dict[Any, dict[str, Any]] = {}
    fecha = desde
    while fecha <= hasta:
        dias[fecha] = {
            "fecha": fecha.isoformat(),
            "acciones": 0,
            "mensajes": 0,
            "respuestas": 0,
            "positivas": 0,
            "sin_respuesta": 0,
            "fallidos": 0,
        }
        fecha += timedelta(days=1)

    rows = (
        qs.annotate(fecha=TruncDate("creado"))
        .values("fecha")
        .annotate(
            acciones=Count("id"),
            mensajes=Count("id", filter=_q_contacto()),
            respuestas=Count("id", filter=_q_respuesta()),
            positivas=Count("id", filter=_q_positivo()),
            sin_respuesta=Count("id", filter=_q_sin_respuesta()),
            fallidos=Count("id", filter=_q_fallido()),
        )
        .order_by("fecha")
    )

    for row in rows:
        if row["fecha"] in dias:
            dias[row["fecha"]].update(
                {
                    "acciones": int(row["acciones"] or 0),
                    "mensajes": int(row["mensajes"] or 0),
                    "respuestas": int(row["respuestas"] or 0),
                    "positivas": int(row["positivas"] or 0),
                    "sin_respuesta": int(row["sin_respuesta"] or 0),
                    "fallidos": int(row["fallidos"] or 0),
                }
            )

    return list(dias.values())


# -----------------------------------------------------------------------------
# API de analítica
# -----------------------------------------------------------------------------

@api_view(["GET"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def analitica_asesores_view(request):
    marcar_eventos_sin_respuesta()
    lineas, error = _lineas_permitidas(request)
    if error:
        return error

    desde, hasta, inicio, fin = _rango_fechas(request)
    qs = BitacoraAsesorDigital.objects.filter(
        numero_asesor__in=lineas,
        creado__gte=inicio,
        creado__lt=fin,
    )

    resultado = str(request.query_params.get("resultado", "") or "").strip()
    tipo = str(request.query_params.get("tipo", "") or "").strip()
    buscar = str(request.query_params.get("buscar", "") or "").strip()

    if resultado:
        qs = qs.filter(resultado=resultado)
    if tipo:
        qs = qs.filter(tipo=tipo)
    if buscar:
        qs = qs.filter(
            Q(expediente__cliente__nombre__icontains=buscar)
            | Q(expediente__cliente__telefono__icontains=buscar)
            | Q(accion__icontains=buscar)
            | Q(plantilla_nombre__icontains=buscar)
        )

    tiempos_atencion = _calcular_primera_atencion(
        lineas=lineas,
        inicio=inicio,
        fin=fin,
    )

    resumen = qs.aggregate(
        acciones=Count("id"),
        clientes=Count("expediente_id", distinct=True),
        mensajes=Count("id", filter=_q_contacto()),
        plantillas=Count("id", filter=Q(tipo=TIPO_PLANTILLA)),
        respuestas=Count("id", filter=_q_respuesta()),
        respuestas_positivas=Count("id", filter=_q_positivo()),
        respuestas_negativas=Count("id", filter=_q_negativo()),
        sin_respuesta=Count("id", filter=_q_sin_respuesta()),
        fallidos=Count("id", filter=_q_fallido()),
        promedio_respuesta_cliente=Avg(
            "tiempo_respuesta_segundos",
            filter=_q_respuesta(),
        ),
    )
    resumen["positivas"] = int(resumen.get("respuestas_positivas") or 0)
    resumen["promedio_respuesta_cliente_label"] = _segundos_label(
        resumen.get("promedio_respuesta_cliente")
    )
    resumen["primera_atencion_humana"] = tiempos_atencion["general"]
    resumen.update(
        {
            "primera_atencion_promedio_label": tiempos_atencion["general"]["promedio_label"],
            "cobertura_primera_atencion_pct": tiempos_atencion["general"]["cobertura_atencion_pct"],
            "sin_atencion_48h": tiempos_atencion["general"]["sin_atencion_48h"],
        }
    )
    _aplicar_metricas_contacto(resumen)

    agregados = {
        row["numero_asesor"]: row
        for row in (
            qs.values("numero_asesor")
            .annotate(
                acciones=Count("id"),
                clientes=Count("expediente_id", distinct=True),
                mensajes=Count("id", filter=_q_contacto()),
                plantillas=Count("id", filter=Q(tipo=TIPO_PLANTILLA)),
                respuestas=Count("id", filter=_q_respuesta()),
                positivas=Count("id", filter=_q_positivo()),
                sin_respuesta=Count("id", filter=_q_sin_respuesta()),
                fallidos=Count("id", filter=_q_fallido()),
                promedio_respuesta_cliente=Avg(
                    "tiempo_respuesta_segundos",
                    filter=_q_respuesta(),
                ),
                ultima_actividad=Max("creado"),
            )
        )
    }

    asesores = []
    for numero in lineas:
        cfg = WHATSAPP_LINES.get(numero, {})
        row = {
            "numero_asesor": numero,
            "asesor_digital": cfg.get("asesor_digital", "") or numero,
            "agencia": cfg.get("agencia", ""),
            "business": cfg.get("business", ""),
            "acciones": 0,
            "clientes": 0,
            "mensajes": 0,
            "plantillas": 0,
            "respuestas": 0,
            "positivas": 0,
            "sin_respuesta": 0,
            "fallidos": 0,
            "promedio_respuesta_cliente": None,
            "ultima_actividad": None,
            **agregados.get(numero, {}),
        }
        row["asesor_digital"] = cfg.get("asesor_digital", "") or row.get("asesor_digital") or numero
        row["agencia"] = cfg.get("agencia", "")
        row["business"] = cfg.get("business", "")
        row["promedio_respuesta_cliente_label"] = _segundos_label(
            row.get("promedio_respuesta_cliente")
        )
        row["primera_atencion_humana"] = tiempos_atencion["por_linea"][numero]
        row["ultima_actividad"] = _iso_datetime(row.get("ultima_actividad"))
        _aplicar_metricas_contacto(row)
        asesores.append(row)

    asesores.sort(
        key=lambda item: (
            item["tasa_respuesta_cliente"],
            item["contactos_validos"],
            item["clientes"],
        ),
        reverse=True,
    )

    plantillas = []
    for row in (
        qs.filter(tipo=TIPO_PLANTILLA)
        .exclude(plantilla_nombre="")
        .values("plantilla_nombre")
        .annotate(
            mensajes=Count("id"),
            respuestas=Count("id", filter=_q_respuesta()),
            positivas=Count("id", filter=_q_positivo()),
            sin_respuesta=Count("id", filter=_q_sin_respuesta()),
            fallidos=Count("id", filter=_q_fallido()),
        )
        .order_by("-mensajes")[:10]
    ):
        row["envios"] = int(row.get("mensajes") or 0)
        _aplicar_metricas_contacto(row)
        plantillas.append(row)

    actividad_diaria = _completar_actividad_diaria(
        qs=qs,
        desde=desde,
        hasta=hasta,
    )

    latest = qs.filter(
        expediente_id=OuterRef("expediente_id"),
        numero_asesor=OuterRef("numero_asesor"),
    ).order_by("-creado", "-id")

    clientes_qs = (
        qs.exclude(expediente_id=None)
        .values(
            "expediente_id",
            "numero_asesor",
            "expediente__cliente__nombre",
            "expediente__cliente__telefono",
            "expediente__estado",
            "expediente__auto_interes",
            "expediente__ia_pausada",
            "expediente__ia_pausada_motivo",
        )
        .annotate(
            acciones=Count("id"),
            mensajes=Count("id", filter=_q_contacto()),
            plantillas=Count("id", filter=Q(tipo=TIPO_PLANTILLA)),
            respuestas=Count("id", filter=_q_respuesta()),
            positivas=Count("id", filter=_q_positivo()),
            sin_respuesta=Count("id", filter=_q_sin_respuesta()),
            fallidos=Count("id", filter=_q_fallido()),
            promedio_respuesta_cliente=Avg(
                "tiempo_respuesta_segundos",
                filter=_q_respuesta(),
            ),
            ultima_actividad=Max("creado"),
            ultima_accion=Subquery(latest.values("accion")[:1]),
            ultimo_resultado=Subquery(latest.values("resultado")[:1]),
        )
        .order_by("-ultima_actividad")
    )

    try:
        page_number = max(1, int(request.query_params.get("page", 1)))
        page_size = min(150, max(10, int(request.query_params.get("page_size", 25))))
    except (TypeError, ValueError):
        page_number, page_size = 1, 25

    paginator = Paginator(clientes_qs, page_size)
    page = paginator.get_page(page_number)
    page_rows = list(page.object_list)
    expediente_ids = [int(row["expediente_id"]) for row in page_rows]

    configs = {
        item.numero_asesor: bool(item.activo)
        for item in ConfiguracionIAWhatsApp.objects
        .filter(numero_asesor__in=lineas)
        .only("numero_asesor", "activo")
    }
    conversaciones = {
        (row["expediente_id"], row["numero_asesor"]): row
        for row in ConversacionIA.objects
        .filter(expediente_id__in=expediente_ids, numero_asesor__in=lineas)
        .values(
            "expediente_id",
            "numero_asesor",
            "ia_activa",
            "ia_pausada",
            "motivo_pausa",
            "estado_conversacion",
        )
    }

    catalogos = _catalogos_dinamicos(lineas)
    catalogo_resultados = {item["value"]: item for item in catalogos["resultados"]}
    clientes = []

    for row in page_rows:
        row["nombre"] = row.pop("expediente__cliente__nombre") or "Sin nombre"
        row["telefono"] = row.pop("expediente__cliente__telefono") or ""
        row["estado"] = row.pop("expediente__estado") or ""
        row["auto_interes"] = row.pop("expediente__auto_interes") or ""
        exp_pausado = bool(row.pop("expediente__ia_pausada") or False)
        exp_motivo = row.pop("expediente__ia_pausada_motivo") or ""
        row["asesor_digital"] = WHATSAPP_LINES.get(row["numero_asesor"], {}).get("asesor_digital", "")
        row["agencia"] = WHATSAPP_LINES.get(row["numero_asesor"], {}).get("agencia", "")
        row["ultima_actividad"] = _iso_datetime(row.get("ultima_actividad"))
        row["promedio_respuesta_cliente_label"] = _segundos_label(
            row.get("promedio_respuesta_cliente")
        )
        _aplicar_metricas_contacto(row)

        ultimo = catalogo_resultados.get(row.get("ultimo_resultado") or "", {})
        row["ultimo_resultado_label"] = ultimo.get("label") or _label_abierto(
            row.get("ultimo_resultado"), LABELS_RESULTADO_BASE
        )
        row["ultimo_resultado_grupo"] = ultimo.get("grupo") or _inferir_grupo_resultado(
            row.get("ultimo_resultado")
        )
        row["resumen_operativo"] = _resumen_operativo_cliente(row)
        row["ia_estado"] = _estado_ia_desde_filas(
            numero_asesor=row["numero_asesor"],
            expediente_pausado=exp_pausado,
            expediente_motivo=exp_motivo,
            config_activa=configs.get(row["numero_asesor"]),
            conversacion=conversaciones.get((row["expediente_id"], row["numero_asesor"])),
        )
        row["primera_atencion_humana"] = tiempos_atencion["por_chat"].get(
            (row["telefono"], row["numero_asesor"]),
            {
                "estado": "sin_mensaje_entrante_en_periodo",
                "inicio": None,
                "respuesta_humana": None,
                "segundos": None,
                "label": "—",
            },
        )
        clientes.append(row)

    lineas_payload = [
        {
            "numero": numero,
            "asesor_digital": WHATSAPP_LINES[numero].get("asesor_digital", ""),
            "agencia": WHATSAPP_LINES[numero].get("agencia", ""),
            "business": WHATSAPP_LINES[numero].get("business", ""),
            "tiene_actividad": numero in agregados,
        }
        for numero in lineas
    ]

    return Response(
        {
            "ok": True,
            "rango": {
                "fecha_desde": desde.isoformat(),
                "fecha_hasta": hasta.isoformat(),
            },
            "horas_sin_respuesta": HORAS_SIN_RESPUESTA,
            "definiciones_metricas": {
                "tasa_respuesta_cliente": "Respuestas del cliente / intentos de contacto enviados correctamente.",
                "tasa_interes_respuestas": "Respuestas con intención comercial / respuestas recibidas.",
                "sin_respuesta_48h": "Intento sin respuesta después de 48 horas.",
                "pendiente": "Intento todavía dentro de las primeras 48 horas.",
                "primera_atencion_humana": "Tiempo entre el primer mensaje entrante del periodo y la primera respuesta humana; la IA y los fallidos se excluyen.",
                "respuesta_cliente": "Tiempo entre una acción humana saliente y la primera respuesta entrante asociada.",
            },
            "resumen": resumen,
            "asesores": asesores,
            "plantillas": plantillas,
            "actividad_diaria": actividad_diaria,
            "clientes": clientes,
            "paginacion": {
                "page": page.number,
                "page_size": page_size,
                "pages": paginator.num_pages,
                "total": paginator.count,
                "has_next": page.has_next(),
                "has_previous": page.has_previous(),
            },
            "lineas": lineas_payload,
            "catalogos": catalogos,
        }
    )


@api_view(["GET"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def analitica_cliente_view(request, expediente_id: int):
    marcar_eventos_sin_respuesta()
    lineas, error = _lineas_permitidas(request)
    if error:
        return error

    expediente = (
        ExpedienteDigital.objects
        .select_related("cliente")
        .filter(id=expediente_id)
        .first()
    )
    if not expediente:
        return Response(
            {"ok": False, "error": "Prospecto no encontrado."},
            status=status.HTTP_404_NOT_FOUND,
        )

    numero = normaliza_tel_mx(request.query_params.get("numero_asesor", ""))
    if numero and numero not in lineas:
        return Response(
            {"ok": False, "error": "No tienes permiso para esa línea."},
            status=status.HTTP_403_FORBIDDEN,
        )

    numeros = [numero] if numero else lineas
    eventos = list(
        BitacoraAsesorDigital.objects
        .select_related("mensaje", "respuesta_mensaje")
        .filter(expediente=expediente, numero_asesor__in=numeros)
        .order_by("-creado", "-id")[:200]
    )
    eventos_cronologicos = list(reversed(eventos))

    mensajes = list(
        MensajeWhatsApp.objects
        .filter(
            telefono=expediente.cliente.telefono,
            numero_asesor__in=numeros,
        )
        .order_by("-created_at", "-id")[:160]
    )
    mensajes.reverse()

    numero_estado = numero or (eventos[0].numero_asesor if eventos else numeros[0])
    ia_estado = _estado_ia_chat(
        expediente=expediente,
        numero_asesor=numero_estado,
        fuente="estado_actual",
    )

    ultimo_evento = eventos[0] if eventos else None
    ultimo_mensaje = mensajes[-1] if mensajes else None
    cache_key = (
        f"digitales:resumen-atencion:{expediente.id}:{numero_estado}:"
        f"{getattr(ultimo_evento, 'id', 0)}:{getattr(ultimo_evento, 'actualizado', '')}:"
        f"{getattr(ultimo_mensaje, 'id', 0)}"
    )
    resumen_atencion = cache.get(cache_key)
    if not resumen_atencion:
        resumen_atencion = generar_resumen_atencion_con_gemini(
            mensajes=mensajes,
            eventos=eventos_cronologicos,
            telefono=expediente.cliente.telefono,
            estado_ia=ia_estado,
        )
        cache.set(cache_key, resumen_atencion, timeout=60 * 30)

    metricas = {
        "mensajes": sum(1 for item in eventos if item.tipo in TIPOS_CONTACTO),
        "respuestas": sum(1 for item in eventos if _grupo_resultado_evento(item) in GRUPOS_RESPUESTA),
        "positivas": sum(1 for item in eventos if _grupo_resultado_evento(item) == GRUPO_POSITIVO),
        "sin_respuesta": sum(1 for item in eventos if _grupo_resultado_evento(item) == GRUPO_SIN_RESPUESTA),
        "fallidos": sum(1 for item in eventos if _grupo_resultado_evento(item) == GRUPO_FALLIDO),
    }
    _aplicar_metricas_contacto(metricas)

    return Response(
        {
            "ok": True,
            "cliente": {
                "expediente_id": expediente.id,
                "nombre": expediente.cliente.nombre or "Sin nombre",
                "telefono": expediente.cliente.telefono,
                "estado": expediente.estado,
                "auto_interes": expediente.auto_interes,
                "asesor_digital": expediente.asesor_digital,
                "asesor_ventas": expediente.asesor_ventas,
                "ia_estado": ia_estado,
            },
            "metricas": metricas,
            "resumen_atencion_ia": resumen_atencion,
            "eventos": [
                _serializar_evento(item, ia_fallback=ia_estado)
                for item in eventos
            ],
            "catalogos": _catalogos_dinamicos(lineas),
        }
    )


@api_view(["PATCH"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def analitica_evento_resultado_view(request, evento_id):
    """Compatibilidad administrativa. La interfaz principal ya no expone un selector manual."""
    lineas, error = _lineas_permitidas(request)
    if error:
        return error

    evento = (
        BitacoraAsesorDigital.objects
        .filter(evento_id=evento_id, numero_asesor__in=lineas)
        .first()
    )
    if not evento:
        return Response(
            {"ok": False, "error": "Evento no encontrado."},
            status=status.HTTP_404_NOT_FOUND,
        )

    resultado = _clave_abierta(request.data.get("resultado", ""), "")
    if not resultado:
        return Response(
            {"ok": False, "error": "El resultado es obligatorio."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    resultado_label = str(request.data.get("resultado_label", "") or "").strip()[:120]
    grupo_resultado = str(request.data.get("grupo_resultado", "") or "").strip().lower()
    if grupo_resultado and grupo_resultado not in GRUPOS_RESULTADO_VALIDOS:
        return Response(
            {"ok": False, "error": "El grupo del resultado no es válido."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    grupo_resultado = grupo_resultado or _inferir_grupo_resultado(resultado)
    resultado_label = resultado_label or _label_abierto(resultado, LABELS_RESULTADO_BASE)
    metadata = _dict_seguro(evento.metadata)
    metadata.update(
        {
            "clasificacion_manual": True,
            "clasificado_por": _usuario_crm(request),
            "clasificado_at": _ahora().isoformat(),
            "grupo_resultado": grupo_resultado,
            "resultado_label": resultado_label,
        }
    )
    evento.resultado = resultado
    evento.metadata = metadata
    evento.save(update_fields=["resultado", "metadata", "actualizado"])

    return Response({"ok": True, "evento": _serializar_evento(evento)})
