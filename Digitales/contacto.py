# digitales/contacto.py
import requests
from .sett import whatsapp_url, whatsapp_token

DEFAULT_IDIOMA = "es"

def _meta_error(r):
    try:
        return r.json()
    except Exception:
        return {"text": r.text}
    
def enviar_template_whatsapp(to: str, template_name: str, params: list[str], idioma: str = DEFAULT_IDIOMA) -> dict:
    if not to:
        raise ValueError("Falta número destino")
    if not template_name:
        raise ValueError("Falta template_name")
    headers = {
        "Authorization": f"Bearer {whatsapp_token}",
        "Content-Type": "application/json",
    }

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
    return "mensaje no procesado"


def replace_start(s: str) -> str:
    s = "".join(c for c in str(s or "") if c.isdigit())
    if s.startswith("521"):
        return "52" + s[3:]
    return s
