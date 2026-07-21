# Digitales/atribucion_meta.py
import json
import logging
from typing import Any

import requests
from django.utils import timezone

from .models import CampanaMeta, MapeoFuenteMeta
from citas.models import normaliza_tel_mx

from .sett import GRAPH_VERSION, WHATSAPP_LINES

try:
    from .sett import META_ADS_ACCESS_TOKEN
except ImportError:
    META_ADS_ACCESS_TOKEN = ""

logger = logging.getLogger(__name__)

def obtener_cfg_linea_meta(numero_asesor: str = "") -> dict:
    numero = normaliza_tel_mx(numero_asesor or "")
    return WHATSAPP_LINES.get(numero, {}) or {}


def obtener_tokens_meta_ads(numero_asesor: str = "") -> list[str]:
    """
    Devuelve tokens válidos para Marketing API.

    Importante: NO usamos el token de WhatsApp Cloud API como fallback,
    porque normalmente no tiene permisos de Marketing API como ads_read.
    """
    cfg = obtener_cfg_linea_meta(numero_asesor)

    candidatos = []

    tokens_linea = cfg.get("meta_ads_access_tokens")
    if isinstance(tokens_linea, (list, tuple)):
        candidatos.extend(tokens_linea)

    token_linea = cfg.get("meta_ads_access_token")
    if token_linea:
        candidatos.append(token_linea)

    if META_ADS_ACCESS_TOKEN:
        candidatos.append(META_ADS_ACCESS_TOKEN)

    salida = []
    vistos = set()
    for token in candidatos:
        token = str(token or "").strip()
        if not token or token in vistos:
            continue
        vistos.add(token)
        salida.append(token)

    return salida


def obtener_token_meta_ads(numero_asesor: str = "") -> str:
    tokens = obtener_tokens_meta_ads(numero_asesor)
    return tokens[0] if tokens else ""


def obtener_sucursal_fallback(numero_asesor: str = "") -> str:
    cfg = obtener_cfg_linea_meta(numero_asesor)
    return str(cfg.get("agencia") or "").strip()

def limpiar_id(valor: Any) -> str:
    return str(valor or "").strip()


def normalizar_tipo_fuente(valor: Any) -> str:
    texto = str(valor or "").strip().lower()

    aliases = {
        "ad": "ad",
        "ads": "ad",
        "anuncio": "ad",
        "advertisement": "ad",
        "adset": "adset",
        "ad_set": "adset",
        "adgroup": "adset",
        "conjunto": "adset",
        "campaign": "campaign",
        "campana": "campaign",
        "campaña": "campaign",
    }

    return aliases.get(texto, texto)



def convertir_bigint(valor: Any):
    texto = limpiar_id(valor)
    if not texto or not texto.isdigit():
        return None
    try:
        return int(texto)
    except (TypeError, ValueError, OverflowError):
        return None


def obtener_referencia_meta(mensaje_whatsapp: dict) -> dict:
    """
    WhatsApp Cloud API puede mandar referral en message.referral o message.context.referral.
    """
    if not isinstance(mensaje_whatsapp, dict):
        return {}

    referencia = mensaje_whatsapp.get("referral") or {}

    if not referencia:
        contexto = mensaje_whatsapp.get("context") or {}
        if isinstance(contexto, dict):
            referencia = contexto.get("referral") or {}

    return referencia if isinstance(referencia, dict) else {}


def extraer_id_fuente(referencia: dict) -> str:
    """
    El campo normal es source_id, pero dejamos fallback para payloads variantes.
    """
    for key in ("source_id", "ad_id", "campaign_id", "post_id"):
        valor = limpiar_id((referencia or {}).get(key))
        if valor:
            return valor
    return ""


def armar_nombre_pauta(*, sucursal: str = "", nombre_campana: str = "") -> str:
    sucursal = str(sucursal or "").strip()
    nombre_campana = str(nombre_campana or "").strip()

    if sucursal and nombre_campana:
        return f"{sucursal} - {nombre_campana}"

    return nombre_campana or sucursal


def buscar_campana_por_id_campana(id_campana):
    id_campana_int = convertir_bigint(id_campana)
    if id_campana_int is None:
        return None

    try:
        return (
            CampanaMeta.objects.using("sqlserver")
            .filter(id_campana=id_campana_int)
            .only("id_campana", "sucursal", "nombre_campana")
            .first()
        )
    except Exception as error:
        logger.exception("ERROR BUSCANDO campanas_meta | id_campana=%s | error=%s", id_campana, error)
        return None


def buscar_mapeo_por_id_fuente(id_fuente: str):
    id_fuente = limpiar_id(id_fuente)
    if not id_fuente:
        return None

    try:
        return (
            MapeoFuenteMeta.objects.using("sqlserver")
            .filter(id_fuente=id_fuente)
            .first()
        )
    except Exception as error:
        logger.exception("ERROR BUSCANDO mapeo_fuentes_meta | id_fuente=%s | error=%s", id_fuente, error)
        return None


def guardar_mapeo_fuente_meta(
    *,
    id_fuente: str,
    tipo_fuente: str,
    id_campana=None,
    nombre_campana: str = "",
    id_anuncio=None,
    nombre_anuncio: str = "",
    id_conjunto=None,
    nombre_conjunto: str = "",
    sucursal: str = "",
    respuesta_meta: dict | None = None,
):
    id_fuente = limpiar_id(id_fuente)
    tipo_fuente = normalizar_tipo_fuente(tipo_fuente) or "desconocido"

    if not id_fuente:
        return None

    ahora = timezone.now()

    valores_update = {
        "tipo_fuente": tipo_fuente,
        "id_campana": convertir_bigint(id_campana),
        "nombre_campana": str(nombre_campana or "").strip(),
        "id_anuncio": convertir_bigint(id_anuncio),
        "nombre_anuncio": str(nombre_anuncio or "").strip(),
        "id_conjunto": convertir_bigint(id_conjunto),
        "nombre_conjunto": str(nombre_conjunto or "").strip(),
        "sucursal": str(sucursal or "").strip(),
        "respuesta_meta": json.dumps(respuesta_meta or {}, ensure_ascii=False),
        "actualizado_en": ahora,
    }

    valores_create = {
        **valores_update,
        "creado_en": ahora,
    }

    try:
        obj, created = MapeoFuenteMeta.objects.using("sqlserver").update_or_create(
            id_fuente=id_fuente,
            defaults=valores_update,
            create_defaults=valores_create,
        )

        return obj

    except Exception as error:
        logger.exception(
            "ERROR GUARDANDO mapeo_fuentes_meta | id_fuente=%s | tipo=%s | error=%s",
            id_fuente,
            tipo_fuente,
            error,
        )
        return None

def consultar_objeto_meta(id_objeto: str, fields: str, numero_asesor: str = "") -> dict:
    id_objeto = limpiar_id(id_objeto)

    if not id_objeto:
        return {"ok": False, "motivo": "sin_id_objeto"}

    tokens = obtener_tokens_meta_ads(numero_asesor)

    if not tokens:
        return {
            "ok": False,
            "motivo": "sin_token_meta_ads_para_linea",
            "numero_asesor": normaliza_tel_mx(numero_asesor or ""),
        }

    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{id_objeto}"
    errores = []

    for index, access_token in enumerate(tokens, start=1):
        parametros = {
            "access_token": access_token,
            "fields": fields,
        }

        try:
            respuesta = requests.get(url, params=parametros, timeout=20)

            if respuesta.status_code < 400:
                return {"ok": True, "data": respuesta.json(), "token_index": index}

            errores.append({
                "status_code": respuesta.status_code,
                "detalle": respuesta.text,
                "token_index": index,
            })

        except requests.RequestException as error:
            errores.append({
                "motivo": "error_conexion_meta_ads",
                "detalle": str(error),
                "token_index": index,
            })

    return {
        "ok": False,
        "motivo": "error_meta_ads",
        "errores": errores,
        "numero_asesor": normaliza_tel_mx(numero_asesor or ""),
    }


def consultar_anuncio_meta(id_anuncio: str, numero_asesor: str = "") -> dict:
    return consultar_objeto_meta(
        id_anuncio,
        "id,name,campaign_id,adset_id,campaign{name},adset{name}",
        numero_asesor=numero_asesor,
    )


def consultar_conjunto_meta(id_conjunto: str, numero_asesor: str = "") -> dict:
    return consultar_objeto_meta(
        id_conjunto,
        "id,name,campaign_id,campaign{name}",
        numero_asesor=numero_asesor,
    )


def consultar_campana_meta_api(id_campana: str, numero_asesor: str = "") -> dict:
    return consultar_objeto_meta(
        id_campana,
        "id,name",
        numero_asesor=numero_asesor,
    )


def resolver_pauta_desde_mapeo(id_fuente: str) -> dict:
    mapeo = buscar_mapeo_por_id_fuente(id_fuente)
    if not mapeo:
        return {"ok": False, "motivo": "mapeo_no_encontrado"}

    pauta = armar_nombre_pauta(
        sucursal=mapeo.sucursal,
        nombre_campana=mapeo.nombre_campana,
    )

    if not pauta:
        return {"ok": False, "motivo": "mapeo_sin_nombre_campana"}

    return {
        "ok": True,
        "motivo": "pauta_resuelta_desde_mapeo",
        "id_fuente": mapeo.id_fuente,
        "tipo_fuente": mapeo.tipo_fuente,
        "id_campana": mapeo.id_campana,
        "nombre_campana": mapeo.nombre_campana,
        "id_anuncio": mapeo.id_anuncio,
        "nombre_anuncio": mapeo.nombre_anuncio,
        "id_conjunto": mapeo.id_conjunto,
        "nombre_conjunto": mapeo.nombre_conjunto,
        "sucursal": mapeo.sucursal,
        "pauta": pauta,
    }


def resolver_pauta_desde_campana_directa(id_fuente: str, tipo_fuente: str) -> dict:
    """
    Solo debe usarse cuando la fuente realmente es campaign/campaña.
    No se usa para ad, porque un ad_id puede coincidir por accidente con un id_campana.
    """
    tipo_fuente = normalizar_tipo_fuente(tipo_fuente)

    if tipo_fuente not in ("campaign", "campana", "campaña"):
        return {
            "ok": False,
            "motivo": "tipo_fuente_no_es_campana_directa",
            "tipo_fuente": tipo_fuente,
        }

    campana = buscar_campana_por_id_campana(id_fuente)
    if not campana:
        return {"ok": False, "motivo": "campana_no_encontrada_en_bd"}

    pauta = armar_nombre_pauta(
        sucursal=campana.sucursal,
        nombre_campana=campana.nombre_campana,
    )

    guardar_mapeo_fuente_meta(
        id_fuente=id_fuente,
        tipo_fuente="campaign",
        id_campana=campana.id_campana,
        nombre_campana=campana.nombre_campana,
        sucursal=campana.sucursal,
        respuesta_meta={
            "origen": "campanas_meta",
            "id_campana": campana.id_campana,
            "nombre_campana": campana.nombre_campana,
            "sucursal": campana.sucursal,
        },
    )

    return {
        "ok": True,
        "motivo": "pauta_resuelta_desde_campanas_meta",
        "id_fuente": id_fuente,
        "tipo_fuente": "campaign",
        "id_campana": campana.id_campana,
        "nombre_campana": campana.nombre_campana,
        "sucursal": campana.sucursal,
        "pauta": pauta,
    }


def _resolver_pauta_por_id_campana_meta(
    id_campana,
    nombre_campana_api: str = "",
    sucursal_fallback: str = "",
) -> tuple[str, str, str]:
    """
    Retorna:
    pauta, nombre_campana_final, sucursal_final.

    Prioridad:
    1. SQL Server campanas_meta.
    2. Nombre devuelto por Meta API.
    3. Sucursal de la línea WhatsApp como fallback.
    """
    campana_bd = buscar_campana_por_id_campana(id_campana)

    if campana_bd:
        nombre_campana_final = campana_bd.nombre_campana or ""
        sucursal_final = campana_bd.sucursal or ""
    else:
        nombre_campana_final = nombre_campana_api or ""
        sucursal_final = sucursal_fallback or ""

    pauta = armar_nombre_pauta(
        sucursal=sucursal_final,
        nombre_campana=nombre_campana_final,
    )

    return pauta, nombre_campana_final, sucursal_final

def resolver_pauta_desde_meta_ads(
    id_fuente: str,
    tipo_fuente: str,
    numero_asesor: str = "",
) -> dict:
    """
    Resuelve según el tipo real de fuente:
    - ad: source_id = ad_id -> campaign_id -> campanas_meta.
    - adgroup/adset: source_id = adset_id -> campaign_id -> campanas_meta.
    - campaign: source_id = campaign_id -> campanas_meta.
    """
    id_fuente = limpiar_id(id_fuente)
    tipo_fuente = normalizar_tipo_fuente(tipo_fuente)
    sucursal_fallback = obtener_sucursal_fallback(numero_asesor)

    if tipo_fuente in ("ad", "anuncio"):
        respuesta = consultar_anuncio_meta(id_fuente, numero_asesor=numero_asesor)
        if not respuesta.get("ok"):
            return respuesta

        anuncio = respuesta.get("data") or {}
        id_anuncio = anuncio.get("id") or id_fuente
        nombre_anuncio = anuncio.get("name") or ""
        id_campana = anuncio.get("campaign_id") or ""
        campaign_obj = anuncio.get("campaign") or {}
        nombre_campana_api = campaign_obj.get("name") or ""
        id_conjunto = anuncio.get("adset_id") or ""
        adset_obj = anuncio.get("adset") or {}
        nombre_conjunto = adset_obj.get("name") or ""

        pauta, nombre_campana_final, sucursal_final = _resolver_pauta_por_id_campana_meta(
            id_campana,
            nombre_campana_api,
            sucursal_fallback=sucursal_fallback,
        )

        if not pauta:
            return {
                "ok": False,
                "motivo": "anuncio_sin_campana_resoluble",
                "id_fuente": id_fuente,
                "tipo_fuente": tipo_fuente,
                "respuesta_meta": anuncio,
            }

        # Guardamos varios aliases para que próximos leads resuelvan sin consultar Meta.
        respuesta_meta = {"ad": anuncio}
        for fuente_id, fuente_tipo in (
            (id_anuncio, "ad"),
            (id_conjunto, "adset"),
            (id_campana, "campaign"),
        ):
            guardar_mapeo_fuente_meta(
                id_fuente=fuente_id,
                tipo_fuente=fuente_tipo,
                id_campana=id_campana,
                nombre_campana=nombre_campana_final,
                id_anuncio=id_anuncio,
                nombre_anuncio=nombre_anuncio,
                id_conjunto=id_conjunto,
                nombre_conjunto=nombre_conjunto,
                sucursal=sucursal_final,
                respuesta_meta=respuesta_meta,
            )

        return {
            "ok": True,
            "motivo": "pauta_resuelta_desde_meta_ads_ad",
            "id_fuente": id_fuente,
            "tipo_fuente": tipo_fuente,
            "id_campana": id_campana,
            "nombre_campana": nombre_campana_final,
            "id_anuncio": id_anuncio,
            "nombre_anuncio": nombre_anuncio,
            "id_conjunto": id_conjunto,
            "nombre_conjunto": nombre_conjunto,
            "sucursal": sucursal_final,
            "pauta": pauta,
        }

    if tipo_fuente in ("adset", "adgroup", "conjunto"):
        respuesta = consultar_conjunto_meta(id_fuente, numero_asesor=numero_asesor)
        if not respuesta.get("ok"):
            return respuesta

        conjunto = respuesta.get("data") or {}
        id_conjunto = conjunto.get("id") or id_fuente
        nombre_conjunto = conjunto.get("name") or ""
        id_campana = conjunto.get("campaign_id") or ""
        campaign_obj = conjunto.get("campaign") or {}
        nombre_campana_api = campaign_obj.get("name") or ""

        pauta, nombre_campana_final, sucursal_final = _resolver_pauta_por_id_campana_meta(
            id_campana,
            nombre_campana_api,
            sucursal_fallback=sucursal_fallback,
        )

        if not pauta:
            return {
                "ok": False,
                "motivo": "conjunto_sin_campana_resoluble",
                "id_fuente": id_fuente,
                "tipo_fuente": tipo_fuente,
                "respuesta_meta": conjunto,
            }

        for fuente_id, fuente_tipo in ((id_conjunto, "adset"), (id_campana, "campaign")):
            guardar_mapeo_fuente_meta(
                id_fuente=fuente_id,
                tipo_fuente=fuente_tipo,
                id_campana=id_campana,
                nombre_campana=nombre_campana_final,
                id_conjunto=id_conjunto,
                nombre_conjunto=nombre_conjunto,
                sucursal=sucursal_final,
                respuesta_meta={"adset": conjunto},
            )

        return {
            "ok": True,
            "motivo": "pauta_resuelta_desde_meta_ads_adset",
            "id_fuente": id_fuente,
            "tipo_fuente": tipo_fuente,
            "id_campana": id_campana,
            "nombre_campana": nombre_campana_final,
            "id_conjunto": id_conjunto,
            "nombre_conjunto": nombre_conjunto,
            "sucursal": sucursal_final,
            "pauta": pauta,
        }

    if tipo_fuente in ("campaign", "campana", "campaña"):
        # Primero SQL Server, luego Meta API como fallback.
        directo = resolver_pauta_desde_campana_directa(id_fuente, "campaign")
        if directo.get("ok"):
            return directo

        respuesta = consultar_campana_meta_api(id_fuente, numero_asesor=numero_asesor)
        if not respuesta.get("ok"):
            return respuesta

        campana_api = respuesta.get("data") or {}
        id_campana = campana_api.get("id") or id_fuente
        nombre_campana_api = campana_api.get("name") or ""

        pauta, nombre_campana_final, sucursal_final = _resolver_pauta_por_id_campana_meta(
            id_campana,
            nombre_campana_api,
            sucursal_fallback=sucursal_fallback,
        )

        if not pauta:
            return {
                "ok": False,
                "motivo": "campana_sin_nombre_resoluble",
                "id_fuente": id_fuente,
                "tipo_fuente": tipo_fuente,
                "respuesta_meta": campana_api,
            }

        guardar_mapeo_fuente_meta(
            id_fuente=id_campana,
            tipo_fuente="campaign",
            id_campana=id_campana,
            nombre_campana=nombre_campana_final,
            sucursal=sucursal_final,
            respuesta_meta={"campaign": campana_api},
        )

        return {
            "ok": True,
            "motivo": "pauta_resuelta_desde_meta_ads_campaign",
            "id_fuente": id_fuente,
            "tipo_fuente": tipo_fuente,
            "id_campana": id_campana,
            "nombre_campana": nombre_campana_final,
            "sucursal": sucursal_final,
            "pauta": pauta,
        }

    return {
        "ok": False,
        "motivo": "tipo_fuente_no_soportado",
        "tipo_fuente": tipo_fuente,
        "id_fuente": id_fuente,
    }

def debe_reemplazar_pauta(expediente, resultado: dict) -> bool:
    """
    Regla operativa:
    - Si llega una nueva pauta real desde Meta, representa el interés actual.
    - Por eso sí debe reemplazar la pauta anterior.
    - Solo no reemplaza si la pauta nueva viene vacía.
    """
    pauta_actual = str(getattr(expediente, "pauta", "") or "").strip()
    pauta_nueva = str((resultado or {}).get("pauta") or "").strip()

    if not pauta_nueva:
        return False

    return pauta_actual != pauta_nueva

def resolver_pauta_por_tipos_probables(
    id_fuente: str,
    tipo_fuente: str = "",
    numero_asesor: str = "",
) -> dict:
    """
    Meta normalmente envía source_id como ad_id en Click-to-WhatsApp.
    Aun así, algunos payloads pueden venir sin source_type o con variantes.
    Por eso probamos en este orden: tipo reportado, ad, adset y campaign.
    """
    tipo_normalizado = normalizar_tipo_fuente(tipo_fuente)

    tipos = []
    if tipo_normalizado:
        tipos.append(tipo_normalizado)

    for candidato in ("ad", "adset", "campaign"):
        if candidato not in tipos:
            tipos.append(candidato)

    intentos = []

    for tipo in tipos:
        if tipo == "campaign":
            resultado = resolver_pauta_desde_campana_directa(id_fuente, "campaign")
            if resultado.get("ok"):
                return resultado
            intentos.append({"tipo": tipo, "resultado": resultado})

        resultado = resolver_pauta_desde_meta_ads(
            id_fuente,
            tipo,
            numero_asesor=numero_asesor,
        )

        if resultado.get("ok"):
            return resultado

        intentos.append({"tipo": tipo, "resultado": resultado})

    return {
        "ok": False,
        "motivo": "no_resuelto_por_tipos_probables",
        "id_fuente": id_fuente,
        "tipo_fuente": tipo_normalizado,
        "intentos": intentos,
    }

def detectar_canal_desde_referencia(referencia: dict) -> str:
    """
    Si el mensaje trae un referral de anuncio (Meta), Se marca como
    "Facebook"
    """
    if not isinstance(referencia, dict):
        return ""

    if referencia.get("source_id") or referencia.get("source_type") or referencia.get("source_url"):
        return "Facebook"

    return ""

def aplicar_pauta_desde_referencia_meta(
    *,
    expediente,
    mensaje_whatsapp: dict,
    numero_asesor: str = "",
) -> dict:
    if not expediente:
        return {"ok": False, "motivo": "sin_expediente"}

    referencia = obtener_referencia_meta(mensaje_whatsapp)
    if not referencia:
        return {"ok": False, "motivo": "sin_referencia_meta"}

    canal_detectado = detectar_canal_desde_referencia(referencia)
    if canal_detectado and expediente.canal_contacto != canal_detectado:
        expediente.__class__.objects.filter(pk=expediente.pk).update(
            canal_contacto=canal_detectado
        )
        expediente.canal_contacto = canal_detectado

    id_fuente = extraer_id_fuente(referencia)
    tipo_fuente = normalizar_tipo_fuente(referencia.get("source_type"))

    if not id_fuente:
        return {
            "ok": False,
            "motivo": "sin_id_fuente",
            "referencia": referencia,
        }

    # Primero intentamos cache local. Si ya resolvimos ese ad_id/adset_id/campaign_id,
    # no volvemos a pegarle a Meta.
    resultado = resolver_pauta_desde_mapeo(id_fuente)

    if not resultado.get("ok"):
        resultado = resolver_pauta_por_tipos_probables(
            id_fuente,
            tipo_fuente,
            numero_asesor=numero_asesor,
        )

    if not resultado.get("ok"):
        resultado["id_fuente"] = id_fuente
        resultado["tipo_fuente"] = tipo_fuente
        resultado["referencia"] = referencia
        return resultado

    if debe_reemplazar_pauta(expediente, resultado):
        pauta_nueva = resultado.get("pauta") or ""

        expediente.__class__.objects.filter(pk=expediente.pk).update(
            pauta=pauta_nueva
        )

        expediente.pauta = pauta_nueva
        resultado["pauta_aplicada"] = True
    else:
        resultado["pauta_aplicada"] = False
        resultado["pauta_actual"] = expediente.pauta

    resultado["referencia"] = referencia
    resultado["numero_asesor"] = numero_asesor

    return resultado
