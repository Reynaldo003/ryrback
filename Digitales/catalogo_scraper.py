"""
Digitales/catalogo_scraper.py

Scraper de precios VW usando requests + BeautifulSoup.
NO necesita Selenium — el configurador de vw.com.mx renderiza HTML estático.

Instalar dependencias:
    pip install requests beautifulsoup4 lxml
"""

from __future__ import annotations
import re
import logging
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ── Configuración ─────────────────────────────────────────────────────────────

BASE_URL     = "https://www.vw.com.mx"
CONFIGURADOR = f"{BASE_URL}/es/configurador.html"
APP_URL      = f"{CONFIGURADOR}/__app/{{slug}}.app"

# slug de vw.com.mx → clave EXACTA en CATALOGO_VEHICULOS (mayúsculas)
MODELOS_SLUGS: dict[str, str] = {
    "polo":           "POLO 2026",
    "virtus":         "VIRTUS 2026",
    "tera":           "TERA 2026",
    "nivus":          "NUEVO NIVUS 2026",
    "jetta":          "JETTA 2026",
    "jetta-gli":      "GLI 2026",
    "golf-gti":       "GTI 2026",
    "saveiro":        "SAVEIRO 2026",        # precio Robust (más bajo)
    "saveiro-extreme":"SAVEIRO 2026",        # mismo modelo — se queda el precio menor
    "taigun":         "TAIGUN 2026",
    "taos":           "TAOS 2026",
    "tiguan":         "TIGUAN 2026",
    "teramont":       "TERAMONT 2026",
    "cross-sport":    "CROSS SPORT 2026",
    # Transporter Combi no aparece en el configurador web de VW MX
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-MX,es;q=0.9",
}

TIMEOUT = 20  # segundos


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_precio(texto: str) -> Optional[int]:
    """Convierte '$449,290' → 449290. Retorna None si no puede parsear."""
    if not texto:
        return None
    digits = re.sub(r"[^\d]", "", texto)
    return int(digits) if digits else None


def _fmt_precio(num: Optional[int]) -> str:
    """449290 → '$449,290'"""
    if num is None:
        return ""
    return f"${num:,}"


def _get_soup(url: str) -> Optional[BeautifulSoup]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        return BeautifulSoup(r.text, "lxml")
    except Exception as e:
        logger.warning("Error fetching %s: %s", url, e)
        return None


# ── Scraping por modelo ───────────────────────────────────────────────────────

def _scrapear_versiones(slug: str) -> dict:
    """
    Retorna dict con precio_lista_num, precio_desde y versiones,
    o {} si no encontró nada.
    """
    url  = APP_URL.format(slug=slug)
    soup = _get_soup(url)
    if not soup:
        return {}

    versiones = {}

    # Buscar h3 (nombre de versión) y el precio en su bloque padre
    for h3 in soup.find_all("h3"):
        nombre_version = h3.get_text(strip=True)
        if not nombre_version:
            continue

        precio_num = None
        parent = h3.find_parent()
        if parent:
            texto_bloque = parent.get_text(" ", strip=True)
            match = re.search(r"Precio de lista desde\s*\$([\d,]+)", texto_bloque)
            if match:
                precio_num = _parse_precio(match.group(1))

        if precio_num:
            versiones[nombre_version] = {
                "precio_lista_num": precio_num,
                "precio_desde":     _fmt_precio(precio_num),
            }

    if not versiones:
        # Fallback: cualquier "Precio de lista desde" en la página
        matches = re.findall(r"Precio de lista desde\s*\$([\d,]+)", soup.get_text())
        if matches:
            nums = [_parse_precio(m) for m in matches if _parse_precio(m)]
            if nums:
                precio_base = min(nums)
                return {
                    "precio_lista_num": precio_base,
                    "precio_desde":     _fmt_precio(precio_base),
                    "versiones":        {},
                }
        return {}

    precio_base = min(v["precio_lista_num"] for v in versiones.values())
    return {
        "precio_lista_num": precio_base,
        "precio_desde":     _fmt_precio(precio_base),
        "versiones":        versiones,
    }


# ── Función principal ─────────────────────────────────────────────────────────

def scrapear_precios() -> dict:
    """
    Retorna:
    {
        "exitoso":  True/False,
        "precios": {
            "JETTA 2026": {
                "precio_lista_num": 449290,
                "precio_desde": "$449,290",
                "versiones": {
                    "Trendline":   {"precio_lista_num": 449290, "precio_desde": "$449,290"},
                    "Comfortline": {"precio_lista_num": 498290, "precio_desde": "$498,290"},
                }
            },
            ...
        },
        "fallidos": ["GLI 2026", ...],
        "error":    "",
    }
    """
    logger.info("Iniciando scraping de precios VW (sin Selenium)...")

    precios      : dict[str, dict] = {}
    fallidos     : list[str]       = []
    ya_scrapeados: set[str]        = set()
    error_global                   = ""

    # 1. Verificar conectividad
    soup_main = _get_soup(CONFIGURADOR)
    if not soup_main:
        return {
            "exitoso": False,
            "precios": {},
            "fallidos": list(dict.fromkeys(MODELOS_SLUGS.values())),
            "error": f"No se pudo acceder a {CONFIGURADOR}. Verifica conectividad del servidor.",
        }

    # 2. Scrapear cada slug
    for slug, nombre_canonico in MODELOS_SLUGS.items():
        logger.info("  Scrapeando: %s (%s)...", nombre_canonico, slug)
        try:
            datos = _scrapear_versiones(slug)
            if datos and datos.get("precio_lista_num"):
                if nombre_canonico in precios:
                    # Mismo modelo, dos slugs (Saveiro): conservar el precio más bajo
                    if datos["precio_lista_num"] < precios[nombre_canonico]["precio_lista_num"]:
                        precios[nombre_canonico] = datos
                else:
                    precios[nombre_canonico] = datos
                ya_scrapeados.add(nombre_canonico)
                logger.info(
                    "    v %s — desde %s — %d versiones",
                    nombre_canonico,
                    datos["precio_desde"],
                    len(datos.get("versiones", {})),
                )
            else:
                if nombre_canonico not in ya_scrapeados:
                    logger.warning("    x %s — sin datos de precio", nombre_canonico)
                    fallidos.append(nombre_canonico)
        except Exception as e:
            logger.error("    x %s — excepcion: %s", nombre_canonico, e)
            if nombre_canonico not in ya_scrapeados:
                fallidos.append(nombre_canonico)

    # Deduplicar fallidos y quitar los que sí se obtuvieron
    fallidos = list(dict.fromkeys(f for f in fallidos if f not in precios))

    exitoso = len(precios) > 0
    if fallidos:
        error_global = f"Sin precio para: {', '.join(fallidos)}."
    if not exitoso:
        error_global = "No se pudo obtener ningun precio. El formato de la pagina puede haber cambiado."

    logger.info("Scraping finalizado — %d OK, %d fallidos", len(precios), len(fallidos))

    return {
        "exitoso": exitoso,
        "precios": precios,
        "fallidos": fallidos,
        "error":    error_global,
    }


# ── Test rápido desde terminal ────────────────────────────────────────────────
if __name__ == "__main__":
    import json, sys
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    resultado = scrapear_precios()
    print(json.dumps(resultado, ensure_ascii=False, indent=2))