# digitales/contacto.py
import mimetypes
import requests
from .sett import whatsapp_url, whatsapp_token

DEFAULT_IDIOMA = "es"


def _meta_error(r):
    try:
        return r.json()
    except Exception:
        return {"text": r.text}


def _graph_base_from_messages_url(messages_url: str) -> str:
    u = (messages_url or "").strip().rstrip("/")
    if not u:
        return ""
    if u.endswith("/messages"):
        return u[: -len("/messages")]
    return u


def enviar_template_whatsapp(
    to: str,
    template_name: str,
    params: list[str] | None = None,
    idioma: str = DEFAULT_IDIOMA,
    components: list[dict] | None = None,
) -> dict:
    """
    - Si components viene, se usa tal cual (header/body/footer).
    - Si NO viene components, se asume BODY con params (compatibilidad hacia atrás).
    """
    if not to:
        raise ValueError("Falta número destino")
    if not template_name:
        raise ValueError("Falta template_name")

    headers = {
        "Authorization": f"Bearer {whatsapp_token}",
        "Content-Type": "application/json",
    }

    if components:
        # Normaliza a formato Meta: type en MAYÚSCULA y parameters igual
        norm_components = []
        for c in components:
            ctype = str(c.get("type", "")).upper()
            if ctype not in ("HEADER", "BODY", "FOOTER", "BUTTONS"):
                continue
            item = {"type": ctype}
            if "parameters" in c:
                item["parameters"] = c["parameters"]
            if "sub_type" in c:
                item["sub_type"] = c["sub_type"]
            if "index" in c:
                item["index"] = c["index"]
            norm_components.append(item)

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": idioma},
                "components": norm_components,
            },
        }
    else:
        # compat: solo BODY con params
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": idioma},
                "components": [
                    {
                        "type": "body",
                        "parameters": [{"type": "text", "text": str(x)} for x in (params or [])],
                    }
                ],
            },
        }

    r = requests.post(whatsapp_url, headers=headers, json=payload, timeout=20)
    if r.status_code >= 400:
        err = _meta_error(r)
        raise RuntimeError(f"Meta error {r.status_code}: {err}")
    return r.json()

def enviar_texto_whatsapp(to: str, text: str) -> dict:
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {whatsapp_token}",
    }

    r = requests.post(whatsapp_url, headers=headers, json=payload, timeout=20)
    if r.status_code >= 400:
        raise RuntimeError(f"Meta error {r.status_code}: {r.text}")
    return r.json()


def subir_media_whatsapp(file_obj, filename: str | None = None, content_type: str | None = None) -> dict:
    """
    Sube un archivo a WhatsApp Cloud y devuelve respuesta que incluye:
    { "id": "<MEDIA_ID>" }
    """
    base = _graph_base_from_messages_url(whatsapp_url)
    if not base:
        raise RuntimeError("No se pudo derivar base URL de WhatsApp (whatsapp_url inválida).")

    media_url = f"{base}/media"

    headers = {
        "Authorization": f"Bearer {whatsapp_token}",
        # OJO: en multipart NO se manda Content-Type manual
    }

    # intenta inferir content-type
    ct = content_type or ""
    if not ct and filename:
        ct = mimetypes.guess_type(filename)[0] or ""

    files = {
        "file": (filename or getattr(file_obj, "name", "file"), file_obj, ct or "application/octet-stream"),
    }

    data = {
        "messaging_product": "whatsapp",
        # opcional: "type": ct (Meta lo acepta, pero no siempre requerido)
    }

    r = requests.post(media_url, headers=headers, files=files, data=data, timeout=45)
    if r.status_code >= 400:
        err = _meta_error(r)
        raise RuntimeError(f"Meta media upload error {r.status_code}: {err}")
    return r.json()


def enviar_media_whatsapp(to: str, media_id: str, media_type: str, caption: str = "", filename: str = "") -> dict:
    """
    Envía media ya subida (media_id) como image/document/video/audio.
    """
    if media_type not in ("image", "document", "video", "audio"):
        raise ValueError("media_type inválido")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {whatsapp_token}",
    }

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": media_type,
        media_type: {
            "id": media_id,
        },
    }

    # caption aplica a image/video/document (en audio normalmente no)
    if caption and media_type in ("image", "video", "document"):
        payload[media_type]["caption"] = caption

    # filename aplica a document
    if filename and media_type == "document":
        payload[media_type]["filename"] = filename

    r = requests.post(whatsapp_url, headers=headers, json=payload, timeout=20)
    if r.status_code >= 400:
        err = _meta_error(r)
        raise RuntimeError(f"Meta send media error {r.status_code}: {err}")
    return r.json()


def obtener_mensaje_whatsapp(message: dict) -> str:
    if not isinstance(message, dict) or "type" not in message:
        return "mensaje no reconocido"

    t = message["type"]
    if t == "text":
        return message.get("text", {}).get("body", "")
    if t == "button":
        return message.get("button", {}).get("text", "")
    if t == "interactive":
        it = message.get("interactive", {})
        if it.get("type") == "list_reply":
            return it.get("list_reply", {}).get("title", "")
        if it.get("type") == "button_reply":
            return it.get("button_reply", {}).get("title", "")
    # media entrante (si lo quieres manejar mejor después)
    if t in ("image", "document", "video", "audio", "sticker"):
        return f"[{t.upper()}]"
    return "mensaje no procesado"


def replace_start(s: str) -> str:
    s = "".join(c for c in str(s or "") if c.isdigit())
    if s.startswith("521"):
        return "52" + s[3:]
    return s

def editar_texto_whatsapp(to: str, original_message_id: str, new_text: str) -> dict:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {whatsapp_token}",
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        # 🔑 referencia al mensaje a editar (según spec de Meta)
        "context": {"message_id": original_message_id},
        "text": {"body": new_text},
    }

    r = requests.post(whatsapp_url, headers=headers, json=payload, timeout=20)
    if r.status_code >= 400:
        raise RuntimeError(f"Meta edit error {r.status_code}: {r.text}")
    return r.json()