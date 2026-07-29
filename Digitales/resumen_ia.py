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

# -----------------------------------------------------------------------------
# Resumen analítico de la atención del asesor
# -----------------------------------------------------------------------------

PROMPT_RESUMEN_ATENCION = """
Eres un auditor de calidad comercial para un CRM automotriz Volkswagen.

Analiza la conversación y la bitácora de acciones. Tu objetivo no es repetir mensajes,
sino explicar qué hizo el asesor, cómo reaccionó el cliente y qué debe hacerse después.

Reglas obligatorias:
- No inventes datos ni resultados comerciales.
- Distingue claramente asesor humano, cliente e IA.
- No premies como interés una respuesta de cortesía aislada.
- Considera interés únicamente cuando el cliente pide información concreta, cotización,
  crédito, disponibilidad, cita, llamada, visita o expresa intención de compra.
- Si el asesor envió contacto y el cliente no respondió, indícalo claramente.
- Si el cliente escribió y no existe atención humana posterior, marca la atención como crítica.
- Si la IA estaba activa, menciona si apoyó o si la conversación terminó requiriendo atención humana.
- Redacta en español, con lenguaje ejecutivo y fácil de medir.

Devuelve exclusivamente el objeto JSON solicitado por el esquema.
"""

GEMINI_RESUMEN_ATENCION_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "resumen_acciones": {"type": "STRING"},
        "estado_atencion": {
            "type": "STRING",
            "enum": [
                "sin_atencion",
                "esperando_cliente",
                "cliente_interesado",
                "seguimiento_activo",
                "atencion_completada",
                "atencion_mejorable",
                "atencion_critica",
                "sin_datos",
            ],
        },
        "evaluacion": {"type": "STRING"},
        "siguiente_accion": {"type": "STRING"},
        "calidad": {
            "type": "STRING",
            "enum": ["buena", "mejorable", "critica", "sin_datos"],
        },
        "interes_detectado": {"type": "BOOLEAN"},
    },
    "required": [
        "resumen_acciones",
        "estado_atencion",
        "evaluacion",
        "siguiente_accion",
        "calidad",
        "interes_detectado",
    ],
}


def _evento_a_linea(evento) -> str:
    creado = getattr(evento, "creado", None)
    fecha = creado.strftime("%Y-%m-%d %H:%M:%S") if creado else ""
    accion = _limpiar_texto(getattr(evento, "accion", ""))
    detalle = _limpiar_texto(getattr(evento, "detalle", ""))
    resultado = _limpiar_texto(getattr(evento, "resultado", ""))
    respuesta = _limpiar_texto(getattr(evento, "respuesta_texto", ""))

    partes = [f"[{fecha}] Acción: {accion or 'Sin descripción'}"]

    if detalle:
        partes.append(f"Detalle: {detalle}")

    if resultado:
        partes.append(f"Clasificación interna: {resultado}")

    if respuesta:
        partes.append(f"Respuesta del cliente: {respuesta}")

    return " | ".join(partes)


def construir_contexto_atencion(*, mensajes, eventos, estado_ia: dict | None = None) -> str:
    conversacion = construir_conversacion_para_resumen(mensajes)
    bitacora = "\n".join(_evento_a_linea(evento) for evento in eventos)
    estado_ia = estado_ia if isinstance(estado_ia, dict) else {}

    return (
        "ESTADO DE IA\n"
        f"{json.dumps(estado_ia, ensure_ascii=False)}\n\n"
        "CONVERSACIÓN\n"
        f"{conversacion or 'Sin mensajes disponibles'}\n\n"
        "BITÁCORA DEL ASESOR\n"
        f"{bitacora or 'Sin acciones registradas'}"
    ).strip()


def _normalizar_resumen_atencion(data: dict, *, fuente: str) -> dict:
    estado_valido = {
        "sin_atencion",
        "esperando_cliente",
        "cliente_interesado",
        "seguimiento_activo",
        "atencion_completada",
        "atencion_mejorable",
        "atencion_critica",
        "sin_datos",
    }
    calidad_valida = {"buena", "mejorable", "critica", "sin_datos"}

    estado = str(data.get("estado_atencion") or "sin_datos").strip().lower()
    calidad = str(data.get("calidad") or "sin_datos").strip().lower()

    return {
        "resumen_acciones": _limitar_palabras(
            data.get("resumen_acciones"),
            42,
            "No hay información suficiente para resumir la atención.",
        ),
        "estado_atencion": estado if estado in estado_valido else "sin_datos",
        "evaluacion": _limitar_palabras(
            data.get("evaluacion"),
            24,
            "No hay evidencia suficiente para evaluar la atención.",
        ),
        "siguiente_accion": _limitar_palabras(
            data.get("siguiente_accion"),
            20,
            "Revisar la conversación y definir el siguiente contacto.",
        ),
        "calidad": calidad if calidad in calidad_valida else "sin_datos",
        "interes_detectado": bool(data.get("interes_detectado", False)),
        "generado_por_ia": fuente == "gemini",
        "fuente": fuente,
    }


def generar_resumen_atencion_fallback(*, eventos, estado_ia: dict | None = None) -> dict:
    eventos = list(eventos or [])
    contacto = [
        item
        for item in eventos
        if str(getattr(item, "tipo", "") or "") in {"mensaje", "plantilla", "media"}
    ]
    respondidos = [item for item in contacto if getattr(item, "respondido_at", None)]
    positivos = [
        item
        for item in contacto
        if str(getattr(item, "resultado", "") or "") == "respuesta_positiva"
    ]
    sin_respuesta = [
        item
        for item in contacto
        if str(getattr(item, "resultado", "") or "") == "sin_respuesta"
    ]
    pendientes = [
        item
        for item in contacto
        if str(getattr(item, "resultado", "") or "") == "pendiente"
    ]

    if not eventos:
        data = {
            "resumen_acciones": "No existen acciones registradas del asesor para este prospecto.",
            "estado_atencion": "sin_atencion",
            "evaluacion": "No es posible medir la atención sin eventos registrados.",
            "siguiente_accion": "Revisar el chat y realizar el primer contacto humano.",
            "calidad": "sin_datos",
            "interes_detectado": False,
        }
    elif positivos:
        data = {
            "resumen_acciones": "El asesor dio seguimiento y el cliente respondió con señales concretas de interés comercial.",
            "estado_atencion": "cliente_interesado",
            "evaluacion": "La atención logró una respuesta comercial positiva; falta convertir el interés en una acción concreta.",
            "siguiente_accion": "Confirmar vehículo, forma de pago y agendar llamada o visita.",
            "calidad": "buena",
            "interes_detectado": True,
        }
    elif respondidos:
        data = {
            "resumen_acciones": "El asesor contactó al cliente y recibió respuesta, pero todavía no existe una señal comercial concluyente.",
            "estado_atencion": "seguimiento_activo",
            "evaluacion": "Existe conversación activa; el asesor debe profundizar el perfilamiento y cerrar el siguiente compromiso.",
            "siguiente_accion": "Preguntar necesidad, presupuesto, forma de pago y plazo de compra.",
            "calidad": "mejorable",
            "interes_detectado": False,
        }
    elif sin_respuesta and not pendientes:
        data = {
            "resumen_acciones": "El asesor realizó intentos de contacto, pero el cliente no respondió dentro de la ventana de 48 horas.",
            "estado_atencion": "esperando_cliente",
            "evaluacion": "Hubo seguimiento sin respuesta; conviene variar horario, mensaje y canal antes de cerrar el prospecto.",
            "siguiente_accion": "Programar un recontacto breve con propuesta de valor específica.",
            "calidad": "mejorable",
            "interes_detectado": False,
        }
    else:
        data = {
            "resumen_acciones": "El asesor inició contacto y la conversación continúa dentro de la ventana de seguimiento.",
            "estado_atencion": "seguimiento_activo",
            "evaluacion": "La atención sigue abierta y aún no puede calificarse como respondida o sin respuesta.",
            "siguiente_accion": "Dar seguimiento sin duplicar mensajes y respetar la ventana vigente.",
            "calidad": "mejorable",
            "interes_detectado": False,
        }

    estado_ia = estado_ia if isinstance(estado_ia, dict) else {}
    if estado_ia.get("estado") == "activa":
        data["evaluacion"] = f"{data['evaluacion']} La IA estaba habilitada para apoyar el chat."

    return _normalizar_resumen_atencion(data, fuente="reglas")


def generar_resumen_atencion_con_gemini(
    *,
    mensajes,
    eventos,
    telefono: str = "",
    estado_ia: dict | None = None,
) -> dict:
    mensajes = list(mensajes or [])
    eventos = list(eventos or [])

    if not mensajes and not eventos:
        return generar_resumen_atencion_fallback(eventos=eventos, estado_ia=estado_ia)

    contexto = construir_contexto_atencion(
        mensajes=mensajes,
        eventos=eventos,
        estado_ia=estado_ia,
    )

    client = _get_gemini_client()
    modelo = getattr(
        settings,
        "GEMINI_ANALYTICS_MODEL",
        getattr(
            settings,
            "GEMINI_SUMMARY_MODEL",
            getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash"),
        ),
    )

    contenido = (
        f"Teléfono del prospecto: {telefono or 'No disponible'}\n\n"
        "Genera una lectura ejecutiva de la atención con base exclusivamente en el contexto:\n\n"
        f"{contexto}"
    )

    try:
        response = client.models.generate_content(
            model=modelo,
            contents=contenido,
            config=types.GenerateContentConfig(
                system_instruction=PROMPT_RESUMEN_ATENCION,
                response_mime_type="application/json",
                response_schema=GEMINI_RESUMEN_ATENCION_SCHEMA,
                temperature=0.15,
            ),
        )
        data = _parsear_respuesta_json(getattr(response, "text", "") or "")

        if not data:
            raise RuntimeError("Gemini no devolvió un resumen analítico válido")

        return _normalizar_resumen_atencion(data, fuente="gemini")
    except Exception:
        logger.exception(
            "Error generando resumen de atención | telefono=%s modelo=%s",
            telefono,
            modelo,
        )
        return generar_resumen_atencion_fallback(eventos=eventos, estado_ia=estado_ia)