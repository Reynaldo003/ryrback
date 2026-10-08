# Digitales/bdc_resumen.py
import logging
import re
import unicodedata
from datetime import date, datetime

from django.db.models import Q
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from CrmConformidad.jwt_authentication import CRMJWTAuthentication
from citas.models import Cita

from .models import ExpedienteDigital
from .sett import WHATSAPP_LINES
from .views import (
    ProspectosViewSet,
    _numeros_whatsapp_usuario,
    _usuario_es_admin,
)

logger = logging.getLogger(__name__)

# Port exacto de la lógica client-side de DashboardEjecutivoBDC.jsx
# para que los resultados sean idénticos a los actuales.

ESTADOS_CON_CONTACTO = {
    "contactado",
    "sin respuesta",
    "calificado",
    "pendiente de cotizacion",
    "requiere atencion",
    "requiere asesor",
    "cita programada",
    "asistencia a la cita",
    "no show",
    "no asistio",
    "financiamiento",
}

ORDEN_DEALER_GRUPO = [
    "VW Cordoba",
    "VW Orizaba",
    "VW Poza Rica",
    "VW Tuxtepec",
    "VW Tuxpan",
]

# Equivalencias de nombres (espejo de asesoresGestionComercial.js).
ASESOR_DIGITAL_CANONICO = {
    "lizbeth cano clara": "Lizbeth Cano Clara",
    "erendira santos coyotzi": "Erendira Santos Coyotzi",
    "marelly tenorio salinas": "Marelly Tenorio Salinas",
    "ia vagen": "IA Vagen",
    "edgar omar noguera solis": "Edgar Omar Noguera Solis",
    "dulce abigail garcia olivares": "Dulce Abigail Garcia Olivares",
    "bianca chavez alarcon": "Bianca Chavez Alarcon",
    "bianca isabel chavez alarcon": "Bianca Chavez Alarcon",
    "candy denisse marquez": "Candy Denisse Marquez",
    "candy denisse marquez cortes": "Candy Denisse Marquez",
    "julio ramirez lopez": "Julio Ramirez Lopez",
}


def _param_bool(valor):
    return str(valor or "").strip().casefold() in {
        "1", "true", "yes", "si", "sí", "all", "todos",
    }


def _normaliza_texto(valor):
    return str(valor or "").strip().lower()


def _quita_tildes(valor):
    texto = unicodedata.normalize("NFD", str(valor or ""))
    sin_tildes = "".join(
        ch for ch in texto if unicodedata.category(ch) != "Mn"
    )
    return sin_tildes.casefold()


def normaliza_telefono_mx(valor):
    raw = re.sub(r"\D", "", str(valor or ""))
    if len(raw) == 10:
        return f"52{raw}"
    if len(raw) == 12 and raw.startswith("52"):
        return raw
    return raw


def telefono_valido_bdc(valor):
    return bool(re.fullmatch(r"52\d{10}", valor or ""))


def canonical_asesor_digital(valor):
    normalizado = _quita_tildes(valor).replace("  ", " ").strip()
    if not normalizado:
        return ""
    return (
        ASESOR_DIGITAL_CANONICO.get(normalizado)
        or str(valor or "").strip()
    )


def normalize_dealer_grupo(valor):
    texto = _quita_tildes(valor)
    if "cordoba" in texto and "usados" not in texto:
        return "VW Cordoba"
    if "orizaba" in texto and "usados" not in texto:
        return "VW Orizaba"
    if "poza rica" in texto:
        return "VW Poza Rica"
    if "tuxtepec" in texto:
        return "VW Tuxtepec"
    if "tuxpan" in texto:
        return "VW Tuxpan"
    return str(valor or "").strip()


def solo_fecha(valor):
    if valor is None:
        return ""
    if isinstance(valor, datetime):
        return valor.strftime("%Y-%m-%d")
    if isinstance(valor, date):
        return valor.strftime("%Y-%m-%d")
    raw = str(valor).strip()
    if not raw:
        return ""
    iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})", raw)
    if iso:
        return f"{iso.group(1)}-{iso.group(2)}-{iso.group(3)}"
    mx = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})", raw)
    if mx:
        return (
            f"{mx.group(3)}-"
            f"{mx.group(2).zfill(2)}-"
            f"{mx.group(1).zfill(2)}"
        )
    return ""


def fecha_a_entero(ymd):
    if not ymd or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", ymd):
        return None
    try:
        return int(ymd.replace("-", ""))
    except ValueError:
        return None


def fecha_en_rango(valor, desde, hasta):
    entero = fecha_a_entero(solo_fecha(valor))
    if entero is None:
        return False
    if desde:
        desde_int = fecha_a_entero(solo_fecha(desde))
        if desde_int is not None and entero < desde_int:
            return False
    if hasta:
        hasta_int = fecha_a_entero(solo_fecha(hasta))
        if hasta_int is not None and entero > hasta_int:
            return False
    return True


def get_tipo_unidad(row):
    agencia = _quita_tildes(row.get("agencia") or "")
    linea = _quita_tildes(row.get("business") or "")
    if "usados" in agencia:
        return "Seminuevos"
    if linea in ("usados", "seminuevos"):
        return "Seminuevos"
    if linea == "comerciales":
        return "Comerciales"
    if linea == "nuevos":
        return "Nuevos"
    return ""


def linea_matches(tipo, filtro):
    if not filtro or filtro == "Todos":
        return True
    if not tipo:
        return False
    if filtro == "Nuevos + Seminuevos":
        return tipo in ("Nuevos", "Seminuevos")
    return tipo == filtro


def es_asesor_valido(nombre):
    return bool(nombre)


def es_gestionable(row, telefono):
    return _normaliza_texto(row.get("estado")) != "descalificado" and (
        telefono_valido_bdc(telefono)
    )


def es_contactado(row, telefono):
    estado = _normaliza_texto(row.get("estado"))
    if estado in ESTADOS_CON_CONTACTO:
        return True
    return bool(
        row.get("primer_mensaje_cliente")
        or solo_fecha(row.get("ultimo_contacto_asesor"))
        or row.get("ultima_cita_agendada")
        or row.get("asistencia")
        or str(row.get("folio_solicitud_credito") or "").strip()
        or str(row.get("solicitud_credito_estado") or "").strip()
        or str(row.get("vin_facturado") or "").strip()
    )


def tiene_solicitud(row):
    return bool(
        str(row.get("folio_solicitud_credito") or "").strip()
        or str(row.get("solicitud_credito_estado") or "").strip()
    )


def es_anf(row):
    estado = _normaliza_texto(row.get("solicitud_credito_estado"))
    return (
        estado in ("autorizado", "condicionado")
        and not str(row.get("vin_facturado") or "").strip()
    )


def asistencia_confirmada(valor):
    if valor is True or valor == 1:
        return True
    return _normaliza_texto(valor) in {
        "si", "sí", "true", "1", "asistio", "asistió",
    }


def _timestamp_fecha(valor):
    ymd = solo_fecha(valor)
    entero = fecha_a_entero(ymd)
    return entero or 0


def _prospecto_ts(row):
    for campo in (
        "creado",
        "primer_mensaje_cliente",
        "ultimo_contacto_asesor",
    ):
        ts = _timestamp_fecha(row.get(campo))
        if ts:
            return ts
    return 0


def _fecha_a_entero_inicio_fin(query_params):
    inicio = str(query_params.get("fecha_inicio") or "").strip()
    fin = str(query_params.get("fecha_fin") or "").strip()
    if inicio and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", inicio):
        inicio = ""
    if fin and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fin):
        fin = ""
    return inicio, fin


def _numero_asesor_param(request):
    numero = normaliza_telefono_mx(
        request.query_params.get("numero_asesor") or ""
    )
    # Mismo criterio que views._numero_linea_valido: solo líneas
    # registradas; el resto se ignora (igual que el listado).
    return numero if numero in WHATSAPP_LINES else ""


def _asesores_permitidos_usuario(user):
    """
    Nombres canónicos de asesores que el usuario puede monitorear.
    None => acceso total (admin). Espejo de asesoresPermitidosBDC.
    """
    if _usuario_es_admin(user):
        return None

    permitidos = set()

    for numero in _numeros_whatsapp_usuario(user):
        cfg = WHATSAPP_LINES.get(numero) or {}
        if not cfg:
            continue

        asesores_compartidos = cfg.get("asesores") or []

        if not asesores_compartidos:
            nombre = canonical_asesor_digital(cfg.get("asesor_digital"))
            if nombre:
                permitidos.add(nombre)
            continue

        usuario = str(
            getattr(user, "usuario", "")
            or getattr(user, "username", "")
            or getattr(user, "correo", "")
            or ""
        ).strip().casefold()

        for asesor in asesores_compartidos:
            if asesor.get("activo") is False:
                continue
            if (
                str(asesor.get("usuario") or "").strip().casefold()
                == usuario
            ):
                nombre = canonical_asesor_digital(asesor.get("nombre"))
                if nombre:
                    permitidos.add(nombre)

    return permitidos


def _asesor_puede_monitorearse(nombre, permitidos):
    if permitidos is None:
        return True
    return bool(nombre and nombre in permitidos)


def _queryset_base_bdc(request, viewset):
    """
    Replica el alcance de permisos de ProspectosViewSet.get_queryset
    para la vista BDC (todos / una línea / varias líneas del usuario).
    """
    user = getattr(request, "user", None)
    es_admin = _usuario_es_admin(user)
    solicita_todos = _param_bool(
        request.query_params.get("todos")
    )
    numero_param = _numero_asesor_param(request)

    if solicita_todos and es_admin:
        return viewset._base_queryset()

    if es_admin:
        numero = numero_param
        if not numero:
            from .views import _get_numero_asesor_request
            numero = _get_numero_asesor_request(request)
        return viewset._queryset_por_linea(numero)

    numeros = _numeros_whatsapp_usuario(user)

    if numero_param:
        if numero_param not in numeros:
            raise PermissionDenied(
                f"No tienes permiso para consultar la línea "
                f"{numero_param}."
            )
        return viewset._queryset_por_linea(numero_param)

    if not numeros:
        return ExpedienteDigital.objects.none()

    # Coordinador u usuario con varias líneas: unión de sus líneas.
    ids = set()
    for numero in numeros:
        try:
            ids.update(
                viewset._queryset_por_linea(numero).values_list(
                    "id", flat=True
                )
            )
        except Exception:
            logger.exception(
                "No se pudo consultar la línea %s para BDC", numero
            )

    orden = (
        "-ultimo_contacto_asesor",
        "-primer_contacto_asesor",
        "-primer_mensaje_cliente",
        "-actualizado",
        "-creado",
    )
    return (
        ExpedienteDigital.objects.filter(id__in=ids)
        .select_related("cliente")
        .order_by(*orden)
    )


def _valores_prospecto(queryset):
    return list(
        queryset.values(
            "id",
            "cliente__telefono",
            "agencia",
            "business",
            "canal_contacto",
            "estado",
            "motivo_descalificacion",
            "asesor_digital",
            "folio_solicitud_credito",
            "solicitud_credito_estado",
            "vin_facturado",
            "facturado_at",
            "creado",
            "primer_mensaje_cliente",
            "primer_contacto_asesor",
            "ultimo_contacto_asesor",
            "ultima_cita_agendada",
            "asistencia",
        )
    )


def _citas_periodo(inicio, fin):
    queryset = Cita.objects.exclude(asesor_digital="").exclude(
        asesor_digital__isnull=True
    )
    if inicio:
        queryset = queryset.filter(creado_en__date__gte=inicio)
    if fin:
        queryset = queryset.filter(creado_en__date__lte=fin)
    return list(
        queryset.values(
            "id",
            "agencia",
            "auto_interes",
            "asesor_digital",
            "asistencia",
            "fecha_hora_cita",
            "tipo_cita",
            "fuente_prospeccion",
            "creado_en",
            "cliente__telefono",
        )
    )


def _telefonos(citas_o_filas, getter):
    conjunto = set()
    for item in citas_o_filas:
        tel = normaliza_telefono_mx(getter(item))
        if telefono_valido_bdc(tel):
            conjunto.add(tel)
    return conjunto


def _interseccion_porcentaje(origen, destino):
    if not origen:
        return 0.0
    avanzaron = sum(1 for tel in origen if tel in destino)
    return (avanzaron / len(origen)) * 100


@api_view(["GET"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def bdc_resumen_view(request):
    """
    Resumen agregado del dashboard Ejecutivo BDC.
    Devuelve métricas, embudo, resultados por asesora, orígenes,
    motivos de descarte y opciones de filtros, sin enviar filas
    crudas al navegador.
    """
    inicio, fin = _fecha_a_entero_inicio_fin(request.query_params)

    filtro_asesor = str(
        request.query_params.get("asesor") or ""
    ).strip()
    if filtro_asesor.casefold() == "todos":
        filtro_asesor = ""

    filtro_agencia = str(
        request.query_params.get("agencia") or ""
    ).strip()
    if filtro_agencia.casefold() == "todos":
        filtro_agencia = ""

    filtro_linea = str(
        request.query_params.get("linea") or ""
    ).strip()
    if filtro_linea.casefold() == "todos":
        filtro_linea = ""

    filtro_origen = str(
        request.query_params.get("origen") or ""
    ).strip()
    if filtro_origen.casefold() == "todos":
        filtro_origen = ""

    user = getattr(request, "user", None)
    permitidos = _asesores_permitidos_usuario(user)

    viewset = ProspectosViewSet(request=request, format_kwarg=None)
    queryset = _queryset_base_bdc(request, viewset)

    todas_filas = _valores_prospecto(queryset)

    # Base permisible: equivalente a `rows` del cálculo client-side
    # (filtro de asesores permitidos antes de todo lo demás).
    filas_permitidas = []
    for row in todas_filas:
        row["_telefono"] = normaliza_telefono_mx(
            row.get("cliente__telefono")
        )
        row["_asesor"] = canonical_asesor_digital(
            row.get("asesor_digital")
        )
        if _asesor_puede_monitorearse(row["_asesor"], permitidos):
            filas_permitidas.append(row)

    # Índice de prospectos por teléfono (todas las fechas, como el
    # índice client-side actual) para relacionar citas.
    prospectos_por_telefono = {}
    for row in filas_permitidas:
        tel = row["_telefono"]
        if not telefono_valido_bdc(tel):
            continue
        row["_ts"] = _prospecto_ts(row)
        prospectos_por_telefono.setdefault(tel, []).append(row)

    for lista in prospectos_por_telefono.values():
        lista.sort(key=lambda item: item["_ts"])

    # Prospectos del periodo con filtros de asesora/agencia/línea/origen.
    filas_periodo = []
    for row in filas_permitidas:
        if not fecha_en_rango(row.get("creado"), inicio, fin):
            continue
        if not es_asesor_valido(row["_asesor"]):
            continue
        if (
            filtro_asesor
            and row["_asesor"]
            != canonical_asesor_digital(filtro_asesor)
        ):
            continue
        if (
            filtro_agencia
            and normalize_dealer_grupo(row.get("agencia"))
            != filtro_agencia
        ):
            continue
        if not linea_matches(get_tipo_unidad(row), filtro_linea):
            continue
        if (
            filtro_origen
            and _quita_tildes(row.get("canal_contacto"))
            != _quita_tildes(filtro_origen)
        ):
            continue
        filas_periodo.append(row)

    telefonos_periodo = _telefonos(
        filas_periodo, lambda row: row.get("_telefono")
    )

    # Citas del periodo con permisos y cruce contra prospectos.
    citas_base = []
    vistas = set()
    for cita in _citas_periodo(inicio, fin):
        if cita["id"] in vistas:
            continue
        vistas.add(cita["id"])
        asesor_cita = canonical_asesor_digital(
            cita.get("asesor_digital")
        )
        if not es_asesor_valido(asesor_cita):
            continue
        if not _asesor_puede_monitorearse(asesor_cita, permitidos):
            continue
        cita["_asesor"] = asesor_cita
        citas_base.append(cita)

    def _prospecto_de_cita(cita, fecha_referencia):
        tel = normaliza_telefono_mx(cita.get("cliente__telefono"))
        lista = prospectos_por_telefono.get(tel) or []
        if not lista:
            return None
        ref = _timestamp_fecha(fecha_referencia)
        if not ref:
            return lista[-1]
        for item in reversed(lista):
            if item["_ts"] and item["_ts"] <= ref:
                return item
        return None

    citas_filtradas = []
    for cita in citas_base:
        if filtro_asesor and cita["_asesor"] != canonical_asesor_digital(
            filtro_asesor
        ):
            continue
        tel = normaliza_telefono_mx(cita.get("cliente__telefono"))
        prospecto = _prospecto_de_cita(cita, cita.get("fecha_hora_cita"))
        dealer_cita = normalize_dealer_grupo(
            cita.get("agencia")
            or (prospecto.get("agencia") if prospecto else "")
            or ""
        )
        if filtro_agencia and dealer_cita != filtro_agencia:
            continue
        if tel not in telefonos_periodo:
            continue
        if filtro_linea:
            tipo = get_tipo_unidad(prospecto or {})
            if not tipo:
                agencia_cita = _quita_tildes(cita.get("agencia"))
                auto_cita = _quita_tildes(cita.get("auto_interes"))
                if "usados" in agencia_cita or auto_cita in (
                    "seminuevos",
                    "seminuevo",
                ):
                    tipo = "Seminuevos"
            if not linea_matches(tipo, filtro_linea):
                continue
        if filtro_origen:
            origen_cita = str(
                cita.get("fuente_prospeccion")
                or (prospecto.get("canal_contacto") if prospecto else "")
                or ""
            ).strip()
            if _quita_tildes(origen_cita) != _quita_tildes(
                filtro_origen
            ):
                continue
        citas_filtradas.append(cita)

    # Facturados del periodo (mismos filtros, cruce por teléfono).
    vistos_facturados = set()
    facturados = []
    for row in filas_permitidas:
        if not fecha_en_rango(row.get("facturado_at"), inicio, fin):
            continue
        asesor_canonico = row["_asesor"]
        if not es_asesor_valido(asesor_canonico):
            continue
        if (
            filtro_asesor
            and asesor_canonico
            != canonical_asesor_digital(filtro_asesor)
        ):
            continue
        if (
            filtro_agencia
            and normalize_dealer_grupo(row.get("agencia"))
            != filtro_agencia
        ):
            continue
        if not linea_matches(get_tipo_unidad(row), filtro_linea):
            continue
        if (
            filtro_origen
            and _quita_tildes(row.get("canal_contacto"))
            != _quita_tildes(filtro_origen)
        ):
            continue
        if row["_telefono"] not in telefonos_periodo:
            continue
        if row["id"] in vistos_facturados:
            continue
        vistos_facturados.add(row["id"])
        facturados.append(row)

    # Métricas globales.
    gestionables_rows = [
        row
        for row in filas_periodo
        if es_gestionable(row, row.get("_telefono"))
    ]
    contactados_rows = [
        row
        for row in gestionables_rows
        if es_contactado(row, row.get("_telefono"))
    ]
    solicitudes_rows = [row for row in filas_periodo if tiene_solicitud(row)]

    oportunidades = len(filas_periodo)
    gestionables = len(gestionables_rows)
    contactados = len(contactados_rows)
    solicitudes = len(solicitudes_rows)
    citados = len(citas_filtradas)
    efectivas = sum(
        1
        for cita in citas_filtradas
        if asistencia_confirmada(cita.get("asistencia"))
    )
    facturados_total = len(facturados)
    anf = sum(1 for row in filas_periodo if es_anf(row))
    descartados = sum(
        1
        for row in filas_periodo
        if _normaliza_texto(row.get("estado")) == "descalificado"
    )

    sets = {
        "gestionables": _telefonos(
            gestionables_rows, lambda row: row.get("_telefono")
        ),
        "contactados": _telefonos(
            contactados_rows, lambda row: row.get("_telefono")
        ),
        "citados": _telefonos(
            citas_filtradas, lambda cita: cita.get("cliente__telefono")
        ),
        "efectivas": _telefonos(
            [
                cita
                for cita in citas_filtradas
                if asistencia_confirmada(cita.get("asistencia"))
            ],
            lambda cita: cita.get("cliente__telefono"),
        ),
        "solicitudes": _telefonos(
            solicitudes_rows, lambda row: row.get("_telefono")
        ),
        "facturados": _telefonos(
            facturados, lambda row: row.get("_telefono")
        ),
    }

    metricas = {
        "oportunidades": oportunidades,
        "gestionables": gestionables,
        "contactados": contactados,
        "citados": citados,
        "efectivas": efectivas,
        "solicitudes": solicitudes,
        "anf": anf,
        "facturados": facturados_total,
        "descartados": descartados,
        "tasa_contacto": (
            (contactados / gestionables) * 100 if gestionables else 0
        ),
        "efectividad_citas": (
            (efectivas / citados) * 100 if citados else 0
        ),
        "tasa_facturacion": (
            (facturados_total / solicitudes) * 100 if solicitudes else 0
        ),
    }

    # Embudo con conversión entre etapas (clientes únicos por teléfono).
    orden_etapas = [
        "gestionables",
        "contactados",
        "citados",
        "efectivas",
        "solicitudes",
        "facturados",
    ]
    funnel = {}
    for indice, etapa in enumerate(orden_etapas):
        origen_set = sets[etapa]
        siguiente = (
            orden_etapas[indice + 1]
            if indice + 1 < len(orden_etapas)
            else None
        )
        if siguiente:
            destino_set = sets[siguiente]
            avanzaron = sum(
                1 for tel in origen_set if tel in destino_set
            )
            conversion = _interseccion_porcentaje(
                origen_set, destino_set
            )
        else:
            avanzaron = 0
            conversion = None
        funnel[etapa] = {
            "value": metricas[etapa],
            "conversion": conversion,
            "base_clientes": len(origen_set),
            "avanzaron": avanzaron,
            "perdidos": max(len(origen_set) - avanzaron, 0),
        }

    # Resultados por asesora.
    nombres = []
    vistos_nombres = set()
    for row in filas_periodo:
        if row["_asesor"] not in vistos_nombres:
            vistos_nombres.add(row["_asesor"])
            nombres.append(row["_asesor"])
    for cita in citas_filtradas:
        if cita["_asesor"] not in vistos_nombres:
            vistos_nombres.add(cita["_asesor"])
            nombres.append(cita["_asesor"])

    facturados_por_asesor = {}
    for row in facturados:
        asesor = row["_asesor"]
        facturados_por_asesor[asesor] = (
            facturados_por_asesor.get(asesor, 0) + 1
        )

    resultados_asesor = []
    for nombre in nombres:
        registros = [
            row for row in filas_periodo if row["_asesor"] == nombre
        ]
        citas_asesor = [
            cita for cita in citas_filtradas if cita["_asesor"] == nombre
        ]
        gestionables_a = sum(
            1 for row in registros if es_gestionable(row, row.get("_telefono"))
        )
        contactados_a = sum(
            1
            for row in registros
            if es_gestionable(row, row.get("_telefono"))
            and es_contactado(row, row.get("_telefono"))
        )
        citados_a = len(citas_asesor)
        efectivas_a = sum(
            1
            for cita in citas_asesor
            if asistencia_confirmada(cita.get("asistencia"))
        )
        solicitudes_a = sum(1 for row in registros if tiene_solicitud(row))
        facturados_a = facturados_por_asesor.get(nombre, 0)
        resultados_asesor.append(
            {
                "nombre": nombre,
                "gestionables": gestionables_a,
                "contactados": contactados_a,
                "citados": citados_a,
                "efectivas": efectivas_a,
                "no_show": max(citados_a - efectivas_a, 0),
                "solicitudes": solicitudes_a,
                "facturados": facturados_a,
                "efectividad": (
                    (efectivas_a / citados_a) * 100 if citados_a else 0
                ),
            }
        )

    resultados_asesor.sort(
        key=lambda item: (
            -item["facturados"],
            -item["efectivas"],
            -item["citados"],
            -item["contactados"],
        )
    )

    # Orígenes y motivos de descarte.
    conteo_origen = {}
    for row in filas_periodo:
        clave = str(row.get("canal_contacto") or "").strip() or (
            "Otros / sin origen"
        )
        conteo_origen[clave] = conteo_origen.get(clave, 0) + 1
    origen_stats = sorted(
        conteo_origen.items(), key=lambda item: -item[1]
    )

    conteo_motivos = {}
    for row in filas_periodo:
        if _normaliza_texto(row.get("estado")) != "descalificado":
            continue
        clave = (
            str(row.get("motivo_descalificacion") or "").strip()
            or "Sin motivo capturado"
        )
        conteo_motivos[clave] = conteo_motivos.get(clave, 0) + 1
    motivos_descarte = sorted(
        conteo_motivos.items(), key=lambda item: -item[1]
    )

    # Opciones de los filtros (sobre el universo sin filtro de periodo,
    # igual que el cálculo client-side actual).
    opciones_asesores = set()
    for row in filas_permitidas:
        if es_asesor_valido(row["_asesor"]):
            opciones_asesores.add(row["_asesor"])
    for cita in citas_base:
        opciones_asesores.add(cita["_asesor"])

    opciones_agencias = {
        normalize_dealer_grupo(row.get("agencia"))
        for row in filas_permitidas
        if normalize_dealer_grupo(row.get("agencia"))
    }

    opciones_origenes = {
        str(row.get("canal_contacto") or "").strip()
        for row in filas_permitidas
        if str(row.get("canal_contacto") or "").strip()
    }

    agencias_ordenadas = [
        dealer
        for dealer in ORDEN_DEALER_GRUPO
        if dealer in opciones_agencias
    ] + sorted(
        (
            dealer
            for dealer in opciones_agencias
            if dealer not in ORDEN_DEALER_GRUPO
        ),
        key=str.casefold,
    )

    return Response(
        {
            "metricas": metricas,
            "funnel": funnel,
            "resultados_asesor": resultados_asesor,
            "origen_stats": origen_stats,
            "motivos_descarte": motivos_descarte,
            "opciones": {
                "asesores": sorted(
                    opciones_asesores, key=str.casefold
                ),
                "agencias": agencias_ordenadas,
                "origenes": sorted(
                    opciones_origenes, key=str.casefold
                ),
            },
        }
    )
