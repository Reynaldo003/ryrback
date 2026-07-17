# jdpower/ia_resumen.py
import json
import logging
import os

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def _armar_prompt(tipo_modulo, metricas, comparacion, alertas, comentarios):
    comentarios_texto = "\n".join(
        f"- ({c['origen']}, calificación={c['calificacion']}): {c['texto']}"
        for c in comentarios[:150]
    ) or "No hay comentarios de texto capturados en este periodo."

    return f"""
Eres un analista de calidad para una agencia Volkswagen (Grupo Automotriz R&R).
Analiza estos datos de encuestas JD Power de {tipo_modulo} y genera un reporte
ejecutivo en español, claro, directo y accionable para un gerente de agencia.
NO inventes cifras: usa exclusivamente los datos que te doy abajo. Los números
(NPS, satisfacción, variaciones) ya vienen calculados, tú solo los interpretas
y redactas. Tu único trabajo de análisis original es identificar patrones y
temas recurrentes dentro de los comentarios de texto de clientes.

=== MÉTRICAS DEL PERIODO ACTUAL ===
{json.dumps(metricas, ensure_ascii=False, indent=2)}

=== COMPARACIÓN VS PERIODO ANTERIOR ===
{json.dumps(comparacion, ensure_ascii=False, indent=2)}

=== CONCESIONARIAS EN ALERTA (caída de NPS o satisfacción vs periodo anterior) ===
{json.dumps(alertas, ensure_ascii=False, indent=2)}

=== COMENTARIOS DE CLIENTES (muestra, ordenados de peor a mejor calificación) ===
{comentarios_texto}

Responde ÚNICAMENTE con JSON válido, sin markdown ni texto fuera del JSON,
con esta forma EXACTA:
{{
  "resumen_ejecutivo": "3 a 5 líneas con lo más importante del periodo, tono directo de reporte gerencial",
  "tendencia": "1 a 2 líneas sobre cómo ha evolucionado la satisfacción y el NPS",
  "top_quejas": [
    {{
      "tema": "nombre corto del problema (máx 6 palabras)",
      "frecuencia": "alta|media|baja",
      "detalle": "1 línea explicando el patrón detectado en los comentarios",
      "ejemplo": "frase corta representativa de un comentario real, máximo 20 palabras, sin inventar"
    }}
  ],
  "fortalezas": ["puntos positivos detectados en los comentarios, máximo 3 elementos"],
  "recomendaciones": ["acciones concretas y accionables sugeridas, máximo 3 elementos"]
}}

Reglas:
- Máximo 5 elementos en top_quejas. Si no hay suficientes comentarios negativos, incluye menos.
- Si no hay comentarios de texto, deja top_quejas y fortalezas como listas vacías y dilo en resumen_ejecutivo.
- "ejemplo" debe ser una frase que realmente aparezca (o muy cercana) en los comentarios dados, nunca inventada.
"""


def generar_resumen_ia(*, tipo_modulo, metricas, comparacion, alertas, comentarios):
    if not GEMINI_API_KEY:
        logger.error("IA JDPower: falta GEMINI_API_KEY en variables de entorno.")
        return {
            "ok": False,
            "error": "GEMINI_API_KEY no está configurada en el servidor.",
        }

    prompt = _armar_prompt(tipo_modulo, metricas, comparacion, alertas, comentarios)
    texto = ""

    try:
        client = _get_client()

        chat = client.chats.create(
            model="gemini-3.5-flash",
            config=types.GenerateContentConfig(temperature=0.4),
        )

        response = chat.send_message(prompt)
        texto = (response.text or "").strip()
        texto = texto.replace("```json", "").replace("```", "").strip()

        data = json.loads(texto)

        return {
            "ok": True,
            "resumen_ejecutivo": data.get("resumen_ejecutivo", ""),
            "tendencia": data.get("tendencia", ""),
            "top_quejas": data.get("top_quejas", []),
            "fortalezas": data.get("fortalezas", []),
            "recomendaciones": data.get("recomendaciones", []),
        }

    except json.JSONDecodeError as e:
        logger.error(
            "IA JDPower: respuesta no es JSON válido: %s | texto=%s",
            e,
            texto[:500],
        )
        return {"ok": False, "error": "La IA no devolvió un JSON válido."}

    except Exception as e:
        logger.exception("IA JDPower: error generando resumen: %s", str(e))
        return {"ok": False, "error": str(e)}