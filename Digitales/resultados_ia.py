#Digitales/resultados_ia.py
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import time as time_module
from collections import Counter, defaultdict
from datetime import datetime, time as datetime_time, timedelta
from statistics import median
from typing import Any
from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, Max, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from openai import OpenAI

from CrmConformidad.jwt_authentication import CRMJWTAuthentication
from citas.models import normaliza_tel_mx
from meta_ads.models import CampanaMeta as CampanaMetaAds

from .models import ExpedienteDigital, MensajeWhatsApp
from .sett import WHATSAPP_LINES

logger = logging.getLogger(__name__)

OPENAI_PRESUPUESTO_SEGUNDOS = 120
MAX_LOTE_CHARS = 60_000
MAX_CONVERSACION_CHARS = 55_000
CACHE_SECONDS = 60 * 30
BUSINESS_COMERCIALES = {"nuevos", "usados", "comerciales"}
DIAS_SEMANA = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")
HORARIO_RESPUESTA_PREDETERMINADO = {
    "lunes": {"activo": True, "inicio": "09:00", "fin": "18:00"},
    "martes": {"activo": True, "inicio": "09:00", "fin": "18:00"},
    "miercoles": {"activo": True, "inicio": "09:00", "fin": "18:00"},
    "jueves": {"activo": True, "inicio": "09:00", "fin": "18:00"},
    "viernes": {"activo": True, "inicio": "09:00", "fin": "18:00"},
    "sabado": {"activo": True, "inicio": "09:00", "fin": "14:00"},
    "domingo": {"activo": False, "inicio": "09:00", "fin": "14:00"},
}
PAUSA_COMIDA_PREDETERMINADA = {
    "activo": True,
    "inicio": "14:00",
    "fin": "15:00",
    "dias": ["lunes", "martes", "miercoles", "jueves", "viernes"],
}

PROMPT_AUDITORIA = """
Eres un auditor comercial senior especializado en venta automotriz por WhatsApp.
Analizas conversaciones reales de un CRM de Grupo Automotriz R&R.

Contexto del negocio:
- Business Nuevos y Comerciales: venta de vehículos Volkswagen.
- Business Usados: venta de seminuevos/usados de cualquier marca disponible.
- Debes distinguir cliente, asesor humano e IA.
- Evalúa la atención con criterio comercial: rapidez, claridad, seguimiento, perfilamiento,
  manejo de objeciones, llamada a la acción y avance hacia cotización/cita/venta.
- No consideres "gracias", "ok" o respuestas de cortesía como interés de compra por sí solas.
- Interés comercial real requiere señales como precio, disponibilidad, versión, cotización,
  financiamiento, mensualidad, enganche, crédito, toma de auto, cita, visita o intención de compra.
- No inventes datos. No asumas una venta si no existe evidencia.
- Si el cliente escribió y no hubo respuesta humana posterior, la atención debe considerarse deficiente SOLO cuando sin_respuesta_humana_evaluable=true.
- Si espera_fuera_horario=true o medicion_tiempo_habilitada=false, no penalices al asesor por rapidez ni por ausencia de respuesta en ese tramo.
- tiempo_primera_respuesta_segundos ya representa tiempo HÁBIL, no tiempo calendario.
- Si la IA atendió pero luego era necesaria intervención humana y no ocurrió, señálalo.
- Usa las métricas objetivas proporcionadas; no recalcules tiempos imaginarios.
- Devuelve exclusivamente JSON compatible con el esquema.
"""

AUDITORIA_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "conversaciones": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "id": {"type": "STRING"},
                    "nivel_interes": {"type": "STRING", "enum": ["alto", "medio", "bajo", "nulo"]},
                    "senal_compra": {"type": "BOOLEAN"},
                    "intenciones": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "vehiculos_interes": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "calidad_atencion": {"type": "STRING", "enum": ["excelente", "buena", "mejorable", "deficiente", "critica"]},
                    "puntaje_atencion": {"type": "INTEGER"},
                    "mal_atendido": {"type": "BOOLEAN"},
                    "cliente_dejo_responder": {"type": "BOOLEAN"},
                    "riesgo_perdida": {"type": "STRING", "enum": ["alto", "medio", "bajo"]},
                    "deficiencias": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "objeciones": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "causa_perdida_probable": {"type": "STRING"},
                    "siguiente_accion": {"type": "STRING"},
                    "recomendacion_asesor": {"type": "STRING"},
                    "resumen": {"type": "STRING"},
                },
                "required": [
                    "id", "nivel_interes", "senal_compra", "intenciones", "vehiculos_interes",
                    "calidad_atencion", "puntaje_atencion", "mal_atendido", "cliente_dejo_responder",
                    "riesgo_perdida", "deficiencias", "objeciones", "causa_perdida_probable",
                    "siguiente_accion", "recomendacion_asesor", "resumen",
                ],
            },
        }
    },
    "required": ["conversaciones"],
}

PROMPT_EJECUTIVO = """
Eres director comercial y auditor de calidad de un grupo automotriz.
Recibirás métricas objetivas, auditorías de conversaciones y desempeño de campañas Meta.

Tu objetivo es explicar qué está frenando las ventas y qué acciones tienen mayor probabilidad de mejorar el resultado.
Prioriza causas raíz sobre síntomas. Cruza velocidad de respuesta, calidad de atención, interés,
objeciones, pauta/campaña, audiencia y business.

Reglas:
- No inventes ventas, conversiones ni causalidad.
- Las recomendaciones de pauta deben basarse en los datos de audiencia/costo/calidad de leads disponibles.
- Si la información de segmentación es insuficiente, dilo explícitamente en vez de fabricar una audiencia.
- La predicción debe presentarse como escenario operativo/heurístico, no como forecast financiero ni promesa.
- En Nuevos y Comerciales considera Volkswagen; en Usados pueden existir distintas marcas.
- Recomendaciones concretas, accionables y medibles.
- Devuelve exclusivamente JSON compatible con el esquema.
"""

EJECUTIVO_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "resumen_ejecutivo": {"type": "STRING"},
        "hallazgos_clave": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "titulo": {"type": "STRING"},
                    "detalle": {"type": "STRING"},
                    "severidad": {"type": "STRING", "enum": ["alta", "media", "baja"]},
                    "metrica": {"type": "STRING"},
                },
                "required": ["titulo", "detalle", "severidad", "metrica"],
            },
        },
        "causas_raiz": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "causa": {"type": "STRING"},
                    "evidencia": {"type": "STRING"},
                    "impacto": {"type": "STRING"},
                    "prioridad": {"type": "STRING", "enum": ["alta", "media", "baja"]},
                },
                "required": ["causa", "evidencia", "impacto", "prioridad"],
            },
        },
        "recomendaciones_globales": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "accion": {"type": "STRING"},
                    "motivo": {"type": "STRING"},
                    "impacto_esperado": {"type": "STRING"},
                    "prioridad": {"type": "STRING", "enum": ["alta", "media", "baja"]},
                },
                "required": ["accion", "motivo", "impacto_esperado", "prioridad"],
            },
        },
        "recomendaciones_asesores": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "asesor": {"type": "STRING"},
                    "fortalezas": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "deficiencias": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "recomendaciones": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "prioridad": {"type": "STRING", "enum": ["alta", "media", "baja"]},
                },
                "required": ["asesor", "fortalezas", "deficiencias", "recomendaciones", "prioridad"],
            },
        },
        "recomendaciones_campanas": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "campana": {"type": "STRING"},
                    "diagnostico": {"type": "STRING"},
                    "recomendacion": {"type": "STRING"},
                    "audiencia_sugerida": {"type": "STRING"},
                    "prioridad": {"type": "STRING", "enum": ["alta", "media", "baja"]},
                },
                "required": ["campana", "diagnostico", "recomendacion", "audiencia_sugerida", "prioridad"],
            },
        },
        "prediccion": {
            "type": "OBJECT",
            "properties": {
                "escenario_sin_mejoras": {"type": "STRING"},
                "riesgo": {"type": "STRING", "enum": ["alto", "medio", "bajo"]},
                "impacto_estimado": {"type": "STRING"},
                "nota_metodologica": {"type": "STRING"},
            },
            "required": ["escenario_sin_mejoras", "riesgo", "impacto_estimado", "nota_metodologica"],
        },
        "oportunidades": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "titulo": {"type": "STRING"},
                    "accion": {"type": "STRING"},
                    "impacto_estimado": {"type": "STRING"},
                },
                "required": ["titulo", "accion", "impacto_estimado"],
            },
        },
    },
    "required": [
        "resumen_ejecutivo", "hallazgos_clave", "causas_raiz", "recomendaciones_globales",
        "recomendaciones_asesores", "recomendaciones_campanas", "prediccion", "oportunidades",
    ],
}

def _convertir_schema_openai(valor):
    """
    Convierte los schemas existentes a JSON Schema estándar
    compatible con Structured Outputs de OpenAI.
    """
    if isinstance(valor, dict):
        resultado = {}

        for clave, contenido in valor.items():
            if clave == "type":
                if isinstance(contenido, str):
                    resultado[clave] = contenido.lower()

                elif isinstance(contenido, list):
                    resultado[clave] = [
                        item.lower()
                        if isinstance(item, str)
                        else _convertir_schema_openai(item)
                        for item in contenido
                    ]

                else:
                    resultado[clave] = _convertir_schema_openai(
                        contenido
                    )
            else:
                resultado[clave] = _convertir_schema_openai(
                    contenido
                )

        return resultado

    if isinstance(valor, list):
        return [
            _convertir_schema_openai(item)
            for item in valor
        ]

    return valor


OPENAI_AUDITORIA_SCHEMA = _convertir_schema_openai(
    AUDITORIA_SCHEMA
)

OPENAI_EJECUTIVO_SCHEMA = _convertir_schema_openai(
    EJECUTIVO_SCHEMA
)

def _texto(value) -> str:
    return " ".join(str(value or "").split()).strip()


def _normaliza(value) -> str:
    value = _texto(value).lower()
    return value.translate(str.maketrans("áéíóúüñ", "aeiouun"))


def _porcentaje(num, den) -> float:
    return round((float(num) / float(den)) * 100, 1) if den else 0.0


def _segundos_label(value) -> str:
    if value in (None, ""):
        return "—"
    segundos = max(0, int(value))
    if segundos < 60:
        return f"{segundos} s"
    minutos = segundos // 60
    if minutos < 60:
        return f"{minutos} min"
    horas, mins = divmod(minutos, 60)
    if horas < 24:
        return f"{horas} h {mins} min" if mins else f"{horas} h"
    dias, horas = divmod(horas, 24)
    return f"{dias} d {horas} h" if horas else f"{dias} d"


def _es_ia(raw) -> bool:
    raw = raw if isinstance(raw, dict) else {}
    return bool(
        raw.get("ia_provider") or raw.get("ia_model") or raw.get("openai_model")
        or raw.get("gemini_model") or raw.get("decision") or raw.get("origen") == "ia"
    )


def _usuario_login(user) -> str:
    return _texto(
        getattr(user, "usuario", "") or getattr(user, "username", "")
        or getattr(user, "email", "") or ""
    )


def _rol_usuario(user) -> str:
    rol_obj = getattr(user, "rol", None)
    return _normaliza(
        getattr(rol_obj, "nombre", "") or getattr(rol_obj, "name", "")
        or (rol_obj if isinstance(rol_obj, str) else "")
    )


def _permisos_usuario(user) -> set[str]:
    permisos = getattr(user, "permisos", None)
    try:
        if hasattr(permisos, "all"):
            permisos = permisos.all()
        salida = set()
        for item in permisos or []:
            valor = item if isinstance(item, str) else (
                getattr(item, "codigo", "") or getattr(item, "nombre", "")
                or getattr(item, "name", "") or item
            )
            salida.add(_texto(valor).upper())
        return salida
    except Exception:
        return set()


def _es_admin(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if bool(getattr(user, "is_superuser", False)):
        return True
    return _rol_usuario(user) in {"administrador", "admin"} or bool(
        {"ALL", "USUARIOS_ADMIN"} & _permisos_usuario(user)
    )


def _es_coordinador(user) -> bool:
    rol = _rol_usuario(user)
    return ("coordinador" in rol and "digital" in rol) or "CRM_COORDINADOR_DIGITAL" in _permisos_usuario(user)


def _grupo_agencia(value: str) -> str:
    text = _normaliza(value)
    for token, label in (
        ("cordoba", "VW Cordoba"), ("orizaba", "VW Orizaba"),
        ("poza rica", "VW Poza Rica"), ("tuxtepec", "VW Tuxtepec"),
        ("tuxpan", "VW Tuxpan"), ("automotriz r&r", "Automotriz R&R"),
    ):
        if token in text:
            return label
    return _texto(value)


def _numeros_usuario(user) -> list[str]:
    raw = _texto(
        getattr(user, "telefono", "") or getattr(user, "numero_asesor", "")
        or getattr(user, "whatsapp_number", "") or getattr(user, "phone", "")
    )
    numeros = []
    for value in re.split(r"[|,;\n]+", raw):
        numero = normaliza_tel_mx(value)
        if numero in WHATSAPP_LINES and numero not in numeros:
            numeros.append(numero)
    return numeros


def _agencias_usuario(user) -> set[str]:
    raw = _texto(getattr(user, "agencia", ""))
    return {_grupo_agencia(value) for value in re.split(r"[|,;\n]+", raw) if _texto(value)}


def _lineas_ventas() -> list[str]:
    return [
        numero for numero, cfg in WHATSAPP_LINES.items()
        if _normaliza(cfg.get("business")) in BUSINESS_COMERCIALES
    ]


def _lineas_permitidas(request) -> tuple[list[str], Response | None, bool, bool]:
    user = getattr(request, "user", None)
    es_admin = _es_admin(user)
    es_coordinador = _es_coordinador(user)
    lineas_venta = _lineas_ventas()

    if es_admin:
        permitidas = lineas_venta
    else:
        asignadas = [n for n in _numeros_usuario(user) if n in lineas_venta]
        if es_coordinador:
            agencias = _agencias_usuario(user)
            por_agencia = [
                numero for numero in lineas_venta
                if _grupo_agencia(WHATSAPP_LINES.get(numero, {}).get("agencia", "")) in agencias
            ]
            permitidas = list(dict.fromkeys(asignadas + por_agencia))
        else:
            permitidas = asignadas

    if not permitidas:
        return [], Response(
            {"ok": False, "error": "Tu usuario no tiene líneas comerciales de WhatsApp disponibles."},
            status=status.HTTP_403_FORBIDDEN,
        ), es_admin, es_coordinador

    solicitada = normaliza_tel_mx(request.query_params.get("numero_asesor", ""))
    if solicitada:
        if solicitada not in permitidas:
            return [], Response(
                {"ok": False, "error": "No tienes permiso para consultar esa línea."},
                status=status.HTTP_403_FORBIDDEN,
            ), es_admin, es_coordinador
        permitidas = [solicitada]

    return permitidas, None, es_admin, es_coordinador


def _rango_mes(mes_raw: str):
    ahora = timezone.now()
    hoy = timezone.localtime(ahora).date() if settings.USE_TZ and timezone.is_aware(ahora) else ahora.date()
    match = re.fullmatch(r"(\d{4})-(\d{2})", _texto(mes_raw))
    if match:
        anio, mes = int(match.group(1)), int(match.group(2))
        if not 1 <= mes <= 12:
            anio, mes = hoy.year, hoy.month
    else:
        anio, mes = hoy.year, hoy.month

    desde = datetime(anio, mes, 1)
    hasta = datetime(anio + 1, 1, 1) if mes == 12 else datetime(anio, mes + 1, 1)
    if settings.USE_TZ:
        zona = timezone.get_current_timezone()
        desde = timezone.make_aware(desde, zona)
        hasta = timezone.make_aware(hasta, zona)
    return f"{anio:04d}-{mes:02d}", desde, hasta


def _copiar_horario_predeterminado() -> dict:
    horario = {dia: dict(config) for dia, config in HORARIO_RESPUESTA_PREDETERMINADO.items()}
    horario["pausa_comida"] = {
        **PAUSA_COMIDA_PREDETERMINADA,
        "dias": list(PAUSA_COMIDA_PREDETERMINADA["dias"]),
    }
    return horario


def _hora_hhmm(valor: str, default: str) -> str:
    valor = _texto(valor)
    if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", valor):
        return valor
    return default


def _parsear_horario_respuesta(valor: str) -> dict:
    horario = _copiar_horario_predeterminado()
    valor = _texto(valor)
    if not valor:
        return horario

    try:
        recibido = json.loads(valor)
    except Exception:
        return horario

    if not isinstance(recibido, dict):
        return horario

    for dia in DIAS_SEMANA:
        item = recibido.get(dia)
        if not isinstance(item, dict):
            continue

        base = horario[dia]
        activo = item.get("activo", base["activo"])
        if isinstance(activo, str):
            activo = _normaliza(activo) in {"1", "true", "si", "sí", "yes", "on"}

        inicio = _hora_hhmm(item.get("inicio"), base["inicio"])
        fin = _hora_hhmm(item.get("fin"), base["fin"])
        if fin <= inicio:
            activo = False

        horario[dia] = {"activo": bool(activo), "inicio": inicio, "fin": fin}

    pausa_recibida = recibido.get("pausa_comida")
    if isinstance(pausa_recibida, dict):
        base = horario["pausa_comida"]
        activo = pausa_recibida.get("activo", base["activo"])
        if isinstance(activo, str):
            activo = _normaliza(activo) in {"1", "true", "si", "sí", "yes", "on"}
        inicio = _hora_hhmm(pausa_recibida.get("inicio"), base["inicio"])
        fin = _hora_hhmm(pausa_recibida.get("fin"), base["fin"])
        dias = pausa_recibida.get("dias", base["dias"])
        if not isinstance(dias, (list, tuple, set)):
            dias = base["dias"]
        dias = [dia for dia in dias if dia in DIAS_SEMANA]
        if fin <= inicio:
            activo = False
        horario["pausa_comida"] = {"activo": bool(activo), "inicio": inicio, "fin": fin, "dias": dias}

    return horario


def _parsear_lineas_excluidas_tiempo(valor, lineas_permitidas) -> set[str]:
    if isinstance(valor, (list, tuple, set)):
        partes = list(valor)
    else:
        texto = _texto(valor)
        if texto.startswith("["):
            try:
                parsed = json.loads(texto)
                partes = parsed if isinstance(parsed, list) else []
            except Exception:
                partes = re.split(r"[,;|\n]+", texto)
        else:
            partes = re.split(r"[,;|\n]+", texto)

    permitidas = set(lineas_permitidas or [])
    return {
        numero
        for numero in (normaliza_tel_mx(item or "") for item in partes)
        if numero and numero in permitidas
    }


def _datetime_local(valor):
    if valor is None:
        return None
    if settings.USE_TZ:
        zona = timezone.get_current_timezone()
        if timezone.is_naive(valor):
            valor = timezone.make_aware(valor, zona)
        return timezone.localtime(valor, zona)
    if timezone.is_aware(valor):
        return timezone.make_naive(valor, timezone.get_current_timezone())
    return valor


def _datetime_dia_hora(fecha, hora_texto: str):
    try:
        partes = str(hora_texto or "09:00").strip().split(":")
        hora = int(partes[0])
        minuto = int(partes[1]) if len(partes) > 1 else 0

        hora = max(0, min(hora, 23))
        minuto = max(0, min(minuto, 59))
    except (TypeError, ValueError, IndexError):
        hora = 9
        minuto = 0

    valor = datetime.combine(fecha, datetime_time(hour=hora, minute=minuto))

    if settings.USE_TZ:
        if timezone.is_naive(valor):
            valor = timezone.make_aware(
                valor,
                timezone.get_current_timezone(),
            )

    return valor

def _segundos_habiles_entre(inicio, fin, horario: dict) -> int:
    inicio = _datetime_local(inicio)
    fin = _datetime_local(fin)
    if not inicio or not fin or fin <= inicio:
        return 0

    total = 0.0
    fecha = inicio.date()
    fecha_fin = fin.date()
    pausa = horario.get("pausa_comida") or PAUSA_COMIDA_PREDETERMINADA
    dias_pausa = set(pausa.get("dias") or [])

    while fecha <= fecha_fin:
        dia = DIAS_SEMANA[fecha.weekday()]
        config = horario.get(dia) or {}
        if config.get("activo"):
            jornada_inicio = _datetime_dia_hora(fecha, config.get("inicio") or "09:00")
            jornada_fin = _datetime_dia_hora(fecha, config.get("fin") or "18:00")
            desde = max(inicio, jornada_inicio)
            hasta = min(fin, jornada_fin)
            if hasta > desde:
                segundos_dia = (hasta - desde).total_seconds()
                if pausa.get("activo") and dia in dias_pausa:
                    pausa_inicio = _datetime_dia_hora(fecha, pausa.get("inicio") or "14:00")
                    pausa_fin = _datetime_dia_hora(fecha, pausa.get("fin") or "15:00")
                    solape_inicio = max(desde, pausa_inicio)
                    solape_fin = min(hasta, pausa_fin)
                    if solape_fin > solape_inicio:
                        segundos_dia -= (solape_fin - solape_inicio).total_seconds()
                total += max(0, segundos_dia)
        fecha += timedelta(days=1)

    return max(0, int(total))


def _estado_medicion_respuesta(*, primer_cliente, primera_respuesta_humana, numero: str, horario: dict, lineas_excluidas: set[str], corte):
    if not primer_cliente:
        return {
            "medicion_tiempo_habilitada": False,
            "motivo_exclusion_tiempo": "sin_mensaje_cliente",
            "tiempo_primera_respuesta_segundos": None,
            "tiempo_primera_respuesta_crudo_segundos": None,
            "segundos_habiles_transcurridos": 0,
            "espera_fuera_horario": False,
            "sin_respuesta_humana_evaluable": False,
        }

    if numero in lineas_excluidas:
        return {
            "medicion_tiempo_habilitada": False,
            "motivo_exclusion_tiempo": "linea_excluida",
            "tiempo_primera_respuesta_segundos": None,
            "tiempo_primera_respuesta_crudo_segundos": None,
            "segundos_habiles_transcurridos": 0,
            "espera_fuera_horario": False,
            "sin_respuesta_humana_evaluable": False,
        }

    inicio = primer_cliente.get("created_at")
    fin_medicion = primera_respuesta_humana.get("created_at") if primera_respuesta_humana else corte
    segundos_habiles = _segundos_habiles_entre(inicio, fin_medicion, horario)
    crudos = None
    if primera_respuesta_humana and inicio and primera_respuesta_humana.get("created_at"):
        crudos = max(0, int((primera_respuesta_humana["created_at"] - inicio).total_seconds()))

    if primera_respuesta_humana and segundos_habiles <= 0:
        return {
            "medicion_tiempo_habilitada": False,
            "motivo_exclusion_tiempo": "respuesta_completa_fuera_de_horario",
            "tiempo_primera_respuesta_segundos": None,
            "tiempo_primera_respuesta_crudo_segundos": crudos,
            "segundos_habiles_transcurridos": 0,
            "espera_fuera_horario": False,
            "sin_respuesta_humana_evaluable": False,
        }

    sin_respuesta = primera_respuesta_humana is None
    espera_fuera_horario = bool(sin_respuesta and segundos_habiles <= 0)
    return {
        "medicion_tiempo_habilitada": True,
        "motivo_exclusion_tiempo": "",
        "tiempo_primera_respuesta_segundos": segundos_habiles if primera_respuesta_humana else None,
        "tiempo_primera_respuesta_crudo_segundos": crudos,
        "segundos_habiles_transcurridos": segundos_habiles,
        "espera_fuera_horario": espera_fuera_horario,
        "sin_respuesta_humana_evaluable": bool(sin_respuesta and segundos_habiles > 0),
    }

def _get_openai_client() -> OpenAI:
    api_key = _texto(
        getattr(
            settings,
            "OPENAI_API_KEY",
            "",
        )
    )

    if not api_key:
        raise RuntimeError(
            "Falta configurar OPENAI_API_KEY en settings.py"
        )

    timeout_ms = int(
        getattr(
            settings,
            "OPENAI_RESULTS_TIMEOUT_MS",
            45000,
        )
    )

    return OpenAI(
        api_key=api_key,
        timeout=timeout_ms / 1000.0,
        max_retries=2,
    )


def _modelo_openai() -> str:
    return _texto(
        getattr(settings, "OPENAI_RESULTS_MODEL", "")
        or getattr(settings, "OPENAI_MODEL", "")
        or "gpt-5.6-luna"
    )

def _parse_json(texto: str) -> dict:
    try:
        data = json.loads(_texto(texto))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _percentil(values: list[int], q: float):
    if not values:
        return None
    orden = sorted(values)
    idx = max(0, min(len(orden) - 1, math.ceil(q * len(orden)) - 1))
    return orden[idx]


def _recortar_conversacion(texto: str) -> tuple[str, bool]:
    if len(texto) <= MAX_CONVERSACION_CHARS:
        return texto, False
    mitad = MAX_CONVERSACION_CHARS // 2
    return (
        texto[:mitad]
        + "\n\n[... tramo central omitido por límite técnico ...]\n\n"
        + texto[-mitad:],
        True,
    )


def _rol_mensaje(row: dict) -> str:
    if row.get("direction") == MensajeWhatsApp.Direccion.IN:
        return "Cliente"
    return "IA" if _es_ia(row.get("raw")) else "Asesor humano"


def _contextos_conversacion(*, lineas, inicio, fin, request, es_admin, es_coordinador, horario_respuesta, lineas_excluidas_tiempo):
    mensajes = list(
        MensajeWhatsApp.objects
        .filter(numero_asesor__in=lineas, created_at__gte=inicio, created_at__lt=fin)
        .values("id", "telefono", "numero_asesor", "direction", "body", "raw", "status", "created_at", "cliente_id")
        .order_by("telefono", "numero_asesor", "created_at", "id")
    )

    cliente_ids = {row["cliente_id"] for row in mensajes if row.get("cliente_id")}
    telefonos = {normaliza_tel_mx(row.get("telefono", "")) for row in mensajes}
    expedientes = list(
        ExpedienteDigital.objects.select_related("cliente")
        .filter(Q(cliente_id__in=cliente_ids) | Q(cliente__telefono__in=telefonos))
    )
    por_cliente = {item.cliente_id: item for item in expedientes}
    por_telefono = {normaliza_tel_mx(item.cliente.telefono): item for item in expedientes}

    agrupados = defaultdict(list)
    for row in mensajes:
        key = (normaliza_tel_mx(row.get("telefono", "")), normaliza_tel_mx(row.get("numero_asesor", "")))
        agrupados[key].append(row)

    agencia_raw = _texto(request.query_params.get("agencia", ""))
    agencia_filtro = "" if _normaliza(agencia_raw) in {"", "todos", "todas"} else _grupo_agencia(agencia_raw)
    business_filtro = _normaliza(request.query_params.get("business", ""))
    usuario = _normaliza(_usuario_login(getattr(request, "user", None)))
    contextos = []
    recortadas = 0

    for (telefono, numero), rows in agrupados.items():
        exp = None
        cliente_id = next((r.get("cliente_id") for r in rows if r.get("cliente_id")), None)
        if cliente_id:
            exp = por_cliente.get(cliente_id)
        exp = exp or por_telefono.get(telefono)
        cfg = WHATSAPP_LINES.get(numero, {})

        agencia = _texto(getattr(exp, "agencia", "") or cfg.get("agencia", ""))
        business = _texto(getattr(exp, "business", "") or cfg.get("business", ""))
        asesor = _texto(getattr(exp, "asesor_digital", "") or cfg.get("asesor_digital", "") or numero)

        if agencia_filtro and _grupo_agencia(agencia_filtro) != _grupo_agencia(agencia):
            continue
        if business_filtro and business_filtro not in {"todos", "todas"} and _normaliza(business) != business_filtro:
            continue

        asesores_compartidos = cfg.get("asesores") or []
        if asesores_compartidos and not es_admin and not es_coordinador:
            asignado = _normaliza(getattr(exp, "usuario_crm_asignado", "") if exp else "")
            if not asignado or asignado != usuario:
                continue

        primer_cliente = next((r for r in rows if r.get("direction") == MensajeWhatsApp.Direccion.IN), None)
        primera_respuesta_humana = None
        if primer_cliente:
            for r in rows:
                if r.get("created_at") <= primer_cliente.get("created_at"):
                    continue
                if r.get("direction") == MensajeWhatsApp.Direccion.OUT and not _es_ia(r.get("raw")) and r.get("status") != "failed":
                    primera_respuesta_humana = r
                    break

        ahora = timezone.now()
        corte = min(ahora, fin) if ahora >= inicio else inicio
        medicion = _estado_medicion_respuesta(
            primer_cliente=primer_cliente,
            primera_respuesta_humana=primera_respuesta_humana,
            numero=numero,
            horario=horario_respuesta,
            lineas_excluidas=lineas_excluidas_tiempo,
            corte=corte,
        )

        lineas_texto = []
        for r in rows:
            body = _texto(r.get("body"))
            if not body:
                continue
            fecha = r.get("created_at").isoformat() if r.get("created_at") else ""
            lineas_texto.append(f"[{fecha}] {_rol_mensaje(r)}: {body}")
        conversacion, recortada = _recortar_conversacion("\n".join(lineas_texto))
        recortadas += int(recortada)

        nombre = _texto(getattr(getattr(exp, "cliente", None), "nombre", "") if exp else "")
        contexto = {
            "id": f"{numero}:{telefono}",
            "telefono": telefono,
            "numero_asesor": numero,
            "asesor": asesor or "Sin asesor",
            "agencia": agencia,
            "business": business,
            "nombre_cliente": nombre or "Sin nombre",
            "estado_crm": _texto(getattr(exp, "estado", "") if exp else ""),
            "vehiculo_crm": _texto(getattr(exp, "auto_interes", "") if exp else ""),
            "pauta": _texto(getattr(exp, "pauta", "") if exp else ""),
            "forma_pago": _texto(getattr(exp, "forma_pago", "") if exp else ""),
            "plazo_compra": _texto(getattr(exp, "plazo_compra", "") if exp else ""),
            "requiere_asesor": bool(getattr(exp, "requiere_asesor", False)) if exp else False,
            "cotizacion_pendiente": bool(getattr(exp, "cotizacion_pendiente", False)) if exp else False,
            "tiene_cita": bool(getattr(exp, "ultima_cita_id", None)) if exp else False,
            "asistencia": bool(getattr(exp, "asistencia", False)) if exp else False,
            "facturado": bool(_texto(getattr(exp, "vin_facturado", "") if exp else "")),
            "primer_mensaje_cliente": primer_cliente["created_at"].isoformat() if primer_cliente else None,
            "primera_respuesta_humana": primera_respuesta_humana["created_at"].isoformat() if primera_respuesta_humana else None,
            "medicion_tiempo_habilitada": medicion["medicion_tiempo_habilitada"],
            "motivo_exclusion_tiempo": medicion["motivo_exclusion_tiempo"],
            "tiempo_primera_respuesta_segundos": medicion["tiempo_primera_respuesta_segundos"],
            "tiempo_primera_respuesta_label": _segundos_label(medicion["tiempo_primera_respuesta_segundos"]),
            "tiempo_primera_respuesta_crudo_segundos": medicion["tiempo_primera_respuesta_crudo_segundos"],
            "segundos_habiles_transcurridos": medicion["segundos_habiles_transcurridos"],
            "espera_fuera_horario": medicion["espera_fuera_horario"],
            "sin_respuesta_humana_evaluable": medicion["sin_respuesta_humana_evaluable"],
            "mensajes": len(rows),
            "mensajes_cliente": sum(1 for r in rows if r.get("direction") == MensajeWhatsApp.Direccion.IN),
            "mensajes_humanos": sum(1 for r in rows if r.get("direction") == MensajeWhatsApp.Direccion.OUT and not _es_ia(r.get("raw"))),
            "mensajes_ia": sum(1 for r in rows if r.get("direction") == MensajeWhatsApp.Direccion.OUT and _es_ia(r.get("raw"))),
            "conversacion_recortada": recortada,
            "conversacion": conversacion,
        }
        contextos.append(contexto)

    return contextos, {"mensajes": len(mensajes), "conversaciones_recortadas": recortadas}


def _fallback_auditoria(ctx: dict) -> dict:
    text = _normaliza(ctx.get("conversacion"))
    frases_interes = (
        "cotizacion", "precio", "mensualidad", "enganche", "credito", "financiamiento",
        "disponibilidad", "visita", "cita", "prueba", "comprar", "apartar", "toma a cuenta",
    )
    senal = any(token in text for token in frases_interes)
    nivel = "medio" if senal else "bajo"
    if ctx.get("facturado") or ctx.get("tiene_cita") or ctx.get("cotizacion_pendiente"):
        nivel = "alto"
    sin_humano = bool(ctx.get("sin_respuesta_humana_evaluable"))
    segundos = ctx.get("tiempo_primera_respuesta_segundos")
    lento = segundos is not None and segundos > 4 * 3600
    mal = sin_humano or lento
    calidad = "critica" if sin_humano else ("deficiente" if lento else "mejorable")
    return {
        "id": ctx["id"], "nivel_interes": nivel, "senal_compra": bool(senal),
        "intenciones": [], "vehiculos_interes": [ctx["vehiculo_crm"]] if ctx.get("vehiculo_crm") else [],
        "calidad_atencion": calidad, "puntaje_atencion": 30 if sin_humano else (50 if lento else 70),
        "mal_atendido": mal, "cliente_dejo_responder": False,
        "riesgo_perdida": "alto" if mal and senal else ("medio" if mal or senal else "bajo"),
        "deficiencias": ["Sin respuesta humana posterior"] if sin_humano else (["Primera respuesta superior a 4 horas"] if lento else []),
        "objeciones": [], "causa_perdida_probable": "Sin evidencia suficiente",
        "siguiente_accion": "Revisar la conversación y definir el siguiente compromiso comercial.",
        "recomendacion_asesor": "Responder con rapidez, perfilar necesidad y cerrar una acción concreta.",
        "resumen": "Clasificación de respaldo basada en reglas operativas; OpenAI no estuvo disponible.",
    }


def _lotes_contextos(contextos: list[dict]) -> list[list[dict]]:
    lotes, actual, chars = [], [], 0
    for ctx in contextos:
        payload = {k: v for k, v in ctx.items() if k not in {"telefono"}}
        longitud = len(json.dumps(payload, ensure_ascii=False))
        if actual and chars + longitud > MAX_LOTE_CHARS:
            lotes.append(actual)
            actual, chars = [], 0
        actual.append(payload)
        chars += longitud
    if actual:
        lotes.append(actual)
    return lotes


def _auditar_con_openai(
    contextos: list[dict],
    *,
    limite_tiempo: float | None = None,
) -> tuple[list[dict], list[str]]:
    if not contextos:
        return [], []

    client = _get_openai_client()
    modelo = _modelo_openai()

    salida_por_id = {}
    errores = []

    for indice, lote in enumerate(
        _lotes_contextos(contextos),
        start=1,
    ):
        if (
            limite_tiempo is not None
            and time_module.monotonic() >= limite_tiempo
        ):
            errores.append(
                "Se alcanzó el tiempo máximo destinado "
                "al análisis IA. Las conversaciones "
                "restantes utilizaron análisis de respaldo."
            )
            break

        contenido = (
            "Audita todas las conversaciones del siguiente "
            "lote. Respeta exactamente el id de cada una.\n\n"
            + json.dumps(
                lote,
                ensure_ascii=False,
            )
        )

        try:
            response = client.responses.create(
                model=modelo,
                instructions=PROMPT_AUDITORIA,
                input=contenido,
                reasoning={
                    "effort": "none",
                },
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "auditoria_resultados",
                        "schema": OPENAI_AUDITORIA_SCHEMA,
                        "strict": False,
                    }
                },
                temperature=0.15,
                store=False,
            )

            data = _parse_json(
                getattr(
                    response,
                    "output_text",
                    "",
                )
                or ""
            )

            for item in data.get(
                "conversaciones",
                [],
            ):
                if (
                    isinstance(item, dict)
                    and _texto(item.get("id"))
                ):
                    salida_por_id[
                        _texto(item["id"])
                    ] = item

        except Exception as exc:
            logger.exception(
                "Error en lote de resultados IA %s",
                indice,
            )

            mensaje_error = str(exc)
            errores.append(f"Lote {indice}: {mensaje_error}")
            mensaje_normalizado = mensaje_error.lower()
            if (
                "503" in mensaje_error
                or "504" in mensaje_error
                or "unavailable" in mensaje_normalizado
                or "high demand" in mensaje_normalizado
                or "deadline_exceeded" in mensaje_normalizado
            ):
                errores.append(
                    "OpenAI está temporalmente saturado o agotó su tiempo de respuesta; "
                    "los lotes restantes utilizaron análisis de respaldo."
                )
                break

    salida = []

    for ctx in contextos:
        item = (
            salida_por_id.get(ctx["id"])
            or _fallback_auditoria(ctx)
        )

        try:
            puntaje = int(
                item.get(
                    "puntaje_atencion",
                    0,
                )
                or 0
            )
        except (TypeError, ValueError):
            puntaje = 0

        item["puntaje_atencion"] = max(
            0,
            min(
                100,
                puntaje,
            ),
        )

        if ctx.get(
            "sin_respuesta_humana_evaluable"
        ):
            item["mal_atendido"] = True
            item["calidad_atencion"] = "critica"

            item["puntaje_atencion"] = min(
                item["puntaje_atencion"],
                30,
            )

            if item.get("senal_compra"):
                item["riesgo_perdida"] = "alto"

            deficiencias = list(
                item.get("deficiencias")
                or []
            )

            if not any(
                "respuesta humana"
                in _normaliza(x)
                for x in deficiencias
            ):
                deficiencias.append(
                    "El cliente escribió y no existe "
                    "respuesta humana posterior."
                )

            item["deficiencias"] = deficiencias

        salida.append(item)

    try:
        client.close()
    except Exception:
        pass

    return salida, errores

def _normalizar_modelo(value: str) -> str:
    value = _texto(value)
    if not value:
        return ""
    aliases = {
        "gli": "Jetta GLI", "jetta gli": "Jetta GLI", "gti": "Golf GTI", "golf gti": "Golf GTI",
        "cross sport": "Cross Sport", "crossport": "Cross Sport", "seminuevos": "Seminuevos",
    }
    return aliases.get(_normaliza(value), value.title() if value.isupper() else value)


def _campanas_mes(*, inicio, fin, agencia_filtro: str = "") -> list[dict]:
    inicio_date, fin_date = inicio.date(), fin.date()
    qs = CampanaMetaAds.objects.using("sqlserver").filter(
        Q(inicio_informe__lt=fin_date, fin_informe__gte=inicio_date)
        | Q(inicio_campana__lt=fin_date, fin_campana__gte=inicio_date)
        | Q(inicio_campana__gte=inicio_date, inicio_campana__lt=fin_date)
    )
    rows = list(qs.order_by("-importe_gastado")[:100])
    salida = []
    for c in rows:
        if agencia_filtro and _grupo_agencia(c.sucursal) != _grupo_agencia(agencia_filtro):
            continue
        gasto = float(c.importe_gastado or 0)
        resultados = int(c.messaging_first_reply or 0)
        salida.append({
            "id_campana": str(c.id_campana),
            "sucursal": _texto(c.sucursal),
            "nombre_campana": _texto(c.nombre_campana),
            "estado": _texto(c.estado_campana),
            "objetivo": _texto(c.objetivo_campana),
            "resultados": resultados,
            "resultados_fb": int(c.resultados_fb or 0),
            "resultados_ig": int(c.resultados_ig or 0),
            "resultados_wp": int(c.resultados_wp or 0),
            "alcance": int(c.alcance or 0),
            "impresiones": int(c.impresiones or 0),
            "gasto": round(gasto, 2),
            "costo_resultado": round(gasto / resultados, 2) if resultados else None,
            "indicador_resultado": "messaging_first_reply",
            "edad_audiencia": _texto(c.edad_audiencia),
            "intereses_audiencia": _texto(c.intereses_audiencia),
            "comportamiento_audiencia": _texto(c.comportamiento_audiencia),
            "resultados_masc": int(c.resultados_masc or 0),
            "resultados_fem": int(c.resultados_fem or 0),
            "resultados_sin_genero": int(c.resultados_sin_genero or 0),
        })
    return salida

def _agregar_metricas_bd(contextos: list[dict], campanas: list[dict]) -> dict:
    tiempos = [int(ctx["tiempo_primera_respuesta_segundos"]) for ctx in contextos if ctx.get("tiempo_primera_respuesta_segundos") is not None]
    promedio = round(sum(tiempos) / len(tiempos)) if tiempos else None
    mediana_t = round(median(tiempos)) if tiempos else None
    p90 = _percentil(tiempos, .90)
    gasto_meta = round(sum(float(c.get("gasto") or 0) for c in campanas), 2)
    resultados_meta = sum(int(c.get("resultados") or 0) for c in campanas)

    por_asesor = defaultdict(lambda: {"conversaciones": 0, "mensajes": 0, "tiempos": [], "citas": 0, "facturados": 0, "agencias": Counter(), "business": Counter()})
    for ctx in contextos:
        asesor = ctx.get("asesor") or "Sin asesor"
        row = por_asesor[asesor]
        row["conversaciones"] += 1
        row["mensajes"] += int(ctx.get("mensajes") or 0)
        row["citas"] += int(bool(ctx.get("tiene_cita")))
        row["facturados"] += int(bool(ctx.get("facturado")))
        row["agencias"][ctx.get("agencia") or "Sin agencia"] += 1
        row["business"][ctx.get("business") or "Sin business"] += 1
        if ctx.get("tiempo_primera_respuesta_segundos") is not None:
            row["tiempos"].append(int(ctx["tiempo_primera_respuesta_segundos"]))

    asesores_bd = []
    for asesor, row in por_asesor.items():
        prom = round(sum(row["tiempos"]) / len(row["tiempos"])) if row["tiempos"] else None
        asesores_bd.append({
            "asesor": asesor,
            "conversaciones": row["conversaciones"],
            "mensajes": row["mensajes"],
            "citas": row["citas"],
            "facturados": row["facturados"],
            "tiempo_primera_respuesta_segundos": prom,
            "tiempo_primera_respuesta_label": _segundos_label(prom),
            "agencia": row["agencias"].most_common(1)[0][0] if row["agencias"] else "",
            "business": row["business"].most_common(1)[0][0] if row["business"] else "",
        })
    asesores_bd.sort(key=lambda x: (x["tiempo_primera_respuesta_segundos"] is None, x["tiempo_primera_respuesta_segundos"] or 0))

    return {
        "metricas": {
            "conversaciones": len(contextos),
            "mensajes": sum(int(ctx.get("mensajes") or 0) for ctx in contextos),
            "mensajes_cliente": sum(int(ctx.get("mensajes_cliente") or 0) for ctx in contextos),
            "mensajes_humanos": sum(int(ctx.get("mensajes_humanos") or 0) for ctx in contextos),
            "mensajes_ia": sum(int(ctx.get("mensajes_ia") or 0) for ctx in contextos),
            "citas": sum(int(bool(ctx.get("tiene_cita"))) for ctx in contextos),
            "facturados": sum(int(bool(ctx.get("facturado"))) for ctx in contextos),
            "primera_respuesta_promedio_segundos": promedio,
            "primera_respuesta_promedio_label": _segundos_label(promedio),
            "primera_respuesta_mediana_segundos": mediana_t,
            "primera_respuesta_mediana_label": _segundos_label(mediana_t),
            "primera_respuesta_p90_segundos": p90,
            "primera_respuesta_p90_label": _segundos_label(p90),
            "campanas_activas_periodo": len(campanas),
            "gasto_meta": gasto_meta,
            "resultados_meta": resultados_meta,
            "costo_resultado_meta": round(gasto_meta / resultados_meta, 2) if resultados_meta else None,
            "conversaciones_tiempo_evaluable": sum(1 for ctx in contextos if ctx.get("medicion_tiempo_habilitada")),
            "conversaciones_tiempo_excluidas": sum(1 for ctx in contextos if not ctx.get("medicion_tiempo_habilitada")),
            "esperando_inicio_jornada": sum(1 for ctx in contextos if ctx.get("espera_fuera_horario")),
        },
        "asesores_bd": asesores_bd,
        "campanas": campanas,
    }

def _score_rapidez(segundos) -> float:
    if segundos is None:
        return 50.0
    if segundos <= 15 * 60:
        return 100.0
    if segundos <= 30 * 60:
        return 92.0
    if segundos <= 60 * 60:
        return 82.0
    if segundos <= 2 * 60 * 60:
        return 70.0
    if segundos <= 4 * 60 * 60:
        return 55.0
    if segundos <= 6 * 60 * 60:
        return 40.0
    return 25.0


def _deficiencias_resumen_asesor(row: dict, prom_resp) -> list[str]:
    conversaciones = max(1, row["conversaciones"])
    salida = []

    if row["sin_humano"] > 0:
        salida.append(f"{row['sin_humano']} chat(s) sin respuesta humana posterior")

    if prom_resp is not None:
        if prom_resp > 4 * 60 * 60:
            salida.append("Promedio de primera respuesta superior a 4 horas")
        elif prom_resp > 2 * 60 * 60:
            salida.append("Promedio de primera respuesta superior a 2 horas")
        elif prom_resp > 60 * 60:
            salida.append("Promedio de primera respuesta superior a 1 hora")

    extras = []
    for nombre, total in row["deficiencias"].most_common():
        nombre_norm = _normaliza(nombre)
        if "respuesta humana" in nombre_norm:
            continue
        if "primera respuesta superior a 4 horas" in nombre_norm:
            continue
        if "tiempo de respuesta" in nombre_norm:
            continue
        if total < 2:
            continue
        if (total / conversaciones) < 0.05:
            continue
        extras.append(nombre)

    salida.extend(extras[:4])
    return salida[:6]

def _agregar_metricas(contextos: list[dict], auditorias: list[dict], campanas: list[dict]):
    audit_por_id = {a.get("id"): a for a in auditorias}
    total = len(contextos)
    interesados = 0
    alta_intencion = 0
    mal_atendidos = 0
    riesgo_alto = 0
    sin_humano = 0
    facturados = 0
    citas = 0
    tiempos = []
    modelos = Counter()
    objeciones = Counter()
    intenciones = Counter()
    deficiencias = Counter()
    por_asesor = defaultdict(lambda: {
        "conversaciones": 0, "interesados": 0, "mal_atendidos": 0, "riesgo_alto": 0,
        "sin_humano": 0, "puntajes": [], "tiempos": [], "deficiencias": Counter(),
        "facturados": 0, "citas": 0, "agencias": Counter(), "business": Counter(),
    })

    for ctx in contextos:
        aud = audit_por_id.get(ctx["id"]) or _fallback_auditoria(ctx)
        es_interesado = aud.get("nivel_interes") in {"alto", "medio"} or bool(aud.get("senal_compra"))
        interesados += int(es_interesado)
        alta_intencion += int(aud.get("nivel_interes") == "alto" or aud.get("senal_compra"))
        mal_atendidos += int(bool(aud.get("mal_atendido")))
        riesgo_alto += int(aud.get("riesgo_perdida") == "alto")
        sin_humano += int(bool(ctx.get("sin_respuesta_humana_evaluable")))
        facturados += int(ctx.get("facturado", False))
        citas += int(ctx.get("tiene_cita", False))
        if ctx.get("tiempo_primera_respuesta_segundos") is not None:
            tiempos.append(int(ctx["tiempo_primera_respuesta_segundos"]))

        for modelo in list(aud.get("vehiculos_interes") or []) + ([ctx.get("vehiculo_crm")] if ctx.get("vehiculo_crm") else []):
            modelo = _normalizar_modelo(modelo)
            if modelo:
                modelos[modelo] += 1
        for item in aud.get("objeciones") or []:
            if _texto(item): objeciones[_texto(item)] += 1
        for item in aud.get("intenciones") or []:
            if _texto(item): intenciones[_texto(item)] += 1
        for item in aud.get("deficiencias") or []:
            if _texto(item): deficiencias[_texto(item)] += 1

        asesor = ctx.get("asesor") or "Sin asesor"
        row = por_asesor[asesor]
        row["conversaciones"] += 1
        row["interesados"] += int(es_interesado)
        row["mal_atendidos"] += int(bool(aud.get("mal_atendido")))
        row["riesgo_alto"] += int(aud.get("riesgo_perdida") == "alto")
        row["sin_humano"] += int(bool(ctx.get("sin_respuesta_humana_evaluable")))
        row["puntajes"].append(int(aud.get("puntaje_atencion") or 0))
        if ctx.get("tiempo_primera_respuesta_segundos") is not None:
            row["tiempos"].append(int(ctx["tiempo_primera_respuesta_segundos"]))
        row["facturados"] += int(ctx.get("facturado", False))
        row["citas"] += int(ctx.get("tiene_cita", False))
        row["agencias"][ctx.get("agencia") or "Sin agencia"] += 1
        row["business"][ctx.get("business") or "Sin business"] += 1
        for item in aud.get("deficiencias") or []:
            if _texto(item): row["deficiencias"][_texto(item)] += 1

    promedio = round(sum(tiempos) / len(tiempos)) if tiempos else None
    mediana_t = round(median(tiempos)) if tiempos else None
    p90 = _percentil(tiempos, .90)

    asesores = []
    for asesor, row in por_asesor.items():
        prom_resp = round(sum(row["tiempos"]) / len(row["tiempos"])) if row["tiempos"] else None
        score_calidad = round(sum(row["puntajes"]) / len(row["puntajes"]), 1) if row["puntajes"] else 0.0
        score_rapidez = _score_rapidez(prom_resp)
        score_interes = _porcentaje(row["interesados"], row["conversaciones"])
        penalizacion_sin_respuesta = min(20.0, row["sin_humano"] * 5.0)
        penalizacion_mal_atendido = min(20.0, _porcentaje(row["mal_atendidos"], row["conversaciones"]) * 0.2)

        score_final = round(
            (score_calidad * 0.50)
            + (score_rapidez * 0.30)
            + (score_interes * 0.20)
            - penalizacion_sin_respuesta
            - penalizacion_mal_atendido,
            1,
        )
        score_final = max(0.0, min(100.0, score_final))

        asesores.append({
            "asesor": asesor,
            "conversaciones": row["conversaciones"],
            "interesados": row["interesados"],
            "interes_pct": _porcentaje(row["interesados"], row["conversaciones"]),
            "mal_atendidos": row["mal_atendidos"],
            "mal_atendidos_pct": _porcentaje(row["mal_atendidos"], row["conversaciones"]),
            "riesgo_alto": row["riesgo_alto"],
            "sin_respuesta_humana": row["sin_humano"],
            "puntaje_atencion": score_final,
            "puntaje_base_ia": score_calidad,
            "score_rapidez": score_rapidez,
            "score_interes": score_interes,
            "penalizacion_sin_respuesta": penalizacion_sin_respuesta,
            "penalizacion_mal_atendido": penalizacion_mal_atendido,
            "score_detalle": {
                "calidad_atencion": score_calidad,
                "rapidez_respuesta": score_rapidez,
                "aprovechamiento_interes": score_interes,
                "penalizacion_sin_respuesta": penalizacion_sin_respuesta,
                "penalizacion_mal_atendido": penalizacion_mal_atendido,
                "formula": "50% calidad + 30% rapidez + 20% interés - penalizaciones",
            },
            "tiempo_primera_respuesta_segundos": prom_resp,
            "tiempo_primera_respuesta_label": _segundos_label(prom_resp),
            "citas": row["citas"],
            "facturados": row["facturados"],
            "agencia": row["agencias"].most_common(1)[0][0] if row["agencias"] else "",
            "business": row["business"].most_common(1)[0][0] if row["business"] else "",
            "deficiencias_principales": [{"nombre": x, "total": None} for x in _deficiencias_resumen_asesor(row, prom_resp)],
        })
    asesores.sort(key=lambda x: (x["mal_atendidos_pct"], -(x["puntaje_atencion"] or 0)), reverse=True)

    validos_tiempo = [a for a in asesores if a["tiempo_primera_respuesta_segundos"] is not None]
    mas_lento = max(validos_tiempo, key=lambda a: a["tiempo_primera_respuesta_segundos"], default=None)
    mediana_asesores = median([a["tiempo_primera_respuesta_segundos"] for a in validos_tiempo]) if validos_tiempo else None
    if mas_lento and mediana_asesores:
        mas_lento = {**mas_lento, "brecha_vs_mediana_pct": round(((mas_lento["tiempo_primera_respuesta_segundos"] / mediana_asesores) - 1) * 100, 1)}

    # Cruce pauta -> conversación/lead.
    for campana in campanas:
        nombre = _normaliza(campana.get("nombre_campana"))
        atribuidos = []
        for ctx in contextos:
            pauta = _normaliza(ctx.get("pauta"))
            if nombre and pauta and (nombre in pauta or pauta in nombre):
                atribuidos.append(ctx)
        campana["leads_crm_atribuidos"] = len(atribuidos)
        campana["interesados_crm"] = sum(
            1 for ctx in atribuidos
            if (audit_por_id.get(ctx["id"], {}).get("nivel_interes") in {"alto", "medio"}
                or audit_por_id.get(ctx["id"], {}).get("senal_compra"))
        )
        campana["interes_crm_pct"] = _porcentaje(campana["interesados_crm"], len(atribuidos))
        campana["mal_atendidos_crm"] = sum(1 for ctx in atribuidos if audit_por_id.get(ctx["id"], {}).get("mal_atendido"))
        campana["costo_por_interesado_crm"] = round(campana["gasto"] / campana["interesados_crm"], 2) if campana["interesados_crm"] else None

    metricas = {
        "conversaciones": total,
        "mensajes": sum(ctx.get("mensajes", 0) for ctx in contextos),
        "clientes_interesados": interesados,
        "clientes_interesados_pct": _porcentaje(interesados, total),
        "alta_intencion": alta_intencion,
        "alta_intencion_pct": _porcentaje(alta_intencion, total),
        "mal_atendidos": mal_atendidos,
        "mal_atendidos_pct": _porcentaje(mal_atendidos, total),
        "riesgo_alto": riesgo_alto,
        "riesgo_alto_pct": _porcentaje(riesgo_alto, total),
        "sin_respuesta_humana": sin_humano,
        "sin_respuesta_humana_pct": _porcentaje(sin_humano, total),
        "citas": citas,
        "facturados": facturados,
        "primera_respuesta_promedio_segundos": promedio,
        "primera_respuesta_promedio_label": _segundos_label(promedio),
        "primera_respuesta_mediana_segundos": mediana_t,
        "primera_respuesta_mediana_label": _segundos_label(mediana_t),
        "primera_respuesta_p90_segundos": p90,
        "primera_respuesta_p90_label": _segundos_label(p90),
        "campanas_activas_periodo": len(campanas),
        "gasto_meta": round(sum(float(c.get("gasto") or 0) for c in campanas), 2),
        "resultados_meta": sum(int(c.get("resultados") or 0) for c in campanas),
        "costo_resultado_meta": (
            round(sum(float(c.get("gasto") or 0) for c in campanas) / sum(int(c.get("resultados") or 0) for c in campanas), 2)
            if sum(int(c.get("resultados") or 0) for c in campanas) else None
        ),
        "conversaciones_tiempo_evaluable": sum(1 for ctx in contextos if ctx.get("medicion_tiempo_habilitada")),
        "conversaciones_tiempo_excluidas": sum(1 for ctx in contextos if not ctx.get("medicion_tiempo_habilitada")),
        "esperando_inicio_jornada": sum(1 for ctx in contextos if ctx.get("espera_fuera_horario")),
    }

    distribucion_interes = Counter(a.get("nivel_interes", "nulo") for a in auditorias)
    return {
        "metricas": metricas,
        "asesores": asesores,
        "asesor_mas_lento": mas_lento,
        "intereses": [{"nombre": k, "total": v, "pct": _porcentaje(v, total)} for k, v in modelos.most_common(12)],
        "objeciones": [{"nombre": k, "total": v, "pct": _porcentaje(v, total)} for k, v in objeciones.most_common(10)],
        "intenciones": [{"nombre": k, "total": v, "pct": _porcentaje(v, total)} for k, v in intenciones.most_common(10)],
        "deficiencias": [{"nombre": k, "total": v, "pct": _porcentaje(v, total)} for k, v in deficiencias.most_common(10)],
        "distribucion_interes": [
            {"nivel": nivel, "total": distribucion_interes.get(nivel, 0), "pct": _porcentaje(distribucion_interes.get(nivel, 0), total)}
            for nivel in ["alto", "medio", "bajo", "nulo"]
        ],
        "campanas": campanas,
    }

def _fallback_ejecutivo(agregados: dict) -> dict:
    m = agregados["metricas"]
    causas = []
    if m["sin_respuesta_humana"]:
        causas.append({
            "causa": "Prospectos sin respuesta humana", "evidencia": f"{m['sin_respuesta_humana_pct']}% de las conversaciones no registran respuesta humana.",
            "impacto": "Se pierden oportunidades antes de completar perfilamiento o cierre de siguiente acción.", "prioridad": "alta",
        })
    if m["mal_atendidos"]:
        causas.append({
            "causa": "Calidad de atención inconsistente", "evidencia": f"{m['mal_atendidos_pct']}% fueron clasificados como atención deficiente/crítica.",
            "impacto": "Incrementa riesgo de abandono en leads que ya mostraron interés.", "prioridad": "alta",
        })
    return {
        "resumen_ejecutivo": "El panel conserva métricas objetivas; la interpretación avanzada de OpenAI no estuvo disponible en esta ejecución.",
        "hallazgos_clave": [], "causas_raiz": causas,
        "recomendaciones_globales": [{
            "accion": "Atender primero conversaciones con interés alto y riesgo alto.",
            "motivo": "Combina intención comercial con riesgo de pérdida.",
            "impacto_esperado": "Reduce oportunidades que se enfrían por falta de seguimiento.", "prioridad": "alta",
        }],
        "recomendaciones_asesores": [], "recomendaciones_campanas": [],
        "prediccion": {
            "escenario_sin_mejoras": "Si se mantiene el patrón actual, las conversaciones hoy marcadas en riesgo alto seguirán expuestas a enfriamiento o abandono.",
            "riesgo": "alto" if m["riesgo_alto_pct"] >= 25 else ("medio" if m["riesgo_alto_pct"] >= 10 else "bajo"),
            "impacto_estimado": f"Actualmente {m['riesgo_alto']} conversaciones ({m['riesgo_alto_pct']}%) están en riesgo alto.",
            "nota_metodologica": "Escenario heurístico basado en el patrón del mes; no es una predicción financiera ni causal.",
        },
        "oportunidades": [],
    }


def _analisis_ejecutivo_openai(agregados: dict, auditorias: list[dict]) -> dict:
    client = _get_openai_client()
    payload = {
        "metricas": agregados["metricas"],
        "asesores": agregados["asesores"],
        "asesor_mas_lento": agregados["asesor_mas_lento"],
        "intereses": agregados["intereses"],
        "objeciones": agregados["objeciones"],
        "intenciones": agregados["intenciones"],
        "deficiencias": agregados["deficiencias"],
        "campanas": agregados["campanas"],
        "auditorias": [
            {
                "nivel_interes": a.get("nivel_interes"), "senal_compra": a.get("senal_compra"),
                "calidad_atencion": a.get("calidad_atencion"), "puntaje_atencion": a.get("puntaje_atencion"),
                "mal_atendido": a.get("mal_atendido"), "riesgo_perdida": a.get("riesgo_perdida"),
                "deficiencias": a.get("deficiencias"), "objeciones": a.get("objeciones"),
                "causa_perdida_probable": a.get("causa_perdida_probable"),
            }
            for a in auditorias
        ],
    }
    response = client.responses.create(
        model=_modelo_openai(),
        instructions=PROMPT_EJECUTIVO,
        input=json.dumps(
            payload,
            ensure_ascii=False,
        ),
        reasoning={
            "effort": "none",
        },
        text={
            "format": {
                "type": "json_schema",
                "name": "analisis_ejecutivo",
                "schema": OPENAI_EJECUTIVO_SCHEMA,
                "strict": False,
            }
        },
        temperature=0.2,
        store=False,
    )

    data = _parse_json(
        getattr(
            response,
            "output_text",
            "",
        )
        or ""
    )

    if not data:
        raise RuntimeError(
            "OpenAI no devolvió un análisis ejecutivo JSON válido"
        )
    return data

def _fusionar_recomendaciones_asesores(agregados: dict, ejecutivo: dict, auditorias: list[dict]):
    ai_rows = { _normaliza(x.get("asesor")): x for x in ejecutivo.get("recomendaciones_asesores") or [] if isinstance(x, dict) }
    audit_por_asesor = defaultdict(list)
    # El id no contiene asesor, por lo que las recomendaciones individuales se agregan después desde contextos en la vista.
    for row in agregados["asesores"]:
        ai = ai_rows.get(_normaliza(row["asesor"]), {})
        row["fortalezas"] = list(ai.get("fortalezas") or [])
        row["recomendaciones"] = list(ai.get("recomendaciones") or [])
        row["prioridad"] = ai.get("prioridad") or ("alta" if row["mal_atendidos_pct"] >= 30 else "media")
        extra_def = list(ai.get("deficiencias") or [])
        existentes = [x["nombre"] for x in row.get("deficiencias_principales") or []]
        row["deficiencias_ia"] = list(dict.fromkeys(existentes + extra_def))[:6]


def _fusionar_recomendaciones_campanas(agregados: dict, ejecutivo: dict):
    recomendaciones = ejecutivo.get("recomendaciones_campanas") or []
    for campana in agregados["campanas"]:
        nombre = _normaliza(campana.get("nombre_campana"))
        match = next((x for x in recomendaciones if nombre and (
            nombre in _normaliza(x.get("campana")) or _normaliza(x.get("campana")) in nombre
        )), None)
        campana["analisis_ia"] = match or {}

@api_view(["GET"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def resultados_ia_view(request):
    lineas, error, es_admin, es_coordinador = _lineas_permitidas(request)
    if error:
        return error

    horario_respuesta = _parsear_horario_respuesta(request.query_params.get("horario_respuesta", ""))
    lineas_excluidas_tiempo = _parsear_lineas_excluidas_tiempo(
        request.query_params.get("lineas_excluir_tiempo", ""),
        lineas,
    )

    if _normaliza(request.query_params.get("configuracion", "")) in {"1", "true", "si", "yes"}:
        return Response({
            "ok": True,
            "solo_configuracion": True,
            "horario_predeterminado": _copiar_horario_predeterminado(),
            "lineas": [
                {
                    "numero": numero,
                    "asesor_digital": _texto(WHATSAPP_LINES.get(numero, {}).get("asesor_digital")),
                    "agencia": _texto(WHATSAPP_LINES.get(numero, {}).get("agencia")),
                    "business": _texto(WHATSAPP_LINES.get(numero, {}).get("business")),
                }
                for numero in lineas
            ],
        })

    # Estas sí participarán en el análisis completo.
    lineas_analisis = [numero for numero in lineas if numero not in lineas_excluidas_tiempo]

    mes, inicio, fin = _rango_mes(request.query_params.get("mes", ""))
    forzar = _normaliza(request.query_params.get("forzar", "")) in {"1", "true", "si", "yes"}
    agencia = _texto(request.query_params.get("agencia", ""))
    business = _texto(request.query_params.get("business", ""))
    solo_bd = _normaliza(request.query_params.get("solo_bd", "")) in {"1", "true", "si", "yes"}

    firma = (
        MensajeWhatsApp.objects
        .filter(numero_asesor__in=lineas_analisis, created_at__gte=inicio, created_at__lt=fin)
        .aggregate(total=Count("id"), ultimo_id=Max("id"), ultimo_at=Max("created_at"))
    )

    firma_config = hashlib.sha1(
        json.dumps(
            {
                "horario": horario_respuesta,
                "lineas_excluidas": sorted(lineas_excluidas_tiempo),
            },
            sort_keys=True,
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()[:12]

    cache_key = "digitales:resultados_ia:" + ":".join([
        mes,
        ",".join(sorted(lineas_analisis)),
        _normaliza(agencia) or "todos",
        _normaliza(business) or "todos",
        firma_config,
        str(firma.get("total") or 0),
        str(firma.get("ultimo_id") or 0),
    ])

    if not solo_bd and not forzar:
        cached = cache.get(cache_key)
        if isinstance(cached, dict):
            cached = {**cached, "cache": True}
            return Response(cached)

    contextos, cobertura_base = _contextos_conversacion(
        lineas=lineas_analisis,
        inicio=inicio,
        fin=fin,
        request=request,
        es_admin=es_admin,
        es_coordinador=es_coordinador,
        horario_respuesta=horario_respuesta,
        lineas_excluidas_tiempo=lineas_excluidas_tiempo,
    )

    campanas = _campanas_mes(inicio=inicio, fin=fin, agencia_filtro=agencia)

    if solo_bd:
        base = _agregar_metricas_bd(contextos, campanas)
        return Response({
            "ok": True,
            "solo_bd": True,
            "mes": mes,
            "rango": {"inicio": inicio.isoformat(), "fin_exclusivo": fin.isoformat()},
            "generado_at": timezone.now().isoformat(),
            "cobertura": {**cobertura_base, "conversaciones": len(contextos)},
            **base,
            "lineas": [
                {
                    "numero": numero,
                    "asesor_digital": _texto(WHATSAPP_LINES.get(numero, {}).get("asesor_digital")),
                    "agencia": _texto(WHATSAPP_LINES.get(numero, {}).get("agencia")),
                    "business": _texto(WHATSAPP_LINES.get(numero, {}).get("business")),
                }
                for numero in lineas
            ],
            "filtros": {"agencia": agencia, "business": business, "numero_asesor": request.query_params.get("numero_asesor", "")},
            "configuracion_tiempo_respuesta": {
                "horario": horario_respuesta,
                "lineas_excluidas": sorted(lineas_excluidas_tiempo),
                "metodo": "minutos_habiles_con_pausa_comida",
                "nota": "No se contabilizan horas fuera de jornada ni la pausa de comida configurada.",
            },
        })

    errores_ia = []
    limite_ia = time_module.monotonic() + OPENAI_PRESUPUESTO_SEGUNDOS

    try:
        auditorias, errores_lotes = _auditar_con_openai(
            contextos,
            limite_tiempo=limite_ia,
        )
        errores_ia.extend(errores_lotes)
    except Exception as exc:
        logger.exception("No fue posible iniciar auditoría OpenAI de resultados")
        errores_ia.append(str(exc))
        auditorias = [_fallback_auditoria(ctx) for ctx in contextos]

    agregados = _agregar_metricas(contextos, auditorias, campanas)

    try:
        tiempo_disponible = time_module.monotonic() < limite_ia
        if contextos and tiempo_disponible:
            ejecutivo = _analisis_ejecutivo_openai(agregados, auditorias)
            ia_ejecutiva = True
        else:
            ejecutivo = _fallback_ejecutivo(agregados)
            ia_ejecutiva = False
            if contextos:
                errores_ia.append("El análisis ejecutivo utilizó fallback porque se alcanzó el presupuesto máximo de tiempo IA.")
    except Exception as exc:
        logger.exception("Error generando análisis ejecutivo de resultados")
        errores_ia.append(str(exc))
        ejecutivo = _fallback_ejecutivo(agregados)
        ia_ejecutiva = False

    _fusionar_recomendaciones_asesores(agregados, ejecutivo, auditorias)
    _fusionar_recomendaciones_campanas(agregados, ejecutivo)

    payload = {
        "ok": True,
        "cache": False,
        "mes": mes,
        "rango": {"inicio": inicio.isoformat(), "fin_exclusivo": fin.isoformat()},
        "generado_at": timezone.now().isoformat(),
        "modelo_ia": _modelo_openai(),
        "ia": {
            "disponible": not errores_ia,
            "analisis_ejecutivo_generado": ia_ejecutiva,
            "errores": errores_ia[:6],
        },
        "cobertura": {
            **cobertura_base,
            "conversaciones": len(contextos),
            "auditadas": len(auditorias),
            "porcentaje": _porcentaje(len(auditorias), len(contextos)),
            "nota": "Las conversaciones extremadamente largas pueden recortarse en el tramo central para respetar límites del modelo.",
        },
        **agregados,
        "analisis": ejecutivo,
        "lineas": [
            {
                "numero": numero,
                "asesor_digital": _texto(WHATSAPP_LINES.get(numero, {}).get("asesor_digital")),
                "agencia": _texto(WHATSAPP_LINES.get(numero, {}).get("agencia")),
                "business": _texto(WHATSAPP_LINES.get(numero, {}).get("business")),
            }
            for numero in lineas
        ],
        "filtros": {"agencia": agencia, "business": business, "numero_asesor": request.query_params.get("numero_asesor", "")},
        "configuracion_tiempo_respuesta": {
            "horario": horario_respuesta,
            "lineas_excluidas": sorted(lineas_excluidas_tiempo),
            "metodo": "minutos_habiles_con_pausa_comida",
            "nota": "El tiempo fuera del horario configurado y la pausa de comida no se suman; una conversación aún fuera de jornada no se penaliza como falta de respuesta.",
        },
    }

    cache.set(cache_key, payload, CACHE_SECONDS)
    return Response(payload)