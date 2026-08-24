#Digitales/IA.py
from __future__ import annotations

import json
import logging
import re
import time
import unicodedata

from datetime import datetime
from zoneinfo import ZoneInfo
from difflib import SequenceMatcher
from functools import lru_cache
from typing import Any, Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from openai import OpenAI

from google import genai
from google.genai import types

from .sett import WHATSAPP_LINES
from citas.models import ClienteComercial, normaliza_tel_mx
from .models import ExpedienteDigital, MensajeWhatsApp, ConfiguracionIAWhatsApp, ConversacionIA
from .contacto import (
    enviar_texto_whatsapp,
    enviar_documento_whatsapp_por_link,
    enviar_imagen_whatsapp_por_link,
    enviar_video_whatsapp_por_link,
    replace_start,
    download_media_whatsapp,
    enviar_indicador_escribiendo_whatsapp,
)
from .ia_catalogo import obtener_catalogo_activo_para_ia

logger = logging.getLogger(__name__)

# Sucursales y geolocalización por LADA 
SUCURSALES_VW: list[dict] = [
     {
        "nombre": "Agencia VW Cordoba",
        "ciudad": "Cordoba, Veracruz",
        "direccion": "Av. No. 1, C. 26, 94550 Córdoba, Ver.",
        "telefono": "271-313-3332",
        "horario": "Lun-Sáb 9:00-19:00",
        "ladas_cercanas": ["271"], #271=Córdoba
        "google_maps": "https://maps.app.goo.gl/7zy5EiGe1N1wXzuC9",
    },
    {
        "nombre": "Agencia VW Orizaba",
        "ciudad": "Orizaba, Veracruz",
        "direccion": "Blvd. Sur 3, Orizaba, Ver.",
        "telefono": "272-111-1244",
        "horario": "Lun-Sáb 9:00-19:00",
        "ladas_cercanas": ["272"],  # 272=Orizaba
        "google_maps": "https://maps.app.goo.gl/7zy5EiGe1N1wXzuC9",
    },
    {
        "nombre": "Agencia VW Tuxtepec",
        "ciudad": "Tuxtepec, Oaxaca",
        "direccion": "Miguel Alemán Km 13, El Diamante, 68300 San Juan Bautista Tuxtepec, Oax.",
        "telefono": "287-123-2641",
        "horario": "Lun-Sáb 9:00-19:00",
        "ladas_cercanas": ["287"],  # 287=Tuxtepec
        "google_maps": "https://maps.app.goo.gl/7zy5EiGe1N1wXzuC9",
    },
    {
        "nombre": "Agencia VW Poza Rica",
        "ciudad": "Poza Rica, Veracruz",
        "direccion": "Carr. Poza Rica - Cazones 3702, La Rueda, 93306 Poza Rica de Hidalgo, Ver.",
        "telefono": "782-182-0706",
        "horario": "Lun-Sáb 9:00-19:00",
        "ladas_cercanas": ["782"],  # 782=Poza Rica
        "google_maps": "https://maps.app.goo.gl/9KNBE2ied2EL8S6y7",
    },
    {
        "nombre": "Agencia VW Tuxpan",
        "ciudad": "Tuxpan, Veracruz",
        "direccion": "Blvd. Independencia 144, Burocratica, 92870 Túxpan de Rodríguez Cano, Ver.",
        "telefono": "783-126-3814",
        "horario": "Lun-Sáb 9:00-19:00",
        "ladas_cercanas": ["783"],  # 783=Tuxpan
        "google_maps": "https://maps.app.goo.gl/fjP5JD6n3hqKiCsp9",
    },
]

IA_CONFIG_GLOBAL_KEY = "GLOBAL"

def _obtener_config_ia(numero_asesor: str) -> dict:
    """
    Obtiene la configuración propia de IA para el número de WhatsApp.

    Antes:
    - Si no encontraba configuración del número, usaba GLOBAL.

    Ahora:
    - Solo usa configuración propia del número.
    - Si el número no tiene configuración o está inactiva, devuelve {}.
    """
    numero_asesor = normaliza_tel_mx(numero_asesor or "")

    if not numero_asesor:
        return {}

    cfg = ConfiguracionIAWhatsApp.objects.filter(
        numero_asesor=numero_asesor,
    ).first()

    if not cfg:
        return {}

    if not cfg.activo:
        return {}

    return {
        "identidad": cfg.identidad or "",
        "precios": cfg.precios or "",
        "perfilamiento": cfg.perfilamiento or "",
        "limites": cfg.limites or "",
        "personalidad": cfg.personalidad or "",
        "condiciones_fijas": cfg.condiciones_fijas or "",
        "promociones_eventos": cfg.promociones_eventos or "",
    }

def _clave_catalogo(item: dict) -> str:
    base = f"{item.get('modelo', '')} {item.get('ano', '')}".strip().upper()

    if item.get("version"):
        base = f"{base} {item.get('version')}".strip().upper()

    return base


def _obtener_catalogo_dict() -> dict:
    items = obtener_catalogo_activo_para_ia()

    catalogo = {}

    for item in items:
        clave = _clave_catalogo(item)
        if clave:
            catalogo[clave] = item

    return catalogo


def _normalizar_version_catalogo(version: str | None) -> str | None:
    if not version:
        return None

    version_normalizada = str(version).strip().upper()
    catalogo = _obtener_catalogo_dict()

    return version_normalizada if version_normalizada in catalogo else None


def _catalogo_para_prompt() -> list[dict]:
    return obtener_catalogo_activo_para_ia()


def _texto_precios_version(version: str) -> str:
    catalogo = _obtener_catalogo_dict()
    item = catalogo.get(str(version or "").strip().upper())

    if not item:
        return "Por el momento no tengo precio activo para ese modelo."

    precio_lista = item.get("precio_lista")
    precio_contado = item.get("precio_contado")
    precio_financiado = item.get("precio_financiado")

    lineas = []

    if precio_lista:
        lineas.append(f"Precio de lista: ${precio_lista:,.0f} MXN")

    if precio_contado:
        lineas.append(f"Precio contado: ${precio_contado:,.0f} MXN")

    if precio_financiado:
        lineas.append(f"Precio financiado: ${precio_financiado:,.0f} MXN")

    return "\n".join(lineas) if lineas else "Por el momento no tengo precio activo para ese modelo."


def _resumen_ficha_texto(version: str) -> str:
    catalogo = _obtener_catalogo_dict()
    item = catalogo.get(str(version or "").strip().upper())

    if not item:
        return "Con gusto te comparto información, pero necesito confirmar el modelo exacto."

    resumen = item.get("resumen") or ""
    ficha = item.get("ficha_tecnica") or {}

    lineas = []

    if resumen:
        lineas.append(resumen)

    if isinstance(ficha, dict):
        for clave, valor in ficha.items():
            if valor:
                lineas.append(f"• {clave}: {valor}")

    return "\n".join(lineas).strip() or "Tengo información disponible de este modelo."


def _imagenes_de_version(version: str) -> list[str]:
    catalogo = _obtener_catalogo_dict()
    item = catalogo.get(str(version or "").strip().upper())

    if not item:
        return []

    imagenes = item.get("imagenes") or []

    return imagenes if isinstance(imagenes, list) else []

def _videos_de_version(version: str) -> list[str]:
    catalogo = _obtener_catalogo_dict()
    item = catalogo.get(str(version or "").strip().upper())

    if not item:
        return []

    videos = item.get("videos") or []

    return videos if isinstance(videos, list) else []

def _lada_de_telefono(telefono: str) -> str:
    """Extrae la LADA (3 dígitos) de un número mexicano normalizado (10 dígitos sin +52)."""
    tel = re.sub(r"\D", "", telefono or "")
    if tel.startswith("52") and len(tel) == 12:
        tel = tel[2:]
    if len(tel) == 10:
        return tel[:3]
    return ""


def _sucursal_mas_cercana(telefono: str) -> dict:
    """Devuelve la sucursal más cercana según la LADA del teléfono del cliente."""
    lada = _lada_de_telefono(telefono)
    if lada:
        for sucursal in SUCURSALES_VW:
            if lada in sucursal.get("ladas_cercanas", []):
                return sucursal
    return SUCURSALES_VW[0] if SUCURSALES_VW else {}


def _texto_ubicacion(telefono: str) -> str:
    s = _sucursal_mas_cercana(telefono)
    if not s:
        return "Por favor contáctanos directamente para indicarte nuestra ubicación."
    lineas = [
        f"📍 *Ubicación de tu Agencia VW más cercana:*",
        f"",
        f"🏢 *Agencia:* {s['nombre']}",
        f"🏙️ *Ciudad:* {s['ciudad']}",
        f"🗺️ *Dirección:* {s['direccion']}",
        f"📞 *Teléfono:* {s['telefono']}",
        f"🕐 *Horario:* {s['horario']}",
    ]
    if s.get("google_maps"):
        lineas += [
            f"",
            f"🔗 *Cómo llegar:*",
            f"{s['google_maps']}",
        ]
    lineas += [
        f"",
        f"¡Te esperamos! 🚗",
    ]
    return "\n".join(lineas)


def _enganche_referencial(version: str) -> Optional[str]:
    item = _obtener_catalogo_dict().get(str(version or "").strip().upper())

    if not item:
        return None

    precio_num = item.get("precio_lista")

    if not precio_num:
        return None

    enganche = round(int(precio_num) * 0.20 / 1000) * 1000

    return f"${enganche:,} MXN aprox. (20% referencial)"

COMPARACION_DESEMPENO: dict[str, dict] = {
    "GTI 2026":                      {"hp": 261, "nm": 370, "motor": "2.0L TSI", "transmision": "DSG 7"},
    "GLI 2026":                      {"hp": 230, "nm": 350, "motor": "2.0L TSI", "transmision": "Automatica"},
    "CROSS SPORT 2026":              {"hp": 269, "nm": 350, "motor": "2.0L TSI", "transmision": "Automatica"},
    "TERAMONT 2026":                 {"hp": 269, "nm": 350, "motor": "2.0L TSI", "transmision": "Automatica"},
    "JETTA 2026":                    {"hp": 150, "nm": 250, "motor": "1.4L TSI", "transmision": "Tiptronic 8"},
    "TIGUAN 2026":                   {"hp": 150, "nm": 250, "motor": "1.4L TSI", "transmision": "DSG 7"},
    "TAOS 2026":                     {"hp": 150, "nm": 250, "motor": "1.4L TSI", "transmision": "Tiptronic 8"},
    "NUEVO NIVUS 2026":              {"hp": 114, "nm": 200, "motor": "1.0L TSI", "transmision": "Automatica"},
    "TAIGUN 2026":                   {"hp": 114, "nm": 200, "motor": "1.0L TSI", "transmision": "Tiptronic 6"},
    "TERA 2026":                     {"hp": 114, "nm": 200, "motor": "1.0L TSI", "transmision": "Automatica"},
    "VIRTUS 2026":                   {"hp": 114, "nm": 178, "motor": "1.0L TSI", "transmision": "Tiptronic 6"},
    "POLO 2026":                     {"hp": 109, "nm": 155, "motor": "1.6L MPI", "transmision": "Manual"},
    "SAVEIRO 2026":                  {"hp": 109, "nm": 145, "motor": "1.6L",     "transmision": "Manual"},
    "TRANSPORTER COMBI 5 ASIENTOS": {"hp": 120, "nm": 360, "motor": "2.0L TDI Diesel", "transmision": "Manual 6"},
    "TRANSPORTER COMBI 8 ASIENTOS": {"hp": 150, "nm": 360, "motor": "2.0L TDI Diesel", "transmision": "Automatica 8"},
    "TRANSPORTER COMBI 9 ASIENTOS": {"hp": 150, "nm": 360, "motor": "2.0L TDI Diesel", "transmision": "Automatica 8"},
}

# Perfilado / filtrado de leads
ENGANCHE_MINIMO_CALIFICADO = 69_000   # MXN

ETAPA_PERFILADO = {
    "sin_iniciar":    0,
    "pedir_nombre":   1,
    "pedir_enganche": 2,
    "pedir_buro":     3,
    "completado":     4,
}

STOPWORDS_NOMBRE = {
    "HOLA", "HOLAA", "HOLAAA", "BUENAS", "SALUDOS", "BUENOS", "DIAS", "TARDES", "NOCHES", "HEY", "HI",
    "SI", "SÍ", "SÍP", "SIP", "OK", "OKEY", "VA", "CLARO", "EN", "PDF", "MANDAMELA", "MANDAME",
    "COMPARTELA", "COMPARTEME", "COMPARTEMELA", "FICHA", "TECNICA", "PRECIO",
    "QUIERO", "NECESITO", "PASAME", "PASAMELA", "LISTO", "PERFECTO", "SALE",
    "SERVICIO", "PUBLICO", "TRANSPORTE", "LINEA", "IMAGEN", "IMAGENES", "FOTO", "FOTOS",
    "FINANCIAMIENTO", "CREDITO", "MENSUALIDADES", "COTIZACION", "5", "8", "9",
}

PALABRAS_COTIZACION = {
    "COTIZACION", "COTIZAR", "COTIZA", "PROPUESTA", "PROPUESTA FORMAL",
    "CORRIDA", "CORRIDA FINANCIERA", "MENSUALIDADES", "MENSUALIDAD",
    "ENGANCHE", "PLAN DE PAGOS", "FINANCIAMIENTO", "CREDITO", "LEASING",
    "ARRENDAMIENTO", "NUMEROS", "PAGOS",
}

PALABRAS_COMPRA = {
    "COMPRAR", "ADQUIRIR", "APARTAR", "QUIERO LA UNIDAD", "QUIERO COMPRAR",
    "ME INTERESA COMPRAR", "QUIERO AVANZAR", "QUIERO QUE ME CONTACTEN",
    "QUIERO HABLAR CON VENTAS", "ATENCION PERSONALIZADA",
}

ACCIONES_OFRECIDAS_VALIDAS = {
    "saludo_inicial", "pedir_nombre", "pedir_necesidad", "compartir_precio",
    "compartir_pdf", "confirmar_canalizacion", "preguntar_tipo_cliente",
    "preguntar_forma_pago", "continuar_contexto", "pedir_enganche",
    "pedir_buro", "lead_calificado", "ninguna",
}

PALABRAS_CATALOGO_ANTERIOR = {
    "CRAFTER", "CRAFTER ELEMENTAL", "CRAFTER INSPIRE", "CRAFTER ELITE", "CRAFTER URBAN",
    "ELEMENTAL", "INSPIRE", "ELITE", "URBAN",
}

_ALIASES_VERSION: dict[str, list[str]] = {
    "TRANSPORTER COMBI 5 ASIENTOS": [
        "TRANSPORTER COMBI 5 ASIENTOS", "TRANSPORTER 5 ASIENTOS", "COMBI 5 ASIENTOS",
        "VERSION 5 ASIENTOS", "5 ASIENTOS", "CINCO ASIENTOS", "LA DE 5", "EL DE 5",
    ],
    "TRANSPORTER COMBI 8 ASIENTOS": [
        "TRANSPORTER COMBI 8 ASIENTOS", "TRANSPORTER 8 ASIENTOS", "COMBI 8 ASIENTOS",
        "VERSION 8 ASIENTOS", "8 ASIENTOS", "OCHO ASIENTOS", "LA DE 8", "EL DE 8",
    ],
    "TRANSPORTER COMBI 9 ASIENTOS": [
        "TRANSPORTER COMBI 9 ASIENTOS", "TRANSPORTER 9 ASIENTOS", "COMBI 9 ASIENTOS",
        "VERSION 9 ASIENTOS", "9 ASIENTOS", "NUEVE ASIENTOS", "LA DE 9", "EL DE 9",
    ],
    "POLO 2026":         ["POLO 2026", "POLO TRACK", "EL POLO", "POLO"],
    "VIRTUS 2026":       ["VIRTUS 2026", "EL VIRTUS", "VIRTUS"],
    "TERA 2026":         ["TERA 2026", "EL TERA", "TERA"],
    "NUEVO NIVUS 2026":  ["NUEVO NIVUS 2026", "NIVUS 2026", "EL NIVUS", "NIVUS"],
    "JETTA 2026":        ["JETTA 2026", "EL JETTA", "JETTA"],
    "GLI 2026":          ["GLI 2026", "EL GLI", "GLI"],
    "GTI 2026":          ["GTI 2026", "EL GTI", "GTI"],
    "SAVEIRO 2026":      ["SAVEIRO 2026", "EL SAVEIRO", "SAVEIRO", "SAVEIRO ROBUST", "SAVEIRO EXTREME"],
    "TAIGUN 2026":       ["TAIGUN 2026", "EL TAIGUN", "TAIGUN"],
    "TAOS 2026":         ["TAOS 2026", "EL TAOS", "TAOS"],
    "TIGUAN 2026":       ["TIGUAN 2026", "EL TIGUAN", "TIGUAN"],
    "TERAMONT 2026":     ["TERAMONT 2026", "EL TERAMONT", "TERAMONT", "TERAMONT PEAK", "TERAMONT HIGHLINE"],
    "CROSS SPORT 2026":  ["CROSS SPORT 2026", "CROSS SPORT", "EL CROSS SPORT", "CROSSSPORT"],
}


# Utilidades de texto
def _strip_accents(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto or "")
        if unicodedata.category(c) != "Mn"
    )


def _normalizar_texto(texto: str) -> str:
    texto = _strip_accents(texto or "").upper().strip()
    texto = re.sub(r"[^A-Z0-9$@._ -]+", " ", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto


def _media_base_url() -> str:
    base = getattr(settings, "PUBLIC_API_BASE_URL", "").rstrip("/")
    media_url = getattr(settings, "MEDIA_URL", "/media/")
    return f"{base}{media_url}"


def _build_media_url(relativo: str) -> str:
    return f"{_media_base_url()}{relativo}".replace(" ", "%20")

def _resolver_url_media(valor: str) -> str:
    valor = str(valor or "").strip()

    if not valor:
        return ""

    if valor.startswith("http://") or valor.startswith("https://"):
        return valor

    return _build_media_url(valor)

def _build_pdf_url(pdf_relativo: str) -> str:
    return _build_media_url(pdf_relativo)


def _limitar_texto(texto: str, max_len: int = 900) -> str:
    texto = re.sub(r"\n{3,}", "\n\n", (texto or "").strip())
    if len(texto) <= max_len:
        return texto
    return texto[: max_len - 3].rstrip() + "..."


def _es_email(texto: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", (texto or "").strip()))


def _limpiar_nombre_candidato(texto: str) -> str:
    texto = re.sub(r"[^a-zA-ZáéíóúÁÉÍÓÚüÜñÑ ]+", " ", texto or "").strip()
    return re.sub(r"\s+", " ", texto)


def _parece_nombre_solo(texto: str) -> bool:
    texto = (texto or "").strip()
    if not texto or _es_email(texto):
        return False
    texto_limpio = _limpiar_nombre_candidato(texto)
    if not texto_limpio:
        return False
    palabras = [p.upper() for p in texto_limpio.split() if p.strip()]
    if not palabras or len(palabras) > 3:
        return False
    if any(p in STOPWORDS_NOMBRE for p in palabras):
        return False
    if any(len(p) < 2 for p in palabras):
        return False
    return True


def _extraer_nombre_basico(profile_name: str, texto: str) -> str:
    """
    Extrae únicamente nombres que el cliente escribió explícitamente.

    El profile_name de WhatsApp NO se considera un nombre confirmado.
    Más adelante se usa solo como candidato para preguntarle al cliente
    si desea ser registrado con ese nombre.
    """
    texto = (texto or "").strip()
    for patron in [
        r"\bmi nombre es\s+([a-zA-ZáéíóúÁÉÍÓÚüÜñÑ ]{2,80})",
        r"\bme llamo\s+([a-zA-ZáéíóúÁÉÍÓÚüÜñÑ ]{2,80})",
        r"\bsoy\s+([a-zA-ZáéíóúÁÉÍÓÚüÜñÑ ]{2,80})",
    ]:
        m = re.search(
            patron,
            texto,
            flags=re.IGNORECASE,
        )

        if m:
            nombre = _limpiar_nombre_candidato(
                re.sub(
                    r"\s+",
                    " ",
                    m.group(1),
                ).strip(" .,-")
            )

            if nombre and not _es_email(nombre):
                return nombre
    if _parece_nombre_solo(texto):
        return _limpiar_nombre_candidato(texto)
    return ""

def _json_seguro(texto: str) -> dict[str, Any]:
    """Parsea JSON robusto: maneja prefijos, markdown, trailing commas y JSON truncado."""
    texto = (texto or "").strip()
    if not texto:
        return {}
    try:
        return json.loads(texto)
    except Exception:
        pass
    texto_limpio = re.sub(r"```(?:json)?\s*", "", texto).strip()
    texto_limpio = re.sub(r"```\s*$", "", texto_limpio).strip()
    try:
        return json.loads(texto_limpio)
    except Exception:
        pass
    m = re.search(r"\{.*\}", texto_limpio, flags=re.DOTALL)
    if m:
        fragmento = m.group(0)
        try:
            return json.loads(fragmento)
        except Exception:
            pass
        fragmento_rep = re.sub(r",\s*([}\]])", r"\1", fragmento)
        try:
            return json.loads(fragmento_rep)
        except Exception:
            pass
        try:
            cierre = "]" * max(fragmento_rep.count("[") - fragmento_rep.count("]"), 0)
            cierre += "}" * max(fragmento_rep.count("{") - fragmento_rep.count("}"), 0)
            return json.loads(fragmento_rep + cierre)
        except Exception:
            pass
    return {}


def _texto_refiere_catalogo_anterior(texto: str) -> bool:
    t = _normalizar_texto(texto)
    return "CRAFTER" in t or any(f in t for f in PALABRAS_CATALOGO_ANTERIOR)


def _raw_refiere_catalogo_anterior(raw: Any) -> bool:
    if not isinstance(raw, dict):
        return False
    candidatos = [
        raw.get("version_contexto"), raw.get("filename"),
        raw.get("document_link"), raw.get("media_link"), raw.get("body"),
    ]
    d = raw.get("decision") or {}
    if isinstance(d, dict):
        candidatos += [d.get("selected_version"), d.get("reply_text")]
    return any(_texto_refiere_catalogo_anterior(str(c or "")) for c in candidatos)


def _mensaje_de_historial_vigente(*, body: str, raw: Any = None) -> bool:
    if _texto_refiere_catalogo_anterior(body or ""):
        return False
    if _raw_refiere_catalogo_anterior(raw):
        return False
    return True


def _limpiar_auto_interes_invalido(expediente: ExpedienteDigital) -> Optional[str]:
    ai = (expediente.auto_interes or "").strip()
    if not ai:
        return None
    if ai in _obtener_catalogo_dict():
        return ai
    expediente.auto_interes = ""
    expediente.save(update_fields=["auto_interes", "actualizado"])
    return None


def _buscar_version_en_texto(texto: str) -> Optional[str]:
    t = _normalizar_texto(texto)
    for version, aliases in _ALIASES_VERSION.items():
        for alias in aliases:
            if _normalizar_texto(alias) in t:
                return version
    return None

def _respuesta_precio_version(version: str) -> str:
    return _limitar_texto(
        f"Precios de {version.title()}:\n\n{_texto_precios_version(version)}\n\n"
        "Si gustas, tambien te comparto la ficha tecnica en PDF."
    )

def _detectar_intencion_minima(texto_usuario: str) -> dict[str, bool]:
    t = _normalizar_texto(texto_usuario)
    return {
        "pregunta_precio": any(k in t for k in [
            "PRECIO", "PRECIOS", "COSTO", "COSTOS", "CUANTO CUESTA", "CUANTO VALE",
            "CUANTO SALE", "CUANTO ESTA", "EN CUANTO", "A CUANTO",
            "VALE", "CUESTA", "SALE", "$", "MXN", "PESOS", "DESDE", "MONTO",
            "VERSION", "VERSIONES", "VERSIÓN", "TRIMS", "TRIM", "CUAL TIENE", "QUE VERSIONES",
        ]),
        "pregunta_pdf": any(k in t for k in [
            "PDF", "FICHA", "FICHA TECNICA", "ESPECIFICACIONES", "SPECS",
            "CATALOGO", "DETALLES", "BROCHURE", "INFO", "INFORMACION",
            "DATOS", "CARACTERISTICAS", "QUE TRAE", "QUE TIENE", "COMO ES",
            "CUENTAME", "DIME MAS",
        ]),
        "pregunta_imagenes": any(k in t for k in [
            "IMAGEN", "IMAGENES", "FOTO", "FOTOS", "FOTOGRAFIA",
            "PIC", "PICS", "MUESTRAME FOTOS","MUESTRAME IMAGENES",
            "MANDAME FOTOS", "MANDAME IMAGENES", "PASAME FOTOS",
            "PASAME IMAGENES", "COMO SE VE",
        ]),
        "pregunta_videos": any(k in t for k in [
            "VIDEO", "VIDEOS", "GRABACION", "GRABACIÓN", "RECORRIDO",
            "TOUR", "REEL", "COMO SE VE EN VIDEO", "MANDAME VIDEO",
            "MÁNDAME VIDEO", "PASAME VIDEO", "PÁSAME VIDEO",
            "QUIERO VERLO EN VIDEO", "VERLO EN VIDEO",
        ]),
        "cotizacion_personalizada": any(k in t for k in PALABRAS_COTIZACION),
        "intencion_compra": any(k in t for k in PALABRAS_COMPRA),
        "pregunta_desempeno": any(k in t for k in [
            "RAPIDO", "MAS RAPIDO", "VELOZ", "POTENTE", "MAS POTENTE", "MAS HP",
            "CABALLOS", "HP", "TORQUE", "CUAL ES MEJOR", "COMPARAR",
            "DIFERENCIA", "VS", "VERSUS", "ENTRE EL", "ENTRE LA",
        ]),
        "pregunta_catalogo": any(k in t for k in [
            "QUE MODELOS", "CUALES TIENES", "CUALES SON", "QUE TIENEN", "CATALOGO",
            "QUE AUTOS", "QUE CARROS", "QUE VEHICULOS", "OPCIONES TIENES",
            "TIENEN", "MANEJAN", "VENDEN",
        ]),
        "pregunta_arrendamiento": any(k in t for k in [
            "ARRENDAMIENTO", "ARRENDAR", "LEASING", "RENTA", "RENTA LARGA",
        ]),
        #señal de ubicación ────────────────────────────────────
        "pregunta_ubicacion": any(k in t for k in [
            "UBICACION", "DONDE ESTAN", "DONDE QUEDAN", "DONDE SE ENCUENTRAN",
            "DIRECCION", "COMO LLEGAR", "MAPA", "MAPS", "AGENCIA", "SUCURSAL",
            "DONDE PUEDO IR", "EN PERSONA", "VISITAR", "DONDE ES",
        ]),
    }

# Perfilado de leads
_NUMEROS_LETRAS_MONTO: dict[str, int] = {
    "DIEZ": 10, "ONCE": 11, "DOCE": 12, "TRECE": 13, "CATORCE": 14, "QUINCE": 15,
    "VEINTE": 20, "TREINTA": 30, "CUARENTA": 40, "CINCUENTA": 50,
    "SESENTA": 60, "SETENTA": 70, "OCHENTA": 80, "NOVENTA": 90,
    "CIEN": 100, "CIENTO": 100, "CIENTO CINCUENTA": 150, "DOSCIENTOS": 200,
    "TRESCIENTOS": 300, "CUATROCIENTOS": 400, "QUINIENTOS": 500,
}

def _extraer_monto_pesos(texto: str) -> Optional[int]:
    """Extrae monto en pesos. Soporta digitos, sufijos K/MIL y numeros en letras."""
    if not texto:
        return None
    t = _normalizar_texto(texto)
    t = re.sub(r"[$,]", "", t)
    m = re.search(r"(\d[\d\s\.]*)(\s*(?:MIL|K)\b)?", t)
    if m:
        try:
            num = int(float(re.sub(r"[\s\.]", "", m.group(1))))
            if (m.group(2) or "").strip() in ("MIL", "K"):
                num *= 1000
            elif num < 1000 and any(k in t for k in ["MIL", "K", "PESOS", "MXN"]):
                num *= 1000
            if num > 0:
                return num
        except Exception:
            pass
    for palabra, valor in sorted(_NUMEROS_LETRAS_MONTO.items(), key=lambda x: -len(x[0])):
        if palabra in t and "MIL" in t:
            return valor * 1000
    return None


def _evaluar_buro(texto: str) -> str:
    t = _normalizar_texto(texto)
    if any(k in t for k in ["BUENO", "BUEN BURO", "BUEN HISTORIAL", "EXCELENTE", "MUY BIEN", "LIMPIO"]):
        return "bueno"
    if any(k in t for k in ["REGULAR", "MAS O MENOS", "MEDIO", "NO TAN BUENO"]):
        return "regular"
    if any(k in t for k in ["INICIANDO", "INICIO", "SIN HISTORIAL", "NO TENGO", "NUEVO", "NULO", "NUNCA"]):
        return "iniciando"
    return "desconocido"


def _lead_es_calificado(enganche: Optional[int], buro: str) -> bool:
    buro_normalizado = _normalizar_texto(buro or "")

    if enganche is None or enganche < ENGANCHE_MINIMO_CALIFICADO:
        return False

    if not buro_normalizado or buro_normalizado == "DESCONOCIDO":
        return False

    return not any(k in buro_normalizado for k in ["INICIANDO", "SIN HISTORIAL", "NO TENGO", "NULO"])


def _int_detectado(valor) -> Optional[int]:
    """Convierte valores detectados por IA a entero sin romper el flujo."""
    if valor in (None, ""):
        return None

    try:
        if isinstance(valor, str):
            valor = re.sub(r"[^0-9]", "", valor)

        if valor in (None, ""):
            return None

        entero = int(valor)
        return entero if entero > 0 else None
    except (TypeError, ValueError):
        return None


def _texto_detectado(valor, max_len: int = 120) -> str:
    """Limpia texto detectado para guardarlo en campos formales del expediente."""
    texto = str(valor or "").strip()

    if not texto:
        return ""

    valores_vacios = {
        "desconocido",
        "desconocida",
        "no especificado",
        "no especificada",
        "no definido",
        "no definida",
        "sin especificar",
        "sin definir",
        "null",
        "none",
        "n/a",
        "na",
    }

    if texto.lower() in valores_vacios:
        return ""

    return texto[:max_len]

def _get_or_create_conversacion_ia(
    expediente: ExpedienteDigital,
    numero_asesor: str,
) -> ConversacionIA:
    numero_asesor = normaliza_tel_mx(
        numero_asesor or ""
    )

    conversacion, _ = ConversacionIA.objects.get_or_create(
        expediente=expediente,
        numero_asesor=numero_asesor,
    )

    return conversacion

def _leer_dato_conversacion(
    expediente: ExpedienteDigital,
    numero_asesor: str,
    clave: str,
    default=None,
):
    numero_asesor = normaliza_tel_mx(numero_asesor or "")

    if not numero_asesor:
        return default

    conversacion = ConversacionIA.objects.filter(
        expediente=expediente,
        numero_asesor=numero_asesor,
    ).first()

    if not conversacion:
        return default

    datos_extra = conversacion.datos_extra if isinstance(conversacion.datos_extra, dict) else {}
    return datos_extra.get(clave, default)


def _actualizar_datos_conversacion(
    *,
    expediente: ExpedienteDigital,
    numero_asesor: str,
    datos: dict[str, Any],
    estado_conversacion: str = "",
    pregunta_pendiente: str = "",
) -> None:
    numero_asesor = normaliza_tel_mx(numero_asesor or "")

    if not numero_asesor:
        return

    conversacion = _get_or_create_conversacion_ia(expediente, numero_asesor)
    datos_extra = conversacion.datos_extra if isinstance(conversacion.datos_extra, dict) else {}

    for clave, valor in (datos or {}).items():
        if valor in (None, ""):
            continue
        datos_extra[clave] = valor

    conversacion.datos_extra = datos_extra

    campos_update = ["datos_extra"]

    if estado_conversacion:
        conversacion.estado_conversacion = estado_conversacion
        campos_update.append("estado_conversacion")

    conversacion.pregunta_pendiente = pregunta_pendiente or ""
    campos_update.append("pregunta_pendiente")

    conversacion.save(update_fields=list(dict.fromkeys(campos_update)))


def _obtener_etapa_perfilado(expediente: ExpedienteDigital, numero_asesor: str = "") -> int:
    """
    La pauta del expediente se reserva para la campaña/anuncio de Meta.
    La etapa conversacional de la IA se guarda en ConversacionIA.datos_extra.
    """
    etapa_guardada = _leer_dato_conversacion(
        expediente,
        numero_asesor,
        "etapa_perfilado",
        default="",
    )

    if isinstance(etapa_guardada, int):
        return max(0, min(4, etapa_guardada))

    etapa_guardada = str(etapa_guardada or "").strip()

    if etapa_guardada in ETAPA_PERFILADO:
        return ETAPA_PERFILADO[etapa_guardada]

    # Fallback usando campos reales del expediente, sin tocar pauta.
    if expediente.enganche_monto and expediente.buro_estado:
        return ETAPA_PERFILADO["completado"]

    if expediente.enganche_monto and not expediente.buro_estado:
        return ETAPA_PERFILADO["pedir_buro"]

    if (expediente.cliente.nombre or "").strip():
        return ETAPA_PERFILADO["pedir_enganche"]

    return ETAPA_PERFILADO["sin_iniciar"]


def _determinar_accion_ofrecida(
    *, reply_text: str, send_pdf: bool, requiere_asesor: bool,
    selected_version: Optional[str], texto_usuario: str,
) -> str:
    if requiere_asesor:
        return "confirmar_canalizacion"
    if send_pdf and selected_version:
        return "compartir_pdf"
    rn = _normalizar_texto(reply_text)
    if "TU NOMBRE" in rn or "COMO TE LLAMAS" in rn:
        return "pedir_nombre"
    if any(k in rn for k in ["PARA QUE USO", "QUE USO LE DARAS"]):
        return "pedir_necesidad"
    return "continuar_contexto" if selected_version else "ninguna"


@lru_cache(maxsize=1)
def _get_openai_client() -> OpenAI:
    api_key = getattr(settings, "OPENAI_API_KEY", "") or ""
    if not api_key:
        raise RuntimeError("Falta OPENAI_API_KEY")
    return OpenAI(api_key=api_key, timeout=25.0, max_retries=2)

@lru_cache(maxsize=1)
def _get_gemini_client():
    api_key = getattr(settings, "GEMINI_API_KEY", "") or ""

    if not api_key:
        raise RuntimeError("Falta GEMINI_API_KEY")

    return genai.Client(api_key=api_key)

PREGUNTAS_PERFIL_VALIDAS = {
    "nombre",
    "vehiculo_interes",
    "anio_auto",
    "forma_pago",
    "enganche",
    "presupuesto_mensual",
    "buro",
    "tipo_cliente",
    "personalidad_juridica",
    "comprobacion_ingresos",
    "uso_vehiculo",
    "auto_cuenta",
    "plazo_compra",
}

CAMPOS_CORREGIBLES_IA = {
    "nombre_detectado",
    "enganche_monto",
    "presupuesto_mensual",
    "presupuesto_mensual_min",
    "presupuesto_mensual_max",
    "buro_estado",
    "forma_pago",
    "tipo_cliente",
    "personalidad_juridica",
    "comprobacion_ingresos",
    "uso_vehiculo",
    "auto_cuenta",
    "plazo_compra",
    "ciudad",
    "correo",
    "horario_contacto",
    "vehiculo_interes",
    "anio_auto",
    "comentarios",
}

GEMINI_DECISION_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "reply_text": {"type": "STRING"},
        "intent": {"type": "STRING"},
        "question_key": {
            "anyOf": [
                {"type": "STRING"},
                {"type": "NULL"},
            ]
        },
        "selected_version": {
            "anyOf": [
                {"type": "STRING"},
                {"type": "NULL"},
            ]
        },
        "send_pdf": {"type": "BOOLEAN"},
        "send_images": {"type": "BOOLEAN"},
        "send_videos": {"type": "BOOLEAN"},
        "requiere_asesor": {"type": "BOOLEAN"},
        "accion_ofrecida": {"type": "STRING"},
        "nueva_etapa_perfilado": {"type": "INTEGER"},
        "detected_profile": {
            "type": "OBJECT",
            "properties": {
                "anio_auto": {
                    "anyOf": [
                        {"type": "INTEGER"},
                        {"type": "NULL"},
                    ]
                },
                "comentarios": {"type": "STRING"},
                "vehiculo_interes": {"type": "STRING"},
                "nombre_detectado": {"type": "STRING"},
                "enganche_monto": {
                    "anyOf": [
                        {"type": "INTEGER"},
                        {"type": "NULL"},
                    ]
                },
                "presupuesto_mensual": {
                    "anyOf": [
                        {"type": "INTEGER"},
                        {"type": "NULL"},
                    ]
                },
                "presupuesto_mensual_min": {
                    "anyOf": [
                        {"type": "INTEGER"},
                        {"type": "NULL"},
                    ]
                },
                "presupuesto_mensual_max": {
                    "anyOf": [
                        {"type": "INTEGER"},
                        {"type": "NULL"},
                    ]
                },
                "buro_estado": {"type": "STRING"},
                "forma_pago": {"type": "STRING"},
                "tipo_cliente": {"type": "STRING"},
                "personalidad_juridica": {"type": "STRING"},
                "comprobacion_ingresos": {"type": "STRING"},
                "uso_vehiculo": {"type": "STRING"},
                "auto_cuenta": {"type": "STRING"},
                "plazo_compra": {"type": "STRING"},
                "ciudad": {"type": "STRING"},
                "correo": {"type": "STRING"},
                "horario_contacto": {"type": "STRING"},
                "interes_principal": {"type": "STRING"},
            },
        },
        "correcciones_explicitas": {
            "type": "OBJECT",
            "properties": {
                "nombre_detectado": {"type": "BOOLEAN"},
                "enganche_monto": {"type": "BOOLEAN"},
                "presupuesto_mensual": {"type": "BOOLEAN"},
                "presupuesto_mensual_min": {"type": "BOOLEAN"},
                "presupuesto_mensual_max": {"type": "BOOLEAN"},
                "buro_estado": {"type": "BOOLEAN"},
                "forma_pago": {"type": "BOOLEAN"},
                "tipo_cliente": {"type": "BOOLEAN"},
                "personalidad_juridica": {"type": "BOOLEAN"},
                "comprobacion_ingresos": {"type": "BOOLEAN"},
                "uso_vehiculo": {"type": "BOOLEAN"},
                "auto_cuenta": {"type": "BOOLEAN"},
                "plazo_compra": {"type": "BOOLEAN"},
                "ciudad": {"type": "BOOLEAN"},
                "correo": {"type": "BOOLEAN"},
                "horario_contacto": {"type": "BOOLEAN"},
                "vehiculo_interes": {"type": "BOOLEAN"},
                "anio_auto": {"type": "BOOLEAN"},
                "comentarios": {"type": "BOOLEAN"},
            },
        },
        "reasoning_tags": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
    },
    "required": [
        "reply_text",
        "intent",
        "question_key",
        "selected_version",
        "send_pdf",
        "send_images",
        "send_videos",
        "requiere_asesor",
        "accion_ofrecida",
        "nueva_etapa_perfilado",
        "detected_profile",
        "correcciones_explicitas",
        "reasoning_tags",
    ],
}

PROMPT_OPERATIVO_IA = """
REGLAS OPERATIVAS PRIORITARIAS DEL CRM

La identidad comercial se obtiene exclusivamente de la sección
CONFIGURACIÓN ESPECÍFICA DE LA LÍNEA.

Nunca utilices nombres, agencias, ciudades, direcciones o identidades que no
aparezcan en esa configuración.

No existe identidad de respaldo. Si falta información de identidad, no la
inventes.

CONTINUIDAD DE CONVERSACIÓN

NOMBRE DEL PROSPECTO

- `prospecto.nombre_confirmado` es el único nombre que debe considerarse confirmado.
- `prospecto.nombre_perfil_whatsapp_candidato` es únicamente el nombre visible en WhatsApp y puede ser un apodo, alias o nombre incompleto.
- Si `nombre_confirmado` está vacío y existe `nombre_perfil_whatsapp_candidato`, pregunta de forma natural si desea ser registrado con ese nombre.
- Cuando preguntes si desea ser registrado con el nombre candidato, usa `question_key="nombre"`.
- Ejemplo: "Veo que apareces como Manolo, ¿te registro así?"
- Si el cliente confirma con respuestas como "sí", "sí está bien", "así está bien" o equivalentes, registra ese candidato en `detected_profile.nombre_detectado`.
- Si el cliente corrige el nombre, por ejemplo "No, me llamo José Manuel", registra el nombre corregido en `detected_profile.nombre_detectado`.
- Cuando se detecte o confirme un nombre, marca `correcciones_explicitas.nombre_detectado=true` únicamente si el cliente está corrigiendo un nombre previamente guardado.
- No vuelvas a preguntar el nombre si `nombre_confirmado` ya contiene un valor.
- No asumas que el nombre visible de WhatsApp es correcto sin confirmación del cliente.

- La conversación es continua, aunque hayan pasado horas o días.
- Revisa el expediente, el resumen y el historial antes de responder.
- No reinicies el perfilamiento.
- No vuelvas a presentarte cuando ya existan mensajes anteriores.
- Solo preséntate cuando `es_primer_contacto_real` sea true.
- No preguntes datos que aparezcan en `perfil_confirmado`.
- No preguntes claves incluidas en `preguntas_bloqueadas`.
- Si el cliente ya respondió algo, reconoce brevemente la respuesta y avanza.
- Nunca repitas ni reformules innecesariamente la última respuesta saliente.

ATENCIÓN

- Primero responde la duda actual del cliente.
- Después puedes realizar como máximo UNA pregunta comercial.
- `question_key` debe identificar esa pregunta.
- Si no haces una pregunta, `question_key` debe ser null.
- No conviertas cada respuesta en un cuestionario.
- No sigas un orden rígido de perfilamiento.
- Selecciona la siguiente pregunta según la información que realmente falte.
- Si una pregunta se realizó dos veces, cambia de enfoque o canaliza.
- Si el cliente está molesto, confundido o solicita una persona, canaliza.

EXTRACCIÓN

Registra únicamente datos expresados explícitamente por el cliente o claramente
confirmados por el historial.

Cuando el cliente corrija un dato anterior:
- Coloca el nuevo valor en `detected_profile`.
- Marca ese campo como true dentro de `correcciones_explicitas`.

No marques una inferencia débil como dato confirmado.

FINANCIAMIENTO

- No inventes mensualidades, promociones, descuentos, disponibilidad ni aprobación.
- No calcules una corrida financiera final.
- Puedes orientar usando únicamente el catálogo recibido.
- Cuando solicite mensualidad exacta, corrida, cotización formal, apartado,
  disponibilidad o aprobación, usa `requiere_asesor=true`.
- Una mensualidad objetivo proporcionada por el cliente debe guardarse como perfil,
  no debe responderse preguntando nuevamente cuál mensualidad busca.

CANALIZACIÓN A ASESOR

- El horario de atención de asesores humanos es de 09:00 a 18:00.
- La IA puede continuar atendiendo fuera de ese horario; este horario aplica únicamente al contacto del asesor humano.
- Cuando uses `requiere_asesor=true`, informa al cliente que un asesor dará seguimiento dentro del horario de atención de 09:00 a 18:00.
- No prometas que el asesor responderá inmediatamente, en ciertos minutos ni a una hora exacta.
- Si el contacto ocurre fuera del horario de 09:00 a 18:00, indica que el asesor dará seguimiento a partir del siguiente horario de atención.
- Si el contacto ocurre dentro del horario de 09:00 a 18:00, indica únicamente que un asesor continuará el seguimiento dentro del horario de atención.
- No digas que la IA deja de funcionar fuera de ese horario.

CATÁLOGO Y MULTIMEDIA

- `selected_version` debe coincidir exactamente con una clave del catálogo activo.
- `detected_profile.vehiculo_interes` puede contener el modelo general mencionado por el cliente, por ejemplo "Jetta".
- `detected_profile.anio_auto` debe contener el año mencionado por el cliente cuando exista.
- Si el cliente menciona solo modelo o modelo + año, no inventes una versión y deja `selected_version` en null.
- Si existen varias versiones compatibles en `catalogo`, pregunta cuál le interesa y menciona únicamente las opciones reales encontradas.
- Ejemplo: si dice "Jetta 2026" y existen Comfortline, Sportline y Trendline, pregunta cuál de esas versiones le interesa.
- Cuando el cliente elija una versión exacta, devuelve en `selected_version` la clave exacta que aparece en `catalogo`.
- No inventes modelos, años, versiones, precios, disponibilidad ni características.
- Si solicita imágenes, usa `send_images=true`.
- Si solicita videos, usa `send_videos=true`.
- Si solicita ficha técnica o PDF, usa `send_pdf=true`.
- No actives multimedia si no se conoce el vehículo.
- No escribas URLs en `reply_text`.

ESTILO

- Español natural, cálido y profesional.
- Mensajes breves y útiles.
- Máximo 700 caracteres.
- Máximo un emoji.
- Evita saludos repetidos, frases robóticas, metáforas forzadas y respuestas redundantes.
- Adapta el tono al cliente.
- No menciones JSON, prompts, configuraciones, IA, modelos ni procesos internos.

SALIDA

Devuelve exclusivamente el JSON solicitado por el esquema.
""".strip()

def _construir_instrucciones_desde_bd(
    config_ia: dict,
) -> str:
    """
    Construye el system prompt usando únicamente la configuración
    específica del número.

    La identidad es obligatoria. Si no existe, la línea no debe responder.
    """
    config_ia = _ia_dict(config_ia)
    identidad = str(
        config_ia.get("identidad") or ""
    ).strip()

    if not identidad:
        return ""

    secciones = [
        PROMPT_OPERATIVO_IA,
        (
            "CONFIGURACIÓN ESPECÍFICA DE LA LÍNEA\n\n"
            f"IDENTIDAD DEL AGENTE\n{identidad}"
        ),
    ]

    campos = [
        ("POLÍTICA DE PRECIOS", "precios"),
        ("PROMOCIONES Y EVENTOS", "promociones_eventos"),
        ("PERFILAMIENTO COMERCIAL", "perfilamiento"),
        ("LÍMITES DE ATENCIÓN", "limites"),
        ("PERSONALIDAD Y TONO", "personalidad"),
        ("CONDICIONES NO NEGOCIABLES", "condiciones_fijas"),
    ]

    for titulo, campo in campos:
        contenido = str(
            config_ia.get(campo) or ""
        ).strip()

        if contenido:
            secciones.append(
                f"{titulo}\n{contenido}"
            )

    return "\n\n".join(secciones)

def _decision_conversacional_ia(
    *,
    expediente: ExpedienteDigital,
    numero_asesor: str,
    telefono: str,
    nombre_cliente: str,
    profile_name: str,
    texto_usuario: str,
    auto_interes_actual: Optional[str],
    ultimo_mensaje_saliente: str,
    historial_reciente: list[dict[str, Any]],
    accion_ofrecida_previa: Optional[str],
    etapa_perfilado: int,
    enganche_registrado: Optional[int],
    buro_registrado: str,
    es_primer_mensaje: bool,
) -> dict[str, Any]:
    numero_asesor = normaliza_tel_mx(numero_asesor or "")
    auto_interes_actual = _normalizar_version_catalogo(
        auto_interes_actual
    )

    config_ia = _obtener_config_ia(numero_asesor)
    instrucciones = _construir_instrucciones_desde_bd(
        config_ia
    )

    if not instrucciones:
        logger.error(
            "IA SIN CONFIGURACION UTILIZABLE | linea=%s expediente=%s",
            numero_asesor,
            expediente.pk,
        )
        return {}

    conversacion = _get_or_create_conversacion_ia(
        expediente,
        numero_asesor,
    )

    perfil_confirmado = _perfil_confirmado_para_ia(
        expediente=expediente,
        conversacion=conversacion,
        nombre_cliente=nombre_cliente,
    )

    nombre_perfil_whatsapp = ""
    if (
        profile_name
        and not _es_email(profile_name)
        and _parece_nombre_solo(profile_name)
    ):
        nombre_perfil_whatsapp = _limpiar_nombre_candidato(
            profile_name
        )

    nombre_explicito_usuario = _extraer_nombre_basico(
        "",
        texto_usuario,
    )

    if (
        not (nombre_cliente or "").strip()
        and nombre_perfil_whatsapp
        and not nombre_explicito_usuario
        and conversacion.pregunta_pendiente != "nombre"
    ):
        return {
            "reply_text": (
                f"Veo que apareces como {nombre_perfil_whatsapp}. "
                "¿Te registro con ese nombre?"
            ),
            "intent": "confirmar_nombre",
            "question_key": "nombre",
            "selected_version": None,
            "send_pdf": False,
            "send_images": False,
            "send_videos": False,
            "requiere_asesor": False,
            "accion_ofrecida": "ninguna",
            "nueva_etapa_perfilado": etapa_perfilado,
            "detected_profile": {},
            "correcciones_explicitas": {},
            "reasoning_tags": [
                "confirmacion_nombre_whatsapp",
            ],
        }

    if (
        not (nombre_cliente or "").strip()
        and not nombre_perfil_whatsapp
        and not nombre_explicito_usuario
        and conversacion.pregunta_pendiente != "nombre"
    ):
        return {
            "reply_text": (
                "Antes de continuar, ¿me compartes tu nombre?"
            ),
            "intent": "pedir_nombre",
            "question_key": "nombre",
            "selected_version": None,
            "send_pdf": False,
            "send_images": False,
            "send_videos": False,
            "requiere_asesor": False,
            "accion_ofrecida": "ninguna",
            "nueva_etapa_perfilado": etapa_perfilado,
            "detected_profile": {},
            "correcciones_explicitas": {},
            "reasoning_tags": [
                "solicitud_nombre_sin_candidato",
            ],
        }
    preguntas_bloqueadas = _preguntas_bloqueadas_para_ia(
        perfil=perfil_confirmado,
        conversacion=conversacion,
    )

    datos_extra = _ia_dict(
        conversacion.datos_extra
    )

    preguntas_realizadas = _ia_dict(
        datos_extra.get("preguntas_realizadas")
    )

    respuestas_ia_recientes = datos_extra.get(
        "ultimas_respuestas_ia"
    )

    if not isinstance(respuestas_ia_recientes, list):
        respuestas_ia_recientes = []

    hay_respuesta_previa = any(
        item.get("role") == "assistant"
        for item in historial_reciente
    )

    es_primer_contacto_real = bool(
        es_primer_mensaje
        and not hay_respuesta_previa
        and not conversacion.ultima_intencion
        and not conversacion.resumen_conversacion
        and not expediente.resumen
    )

    ahora_local = datetime.now(
        ZoneInfo("America/Mexico_City")
    )

    en_horario_asesor = (
        9 <= ahora_local.hour < 18
    )

    contexto = {
        "numero_linea": numero_asesor,
        "mensaje_actual": texto_usuario,
        "prospecto": {
        "nombre_confirmado": nombre_cliente or None,
        "nombre_perfil_whatsapp_candidato": (
            nombre_perfil_whatsapp or None
        ),
        "telefono": telefono,
    },
        "es_primer_contacto_real": es_primer_contacto_real,
        "perfil_confirmado": perfil_confirmado,
        "estado_conversacion": {
            "estado": conversacion.estado_conversacion,
            "ultima_intencion": conversacion.ultima_intencion,
            "ultimo_modelo_mencionado": (
                conversacion.ultimo_modelo_mencionado
                or auto_interes_actual
            ),
            "pregunta_pendiente": (
                conversacion.pregunta_pendiente or None
            ),
            "pregunta_pendiente_intentos": (
                conversacion.pregunta_pendiente_intentos
            ),
            "preguntas_realizadas": preguntas_realizadas,
            "preguntas_bloqueadas": preguntas_bloqueadas,
            "accion_ofrecida_previa": accion_ofrecida_previa,
            "ultima_respuesta_saliente": (
                ultimo_mensaje_saliente or None
            ),
            "ultimas_respuestas_ia": respuestas_ia_recientes[-3:],
        },
        "resumen_historico": (
            conversacion.resumen_conversacion
            or expediente.resumen
            or ""
        ),
        "historial_reciente": historial_reciente,
        "perfilado_legacy": {
            "etapa_actual": etapa_perfilado,
            "enganche_registrado": (
                expediente.enganche_monto
                or enganche_registrado
            ),
            "buro_registrado": (
                expediente.buro_estado
                or buro_registrado
                or None
            ),
        },
        "catalogo": _catalogo_para_prompt(),
        "horario_asesor_humano": {
            "inicio": "09:00",
            "fin": "18:00",
            "hora_local_actual": ahora_local.strftime(
                "%Y-%m-%d %H:%M"
            ),
            "en_horario": en_horario_asesor,
        },
        "pauta_origen_interna": expediente.pauta or None,
        "reglas_de_contexto": {
            "la_pauta_es_interna": True,
            "no_repetir_preguntas_bloqueadas": True,
            "maximo_una_pregunta_por_turno": True,
            "no_reiniciar_conversacion": True,
        },
    }

    client = _get_gemini_client()
    modelo = getattr(
        settings,
        "GEMINI_MODEL",
        "gemini-2.5-flash",
    )

    try:
        salida = _llamar_gemini_decision(
            client=client,
            modelo=modelo,
            instrucciones=instrucciones,
            contexto=contexto,
        )

        decision = _sanitizar_decision_ia(
            salida,
            etapa_perfilado=etapa_perfilado,
        )

        if not decision.get("question_key"):
            respuesta_lower = str(
                decision.get("reply_text") or ""
            ).lower()

            if (
                "historial crediticio" in respuesta_lower
                or "buró" in respuesta_lower
                or "buro" in respuesta_lower
            ):
                decision["question_key"] = "buro"

        perfil_actual = _perfil_confirmado_para_ia(
            expediente=expediente,
            conversacion=conversacion,
            nombre_cliente=nombre_cliente,
        )

        perfil_detectado_turno = _ia_dict(
            decision.get("detected_profile")
        )

        campos_faltantes_prioritarios = [
            campo
            for campo in (
                "tipo_cliente",
                "uso_vehiculo",
                "plazo_compra",
            )
            if not (
                perfil_actual.get(campo)
                or _texto_detectado(
                    perfil_detectado_turno.get(campo)
                )
            )
        ]
        texto_usuario_lower = str(
            texto_usuario or ""
        ).lower()

        cliente_pidio_asesor = any(
            frase in texto_usuario_lower
            for frase in (
                "quiero hablar con un asesor",
                "quiero un asesor",
                "asesor humano",
                "que me contacte un asesor",
                "que me llame un asesor",
                "hablar con una persona",
                "hablar con alguien",
            )
        )

        if (
            decision.get("requiere_asesor")
            and campos_faltantes_prioritarios
            and not cliente_pidio_asesor
        ):
            decision["requiere_asesor"] = False
            decision["accion_ofrecida"] = "ninguna"
            decision["intent"] = "continuar_perfilamiento"

            siguiente_campo = campos_faltantes_prioritarios[0]
            decision["question_key"] = siguiente_campo

            preguntas_faltantes = {
                "tipo_cliente": (
                    "Para seguir completando tu perfil, ¿la compra sería "
                    "como particular o como empresa?"
                ),
                "uso_vehiculo": (
                    "Para seguir completando tu perfil, ¿qué uso le darías "
                    "principalmente al vehículo: personal, familiar o trabajo?"
                ),
                "plazo_compra": (
                    "Para seguir completando tu perfil, ¿en cuánto tiempo "
                    "tienes pensado realizar la compra?"
                ),
            }

            decision["reply_text"] = preguntas_faltantes[
                siguiente_campo
            ]

        respuesta = decision.get("reply_text") or ""

        if respuesta and _respuesta_ia_es_repetida(
            nueva_respuesta=respuesta,
            historial=historial_reciente,
        ):
            contexto_reintento = {
                **contexto,
                "control_calidad": {
                    "motivo": "respuesta_demasiado_parecida",
                    "respuesta_rechazada": respuesta,
                    "instruccion": (
                        "Genera una respuesta distinta. Responde directamente "
                        "el mensaje actual, utiliza los datos confirmados y no "
                        "repitas la misma pregunta."
                    ),
                },
            }

            segunda_salida = _llamar_gemini_decision(
                client=client,
                modelo=modelo,
                instrucciones=instrucciones,
                contexto=contexto_reintento,
            )

            segunda_decision = _sanitizar_decision_ia(
                segunda_salida,
                etapa_perfilado=etapa_perfilado,
            )

            segunda_respuesta = (
                segunda_decision.get("reply_text") or ""
            )

            if segunda_respuesta and not _respuesta_ia_es_repetida(
                nueva_respuesta=segunda_respuesta,
                historial=historial_reciente,
            ):
                decision = segunda_decision
            else:
                logger.warning(
                    "IA OMITIDA POR REDUNDANCIA | linea=%s expediente=%s",
                    numero_asesor,
                    expediente.pk,
                )

                return {
                    "skip_send": True,
                    "skip_reason": "respuesta_repetida",
                }

        if not str(
            decision.get("reply_text") or ""
        ).strip():
            return {
                "skip_send": True,
                "skip_reason": "respuesta_vacia",
            }

        return decision

    except Exception:
        logger.exception(
            "ERROR GENERANDO DECISION IA | linea=%s expediente=%s modelo=%s",
            numero_asesor,
            expediente.pk,
            modelo,
        )

        return {
            "skip_send": True,
            "skip_reason": "error_proveedor_ia",
        }

# Historial y persistencia
def _obtener_ultimo_mensaje_saliente(cliente: ClienteComercial, numero_asesor: str) -> str:
    mensajes = (
        MensajeWhatsApp.objects
        .filter(cliente=cliente, numero_asesor=numero_asesor, direction="out")
        .order_by("-id").only("body", "raw")
    )[:25]
    for m in mensajes:
        body = (m.body or "").strip()
        if _mensaje_de_historial_vigente(body=body, raw=m.raw):
            return body
    return ""


def _obtener_ultima_accion_ofrecida(cliente: ClienteComercial, numero_asesor: str) -> Optional[str]:
    mensajes = (
        MensajeWhatsApp.objects
        .filter(cliente=cliente, numero_asesor=numero_asesor, direction="out")
        .order_by("-id").only("body", "raw")
    )[:25]
    for m in mensajes:
        raw = m.raw or {}
        body = (m.body or "").strip()
        if not _mensaje_de_historial_vigente(body=body, raw=raw):
            continue
        accion = (
            raw.get("conversation_meta", {}).get("accion_ofrecida")
            or raw.get("accion_ofrecida") or ""
        ).strip()
        if accion in ACCIONES_OFRECIDAS_VALIDAS:
            return accion
    return None


def _contar_mensajes_entrantes(cliente: ClienteComercial, numero_asesor: str) -> int:
    return MensajeWhatsApp.objects.filter(
        cliente=cliente, numero_asesor=numero_asesor, direction="in"
    ).count()


def _serializar_historial(
    cliente: ClienteComercial,
    numero_asesor: str,
    limite: int = 20,
) -> list[dict[str, Any]]:
    """
    Recupera mensajes recientes de la conversación exacta:
    cliente + línea de WhatsApp.

    Distingue entre:
    - cliente
    - respuesta de IA
    - respuesta de asesor humano
    """
    numero_asesor = normaliza_tel_mx(numero_asesor or "")

    mensajes = list(
        MensajeWhatsApp.objects
        .filter(
            cliente=cliente,
            numero_asesor=numero_asesor,
        )
        .order_by("-created_at", "-id")
        .only(
            "direction",
            "body",
            "raw",
            "created_at",
        )[: max(limite * 3, 30)]
    )

    mensajes.reverse()
    historial: list[dict[str, Any]] = []

    for mensaje in mensajes:
        body = str(mensaje.body or "").strip()
        raw = mensaje.raw if isinstance(mensaje.raw, dict) else {}

        if not body:
            continue

        if raw.get("is_reaction_event"):
            continue

        if not _mensaje_de_historial_vigente(
            body=body,
            raw=raw,
        ):
            continue

        if mensaje.direction == MensajeWhatsApp.Direccion.IN:
            origen = "cliente"
            role = "user"
        else:
            origen = "ia" if raw.get("ia_provider") else "asesor"
            role = "assistant"

        historial.append({
            "role": role,
            "content": body,
            "origen": origen,
            "fecha": (
                mensaje.created_at.isoformat()
                if mensaje.created_at
                else ""
            ),
        })

    return historial[-limite:]

def _ia_dict(valor: Any) -> dict:
    return valor if isinstance(valor, dict) else {}


def _perfil_confirmado_para_ia(
    *,
    expediente: ExpedienteDigital,
    conversacion: ConversacionIA,
    nombre_cliente: str = "",
) -> dict[str, Any]:
    datos_extra = _ia_dict(conversacion.datos_extra)
    perfil_extra = _ia_dict(datos_extra.get("perfil_extra"))

    return {
        "nombre_completo": str(nombre_cliente or "").strip() or None,
        "vehiculo_interes": (
            expediente.auto_interes
            or perfil_extra.get("vehiculo_interes")
            or None
        ),
        "anio_auto": expediente.anio_auto,
        "enganche_monto": expediente.enganche_monto,
        "presupuesto_mensual": expediente.presupuesto_mensual,
        "presupuesto_mensual_min": perfil_extra.get(
            "presupuesto_mensual_min"
        ),
        "presupuesto_mensual_max": perfil_extra.get(
            "presupuesto_mensual_max"
        ),
        "buro_estado": expediente.buro_estado or None,
        "forma_pago": expediente.forma_pago or None,
       "tipo_cliente": (
            _texto_detectado(expediente.tipo_cliente) or None
        ),
        "personalidad_juridica": (
            _texto_detectado(
                perfil_extra.get("personalidad_juridica")
            )
            or None
        ),
        "comprobacion_ingresos": (
            _texto_detectado(
                expediente.comprobacion_ingresos
            )
            or None
        ),
        "uso_vehiculo": (
            _texto_detectado(expediente.uso_vehiculo)
            or None
        ),
        "auto_cuenta": (
            _texto_detectado(
                perfil_extra.get("auto_cuenta")
            )
            or None
        ),
        "plazo_compra": (
            _texto_detectado(expediente.plazo_compra)
            or None
        ),
        "ciudad": perfil_extra.get("ciudad"),
        "correo": (
            expediente.cliente.correo or None
        ),
        "horario_contacto": perfil_extra.get("horario_contacto"),
        "comentarios": expediente.comentarios or None,
    }


def _preguntas_bloqueadas_para_ia(
    *,
    perfil: dict[str, Any],
    conversacion: ConversacionIA,
) -> list[str]:
    datos_extra = _ia_dict(conversacion.datos_extra)
    preguntas_realizadas = _ia_dict(
        datos_extra.get("preguntas_realizadas")
    )

    bloqueadas = {
        clave
        for clave, intentos in preguntas_realizadas.items()
        if int(intentos or 0) >= 2
    }

    campos_conocidos = {
        "nombre": perfil.get("nombre_completo"),
        "vehiculo_interes": perfil.get("vehiculo_interes"),
        "forma_pago": perfil.get("forma_pago"),
        "enganche": perfil.get("enganche_monto"),
        "presupuesto_mensual": (
            perfil.get("presupuesto_mensual")
            or perfil.get("presupuesto_mensual_min")
            or perfil.get("presupuesto_mensual_max")
        ),
        "buro": perfil.get("buro_estado"),
        "tipo_cliente": perfil.get("tipo_cliente"),
        "personalidad_juridica": perfil.get(
            "personalidad_juridica"
        ),
        "comprobacion_ingresos": perfil.get(
            "comprobacion_ingresos"
        ),
        "uso_vehiculo": perfil.get("uso_vehiculo"),
        "auto_cuenta": perfil.get("auto_cuenta"),
        "plazo_compra": perfil.get("plazo_compra"),
    }

    for clave, valor in campos_conocidos.items():
        if valor not in (None, "", [], {}):
            bloqueadas.add(clave)

    return sorted(bloqueadas)


def _normalizar_para_similitud(texto: str) -> str:
    texto = _strip_accents(str(texto or "")).lower()
    texto = re.sub(r"[^a-z0-9 ]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _respuesta_ia_es_repetida(
    *,
    nueva_respuesta: str,
    historial: list[dict[str, Any]],
    umbral: float = 0.86,
) -> bool:
    nueva = _normalizar_para_similitud(nueva_respuesta)

    if not nueva:
        return False

    respuestas_anteriores = [
        _normalizar_para_similitud(item.get("content", ""))
        for item in historial
        if item.get("role") == "assistant"
    ][-4:]

    for anterior in respuestas_anteriores:
        if not anterior:
            continue

        if nueva == anterior:
            return True

        # Evita falsos positivos con respuestas cortas como "Perfecto".
        if min(len(nueva), len(anterior)) < 60:
            continue

        similitud = SequenceMatcher(
            None,
            nueva,
            anterior,
        ).ratio()

        if similitud >= umbral:
            return True

    return False


def _llamar_gemini_decision(
    *,
    client,
    modelo: str,
    instrucciones: str,
    contexto: dict[str, Any],
) -> dict[str, Any]:
    respuesta = client.models.generate_content(
        model=modelo,
        contents=json.dumps(
            contexto,
            ensure_ascii=False,
            default=str,
        ),
        config=types.GenerateContentConfig(
            system_instruction=instrucciones,
            response_mime_type="application/json",
            response_schema=GEMINI_DECISION_SCHEMA,

            # El perfilamiento comercial no necesita razonamiento
            # profundo. Evita consumir tokens de pensamiento.
            thinking_config=types.ThinkingConfig(
                thinking_budget=0,
            ),

            # El JSON contiene varios campos, pero reply_text está
            # limitado a 700 caracteres.
            max_output_tokens=1200,
            temperature=0.45,
        ),
    )

    usage = getattr(
        respuesta,
        "usage_metadata",
        None,
    )

    if usage:
        logger.info(
            (
                "GEMINI USAGE | modelo=%s "
                "entrada=%s salida=%s pensamiento=%s total=%s"
            ),
            modelo,
            getattr(usage, "prompt_token_count", None),
            getattr(usage, "candidates_token_count", None),
            getattr(usage, "thoughts_token_count", None),
            getattr(usage, "total_token_count", None),
        )

    return _json_seguro(
        getattr(respuesta, "text", "") or ""
    )

def _sanitizar_decision_ia(
    salida: dict[str, Any],
    *,
    etapa_perfilado: int,
) -> dict[str, Any]:
    salida = salida if isinstance(salida, dict) else {}

    salida.setdefault("reply_text", "")
    salida.setdefault("intent", "")
    salida.setdefault("question_key", None)
    salida.setdefault("selected_version", None)
    salida.setdefault("send_pdf", False)
    salida.setdefault("send_images", False)
    salida.setdefault("send_videos", False)
    salida.setdefault("requiere_asesor", False)
    salida.setdefault("accion_ofrecida", "ninguna")
    salida.setdefault("nueva_etapa_perfilado", etapa_perfilado)
    salida.setdefault("detected_profile", {})
    salida.setdefault("correcciones_explicitas", {})
    salida.setdefault("reasoning_tags", [])

    salida["reply_text"] = _limitar_texto(
        str(salida.get("reply_text") or ""),
        max_len=700,
    )

    salida["intent"] = str(
        salida.get("intent") or ""
    ).strip()[:80]

    question_key = salida.get("question_key")

    if question_key is not None:
        question_key = str(question_key).strip()

    salida["question_key"] = (
        question_key
        if question_key in PREGUNTAS_PERFIL_VALIDAS
        else None
    )

    version = _normalizar_version_catalogo(
        salida.get("selected_version")
    )

    salida["selected_version"] = version
    salida["send_pdf"] = bool(
        salida.get("send_pdf")
    ) and bool(version)
    salida["send_images"] = bool(
        salida.get("send_images")
    ) and bool(version)
    salida["send_videos"] = bool(
        salida.get("send_videos")
    ) and bool(version)
    salida["requiere_asesor"] = bool(
        salida.get("requiere_asesor")
    )

    accion = str(
        salida.get("accion_ofrecida") or "ninguna"
    ).strip()

    salida["accion_ofrecida"] = (
        accion
        if accion in ACCIONES_OFRECIDAS_VALIDAS
        else "ninguna"
    )

    if salida["accion_ofrecida"] in {
        "lead_calificado",
        "confirmar_canalizacion",
    }:
        salida["requiere_asesor"] = True

    try:
        nueva_etapa = int(
            salida.get(
                "nueva_etapa_perfilado",
                etapa_perfilado,
            )
        )
    except (TypeError, ValueError):
        nueva_etapa = etapa_perfilado

    salida["nueva_etapa_perfilado"] = max(
        etapa_perfilado,
        min(4, nueva_etapa),
    )

    detected_profile = _ia_dict(
        salida.get("detected_profile")
    )

    campos_numericos = (
        "enganche_monto",
        "presupuesto_mensual",
        "presupuesto_mensual_min",
        "presupuesto_mensual_max",
    )

    for campo in campos_numericos:
        detected_profile[campo] = _int_detectado(
            detected_profile.get(campo)
        )

    salida["detected_profile"] = detected_profile

    correcciones = _ia_dict(
        salida.get("correcciones_explicitas")
    )

    salida["correcciones_explicitas"] = {
        campo: bool(valor)
        for campo, valor in correcciones.items()
        if campo in CAMPOS_CORREGIBLES_IA
    }

    reasoning_tags = salida.get("reasoning_tags")

    salida["reasoning_tags"] = (
        [
            str(item).strip()[:80]
            for item in reasoning_tags
            if str(item or "").strip()
        ][:10]
        if isinstance(reasoning_tags, list)
        else []
    )

    return salida

def _guardar_salida(
    *, telefono: str, numero_asesor: str, cliente: ClienteComercial,
    texto: str, wa_message_id: str = "", raw: Optional[dict] = None,
    status_msg: str = "accepted",
) -> MensajeWhatsApp:
    return MensajeWhatsApp.objects.create(
        telefono=telefono, numero_asesor=numero_asesor, cliente=cliente,
        direction="out", body=texto, wa_message_id=wa_message_id or "",
        status=status_msg, raw=raw or {},
    )


# Cliente / expediente

@transaction.atomic
def _get_or_create_cliente_y_expediente(
    *, telefono: str, numero_asesor: str,
    profile_name: str = "", texto_entrante: str = "",
) -> tuple[ClienteComercial, ExpedienteDigital]:
    telefono = normaliza_tel_mx(telefono)
    numero_asesor = normaliza_tel_mx(numero_asesor)
    if not telefono:
        raise ValueError("Telefono invalido")

    nombre_detectado = _extraer_nombre_basico(profile_name, texto_entrante)
    cliente, _ = ClienteComercial.objects.get_or_create(
        telefono=telefono, defaults={"nombre": nombre_detectado},
    )
    if nombre_detectado and not (cliente.nombre or "").strip():
        cliente.nombre = nombre_detectado
        cliente.save(update_fields=["nombre", "actualizado_en"])

    cfg_linea = WHATSAPP_LINES.get(numero_asesor, {})
    agencia_linea = (cfg_linea.get("agencia") or "").strip()
    business_linea = (cfg_linea.get("business") or "Comerciales").strip()
    asesor_digital_linea = (cfg_linea.get("asesor_digital") or "").strip()

    expediente, _ = ExpedienteDigital.objects.get_or_create(
        cliente=cliente,
        defaults={
            "agencia": agencia_linea, 
            "business": business_linea,
            "asesor_digital": asesor_digital_linea,
            "estado": "Contactado"},
    )

    cambios = []
    for campo, valor in [
        ("agencia", agencia_linea), ("business", business_linea),
        ("asesor_digital", asesor_digital_linea),
    ]:
        if valor and getattr(expediente, campo) != valor:
            setattr(expediente, campo, valor); cambios.append(campo)
    if not (expediente.estado or "").strip():
        expediente.estado = "Contactado"; cambios.append("estado")

    version_detectada = _buscar_version_en_texto(texto_entrante)
    if version_detectada and expediente.auto_interes != version_detectada:
        expediente.auto_interes = version_detectada; cambios.append("auto_interes")
    if expediente.auto_interes and expediente.auto_interes not in _obtener_catalogo_dict():
        expediente.auto_interes = ""
        cambios.append("auto_interes")

    now = timezone.now()
    if not expediente.primer_mensaje_cliente:
        expediente.primer_mensaje_cliente = now
        cambios.append("primer_mensaje_cliente")

    if cambios:
        cambios.append("actualizado")
        expediente.save(update_fields=list(dict.fromkeys(cambios)))

    return cliente, expediente


def _estado_conversacion_desde_etapa(etapa: int) -> tuple[str, str]:
    if etapa <= ETAPA_PERFILADO["sin_iniciar"]:
        return "sin_iniciar", ""

    if etapa == ETAPA_PERFILADO["pedir_nombre"]:
        return "perfilando", "nombre"

    if etapa == ETAPA_PERFILADO["pedir_enganche"]:
        return "perfilando", "enganche"

    if etapa == ETAPA_PERFILADO["pedir_buro"]:
        return "perfilando", "buro"

    return "informando", ""


@transaction.atomic
def _guardar_datos_detectados_en_cliente_y_expediente(
    *,
    cliente: ClienteComercial,
    expediente: ExpedienteDigital,
    profile_name: str,
    texto_usuario: str,
    detected_profile: dict[str, Any],
    version_detectada: Optional[str],
    nueva_etapa_perfilado: int,
    numero_asesor: str = "",
    correcciones_explicitas: Optional[dict[str, Any]] = None,
    question_key: Optional[str] = None,
    intent: str = "",
    reply_text: str = "",
    requiere_asesor: bool = False,
    accion_ofrecida: str = "",
) -> None:
    detected_profile = _ia_dict(detected_profile)
    correcciones = {
        campo: bool(valor)
        for campo, valor in _ia_dict(
            correcciones_explicitas
        ).items()
        if campo in CAMPOS_CORREGIBLES_IA
    }

    numero_asesor = normaliza_tel_mx(numero_asesor or "")
    cambios_cliente: list[str] = []
    cambios_expediente: list[str] = []

    conversacion = _get_or_create_conversacion_ia(
        expediente,
        numero_asesor,
    )

    datos_extra = _ia_dict(conversacion.datos_extra).copy()
    perfil_extra = _ia_dict(
        datos_extra.get("perfil_extra")
    ).copy()

    def esta_vacio(valor: Any) -> bool:
        if valor in (None, "", [], {}):
            return True

        if isinstance(valor, str):
            return valor.strip().lower() in {
                "desconocido",
                "desconocida",
                "no especificado",
                "no especificada",
                "no definido",
                "no definida",
                "sin especificar",
                "sin definir",
                "null",
                "none",
                "n/a",
                "na",
            }

        return False
    def permite_actualizar(
        campo_ia: str,
        valor_actual: Any,
    ) -> bool:
        return (
            esta_vacio(valor_actual)
            or correcciones.get(campo_ia, False)
        )

    # ---------------------------------------------------------
    # Nombre
    # ---------------------------------------------------------
    nombre_detectado = _texto_detectado(
        detected_profile.get("nombre_detectado"),
        160,
    )

    nombre_explicito_usuario = _extraer_nombre_basico(
        "",
        texto_usuario,
    )

    esperando_confirmacion_nombre = (
        (conversacion.pregunta_pendiente or "").strip()
        == "nombre"
    )

    correccion_nombre_explicita = correcciones.get(
        "nombre_detectado",
        False,
    )

    nombre_escrito_explicitamente = bool(
        nombre_explicito_usuario
    )

    puede_guardar_nombre_ia = (
        esperando_confirmacion_nombre
        or correccion_nombre_explicita
        or nombre_escrito_explicitamente
    )

    if nombre_escrito_explicitamente:
        nombre_detectado = nombre_explicito_usuario

    if (
        nombre_detectado
        and puede_guardar_nombre_ia
        and permite_actualizar(
            "nombre_detectado",
            cliente.nombre,
        )
        and cliente.nombre != nombre_detectado
    ):
        cliente.nombre = nombre_detectado
        cambios_cliente.extend([
            "nombre",
            "actualizado_en",
        ])

# ---------------------------------------------------------
# Correo
# ---------------------------------------------------------
    correo_detectado = _texto_detectado(
        detected_profile.get("correo"),
        254,
    )

    if (
        correo_detectado
        and _es_email(correo_detectado)
        and permite_actualizar(
            "correo",
            cliente.correo,
        )
        and cliente.correo != correo_detectado
    ):
        cliente.correo = correo_detectado
        cambios_cliente.extend([
            "correo",
            "actualizado_en",
        ])
    # ---------------------------------------------------------
    # Vehículo
    # ---------------------------------------------------------

    version_detectada = _normalizar_version_catalogo(
        version_detectada
    )
    anio_desde_version = None

    if version_detectada:
        match_anio = re.search(
            r"\b(20\d{2})\b",
            version_detectada,
        )

        if match_anio:
            anio_desde_version = int(
                match_anio.group(1)
            )

# ---------------------------------------------------------
# Año del vehículo
# ---------------------------------------------------------
    anio_auto = _int_detectado(
        detected_profile.get("anio_auto")
    )

    if anio_auto is None:
        anio_auto = anio_desde_version

    if (
        anio_auto is not None
        and 1900 <= anio_auto <= 2100
        and permite_actualizar(
            "anio_auto",
            expediente.anio_auto,
        )
        and expediente.anio_auto != anio_auto
    ):
        expediente.anio_auto = anio_auto
        cambios_expediente.append("anio_auto")
# ---------------------------------------------------------
# Comentarios
# ---------------------------------------------------------
    comentarios = _texto_detectado(
        detected_profile.get("comentarios"),
        2000,
    )

    if (
        comentarios
        and permite_actualizar(
            "comentarios",
            expediente.comentarios,
        )
        and expediente.comentarios != comentarios
    ):
        expediente.comentarios = comentarios
        cambios_expediente.append("comentarios")
    # El interés sí puede cambiar cuando el cliente menciona otro modelo.
    if (
        version_detectada
        and expediente.auto_interes != version_detectada
    ):
        expediente.auto_interes = version_detectada
        cambios_expediente.append("auto_interes")

    # ---------------------------------------------------------
    # Enganche
    # ---------------------------------------------------------
    enganche = _int_detectado(
        detected_profile.get("enganche_monto")
    )

    if (
        enganche is not None
        and permite_actualizar(
            "enganche_monto",
            expediente.enganche_monto,
        )
        and expediente.enganche_monto != enganche
    ):
        expediente.enganche_monto = enganche
        cambios_expediente.append("enganche_monto")

    # ---------------------------------------------------------
    # Presupuesto mensual y rango
    # ---------------------------------------------------------
    presupuesto = _int_detectado(
        detected_profile.get("presupuesto_mensual")
    )

    presupuesto_min = _int_detectado(
        detected_profile.get("presupuesto_mensual_min")
    )

    presupuesto_max = _int_detectado(
        detected_profile.get("presupuesto_mensual_max")
    )

    if presupuesto_min is not None:
        perfil_extra["presupuesto_mensual_min"] = presupuesto_min

    if presupuesto_max is not None:
        perfil_extra["presupuesto_mensual_max"] = presupuesto_max

    # La tabla actual solo tiene un presupuesto mensual.
    # Cuando existe rango se guarda el límite superior en el campo principal
    # y ambos extremos dentro de datos_extra.
    presupuesto_principal = (
        presupuesto
        or presupuesto_max
        or presupuesto_min
    )

    correccion_presupuesto = any(
        correcciones.get(campo, False)
        for campo in (
            "presupuesto_mensual",
            "presupuesto_mensual_min",
            "presupuesto_mensual_max",
        )
    )

    if (
        presupuesto_principal is not None
        and (
            esta_vacio(expediente.presupuesto_mensual)
            or correccion_presupuesto
        )
        and expediente.presupuesto_mensual
        != presupuesto_principal
    ):
        expediente.presupuesto_mensual = presupuesto_principal
        cambios_expediente.append("presupuesto_mensual")

    # ---------------------------------------------------------
    # Buró
    # ---------------------------------------------------------
    buro = _texto_detectado(
        detected_profile.get("buro_estado"),
        30,
    ).lower()

    if (
        buro
        and buro != "desconocido"
        and permite_actualizar(
            "buro_estado",
            expediente.buro_estado,
        )
        and expediente.buro_estado != buro
    ):
        expediente.buro_estado = buro
        cambios_expediente.append("buro_estado")

    # ---------------------------------------------------------
    # Forma de pago
    # ---------------------------------------------------------
    forma_pago = _texto_detectado(
        detected_profile.get("forma_pago"),
        30,
    ).lower()

    if (
        forma_pago
        and forma_pago != "desconocido"
        and permite_actualizar(
            "forma_pago",
            expediente.forma_pago,
        )
        and expediente.forma_pago != forma_pago
    ):
        expediente.forma_pago = forma_pago
        cambios_expediente.append("forma_pago")

    # ---------------------------------------------------------
    # Tipo de cliente
    # ---------------------------------------------------------
    tipo_cliente = _texto_detectado(
        detected_profile.get("tipo_cliente"),
        30,
    ).lower()

    if (
        tipo_cliente
        and tipo_cliente != "desconocido"
        and permite_actualizar(
            "tipo_cliente",
            expediente.tipo_cliente,
        )
        and expediente.tipo_cliente != tipo_cliente
    ):
        expediente.tipo_cliente = tipo_cliente
        cambios_expediente.append("tipo_cliente")

    # ---------------------------------------------------------
    # Comprobación de ingresos
    # ---------------------------------------------------------
    comprobacion_ingresos = _texto_detectado(
        detected_profile.get("comprobacion_ingresos"),
        200,
    )

    if (
        comprobacion_ingresos
        and permite_actualizar(
            "comprobacion_ingresos",
            expediente.comprobacion_ingresos,
        )
        and expediente.comprobacion_ingresos
        != comprobacion_ingresos
    ):
        expediente.comprobacion_ingresos = comprobacion_ingresos
        cambios_expediente.append("comprobacion_ingresos")

    # ---------------------------------------------------------
    # Uso del vehículo
    # ---------------------------------------------------------
    uso_vehiculo = _texto_detectado(
        detected_profile.get("uso_vehiculo"),
        255,
    )

    if (
        uso_vehiculo
        and permite_actualizar(
            "uso_vehiculo",
            expediente.uso_vehiculo,
        )
        and expediente.uso_vehiculo != uso_vehiculo
    ):
        expediente.uso_vehiculo = uso_vehiculo
        cambios_expediente.append("uso_vehiculo")

    # ---------------------------------------------------------
    # Plazo de compra
    # ---------------------------------------------------------
    plazo_compra = _texto_detectado(
        detected_profile.get("plazo_compra"),
        120,
    )

    if (
        plazo_compra
        and permite_actualizar(
            "plazo_compra",
            expediente.plazo_compra,
        )
        and expediente.plazo_compra != plazo_compra
    ):
        expediente.plazo_compra = plazo_compra
        cambios_expediente.append("plazo_compra")

    # ---------------------------------------------------------
    # Datos adicionales sin columna propia
    # ---------------------------------------------------------
    campos_extra = {
        "personalidad_juridica": 120,
        "auto_cuenta": 200,
        "ciudad": 120,
        "horario_contacto": 120,
        "vehiculo_interes": 255,
    }

    for campo, longitud in campos_extra.items():
        valor = _texto_detectado(
            detected_profile.get(campo),
            longitud,
        )

        if not valor:
            continue

        valor_actual = perfil_extra.get(campo)

        if (
            esta_vacio(valor_actual)
            or correcciones.get(campo, False)
        ):
            perfil_extra[campo] = valor

    datos_extra["perfil_extra"] = perfil_extra

    # ---------------------------------------------------------
    # Calificación comercial
    # ---------------------------------------------------------
    if _lead_es_calificado(
        expediente.enganche_monto,
        expediente.buro_estado or "desconocido",
    ):
        if expediente.estado not in {
            "Lead Calificado",
            "Pendiente de Cotización",
        }:
            expediente.estado = "Lead Calificado"
            cambios_expediente.append("estado")

    if requiere_asesor:
        if not expediente.requiere_asesor:
            expediente.requiere_asesor = True
            cambios_expediente.append("requiere_asesor")

        motivo = (
            str(intent or accion_ofrecida or "seguimiento_comercial")
            .strip()[:120]
        )

        if (
            motivo
            and expediente.motivo_requiere_asesor != motivo
        ):
            expediente.motivo_requiere_asesor = motivo
            cambios_expediente.append(
                "motivo_requiere_asesor"
            )

    # ---------------------------------------------------------
    # Memoria de preguntas y respuestas
    # ---------------------------------------------------------
    preguntas_realizadas = _ia_dict(
        datos_extra.get("preguntas_realizadas")
    ).copy()

    question_key = (
        str(question_key or "").strip()
        if question_key
        else ""
    )

    if question_key in PREGUNTAS_PERFIL_VALIDAS:
        preguntas_realizadas[question_key] = (
            int(preguntas_realizadas.get(question_key) or 0)
            + 1
        )

        if conversacion.pregunta_pendiente == question_key:
            conversacion.pregunta_pendiente_intentos += 1
        else:
            conversacion.pregunta_pendiente = question_key
            conversacion.pregunta_pendiente_intentos = 1
    else:
        conversacion.pregunta_pendiente = ""
        conversacion.pregunta_pendiente_intentos = 0

    datos_extra["preguntas_realizadas"] = preguntas_realizadas

    ultimas_respuestas = datos_extra.get(
        "ultimas_respuestas_ia"
    )

    if not isinstance(ultimas_respuestas, list):
        ultimas_respuestas = []

    reply_text = str(reply_text or "").strip()

    if reply_text:
        ultimas_respuestas.append(reply_text)
        datos_extra["ultimas_respuestas_ia"] = (
            ultimas_respuestas[-5:]
        )

    conversacion.datos_extra = datos_extra
    conversacion.ultima_intencion = str(
        intent or ""
    ).strip()[:80]

    if version_detectada:
        conversacion.ultimo_modelo_mencionado = (
            version_detectada[:120]
        )

    if requiere_asesor:
        conversacion.estado_conversacion = (
            "pendiente_cotizacion"
        )
    else:
        estado_conversacion, _ = (
            _estado_conversacion_desde_etapa(
                nueva_etapa_perfilado
            )
        )
        conversacion.estado_conversacion = estado_conversacion

    # ---------------------------------------------------------
    # Persistencia
    # ---------------------------------------------------------
    if cambios_cliente:
        cliente.save(
            update_fields=list(
                dict.fromkeys(cambios_cliente)
            )
        )

    if cambios_expediente:
        cambios_expediente.append("actualizado")

        expediente.save(
            update_fields=list(
                dict.fromkeys(cambios_expediente)
            )
        )

    conversacion.save(
        update_fields=[
            "estado_conversacion",
            "pregunta_pendiente",
            "pregunta_pendiente_intentos",
            "ultima_intencion",
            "ultimo_modelo_mencionado",
            "datos_extra",
        ]
    )

def _ya_se_respondio_a_entrada(numero_asesor: str, wa_message_id_entrante: str) -> bool:
    numero_asesor = normaliza_tel_mx(numero_asesor)
    wa_message_id_entrante = (wa_message_id_entrante or "").strip()
    if not numero_asesor or len(wa_message_id_entrante) < 5:
        return False
    return MensajeWhatsApp.objects.filter(
        numero_asesor=numero_asesor, direction="out",
        raw__reply_to=wa_message_id_entrante,
    ).exists()

def construir_respuesta_informativa(
    *,
    expediente: ExpedienteDigital,
    numero_asesor: str,
    telefono: str,
    profile_name: str,
    texto_usuario: str,
    auto_interes_actual: Optional[str] = None,
    ultimo_mensaje_saliente: str = "",
    historial_reciente: Optional[list[dict[str, Any]]] = None,
    accion_ofrecida_previa: Optional[str] = None,
    etapa_perfilado: int = 0,
    enganche_registrado: Optional[int] = None,
    buro_registrado: str = "",
    es_primer_mensaje: bool = False,
    nombre_cliente: str = "",
) -> tuple[
    str,
    Optional[str],
    bool,
    bool,
    bool,
    bool,
    dict[str, Any],
    dict[str, Any],
    str,
    int,
]:
    texto_usuario = str(texto_usuario or "").strip()
    historial_reciente = historial_reciente or []

    try:
        decision = _decision_conversacional_ia(
            expediente=expediente,
            numero_asesor=numero_asesor,
            telefono=telefono,
            nombre_cliente=nombre_cliente,
            profile_name=profile_name,
            texto_usuario=texto_usuario,
            auto_interes_actual=auto_interes_actual,
            ultimo_mensaje_saliente=ultimo_mensaje_saliente,
            historial_reciente=historial_reciente,
            accion_ofrecida_previa=accion_ofrecida_previa,
            etapa_perfilado=etapa_perfilado,
            enganche_registrado=enganche_registrado,
            buro_registrado=buro_registrado,
            es_primer_mensaje=es_primer_mensaje,
        )
    except Exception:
        logger.exception(
            "ERROR CONSTRUYENDO RESPUESTA IA | linea=%s expediente=%s",
            numero_asesor,
            expediente.pk,
        )

        decision = {
            "skip_send": True,
            "skip_reason": "error_construccion_respuesta",
        }

    if not decision or decision.get("skip_send"):
        return (
            "",
            auto_interes_actual,
            False,
            False,
            False,
            False,
            {},
            decision or {
                "skip_send": True,
                "skip_reason": "decision_vacia",
            },
            "ninguna",
            etapa_perfilado,
        )

    respuesta_texto = str(
        decision.get("reply_text") or ""
    ).strip()

    version_contexto = _normalizar_version_catalogo(
        decision.get("selected_version")
    )

    if not version_contexto:
        texto_version = str(texto_usuario or "").strip().upper()

        datos_extra = _ia_dict(
            ConversacionIA.objects.filter(
                expediente=expediente,
                numero_asesor=normaliza_tel_mx(numero_asesor),
            )
            .values_list("datos_extra", flat=True)
            .first()
        )

        perfil_extra = _ia_dict(
            datos_extra.get("perfil_extra")
        )

        modelo_general = str(
            perfil_extra.get("vehiculo_interes") or ""
        ).strip().upper()

        anio_general = expediente.anio_auto

        if modelo_general and anio_general and texto_version:
            candidatos = [
                clave
                for clave in _obtener_catalogo_dict().keys()
                if modelo_general in clave
                and str(anio_general) in clave
                and texto_version in clave
            ]

            if len(candidatos) == 1:
                version_contexto = candidatos[0]
                decision["selected_version"] = version_contexto

    enviar_pdf = bool(
        decision.get("send_pdf")
    ) and bool(version_contexto)

    enviar_imagenes = bool(
        decision.get("send_images")
    ) and bool(version_contexto)

    enviar_videos = bool(
        decision.get("send_videos")
    ) and bool(version_contexto)

    requiere_asesor = bool(
        decision.get("requiere_asesor")
    )

    detected_profile = _ia_dict(
        decision.get("detected_profile")
    )

    accion_ofrecida = str(
        decision.get("accion_ofrecida") or "ninguna"
    ).strip()

    try:
        nueva_etapa = int(
            decision.get(
                "nueva_etapa_perfilado",
                etapa_perfilado,
            )
        )
    except (TypeError, ValueError):
        nueva_etapa = etapa_perfilado

    return (
        respuesta_texto,
        version_contexto,
        enviar_pdf,
        enviar_imagenes,
        enviar_videos,
        requiere_asesor,
        detected_profile,
        decision,
        accion_ofrecida,
        nueva_etapa,
    )

TIPOS_MEDIA_PROCESABLE_IA = {"image", "sticker", "video", "audio"}


def _describir_media_entrante_con_ia(
    *,
    raw_message: Optional[dict],
    numero_asesor: str,
) -> str:
    """
    Descarga el archivo desde Meta y le pide a Gemini que lo convierta
    en contexto útil para atención automotriz.
    """
    media = _extraer_media_entrante(raw_message)

    if not media:
        return ""

    try:
        blob, content_type = download_media_whatsapp(
            media.get("media_id") or media.get("id"),
            numero_asesor=numero_asesor,
        )

        mime_type = media.get("mime_type") or content_type or "application/octet-stream"
        media_type = media.get("type") or "media"

        prompt = f"""
Eres una IA de atención comercial para agencias Volkswagen.

El cliente envió un archivo de tipo: {media_type}.
Analiza el contenido y responde SOLO con un resumen útil para continuar la conversación.

Enfócate en:
- Si se ve o menciona algún vehículo.
- Si parece comprobante, identificación, cotización, captura de pantalla o documento.
- Si el audio/video contiene una solicitud de precio, modelo, cita, financiamiento o ubicación.
- Si el sticker comunica emoción/intención: interés, duda, aprobación, molestia, risa, etc.
- No inventes datos que no se vean o escuchen.

Devuelve máximo 8 líneas.
""".strip()

        client = _get_gemini_client()

        response = client.models.generate_content(
            model=getattr(
                settings,
                "GEMINI_MEDIA_MODEL",
                getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash"),
            ),
            contents=[
                prompt,
                types.Part.from_bytes(
                    data=blob,
                    mime_type=mime_type,
                ),
            ],
        )

        return _limitar_texto((getattr(response, "text", "") or "").strip(), 900)

    except Exception as exc:
        return (
            "El cliente envió un archivo multimedia, pero no pude analizarlo "
            f"automáticamente. Tipo detectado: {media.get('type')}. Error interno: {str(exc)[:180]}"
        )

TIPOS_MEDIA_IA = {
    "image",
    "video",
    "audio",
    "sticker",
    "document",
}

MIME_FALLBACK_MEDIA = {
    "image": "image/jpeg",
    "video": "video/mp4",
    "audio": "audio/ogg",
    "sticker": "image/webp",
    "document": "application/pdf",
}


def _extraer_media_entrante(raw_message: Optional[dict]) -> dict[str, Any]:
    """
    Extrae metadata del media entrante de WhatsApp Cloud API.

    Soporta:
    - image
    - video
    - audio
    - sticker
    - document

    WhatsApp envía el archivo como media_id.
    Después nosotros lo descargamos con download_media_whatsapp().
    """
    if not isinstance(raw_message, dict):
        return {}

    tipo = str(raw_message.get("type") or "").lower().strip()

    if tipo not in TIPOS_MEDIA_IA:
        return {}

    payload = raw_message.get(tipo) or {}

    if not isinstance(payload, dict):
        return {}

    media_id = str(payload.get("id") or "").strip()

    if not media_id:
        return {}

    caption = ""

    if tipo in ("image", "video", "document"):
        caption = str(payload.get("caption") or "").strip()

    return {
        "type": tipo,
        "media_id": media_id,
        "mime_type": str(payload.get("mime_type") or "").strip(),
        "sha256": str(payload.get("sha256") or "").strip(),
        "filename": str(payload.get("filename") or "").strip(),
        "caption": caption,
    }


def _mime_para_gemini(tipo: str, content_type: str = "") -> str:
    """
    Normaliza MIME type para que Gemini pueda interpretar el archivo.

    Cuando Meta no manda content-type claro, usamos un fallback por tipo.
    """
    tipo = str(tipo or "").lower().strip()
    content_type = str(content_type or "").split(";")[0].lower().strip()

    if content_type and content_type != "application/octet-stream":
        return content_type

    return MIME_FALLBACK_MEDIA.get(tipo, "application/octet-stream")


def _instruccion_analisis_multimedia(
    *,
    tipo: str,
    caption: str = "",
    texto_usuario: str = "",
) -> str:
    """
    Prompt para convertir un archivo de WhatsApp en contexto textual útil.

    Punto importante:
    Esta función NO debe vender ni cerrar la conversación. Solo traduce el
    contenido multimedia a texto para que el motor comercial responda mejor.
    """
    tipo = str(tipo or "media").lower().strip()
    caption = str(caption or "").strip()
    texto_usuario = str(texto_usuario or "").strip()

    reglas_por_tipo = {
        "image": (
            "Analiza la imagen. Indica si parece una foto real, render, captura, "
            "documento o publicidad. Si aparece un auto, describe marca visible, "
            "modelo probable, color, ángulo, condición aparente y elementos relevantes. "
            "Si el modelo no es seguro, dilo como probabilidad."
        ),
        "sticker": (
            "Analiza el sticker como reacción emocional del cliente. Describe la "
            "emoción probable: aprobación, duda, risa, molestia, sorpresa, rechazo "
            "o interés. No inventes intención de compra si no hay señales."
        ),
        "video": (
            "Analiza el video. Resume qué ocurre, si aparece o se menciona un vehículo, "
            "detalles visibles, sonido relevante, dudas del cliente y señales comerciales."
        ),
        "audio": (
            "Transcribe primero la idea principal del audio y luego resume intención, "
            "modelo mencionado, presupuesto, forma de pago, enganche, buró, cita, "
            "ubicación o cualquier dato útil del prospecto."
        ),
        "document": (
            "Analiza el documento. Resume datos visibles y clasifica si parece "
            "identificación, comprobante, ficha técnica, cotización, captura, recibo "
            "u otro archivo comercial. No extraigas datos sensibles innecesarios."
        ),
    }

    instruccion_tipo = reglas_por_tipo.get(
        tipo,
        "Analiza el archivo y resume su contenido útil para atención comercial.",
    )

    return f"""
Eres un asistente de CRM automotriz especializado en WhatsApp.

Tu tarea es analizar el archivo que envió el cliente y convertirlo en contexto útil
para que otra IA responda de forma natural y comercial.

{instruccion_tipo}

Reglas estrictas:
- Responde en español.
- No inventes datos que no aparezcan, se vean o se escuchen.
- Si no puedes identificar modelo, versión o documento, dilo claramente.
- No digas que estás limitado a texto.
- No ofrezcas enviar fotos, videos ni fichas; eso lo decide otra parte del flujo.
- No cierres venta ni prometas disponibilidad, precio final o promoción.
- Sé breve pero útil.
- Máximo 1200 caracteres.

Devuelve el análisis con este formato:
Contenido detectado:
Vehículo o documento:
Intención probable del cliente:
Datos útiles para responder:
Nivel de certeza:

Contexto textual adicional del mensaje:
{texto_usuario or "Sin texto adicional."}

Caption del archivo:
{caption or "Sin caption."}
""".strip()



def _analizar_media_con_gemini(
    *,
    media: dict[str, Any],
    blob: bytes,
    content_type: str,
    texto_usuario: str,
    numero_asesor: str,
) -> str:
    """
    Envía el archivo descargado desde Meta a Gemini para convertirlo en texto.

    Para archivos pequeños usamos inline bytes.
    Si el archivo es muy grande, no lo mandamos para evitar romper el request.
    """
    if not blob:
        return ""

    max_bytes = int(
        getattr(
            settings,
            "GEMINI_MAX_INLINE_MEDIA_BYTES",
            18 * 1024 * 1024,
        )
    )

    tipo = str(media.get("type") or "media").lower().strip()

    if len(blob) > max_bytes:
        return (
            f"El cliente envió un archivo de tipo {tipo}, "
            f"pero pesa {round(len(blob) / 1024 / 1024, 2)} MB y supera el límite "
            "configurado para análisis automático."
        )

    mime_type = _mime_para_gemini(tipo, content_type)

    if mime_type == "application/octet-stream":
        return f"El cliente envió un archivo de tipo {tipo}, pero no se pudo determinar el formato."

    prompt = _instruccion_analisis_multimedia(
        tipo=tipo,
        caption=media.get("caption", ""),
        texto_usuario=texto_usuario,
    )

    client = _get_gemini_client()

    modelo_multimodal = getattr(
        settings,
        "GEMINI_MULTIMODAL_MODEL",
        getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash"),
    )

    respuesta = client.models.generate_content(
        model=modelo_multimodal,
        contents=[
            types.Part.from_bytes(
                data=blob,
                mime_type=mime_type,
            ),
            prompt,
        ],
        config=types.GenerateContentConfig(
            temperature=0.2,
        ),
    )

    texto = str(getattr(respuesta, "text", "") or "").strip()

    return _limitar_texto(texto, max_len=1200)


def _enriquecer_texto_usuario_con_media(
    *,
    texto_usuario: str,
    raw_message: Optional[dict],
    numero_asesor: str,
) -> str:
    """
    Si el cliente mandó media, descarga el archivo de Meta, lo analiza con Gemini
    y agrega el resultado al texto que ya usa tu flujo conversacional.

    Esto permite que tu función construir_respuesta_informativa() siga funcionando
    sin reescribir toda la lógica comercial.
    """
    texto_usuario = str(texto_usuario or "").strip()

    media = _extraer_media_entrante(raw_message)

    if not media:
        return texto_usuario

    tipo = media.get("type") or "media"
    caption = str(media.get("caption") or "").strip()
    media_id = str(media.get("media_id") or "").strip()

    descripcion = ""

    try:
        blob, content_type_descargado = download_media_whatsapp(
            media_id,
            numero_asesor=numero_asesor,
        )

        content_type = media.get("mime_type") or content_type_descargado

        descripcion = _analizar_media_con_gemini(
            media=media,
            blob=blob,
            content_type=content_type,
            texto_usuario=texto_usuario,
            numero_asesor=numero_asesor,
        )

    except Exception as exc:
        logger.exception(
            "No se pudo analizar media con Gemini | tipo=%s media_id=%s numero_asesor=%s error=%s",
            tipo,
            media_id,
            numero_asesor,
            str(exc),
        )

        descripcion = (
            f"El cliente envió un archivo de tipo {tipo}, "
            "pero no se pudo analizar automáticamente."
        )

    partes = []

    if texto_usuario and texto_usuario not in {
        "[IMAGE]",
        "[VIDEO]",
        "[AUDIO]",
        "[STICKER]",
        "[DOCUMENT]",
    }:
        partes.append(texto_usuario)

    if caption:
        partes.append(f"Caption del cliente: {caption}")

    if descripcion:
        partes.append(
            "[CONTEXTO MULTIMEDIA ANALIZADO]\n"
            f"Tipo: {tipo}\n"
            f"Media ID: {media_id}\n"
            f"Resumen: {descripcion}"
        )

    return "\n\n".join(partes).strip() or f"El cliente envió un archivo de tipo {tipo}."

def _tiene_contexto_multimedia_analizado(texto: str) -> bool:
    return "[CONTEXTO MULTIMEDIA ANALIZADO]" in str(texto or "")


def _extraer_tipo_multimedia_analizado(texto: str) -> str:
    match = re.search(r"Tipo:\s*([a-zA-Z0-9_-]+)", str(texto or ""), flags=re.IGNORECASE)
    return match.group(1).lower().strip() if match else ""


def _extraer_resumen_multimedia_analizado(texto: str) -> str:
    """
    Extrae solo el resumen del bloque multimedia para poder construir
    una respuesta de respaldo sin mostrar Media ID ni marcadores internos.
    """
    value = str(texto or "")

    if "[CONTEXTO MULTIMEDIA ANALIZADO]" not in value:
        return ""

    match = re.search(r"Resumen:\s*(.+)", value, flags=re.IGNORECASE | re.DOTALL)

    if not match:
        return ""

    resumen = match.group(1).strip()

    # Si en el futuro se agregan más secciones después del resumen, cortamos
    # antes de otros encabezados internos comunes.
    resumen = re.split(
        r"\n(?:Media ID|Raw|Payload|Contexto interno):",
        resumen,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip()

    return _limitar_texto(resumen, max_len=700)


def _respuesta_quiere_enviar_media(texto: str) -> bool:
    t = _normalizar_texto(texto)
    patrones = [
        "TE COMPARTO UNAS IMAGENES",
        "TE COMPARTO IMAGENES",
        "TE COMPARTO FOTOS",
        "TE COMPARTO UN VIDEO",
        "TE COMPARTO VIDEO",
        "TE COMPARTO LA FICHA",
        "TE ENVIO IMAGENES",
        "TE ENVIO FOTOS",
        "TE ENVIO VIDEO",
        "TE ENVIO LA FICHA",
    ]

    return any(patron in t for patron in patrones)


def _respuesta_desde_contexto_multimedia(
    *,
    texto_usuario: str,
    selected_version: Optional[str],
    telefono: str = "",
) -> str:
    """
    Respuesta de seguridad para cuando el cliente mandó una imagen/video/audio
    y preguntó algo como "qué opinas", pero el modelo intentó mandar más media.
    """
    resumen = _extraer_resumen_multimedia_analizado(texto_usuario)
    tipo = _extraer_tipo_multimedia_analizado(texto_usuario)

    if selected_version:
        base = (
            f"Se ve interesante. Por lo que enviaste, parece relacionado con {selected_version.title()}. "
        )
    elif tipo == "sticker":
        base = "Recibí tu sticker. Lo tomo como una reacción a la conversación. "
    elif tipo == "audio":
        base = "Escuché tu audio y tomé los puntos importantes. "
    elif tipo == "document":
        base = "Revisé el documento que enviaste. "
    elif tipo == "video":
        base = "Revisé el video que enviaste. "
    else:
        base = "Revisé la imagen que enviaste. "

    if resumen:
        return _limitar_texto(
            f"{base}\n\n{resumen}\n\n"
            "Si te interesa avanzar, puedo ayudarte con precio, ficha técnica, "
            "opciones de financiamiento o agendar una visita.",
            max_len=900,
        )

    return _limitar_texto(
        f"{base}"
        "Si quieres, puedo ayudarte a identificar el modelo, revisar opciones de precio "
        "o canalizarte con un asesor para una propuesta formal.",
        max_len=700,
    )


def _dividir_mensaje_whatsapp(
    texto: str,
    max_len: int = 500,
    max_partes: int = 2,
) -> list[str]:
    """
    Divide sin cortar palabras ni ideas cuando sea posible.
    Prioridad de corte:
    1. párrafo
    2. oración
    3. espacio
    """
    texto = re.sub(r"\n{3,}", "\n\n", (texto or "").strip())

    if not texto:
        return []

    if len(texto) <= max_len:
        return [texto]

    partes = []
    restante = texto

    while restante and len(partes) < max_partes:
        if len(restante) <= max_len:
            partes.append(restante.strip())
            break

        ventana = restante[:max_len]

        cortes = [
            ventana.rfind("\n\n"),
            ventana.rfind(". "),
            ventana.rfind("? "),
            ventana.rfind("! "),
            ventana.rfind("; "),
            ventana.rfind(", "),
            ventana.rfind(" "),
        ]

        corte = max(cortes)

        if corte < int(max_len * 0.55):
            corte = ventana.rfind(" ")

        if corte <= 0:
            corte = max_len

        parte = restante[:corte].strip()
        restante = restante[corte:].strip()

        if parte:
            partes.append(parte)

    if restante and partes:
        aviso = "Te comparto el resto en el siguiente seguimiento para no saturarte."
        espacio = max_len - len(partes[-1]) - 2

        if espacio >= len(aviso):
            partes[-1] = f"{partes[-1]}\n\n{aviso}"
        else:
            partes[-1] = partes[-1][: max_len - 3].rstrip() + "..."

    return partes


def _segundos_escritura_ia(texto: str) -> int:
    """
    Delay humano. Puedes fijarlo en settings.py:
    IA_WHATSAPP_TYPING_SECONDS = 4
    """
    fijo = getattr(settings, "IA_WHATSAPP_TYPING_SECONDS", None)

    if fijo is not None:
        try:
            return max(0, min(int(fijo), 24))
        except (TypeError, ValueError):
            pass

    largo = len(texto or "")

    if largo <= 180:
        return 2

    if largo <= 500:
        return 4

    return 6

# Respuesta automática completa

def responder_mensaje_automatico(
    *, wa_from: str, numero_asesor: str, profile_name: str = "",
    texto_usuario: str = "", wa_message_id_entrante: str = "",
    raw_message: Optional[dict] = None,
) -> dict:
    telefono = normaliza_tel_mx(replace_start(wa_from))
    numero_asesor = normaliza_tel_mx(numero_asesor)
    wa_message_id_entrante = str(
        wa_message_id_entrante or ""
    ).strip()

    texto_usuario_original = str(
        texto_usuario or ""
    ).strip()

    if not telefono:
        raise ValueError(
            "Número inválido para responder automáticamente."
        )

    if not numero_asesor:
        raise ValueError(
            "Número de asesor inválido."
        )

    if _ya_se_respondio_a_entrada(
        numero_asesor,
        wa_message_id_entrante,
    ):
        return {
            "ok": True,
            "skipped": True,
            "reason": "ya_se_respondio_a_esta_entrada",
            "telefono": telefono,
            "numero_asesor": numero_asesor,
            "wa_message_id_entrante": wa_message_id_entrante,
        }

    # El análisis multimedia se ejecuta una sola vez y únicamente
    # después de verificar que el mensaje no haya sido procesado.
    texto_usuario = _enriquecer_texto_usuario_con_media(
        texto_usuario=texto_usuario_original,
        raw_message=raw_message,
        numero_asesor=numero_asesor,
    )

    cliente, expediente = _get_or_create_cliente_y_expediente(
        telefono=telefono, numero_asesor=numero_asesor,
        profile_name=profile_name, texto_entrante=texto_usuario,
    )

    auto_interes_actual = _limpiar_auto_interes_invalido(expediente)
    nombre_contexto = (cliente.nombre or "").strip() or _extraer_nombre_basico(profile_name, "") or ""
    ultimo_mensaje_saliente = _obtener_ultimo_mensaje_saliente(cliente, numero_asesor)
    historial_reciente = _serializar_historial(cliente,numero_asesor,limite=20,)
    accion_ofrecida_previa = _obtener_ultima_accion_ofrecida(cliente, numero_asesor)

    total_entrantes = _contar_mensajes_entrantes(cliente, numero_asesor)
    es_primer_mensaje = total_entrantes <= 1

    etapa_perfilado = _obtener_etapa_perfilado(expediente, numero_asesor)
    enganche_registrado: Optional[int] = expediente.enganche_monto
    buro_str = expediente.buro_estado or _leer_dato_conversacion(
        expediente,
        numero_asesor,
        "buro_estado",
        default="desconocido",
    )

    (
        respuesta_texto,
        version_contexto,
        enviar_pdf,
        enviar_imagenes,
        enviar_videos,
        requiere_asesor,
        detected_profile,
        raw_decision,
        accion_ofrecida,
        nueva_etapa_perfilado,
    ) = construir_respuesta_informativa(
        expediente=expediente,
        numero_asesor=numero_asesor,
        telefono=telefono,
        profile_name=profile_name,
        texto_usuario=texto_usuario,
        auto_interes_actual=auto_interes_actual,
        ultimo_mensaje_saliente=ultimo_mensaje_saliente,
        historial_reciente=historial_reciente,
        accion_ofrecida_previa=accion_ofrecida_previa,
        etapa_perfilado=etapa_perfilado,
        enganche_registrado=enganche_registrado,
        buro_registrado=buro_str,
        es_primer_mensaje=es_primer_mensaje,
        nombre_cliente=nombre_contexto,
    )

    _guardar_datos_detectados_en_cliente_y_expediente(
        cliente=cliente,
        expediente=expediente,
        profile_name=profile_name,
        texto_usuario=texto_usuario,
        detected_profile=detected_profile,
        version_detectada=version_contexto,
        nueva_etapa_perfilado=nueva_etapa_perfilado,
        numero_asesor=numero_asesor,
        correcciones_explicitas=raw_decision.get(
            "correcciones_explicitas"
        ),
        question_key=raw_decision.get("question_key"),
        intent=raw_decision.get("intent") or "",
        reply_text=respuesta_texto,
        requiere_asesor=requiere_asesor,
        accion_ofrecida=accion_ofrecida,
    )

    if (
        raw_decision.get("skip_send")
        or not str(respuesta_texto or "").strip()
    ):
        motivo = (
            raw_decision.get("skip_reason")
            or "respuesta_ia_no_disponible"
        )

        logger.warning(
            "RESPUESTA IA OMITIDA | linea=%s cliente=%s expediente=%s motivo=%s",
            numero_asesor,
            telefono,
            expediente.pk,
            motivo,
        )

        return {
            "ok": False,
            "skipped": True,
            "reason": motivo,
            "telefono": telefono,
            "numero_asesor": numero_asesor,
            "expediente_id": expediente.pk,
            "wa_message_id_entrante": wa_message_id_entrante,
        }

    partes_respuesta = _dividir_mensaje_whatsapp(
        respuesta_texto,
        max_len=500,
        max_partes=2,
    )

    if not partes_respuesta:
        logger.warning(
            "IA SIN PARTES DE RESPUESTA | linea=%s cliente=%s expediente=%s",
            numero_asesor,
            telefono,
            expediente.pk,
        )

        return {
            "ok": False,
            "skipped": True,
            "reason": "respuesta_sin_contenido",
            "telefono": telefono,
            "numero_asesor": numero_asesor,
            "expediente_id": expediente.pk,
            "wa_message_id_entrante": wa_message_id_entrante,
        }

    try:
        enviar_indicador_escribiendo_whatsapp(
            message_id=wa_message_id_entrante,
            numero_asesor=numero_asesor,
        )
        time.sleep(_segundos_escritura_ia(respuesta_texto))
    except Exception:
        # No rompemos el flujo si Meta no acepta el typing indicator.
        pass

    wa_res = None
    wa_message_id_salida = ""

    for index, parte in enumerate(partes_respuesta):
        reply_context_id = wa_message_id_entrante if index == 0 else ""

        wa_res_parte = enviar_texto_whatsapp(
            to=telefono,
            text=parte,
            numero_asesor=numero_asesor,
            reply_to_message_id=reply_context_id,
        )

        wa_message_id_parte = ""
        try:
            wa_message_id_parte = (wa_res_parte.get("messages") or [{}])[0].get("id", "") or ""
        except Exception:
            pass

        if index == 0:
            wa_res = wa_res_parte
            wa_message_id_salida = wa_message_id_parte

        _guardar_salida(
            telefono=telefono,
            numero_asesor=numero_asesor,
            cliente=cliente,
            texto=parte,
            wa_message_id=wa_message_id_parte,
            raw={
                "reply_to": wa_message_id_entrante,
                "ia_provider": "gemini",
                "ia_model": getattr(
                    settings,
                    "GEMINI_MODEL",
                    "gemini-2.5-flash",
                ),
                "numero_asesor": numero_asesor,
                "version_contexto": version_contexto,
                "requiere_asesor": requiere_asesor,
                "detected_profile": detected_profile,
                "decision": raw_decision,
                "intent": raw_decision.get("intent") or "",
                "question_key": raw_decision.get("question_key"),
                "correcciones_explicitas": raw_decision.get(
                    "correcciones_explicitas"
                ) or {},
                "accion_ofrecida": accion_ofrecida,
                "nueva_etapa_perfilado": nueva_etapa_perfilado,
                "parte": index + 1,
                "partes_total": len(partes_respuesta),
                "texto_usuario_original": texto_usuario_original,
            },
            status_msg="accepted",
        )

        if index < len(partes_respuesta) - 1:
            time.sleep(1.2)

    # Envio de imagenes
    image_results: list = []
    image_errors: list = []
    if enviar_imagenes and version_contexto:
        for imagen_relativa in _imagenes_de_version(version_contexto):
            image_url = _resolver_url_media(imagen_relativa)
            filename = imagen_relativa.rsplit("/", 1)[-1]
            image_error = ""
            try:
                image_res = enviar_imagen_whatsapp_por_link(
                    to=telefono, link=image_url, numero_asesor=numero_asesor,
                    caption=f"Imagen de {version_contexto.title()}",
                )
            except Exception as exc:
                image_error = str(exc)
                image_res = {"ok": False, "error": image_error}

            image_message_id = ""
            try:
                image_message_id = (image_res.get("messages") or [{}])[0].get("id", "") or ""
            except Exception:
                pass

            _guardar_salida(
                telefono=telefono, numero_asesor=numero_asesor, cliente=cliente,
                texto=f"[FILE:{filename}]", wa_message_id=image_message_id,
                raw={"reply_to": wa_message_id_entrante, "version_contexto": version_contexto,
                     "meta_type": "image", "filename": filename, "media_link": image_url,
                     "accion_ofrecida": "continuar_contexto",
                     "conversation_meta": {"accion_ofrecida": "continuar_contexto"},
                     "wa_response": image_res, "image_error": image_error},
                status_msg="accepted" if image_message_id else "failed",
            )
            image_results.append(image_res)
            if image_error:
                image_errors.append(image_error)
    
    # Envio de videos
    video_results: list = []
    video_errors: list = []
    if enviar_videos and version_contexto:
        for video_relativo in _videos_de_version(version_contexto):
            video_url = _resolver_url_media(video_relativo)

            if not video_url:
                continue

            filename = video_relativo.rsplit("/", 1)[-1]
            video_error = ""

            try:
                video_res = enviar_video_whatsapp_por_link(
                    to=telefono, link=video_url, numero_asesor=numero_asesor,
                    caption=f"Video de {version_contexto.title()}",
                )
            except Exception as exc:
                video_error = str(exc)
                video_res = {"ok": False, "error": video_error}

            video_message_id = ""
            try:
                video_message_id = (video_res.get("messages") or [{}])[0].get("id", "") or ""
            except Exception:
                pass

            _guardar_salida(
                telefono=telefono, numero_asesor=numero_asesor, cliente=cliente,
                texto=f"[FILE:{filename}]", wa_message_id=video_message_id,
                raw={"reply_to": wa_message_id_entrante, "version_contexto": version_contexto,
                     "meta_type": "video", "filename": filename, "media_link": video_url,
                     "accion_ofrecida": "continuar_contexto",
                     "conversation_meta": {"accion_ofrecida": "continuar_contexto"},
                     "wa_response": video_res, "video_error": video_error},
                status_msg="accepted" if video_message_id else "failed",
            )
            video_results.append(video_res)
            if video_error:
                video_errors.append(video_error)

    # Envio de PDF
    pdf_res = None
    pdf_error = ""

    if enviar_pdf and version_contexto:
        catalogo = _obtener_catalogo_dict()
        data = catalogo.get(version_contexto) or {}
        pdf_url = _resolver_url_media(data.get("url_ficha_tecnica") or "")

        if pdf_url:
            try:
                pdf_res = enviar_documento_whatsapp_por_link(
                    to=telefono,
                    link=pdf_url,
                    numero_asesor=numero_asesor,
                    caption=f"Ficha tecnica de {version_contexto}",
                    filename=f"{version_contexto.lower().replace(' ', '-')}.pdf",
                )
            except Exception as exc:
                pdf_error = str(exc)
                pdf_res = {"ok": False, "error": pdf_error}

            pdf_message_id = ""
            try:
                pdf_message_id = (pdf_res.get("messages") or [{}])[0].get("id", "") or ""
            except Exception:
                pass

            _guardar_salida(
                telefono=telefono,
                numero_asesor=numero_asesor,
                cliente=cliente,
                texto=f"[FILE:{version_contexto}.pdf]",
                wa_message_id=pdf_message_id,
                raw={
                    "reply_to": wa_message_id_entrante,
                    "version_contexto": version_contexto,
                    "meta_type": "document",
                    "filename": f"{version_contexto.lower().replace(' ', '-')}.pdf",
                    "document_link": pdf_url,
                    "accion_ofrecida": "compartir_pdf",
                    "conversation_meta": {"accion_ofrecida": "compartir_pdf"},
                    "wa_response": pdf_res,
                    "pdf_error": pdf_error,
                },
                status_msg="accepted" if pdf_message_id else "failed",
            )
        else:
            enviar_pdf = False
            pdf_error = "El vehículo no tiene url_ficha_tecnica configurada."

    # Actualizar expediente
    # La IA NO debe actualizar primer_contacto_asesor ni ultimo_contacto_asesor.
    # Esos campos solo deben cambiar cuando responde un asesor humano desde el CRM.
    cambios = []

    if version_contexto and expediente.auto_interes != version_contexto:
        expediente.auto_interes = version_contexto
        cambios.append("auto_interes")

    if requiere_asesor:
        texto_normalizado = _normalizar_texto(texto_usuario)
        requiere_cotizacion = (
            accion_ofrecida in ("lead_calificado", "confirmar_canalizacion")
            or any(palabra in texto_normalizado for palabra in PALABRAS_COTIZACION)
        )

        # Marcar que requiere atención humana, pero SIN pausar la IA automáticamente.
        expediente.requiere_asesor = True
        expediente.motivo_requiere_asesor = (
            "Solicitud de cotización" if requiere_cotizacion else "Atención de asesor requerida"
        )
        cambios.extend(["requiere_asesor", "motivo_requiere_asesor"])

        if requiere_cotizacion:
            expediente.cotizacion_pendiente = True
            expediente.cotizacion_solicitada_at = timezone.now()
            expediente.estado = "Pendiente de Cotización"
            cambios.extend([
                "cotizacion_pendiente",
                "cotizacion_solicitada_at",
                "estado",
            ])
        elif expediente.estado not in ("Lead Calificado", "Requiere Asesor", "Pendiente de Cotización"):
            expediente.estado = "Requiere Asesor"
            cambios.append("estado")
        conversacion = _get_or_create_conversacion_ia(expediente, numero_asesor)

        datos_extra = conversacion.datos_extra if isinstance(conversacion.datos_extra, dict) else {}
        datos_extra.update({
            "requiere_asesor": True,
            "requiere_cotizacion": requiere_cotizacion,
            "accion_ofrecida": accion_ofrecida,
            "auto_interes": version_contexto,
            "marcado_at": timezone.now().isoformat(),
        })

        conversacion.datos_extra = datos_extra
        conversacion.estado_conversacion = (
            "pendiente_cotizacion" if requiere_cotizacion else "informando"
        )
        conversacion.ultima_intencion = accion_ofrecida or ""
        conversacion.ultimo_modelo_mencionado = version_contexto or ""

        conversacion.save(update_fields=[
            "datos_extra",
            "estado_conversacion",
            "ultima_intencion",
            "ultimo_modelo_mencionado",
        ])

    cfg_linea = WHATSAPP_LINES.get(numero_asesor, {})
    for campo, valor in [
        ("agencia", (cfg_linea.get("agencia") or "").strip()),
        ("business", (cfg_linea.get("business") or "Comerciales").strip()),
    ]:
        if valor and getattr(expediente, campo) != valor:
            setattr(expediente, campo, valor); cambios.append(campo)

    if expediente.canal_contacto != "WhatsApp":
        expediente.canal_contacto = "WhatsApp"; cambios.append("canal_contacto")

    cambios.append("actualizado")
    expediente.save(update_fields=list(dict.fromkeys(cambios)))

    return {
        "ok": True, "telefono": telefono, "numero_asesor": numero_asesor,
        "cliente_id": cliente.id_cliente, "expediente_id": expediente.pk,
        "respuesta": respuesta_texto, "version_detectada": version_contexto,
        "pdf_enviado": enviar_pdf, "imagenes_enviadas": enviar_imagenes, 
        "videos_enviados": enviar_videos, "requiere_asesor": requiere_asesor,
        "accion_ofrecida": accion_ofrecida,"accion_ofrecida_previa": accion_ofrecida_previa,
        "etapa_perfilado_anterior": etapa_perfilado,
        "etapa_perfilado_nueva": nueva_etapa_perfilado,
        "detected_profile": detected_profile, "decision": raw_decision,
        "wa_response": wa_res, "pdf_response": pdf_res, "pdf_error": pdf_error,
        "image_responses": image_results, "image_errors": image_errors,
        "video_responses": video_results, "video_errors": video_errors,
    }