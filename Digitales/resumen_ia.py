from __future__ import annotations

import json
import logging
from functools import lru_cache

from django.conf import settings
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


PROMPT_RESUMEN = """
Eres un analista comercial experto en conversaciones de WhatsApp dentro de un CRM automotriz.

Tu tarea es leer TODA la conversación y redactar un resumen general, detallado y útil para seguimiento comercial.

Debes identificar, cuando exista en la conversación:
- nombre del prospecto
- vehículo o versión de interés
- año o modelo mencionado
- uso o necesidad del vehículo
- nivel de interés del prospecto
- si pidió cotización
- si pidió crédito, financiamiento, arrendamiento o plan tradicional
- si pidió que lo contacte un asesor
- objeciones, dudas o aclaraciones importantes
- errores o deficiencias en la calidad de respuesta de la IA o del asesor
- si el prospecto dejó de responder
- siguiente paso comercial sugerido
- recomendacion para mejorar la calidad de atencion o si esta bien atendido el cliente

Reglas:
- No inventes datos.
- Si algo no aparece, simplemente no lo menciones.
- El resumen debe estar redactado en español.
- Debe ser un texto corrido, claro, útil, profesional y entendible para un asesor.
- Debe sonar como nota comercial interna de CRM.
- No uses viñetas.
- No regreses JSON.
- No repitas literalmente toda la conversación.
- El resumen general maximo 30 palabras. Adicionalmente agrega un parrafo de status actual del prospecto max 5 palabras, otro parrafo de retroalimentacion max 15 palabras,
  otro parrafo para la deficiencia de la atencion al prospecto, deficiencia de la IA o asesor si es que se involucro max 20 palabras, otro parrafo para definir cual es el
  siguiente paso recomendable a seguir max 15 palabras y uno ultimo para dar una recomendacion extra para continuar con el proceso de prospeccion e incrementar la probabilidad
  de que se lleve a cabo la venta max 30 palabras.
- El formato que debes devolver es:
  Resumen General:
  Status:
  Retroalimentacion:
  Deficiencia:
  Siguiente paso:
  Recomendacion:
"""

GEMINI_RESUMEN_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "resumen_general": {"type": "STRING"},
        "status": {"type": "STRING"},
        "retroalimentacion": {"type": "STRING"},
        "deficiencia": {"type": "STRING"},
        "siguiente_paso": {"type": "STRING"},
        "recomendacion": {"type": "STRING"},
    },
    "required": [
        "resumen_general",
        "status",
        "retroalimentacion",
        "deficiencia",
        "siguiente_paso",
        "recomendacion",
    ],
}


@lru_cache(maxsize=1)
def _get_gemini_client():
    """Crea una sola instancia del cliente de Gemini por proceso de Django."""
    api_key = str(getattr(settings, "GEMINI_API_KEY", "") or "").strip()

    if not api_key:
        raise RuntimeError("Falta configurar GEMINI_API_KEY en settings.py")

    return genai.Client(api_key=api_key)


def _rol_mensaje(msg) -> str:
    """Diferencia prospecto, IA y asesor humano usando direction y raw."""
    if getattr(msg, "direction", "") == "in":
        return "Prospecto"

    raw = getattr(msg, "raw", None)
    raw = raw if isinstance(raw, dict) else {}

    es_ia = bool(
        raw.get("ia_provider")
        or raw.get("ia_model")
        or raw.get("gemini_model")
        or raw.get("openai_model")
        or raw.get("decision")
    )

    if es_ia:
        return "IA"

    if raw.get("origen") == "asesor_humano":
        return "Asesor humano"

    # Los mensajes salientes antiguos pueden no tener metadata de origen.
    return "Asesor o IA"


def construir_conversacion_para_resumen(mensajes) -> str:
    lineas: list[str] = []

    for msg in mensajes:
        texto = str(getattr(msg, "body", "") or "").strip()

        if not texto:
            continue

        rol = _rol_mensaje(msg)
        created_at = getattr(msg, "created_at", None)
        fecha = created_at.strftime("%Y-%m-%d %H:%M:%S") if created_at else ""

        lineas.append(f"[{fecha}] {rol}: {texto}")

    return "\n".join(lineas).strip()


def _limpiar_texto(valor) -> str:
    """Evita saltos de línea inesperados dentro de cada campo del resumen."""
    return " ".join(str(valor or "").split()).strip()


def _limitar_palabras(valor, limite: int, default: str) -> str:
    texto = _limpiar_texto(valor) or default
    palabras = texto.split()

    if len(palabras) <= limite:
        return texto

    return " ".join(palabras[:limite]).rstrip(".,;:") + "."


def _parsear_respuesta_json(texto: str) -> dict:
    texto = str(texto or "").strip()

    if not texto:
        return {}

    try:
        resultado = json.loads(texto)
        return resultado if isinstance(resultado, dict) else {}
    except json.JSONDecodeError:
        logger.warning("Gemini devolvió un resumen que no era JSON válido: %s", texto[:500])
        return {}


def _formatear_resumen(data: dict) -> str:
    resumen_general = _limitar_palabras(
        data.get("resumen_general"),
        30,
        "No hay información suficiente para generar un resumen comercial.",
    )
    status = _limitar_palabras(
        data.get("status"),
        5,
        "Sin información suficiente",
    )
    retroalimentacion = _limitar_palabras(
        data.get("retroalimentacion"),
        15,
        "No identificada",
    )
    deficiencia = _limitar_palabras(
        data.get("deficiencia"),
        20,
        "Sin deficiencias relevantes",
    )
    siguiente_paso = _limitar_palabras(
        data.get("siguiente_paso"),
        15,
        "Revisar la conversación manualmente",
    )
    recomendacion = _limitar_palabras(
        data.get("recomendacion"),
        30,
        "Confirmar interés, presupuesto, forma de pago y plazo de compra antes del siguiente contacto.",
    )

    return (
        f"Resumen General: {resumen_general}\n"
        f"Status: {status}\n"
        f"Retroalimentacion: {retroalimentacion}\n"
        f"Deficiencia: {deficiencia}\n"
        f"Siguiente paso: {siguiente_paso}\n"
        f"Recomendacion: {recomendacion}"
    )


def generar_resumen_con_gemini(*, mensajes, telefono: str = "") -> str:
    texto_conversacion = construir_conversacion_para_resumen(mensajes)

    if not texto_conversacion:
        return ""

    contenido_usuario = f"""
Teléfono del prospecto: {telefono or "No disponible"}

Analiza la siguiente conversación completa y genera el resumen comercial solicitado:

{texto_conversacion}
""".strip()

    client = _get_gemini_client()
    modelo = getattr(
        settings,
        "GEMINI_SUMMARY_MODEL",
        getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash"),
    )

    try:
        response = client.models.generate_content(
            model=modelo,
            contents=contenido_usuario,
            config=types.GenerateContentConfig(
                system_instruction=PROMPT_RESUMEN,
                response_mime_type="application/json",
                response_schema=GEMINI_RESUMEN_SCHEMA,
                temperature=0.2,
            ),
        )

        data = _parsear_respuesta_json(getattr(response, "text", "") or "")

        if not data:
            raise RuntimeError("Gemini no devolvió un resumen estructurado válido")

        return _formatear_resumen(data)

    except Exception:
        logger.exception(
            "Error generando resumen con Gemini | telefono=%s modelo=%s",
            telefono,
            modelo,
        )
        raise


# Alias temporal para no romper cualquier import antiguo que todavía exista.
def generar_resumen_con_openai(*, mensajes, telefono: str = "") -> str:
    return generar_resumen_con_gemini(
        mensajes=mensajes,
        telefono=telefono,
    )