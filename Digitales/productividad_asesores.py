# Digitales/productividad_asesores.py
import logging
from datetime import date

from django.db.models import Count
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from CrmConformidad.jwt_authentication import CRMJWTAuthentication

from .models import Asesor, ExpedienteDigital
from .prospectos_stats import _filtro_por_agencia, _parse_int, _rango_mes

logger = logging.getLogger(__name__)

CANALES = [
    {"id": "whatsapp", "nombre": "WhatsApp"},
    {"id": "vw_direct", "nombre": "VW Concesionaria/VW Direct"},
    {"id": "facebook", "nombre": "Facebook Ads"},
    {"id": "llamada", "nombre": "Llamada entrante"},
]


def _canal_normalizado(valor):
    texto = str(valor or "").strip().casefold()
    if texto == "whatsapp" or texto == "wa":
        return "whatsapp"
    if texto == "facebook" or texto == "meta" or texto == "facebook ads":
        return "facebook"
    if "llamada" in texto or "telefon" in texto or texto.startswith("tel"):
        return "llamada"
    return "vw_direct"


def _iniciales(nombre):
    partes = [p for p in str(nombre or "").strip().split() if p]
    if not partes:
        return ""
    if len(partes) == 1:
        return partes[0][:2].upper()
    return (partes[0][0] + partes[-1][0]).upper()


def _es_asesor_excluido(nombre):
    tokens = {t for t in str(nombre or "").casefold().split()}
    return "oba" in tokens


@api_view(["GET"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def productividad_asesores_view(request):
    año = _parse_int(request.query_params, "anio", None) or _parse_int(request.query_params, "year", date.today().year)
    mes = _parse_int(request.query_params, "mes", None) or _parse_int(request.query_params, "month", date.today().month)
    agencia = str(request.query_params.get("agencia", "") or "").strip()

    if not (1 <= mes <= 12):
        return Response({"detail": "Parámetro 'mes' inválido."}, status=400)

    inicio, fin = _rango_mes(año, mes)
    filtro_agencia = _filtro_por_agencia(agencia)

    base = (
        ExpedienteDigital.objects
        .filter(creado__gte=inicio, creado__lt=fin)
        .filter(filtro_agencia)
        .exclude(asesor_digital__in=["", None])
    )

    grupos_lead = list(
        base
        .values("asesor_digital")
        .annotate(total=Count("id"))
        .order_by("-total", "asesor_digital")
    )

    filas_canal = list(
        base
        .values("asesor_digital", "canal_contacto")
        .annotate(total=Count("id"))
        .order_by("asesor_digital", "canal_contacto")
    )

    catalogo = {str(a.nombre or "").strip().casefold(): a for a in Asesor.objects.all() if a.nombre and str(a.nombre).strip()}

    conteos = {}
    for fila in filas_canal:
        nombre = str(fila["asesor_digital"] or "").strip()
        canal = _canal_normalizado(fila["canal_contacto"])
        clave = (nombre.casefold(), canal)
        conteos[clave] = conteos.get(clave, 0) + int(fila["total"] or 0)

    totales_por_canal = {c["id"]: 0 for c in CANALES}

    asesores = []
    for grupo in grupos_lead:
        nombre = str(grupo["asesor_digital"] or "").strip()
        if _es_asesor_excluido(nombre):
            continue
        total = int(grupo["total"] or 0)
        clave_nombre = nombre.casefold()
        catalogo_asesor = catalogo.get(clave_nombre)

        canales = []
        for canal_info in CANALES:
            canal_id = canal_info["id"]
            cantidad = conteos.get((clave_nombre, canal_id), 0)
            porcentaje = round((cantidad / total) * 100) if total > 0 else 0
            totales_por_canal[canal_id] += cantidad
            canales.append({
                "id": canal_id,
                "nombre": canal_info["nombre"],
                "total": cantidad,
                "porcentaje": porcentaje,
            })

        asesores.append({
            "nombre": nombre,
            "iniciales": _iniciales(nombre),
            "puesto": (catalogo_asesor.area if catalogo_asesor and catalogo_asesor.area else ""),
            "tipo_asesor": (catalogo_asesor.tipo_asesor if catalogo_asesor and catalogo_asesor.tipo_asesor else ""),
            "agencia_catalogo": (catalogo_asesor.agencia if catalogo_asesor and catalogo_asesor.agencia else ""),
            "activo": bool(catalogo_asesor.activo) if catalogo_asesor else True,
            "total_leads": total,
            "canales": canales,
        })

    total_leads_asesores = sum(a["total_leads"] for a in asesores)
    canales_totales = [
        {
            "id": c["id"],
            "nombre": c["nombre"],
            "total": totales_por_canal[c["id"]],
            "porcentaje": round((totales_por_canal[c["id"]] / total_leads_asesores) * 100) if total_leads_asesores > 0 else 0,
        }
        for c in CANALES
    ]

    return Response({
        "asesores": asesores,
        "canales_totales": canales_totales,
        "total_leads": total_leads_asesores,
        "total_asesores": len(asesores),
        "rango": {
            "inicio": inicio.isoformat(),
            "fin": fin.isoformat(),
            "anio": año,
            "mes": mes,
        },
    })