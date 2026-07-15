from __future__ import annotations

import re
import unicodedata
from typing import Any

import requests
from django.core.cache import cache

from .contacto import MetaAPIError, _normalizar_template_meta, obtener_config_linea
from .sett import GRAPH_VERSION

CACHE_PREFIX = "whatsapp_templates"

REGLAS_UTILITY = [
    "Debe responder a una acción o solicitud específica que el cliente ya realizó.",
    "Debe informar, confirmar o actualizar un proceso existente: cita, pedido, pago, servicio, documento o solicitud.",
    "Evita promociones, descuentos, precios especiales, lanzamientos, invitaciones de compra y llamados comerciales.",
    "No mezcles una actualización operativa con recomendaciones de productos o ventas cruzadas.",
    "Usa variables solo para datos concretos del proceso: nombre, fecha, hora, folio, modelo solicitado o asesor asignado.",
    "El texto debe poder entenderse como una notificación necesaria, no como una campaña para generar interés.",
]

SENALES_MARKETING = {
    "promocion": 28,
    "promoción": 28,
    "oferta": 28,
    "descuento": 30,
    "bono": 24,
    "cashback": 30,
    "gratis": 25,
    "sin costo": 22,
    "precio especial": 30,
    "precio exclusivo": 30,
    "meses sin intereses": 30,
    "enganche desde": 28,
    "mensualidad desde": 28,
    "aprovecha": 24,
    "no te lo pierdas": 24,
    "por tiempo limitado": 28,
    "ultimos dias": 25,
    "últimos días": 25,
    "estrena": 24,
    "compra": 18,
    "cotiza": 18,
    "conoce nuestro": 18,
    "descubre": 16,
    "nuevo lanzamiento": 25,
    "tenemos para ti": 18,
    "te interesa": 16,
    "agenda una prueba": 18,
    "visitanos": 16,
    "visítanos": 16,
}

ANCLAS_UTILITY = [
    "confirmamos tu cita",
    "recordatorio de tu cita",
    "tu solicitud",
    "solicitud registrada",
    "seguimiento de tu solicitud",
    "actualizacion de tu solicitud",
    "actualización de tu solicitud",
    "folio",
    "pedido",
    "factura",
    "pago recibido",
    "pago pendiente",
    "servicio programado",
    "mantenimiento programado",
    "documento pendiente",
    "cambio solicitado",
    "prueba de manejo programada",
]


def _sin_acentos(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFD", str(value or ""))
        if unicodedata.category(char) != "Mn"
    )


def _texto_componentes(components: list[dict]) -> str:
    partes: list[str] = []

    for component in components or []:
        if not isinstance(component, dict):
            continue

        texto = str(component.get("text") or "").strip()
        if texto:
            partes.append(texto)

        for button in component.get("buttons") or []:
            if not isinstance(button, dict):
                continue
            for key in ("text", "url"):
                value = str(button.get(key) or "").strip()
                if value:
                    partes.append(value)

    return "\n".join(partes)


def analizar_riesgo_marketing(components: list[dict], category: str = "UTILITY") -> dict[str, Any]:
    texto_original = _texto_componentes(components)
    texto = _sin_acentos(texto_original).lower()
    hallazgos: list[dict[str, Any]] = []
    score = 0

    for frase, peso in SENALES_MARKETING.items():
        normalizada = _sin_acentos(frase).lower()
        if normalizada in texto:
            hallazgos.append({"tipo": "marketing", "texto": frase, "peso": peso})
            score += peso

    anclas = [ancla for ancla in ANCLAS_UTILITY if _sin_acentos(ancla).lower() in texto]

    if anclas:
        score = max(0, score - min(20, len(anclas) * 7))

    # Un llamado a responder puede ser operativo, pero eleva el riesgo si no existe
    # una referencia clara a una solicitud, cita o proceso previo.
    if any(frase in texto for frase in ("responde si", "confirmanos", "confírmanos", "quieres continuar")) and not anclas:
        hallazgos.append({"tipo": "contexto", "texto": "llamado a responder sin proceso previo claro", "peso": 14})
        score += 14

    score = min(100, score)
    nivel = "alto" if score >= 45 else "medio" if score >= 18 else "bajo"
    category = str(category or "UTILITY").upper().strip()

    return {
        "score": score,
        "nivel": nivel,
        "parece_marketing": nivel in ("medio", "alto"),
        "requiere_confirmacion": category == "UTILITY" and nivel in ("medio", "alto"),
        "hallazgos": hallazgos,
        "anclas_utility": anclas,
        "reglas_utility": REGLAS_UTILITY,
        "mensaje": (
            "El contenido tiene señales comerciales y Meta podría reclasificarlo como MARKETING."
            if category == "UTILITY" and nivel in ("medio", "alto")
            else "El contenido es compatible con una notificación operativa, sujeto a la revisión final de Meta."
        ),
    }


def _cache_key(numero_asesor: str) -> str:
    return f"{CACHE_PREFIX}:{numero_asesor}"


def invalidar_cache_plantillas(numero_asesor: str) -> None:
    cache.delete(_cache_key(numero_asesor))


def _token_linea(cfg: dict) -> str:
    token = str(cfg.get("access_token") or "").strip()
    if not token:
        raise ValueError("La línea no tiene access_token configurado.")
    return token


def _headers(cfg: dict) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_token_linea(cfg)}",
        "Content-Type": "application/json",
    }


def _error_body(response: requests.Response) -> dict:
    try:
        data = response.json()
        return data if isinstance(data, dict) else {"data": data}
    except Exception:
        return {"error": {"message": response.text or "Error desconocido de Meta."}}


def _raise_meta(response: requests.Response, message: str) -> None:
    if response.status_code < 400:
        return

    body = _error_body(response)
    error = body.get("error") if isinstance(body, dict) else {}
    is_transient = bool((error or {}).get("is_transient"))
    retryable = response.status_code in (408, 409, 425, 429, 500, 502, 503, 504) or is_transient

    raise MetaAPIError(
        status_code=response.status_code,
        error_body=body,
        retryable=retryable,
        attempts=1,
        message=message,
    )


def _waba_id(cfg: dict) -> str:
    value = str(cfg.get("waba_id") or "").strip()
    if not value:
        raise ValueError("Esta línea no tiene waba_id configurado en WHATSAPP_LINES.")
    return value


def listar_plantillas_meta(numero_asesor: str) -> list[dict]:
    cfg = obtener_config_linea(numero_asesor=numero_asesor)
    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{_waba_id(cfg)}/message_templates"
    params: dict[str, Any] = {
        "fields": "name,status,category,language,components,id",
        "limit": 100,
    }

    items: list[dict] = []
    paginas = 0

    while paginas < 10:
        response = requests.get(url, headers=_headers(cfg), params=params, timeout=(5, 30))
        _raise_meta(response, "Meta rechazó la consulta de plantillas.")
        data = response.json() if response.content else {}
        items.extend(data.get("data") or [])

        cursor = ((data.get("paging") or {}).get("cursors") or {}).get("after")
        if not cursor:
            break

        params["after"] = cursor
        paginas += 1

    salida = [_normalizar_template_meta(item) for item in items]
    return sorted(salida, key=lambda item: (item.get("title") or item.get("name") or "").lower())


def _normalizar_nombre(value: str) -> str:
    return re.sub(r"_+", "_", str(value or "").strip().lower().replace(" ", "_"))


def _variables(texto: str) -> list[int]:
    return sorted({int(value) for value in re.findall(r"\{\{(\d+)\}\}", str(texto or ""))})


def _validar_variables(texto: str, ejemplos: list[str], etiqueta: str) -> None:
    variables = _variables(texto)

    if variables and variables != list(range(1, max(variables) + 1)):
        raise ValueError(f"Las variables de {etiqueta} deben ser consecutivas desde {{1}}.")

    if variables and len(ejemplos) < len(variables):
        raise ValueError(f"Faltan ejemplos para las variables de {etiqueta}.")


def normalizar_componentes_plantilla(components: list[dict]) -> list[dict]:
    if not isinstance(components, list):
        raise ValueError("components debe ser una lista.")

    salida: list[dict] = []
    body_encontrado = False

    for raw in components:
        if not isinstance(raw, dict):
            continue

        tipo = str(raw.get("type") or "").upper().strip()

        if tipo == "HEADER":
            formato = str(raw.get("format") or "TEXT").upper().strip()
            item: dict[str, Any] = {"type": "HEADER", "format": formato}

            if formato == "TEXT":
                texto = str(raw.get("text") or "").strip()
                if not texto:
                    continue
                if len(texto) > 60:
                    raise ValueError("El encabezado no puede superar 60 caracteres.")

                ejemplos = list(((raw.get("example") or {}).get("header_text") or []))
                _validar_variables(texto, ejemplos, "encabezado")
                item["text"] = texto
                if _variables(texto):
                    item["example"] = {"header_text": [str(value) for value in ejemplos[: len(_variables(texto))]]}
            else:
                # Para IMAGE, VIDEO o DOCUMENT Meta exige un header_handle obtenido
                # mediante su flujo de carga. Se conserva cuando el frontend ya lo envía.
                handles = list(((raw.get("example") or {}).get("header_handle") or []))
                if handles:
                    item["example"] = {"header_handle": handles}
                elif raw.get("example"):
                    item["example"] = raw.get("example")

            salida.append(item)

        elif tipo == "BODY":
            texto = str(raw.get("text") or "").strip()
            if not texto:
                raise ValueError("El cuerpo de la plantilla es obligatorio.")
            if len(texto) > 1024:
                raise ValueError("El cuerpo no puede superar 1024 caracteres.")

            body_rows = list(((raw.get("example") or {}).get("body_text") or []))
            ejemplos = list(body_rows[0]) if body_rows and isinstance(body_rows[0], list) else []
            _validar_variables(texto, ejemplos, "cuerpo")

            item = {"type": "BODY", "text": texto}
            if _variables(texto):
                item["example"] = {"body_text": [[str(value) for value in ejemplos[: len(_variables(texto))]]]}

            salida.append(item)
            body_encontrado = True

        elif tipo == "FOOTER":
            texto = str(raw.get("text") or "").strip()
            if not texto:
                continue
            if len(texto) > 60:
                raise ValueError("El pie no puede superar 60 caracteres.")
            salida.append({"type": "FOOTER", "text": texto})

        elif tipo == "BUTTONS":
            botones: list[dict] = []

            for raw_button in raw.get("buttons") or []:
                if not isinstance(raw_button, dict):
                    continue

                button_type = str(raw_button.get("type") or "QUICK_REPLY").upper().strip()
                text = str(raw_button.get("text") or "").strip()

                if not text:
                    continue
                if len(text) > 25:
                    raise ValueError("El texto de cada botón no puede superar 25 caracteres.")

                button: dict[str, Any] = {"type": button_type, "text": text}

                if button_type == "URL":
                    url = str(raw_button.get("url") or "").strip()
                    if not url.startswith(("http://", "https://")):
                        raise ValueError("Los botones URL deben comenzar con http:// o https://.")
                    button["url"] = url
                    examples = raw_button.get("example") or []
                    if _variables(url) and not examples:
                        raise ValueError("El botón URL dinámico necesita un ejemplo.")
                    if examples:
                        button["example"] = [str(value) for value in examples]

                elif button_type == "PHONE_NUMBER":
                    phone = re.sub(r"[^0-9+]", "", str(raw_button.get("phone_number") or ""))
                    if not phone:
                        raise ValueError("El botón de llamada necesita phone_number.")
                    button["phone_number"] = phone

                elif button_type != "QUICK_REPLY":
                    raise ValueError(f"Tipo de botón no soportado por este editor: {button_type}.")

                botones.append(button)

            if botones:
                salida.append({"type": "BUTTONS", "buttons": botones[:3]})

    if not body_encontrado:
        raise ValueError("La plantilla debe incluir un componente BODY.")

    return salida


def _buscar_plantilla_linea(numero_asesor: str, template_id: str, name: str = "") -> dict:
    template_id = str(template_id or "").strip()
    name = str(name or "").strip()

    for item in listar_plantillas_meta(numero_asesor):
        if template_id and str(item.get("id") or "") == template_id:
            return item
        if name and str(item.get("name") or "") == name:
            return item

    raise ValueError("La plantilla no pertenece a la cuenta de WhatsApp de esta línea.")


def crear_plantilla_meta(numero_asesor: str, data: dict) -> dict:
    cfg = obtener_config_linea(numero_asesor=numero_asesor)
    name = _normalizar_nombre(data.get("name"))

    if not re.fullmatch(r"[a-z0-9_]{1,512}", name):
        raise ValueError("El nombre solo puede contener minúsculas, números y guion bajo.")

    language = str(data.get("language") or "es_MX").strip()
    category = str(data.get("category") or "UTILITY").upper().strip()

    if category not in ("UTILITY", "MARKETING"):
        raise ValueError("Este editor permite crear plantillas UTILITY o MARKETING.")

    components = normalizar_componentes_plantilla(data.get("components") or [])
    analysis = analizar_riesgo_marketing(components, category)

    if analysis["requiere_confirmacion"] and not bool(data.get("aceptar_riesgo_marketing")):
        error = ValueError(analysis["mensaje"])
        error.analysis = analysis
        raise error

    payload = {
        "name": name,
        "language": language,
        "category": category,
        "components": components,
        "allow_category_change": bool(data.get("allow_category_change", True)),
    }

    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{_waba_id(cfg)}/message_templates"
    response = requests.post(url, headers=_headers(cfg), json=payload, timeout=(5, 35))
    _raise_meta(response, "Meta rechazó la creación de la plantilla.")
    invalidar_cache_plantillas(numero_asesor)

    return {
        "meta": response.json() if response.content else {},
        "analysis": analysis,
        "payload": payload,
    }


def editar_plantilla_meta(numero_asesor: str, template_id: str, data: dict) -> dict:
    existente = _buscar_plantilla_linea(numero_asesor, template_id, str(data.get("name") or ""))
    status = str(existente.get("status") or "").upper()

    if status not in ("APPROVED", "REJECTED", "PAUSED"):
        raise ValueError("Meta solo permite editar plantillas APPROVED, REJECTED o PAUSED.")

    category = str(data.get("category") or existente.get("category") or "UTILITY").upper().strip()
    components = normalizar_componentes_plantilla(data.get("components") or [])
    analysis = analizar_riesgo_marketing(components, category)

    if analysis["requiere_confirmacion"] and not bool(data.get("aceptar_riesgo_marketing")):
        error = ValueError(analysis["mensaje"])
        error.analysis = analysis
        raise error

    payload: dict[str, Any] = {
        "category": category,
        "components": components,
    }

    if data.get("message_send_ttl_seconds") not in (None, ""):
        payload["message_send_ttl_seconds"] = int(data["message_send_ttl_seconds"])

    cfg = obtener_config_linea(numero_asesor=numero_asesor)
    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{template_id}"
    response = requests.post(url, headers=_headers(cfg), json=payload, timeout=(5, 35))
    _raise_meta(response, "Meta rechazó la edición de la plantilla.")
    invalidar_cache_plantillas(numero_asesor)

    return {
        "meta": response.json() if response.content else {},
        "analysis": analysis,
        "payload": payload,
    }


def eliminar_plantilla_meta(numero_asesor: str, template_id: str, name: str) -> dict:
    existente = _buscar_plantilla_linea(numero_asesor, template_id, name)
    cfg = obtener_config_linea(numero_asesor=numero_asesor)
    params = {
        "hsm_id": str(existente.get("id") or template_id),
        "name": str(existente.get("name") or name),
    }
    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{_waba_id(cfg)}/message_templates"
    response = requests.delete(url, headers=_headers(cfg), params=params, timeout=(5, 30))
    _raise_meta(response, "Meta rechazó la eliminación de la plantilla.")
    invalidar_cache_plantillas(numero_asesor)

    return response.json() if response.content else {"success": True}
