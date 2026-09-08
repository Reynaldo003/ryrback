# Digitales/lineas_negocio.py
import logging
from datetime import date

from django.db.models import Count
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from CrmConformidad.jwt_authentication import CRMJWTAuthentication

from .models import ExpedienteDigital
from .prospectos_stats import _filtro_por_agencia, _parse_int, _rango_mes

logger = logging.getLogger(__name__)

LINEAS = [
    {"id": "nuevos", "nombre": "Nuevos Volkswagen"},
    {"id": "usados", "nombre": "Seminuevos/Usados"},
    {"id": "sin_clasificar", "nombre": "Sin clasificar"},
]

CANALES = [
    {"id": "whatsapp", "nombre": "WhatsApp"},
    {"id": "vw_direct", "nombre": "VW Concesionaria/VW Direct"},
    {"id": "facebook", "nombre": "Facebook Ads"},
    {"id": "llamada", "nombre": "Llamada entrante"},
    {"id": "sin_clasificar", "nombre": "Sin clasificar"},
]


def _linea_de_business(business):
    valor = str(business or "").strip().casefold()
    if valor in ("nuevos", "comerciales"):
        return "nuevos"
    if valor == "usados":
        return "usados"
    return "sin_clasificar"


def _canal_normalizado(canal):
    valor = str(canal or "").strip().casefold()
    if valor == "whatsapp" or valor == "wa":
        return "whatsapp"
    if valor == "facebook" or valor == "meta" or valor == "facebook ads":
        return "facebook"
    if not valor:
        return "sin_clasificar"
    if "llamada" in valor or "telefon" in valor or valor.startswith("tel"):
        return "llamada"
    return "vw_direct"


def _porcentaje(parte, total):
    if not total:
        return 0.0
    return round((parte / total) * 100, 1)


@api_view(["GET"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def lineas_negocio_view(request):
    año = _parse_int(request.query_params, "anio", None) or _parse_int(request.query_params, "year", date.today().year)
    mes = _parse_int(request.query_params, "mes", None) or _parse_int(request.query_params, "month", date.today().month)
    agencia = str(request.query_params.get("agencia", "") or "").strip()
    limite = _parse_int(request.query_params, "limite", 5) or 5

    if not (1 <= mes <= 12):
        return Response({"detail": "Parámetro 'mes' inválido."}, status=400)

    inicio, fin = _rango_mes(año, mes)
    filtro_agencia = _filtro_por_agencia(agencia)

    base = (
        ExpedienteDigital.objects
        .filter(creado__gte=inicio, creado__lt=fin)
        .filter(filtro_agencia)
    )

    demanda_total = base.count()

    filas_canal = list(
        base
        .values("canal_contacto")
        .annotate(total=Count("id"))
    )
    totales_canal = {c["id"]: 0 for c in CANALES}
    for fila in filas_canal:
        canal_id = _canal_normalizado(fila["canal_contacto"])
        totales_canal[canal_id] += int(fila["total"] or 0)

    canales = [
        {
            "id": c["id"],
            "nombre": c["nombre"],
            "total": totales_canal[c["id"]],
            "porcentaje": _porcentaje(totales_canal[c["id"]], demanda_total),
        }
        for c in CANALES
    ]

    filas_linea = list(
        base
        .values("business")
        .annotate(total=Count("id"))
    )
    totales_linea = {l["id"]: 0 for l in LINEAS}
    for fila in filas_linea:
        linea_id = _linea_de_business(fila["business"])
        totales_linea[linea_id] += int(fila["total"] or 0)

    filas_detalle = list(
        base
        .values("business", "auto_interes", "pauta")
        .annotate(total=Count("id"))
        .order_by("-total")
    )

    filas_linea_canal = list(
        base
        .values("business", "canal_contacto")
        .annotate(total=Count("id"))
    )
    canal_por_linea = {}
    for fila in filas_linea_canal:
        linea_id = _linea_de_business(fila["business"])
        canal_id = _canal_normalizado(fila.get("canal_contacto"))
        canal_por_linea[(linea_id, canal_id)] = canal_por_linea.get((linea_id, canal_id), 0) + int(fila["total"] or 0)

    detalle_por_linea = {l["id"]: [] for l in LINEAS}
    for fila in filas_detalle:
        linea_id = _linea_de_business(fila["business"])
        if linea_id == "usados":
            nombre = str(fila["pauta"] or "").strip() or str(fila["auto_interes"] or "").strip()
        else:
            nombre = str(fila["auto_interes"] or "").strip() or str(fila["pauta"] or "").strip()
        if not nombre:
            continue
        detalle_por_linea[linea_id].append({
            "nombre": nombre,
            "total": int(fila["total"] or 0),
            "porcentaje": _porcentaje(int(fila["total"] or 0), totales_linea[linea_id]),
        })

    lineas = []
    for linea_info in LINEAS:
        linea_id = linea_info["id"]
        total_linea = totales_linea[linea_id]
        items = sorted(detalle_por_linea[linea_id], key=lambda x: -x["total"])[:limite]
        canales_linea = [
            {
                "id": c_info["id"],
                "total": canal_por_linea.get((linea_id, c_info["id"]), 0),
            }
            for c_info in CANALES
            if c_info["id"] != "sin_clasificar"
        ]
        lineas.append({
            "id": linea_id,
            "nombre": linea_info["nombre"],
            "total": total_linea,
            "porcentaje": _porcentaje(total_linea, demanda_total),
            "canales": canales_linea,
            "items": items,
            "total_items": len(detalle_por_linea[linea_id]),
        })

    return Response({
        "demanda_total": demanda_total,
        "canales": canales,
        "lineas": lineas,
        "rango": {
            "inicio": inicio.isoformat(),
            "fin": fin.isoformat(),
            "anio": año,
            "mes": mes,
        },
    })