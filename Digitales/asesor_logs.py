from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from django.conf import settings
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

from .models import BitacoraAsesorDigital, ExpedienteDigital, MensajeWhatsApp
from .sett import WHATSAPP_LINES


# -----------------------------------------------------------------------------
# Valores convencionales del sistema
# -----------------------------------------------------------------------------
# Estos valores NO son choices del modelo y NO restringen lo que puede guardar
# el frontend. Solo son convenciones para los eventos generados automáticamente.

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
    "si",
    "sí",
    "claro",
    "me interesa",
    "interesado",
    "interesada",
    "quiero",
    "cotizacion",
    "cotización",
    "cita",
    "agendar",
    "agenda",
    "horario",
    "disponible",
    "adelante",
    "llamada",
    "marcame",
    "márcame",
    "gracias",
    "perfecto",
    "de acuerdo",
    "envíame",
    "enviame",
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
# Helpers de normalización y etiquetas
# -----------------------------------------------------------------------------

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
    if any(raw.get(key) for key in ("ia_provider", "ia_model", "openai_model", "gemini_model")):
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
    metadata_actual = dict(evento.metadata or {})
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

    segundos = max(
        0,
        int((mensaje_entrante.created_at - evento.creado).total_seconds()),
    )

    resultado = clasificar_respuesta_cliente(mensaje_entrante.body)
    metadata = dict(evento.metadata or {})
    metadata["grupo_resultado"] = _inferir_grupo_resultado(resultado)
    metadata["resultado_label"] = LABELS_RESULTADO_BASE.get(resultado, "")
    metadata["clasificacion_automatica"] = True
    metadata["clasificado_at"] = timezone.now().isoformat()

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
    metadata = dict(evento.metadata or {})

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
    limite = timezone.now() - timedelta(hours=max(1, int(horas)))

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

    now = timezone.now()
    actualizados = 0

    # Se actualiza por evento para conservar el grupo y la etiqueta en metadata.
    for evento in BitacoraAsesorDigital.objects.filter(id__in=ids).iterator(chunk_size=500):
        metadata = dict(evento.metadata or {})
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

    metadata_final = dict(metadata or {})
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
    hoy = timezone.localdate()
    desde = parse_date(request.query_params.get("fecha_desde", "")) or (hoy - timedelta(days=29))
    hasta = parse_date(request.query_params.get("fecha_hasta", "")) or hoy

    if desde > hasta:
        desde, hasta = hasta, desde

    if (hasta - desde).days > 366:
        desde = hasta - timedelta(days=366)

    inicio = timezone.datetime.combine(desde, timezone.datetime.min.time())
    fin = timezone.datetime.combine(hasta + timedelta(days=1), timezone.datetime.min.time())

    if settings.USE_TZ:
        inicio = timezone.make_aware(inicio, timezone.get_current_timezone())
        fin = timezone.make_aware(fin, timezone.get_current_timezone())

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

def _serializar_evento(item: BitacoraAsesorDigital) -> dict[str, Any]:
    metadata = item.metadata if isinstance(item.metadata, dict) else {}

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
        "respondido_at": item.respondido_at.isoformat() if item.respondido_at else None,
        "tiempo_respuesta_segundos": item.tiempo_respuesta_segundos,
        "tiempo_respuesta_label": _segundos_label(item.tiempo_respuesta_segundos),
        "metadata": metadata,
        "creado": item.creado.isoformat(),
        "actualizado": item.actualizado.isoformat() if item.actualizado else None,
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
        promedio_respuesta=Avg(
            "tiempo_respuesta_segundos",
            filter=_q_respuesta(),
        ),
    )

    cerrados = int(resumen["respuestas"] or 0) + int(resumen["sin_respuesta"] or 0)
    resumen["tasa_respuesta"] = _porcentaje(int(resumen["respuestas"] or 0), cerrados)
    resumen["tasa_respuesta_positiva"] = _porcentaje(
        int(resumen["respuestas_positivas"] or 0),
        int(resumen["respuestas"] or 0),
    )
    resumen["promedio_respuesta_label"] = _segundos_label(resumen["promedio_respuesta"])

    asesores_qs = (
        qs.values("numero_asesor", "asesor_digital")
        .annotate(
            acciones=Count("id"),
            clientes=Count("expediente_id", distinct=True),
            mensajes=Count("id", filter=_q_contacto()),
            plantillas=Count("id", filter=Q(tipo=TIPO_PLANTILLA)),
            respuestas=Count("id", filter=_q_respuesta()),
            positivas=Count("id", filter=_q_positivo()),
            sin_respuesta=Count("id", filter=_q_sin_respuesta()),
            fallidos=Count("id", filter=_q_fallido()),
            promedio_respuesta=Avg(
                "tiempo_respuesta_segundos",
                filter=_q_respuesta(),
            ),
            ultima_actividad=Max("creado"),
        )
        .order_by("-respuestas", "-mensajes")
    )

    asesores = []

    for row in asesores_qs:
        cerrados_asesor = int(row["respuestas"] or 0) + int(row["sin_respuesta"] or 0)
        row["tasa_respuesta"] = _porcentaje(int(row["respuestas"] or 0), cerrados_asesor)
        row["tasa_positiva"] = _porcentaje(
            int(row["positivas"] or 0),
            int(row["respuestas"] or 0),
        )
        row["promedio_respuesta_label"] = _segundos_label(row["promedio_respuesta"])
        row["agencia"] = WHATSAPP_LINES.get(row["numero_asesor"], {}).get("agencia", "")
        row["ultima_actividad"] = (
            row["ultima_actividad"].isoformat()
            if row["ultima_actividad"]
            else None
        )
        asesores.append(row)

    plantillas_qs = (
        qs.filter(tipo=TIPO_PLANTILLA)
        .exclude(plantilla_nombre="")
        .values("plantilla_nombre")
        .annotate(
            envios=Count("id"),
            respuestas=Count("id", filter=_q_respuesta()),
            positivas=Count("id", filter=_q_positivo()),
            sin_respuesta=Count("id", filter=_q_sin_respuesta()),
            fallidos=Count("id", filter=_q_fallido()),
        )
        .order_by("-envios")[:10]
    )

    plantillas = []

    for row in plantillas_qs:
        cerrados_plantilla = int(row["respuestas"] or 0) + int(row["sin_respuesta"] or 0)
        row["tasa_respuesta"] = _porcentaje(
            int(row["respuestas"] or 0),
            cerrados_plantilla,
        )
        plantillas.append(row)

    actividad_diaria = []

    for row in (
        qs.annotate(fecha=TruncDate("creado"))
        .values("fecha")
        .annotate(
            acciones=Count("id"),
            mensajes=Count("id", filter=_q_contacto()),
            respuestas=Count("id", filter=_q_respuesta()),
        )
        .order_by("fecha")
    ):
        actividad_diaria.append(
            {
                "fecha": row["fecha"].isoformat() if row["fecha"] else None,
                "acciones": row["acciones"],
                "mensajes": row["mensajes"],
                "respuestas": row["respuestas"],
            }
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
            "asesor_digital",
            "expediente__cliente__nombre",
            "expediente__cliente__telefono",
            "expediente__estado",
            "expediente__auto_interes",
        )
        .annotate(
            acciones=Count("id"),
            mensajes=Count("id", filter=_q_contacto()),
            plantillas=Count("id", filter=Q(tipo=TIPO_PLANTILLA)),
            respuestas=Count("id", filter=_q_respuesta()),
            positivas=Count("id", filter=_q_positivo()),
            sin_respuesta=Count("id", filter=_q_sin_respuesta()),
            ultima_actividad=Max("creado"),
            ultima_accion=Subquery(latest.values("accion")[:1]),
            ultimo_resultado=Subquery(latest.values("resultado")[:1]),
        )
        .order_by("-ultima_actividad")
    )

    try:
        page_number = max(1, int(request.query_params.get("page", 1)))
        page_size = min(100, max(10, int(request.query_params.get("page_size", 25))))
    except (TypeError, ValueError):
        page_number, page_size = 1, 25

    paginator = Paginator(clientes_qs, page_size)
    page = paginator.get_page(page_number)
    clientes = []

    catalogos = _catalogos_dinamicos(lineas)
    catalogo_resultados = {
        item["value"]: item
        for item in catalogos["resultados"]
    }

    for row in page.object_list:
        row["nombre"] = row.pop("expediente__cliente__nombre") or "Sin nombre"
        row["telefono"] = row.pop("expediente__cliente__telefono") or ""
        row["estado"] = row.pop("expediente__estado") or ""
        row["auto_interes"] = row.pop("expediente__auto_interes") or ""
        row["ultima_actividad"] = (
            row["ultima_actividad"].isoformat()
            if row["ultima_actividad"]
            else None
        )

        ultimo = catalogo_resultados.get(row["ultimo_resultado"] or "", {})
        row["ultimo_resultado_label"] = ultimo.get("label") or _label_abierto(
            row["ultimo_resultado"],
            LABELS_RESULTADO_BASE,
        )
        row["ultimo_resultado_grupo"] = ultimo.get("grupo") or _inferir_grupo_resultado(
            row["ultimo_resultado"]
        )
        clientes.append(row)

    lineas_payload = [
        {
            "numero": numero,
            "asesor_digital": WHATSAPP_LINES[numero].get("asesor_digital", ""),
            "agencia": WHATSAPP_LINES[numero].get("agencia", ""),
            "business": WHATSAPP_LINES[numero].get("business", ""),
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

    qs = (
        BitacoraAsesorDigital.objects
        .select_related("mensaje", "respuesta_mensaje")
        .filter(
            expediente=expediente,
            numero_asesor__in=([numero] if numero else lineas),
        )
        .order_by("-creado", "-id")[:200]
    )

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
            },
            "eventos": [_serializar_evento(item) for item in qs],
            "catalogos": _catalogos_dinamicos(lineas),
        }
    )


@api_view(["PATCH"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def analitica_evento_resultado_view(request, evento_id):
    lineas, error = _lineas_permitidas(request)

    if error:
        return error

    evento = (
        BitacoraAsesorDigital.objects
        .filter(
            evento_id=evento_id,
            numero_asesor__in=lineas,
        )
        .first()
    )

    if not evento:
        return Response(
            {"ok": False, "error": "Evento no encontrado."},
            status=status.HTTP_404_NOT_FOUND,
        )

    resultado = _clave_abierta(
        request.data.get("resultado", ""),
        "",
    )

    if not resultado:
        return Response(
            {"ok": False, "error": "El resultado es obligatorio."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    resultado_label = str(request.data.get("resultado_label", "") or "").strip()[:120]
    grupo_resultado = str(request.data.get("grupo_resultado", "") or "").strip().lower()

    if grupo_resultado and grupo_resultado not in GRUPOS_RESULTADO_VALIDOS:
        return Response(
            {
                "ok": False,
                "error": "El grupo del resultado no es válido.",
                "grupos_validos": sorted(GRUPOS_RESULTADO_VALIDOS),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not grupo_resultado:
        grupo_resultado = _inferir_grupo_resultado(resultado)

    if not resultado_label:
        resultado_label = _label_abierto(resultado, LABELS_RESULTADO_BASE)

    metadata = dict(evento.metadata or {})
    metadata["clasificacion_manual"] = True
    metadata["clasificado_por"] = _usuario_crm(request)
    metadata["clasificado_at"] = timezone.now().isoformat()
    metadata["grupo_resultado"] = grupo_resultado
    metadata["resultado_label"] = resultado_label

    evento.resultado = resultado
    evento.metadata = metadata
    evento.save(update_fields=["resultado", "metadata", "actualizado"])

    return Response(
        {
            "ok": True,
            "evento": _serializar_evento(evento),
        }
    )