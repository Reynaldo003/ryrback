# Digitales/pautas_origen.py
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

NOMBRE_SIN_PAUTA = "Sin pauta identificada"


def _canal_normalizado(canal):
    valor = str(canal or "").strip().casefold()
    if valor == "whatsapp" or valor == "wa":
        return "WhatsApp"
    if valor == "facebook" or valor == "meta" or valor == "facebook ads":
        return "Facebook Ads"
    if not valor:
        return "Sin canal"
    return "VW Concesionaria/VW Direct"


def _porcentaje(parte, total):
    if not total:
        return 0.0
    return round((parte / total) * 100, 1)


@api_view(["GET"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def pautas_origen_view(request):
    año = _parse_int(request.query_params, "anio", None) or _parse_int(request.query_params, "year", date.today().year)
    mes = _parse_int(request.query_params, "mes", None) or _parse_int(request.query_params, "month", date.today().month)
    agencia = str(request.query_params.get("agencia", "") or "").strip()
    limite = _parse_int(request.query_params, "limite", None)

    if not (1 <= mes <= 12):
        return Response({"detail": "Parámetro 'mes' inválido."}, status=400)

    inicio, fin = _rango_mes(año, mes)
    filtro_agencia = _filtro_por_agencia(agencia)

    base = (
        ExpedienteDigital.objects
        .filter(creado__gte=inicio, creado__lt=fin)
        .filter(filtro_agencia)
    )

    filas = list(
        base
        .values("pauta", "canal_contacto")
        .annotate(total=Count("id"))
        .order_by("-total", "pauta")
    )

    total_pautas = 0
    acumulado = {}
    for fila in filas:
        nombre = str(fila["pauta"] or "").strip() or NOMBRE_SIN_PAUTA
        total_pautas += int(fila["total"] or 0)
        clave = (nombre, _canal_normalizado(fila["canal_contacto"]))
        acumulado[clave] = acumulado.get(clave, 0) + int(fila["total"] or 0)

    por_pauta = {}
    for (nombre, canal), total in acumulado.items():
        if nombre not in por_pauta:
            por_pauta[nombre] = {"nombre": nombre, "total": 0, "canal": canal}
        por_pauta[nombre]["total"] += total

    pautas = sorted(por_pauta.values(), key=lambda x: -x["total"])
    if limite and limite > 0:
        pautas = pautas[:limite]

    for pauta in pautas:
        pauta["porcentaje"] = _porcentaje(pauta["total"], total_pautas)

    return Response({
        "pautas": pautas,
        "total_leads_con_pauta": total_pautas,
        "total_pautas": len(por_pauta),
        "rango": {
            "inicio": inicio.isoformat(),
            "fin": fin.isoformat(),
            "anio": año,
            "mes": mes,
        },
    })