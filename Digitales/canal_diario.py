# Digitales/canal_diario.py
import calendar
import logging
from datetime import date

from django.db.models import Count
from django.db.models.functions import TruncDate
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from CrmConformidad.jwt_authentication import CRMJWTAuthentication

from .lineas_negocio import _canal_normalizado
from .models import ExpedienteDigital
from .prospectos_stats import _filtro_por_agencia, _parse_int, _rango_mes

logger = logging.getLogger(__name__)

CANALES = [
    {"id": "whatsapp", "nombre": "WhatsApp"},
    {"id": "vw_direct", "nombre": "VW Concesionaria/VW"},
    {"id": "facebook", "nombre": "Facebook Ads"},
    {"id": "llamada", "nombre": "Llamada entrante"},
]


@api_view(["GET"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def canal_diario_view(request):
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
    )

    filas = list(
        base
        .annotate(fecha=TruncDate("creado"))
        .values("fecha", "canal_contacto")
        .annotate(total=Count("id"))
    )

    acumulado = {}
    totales = {c["id"]: 0 for c in CANALES}
    total_general = 0
    for fila in filas:
        if not fila.get("fecha"):
            continue
        canal = _canal_normalizado(fila.get("canal_contacto"))
        if canal not in totales:
            continue
        dia = fila["fecha"].day
        total = int(fila["total"] or 0)
        acumulado[(dia, canal)] = acumulado.get((dia, canal), 0) + total
        totales[canal] += total
        total_general += total

    items = []
    for dia in range(1, calendar.monthrange(año, mes)[1] + 1):
        suma = sum(acumulado.get((dia, c["id"]), 0) for c in CANALES)
        items.append({
            "dia": dia,
            "rotulo": f"{dia:02d}",
            "whatsapp": acumulado.get((dia, "whatsapp"), 0),
            "vw_direct": acumulado.get((dia, "vw_direct"), 0),
            "facebook": acumulado.get((dia, "facebook"), 0),
            "llamada": acumulado.get((dia, "llamada"), 0),
            "total": suma,
        })

    return Response({
        "items": items,
        "canales": CANALES,
        "totales": totales,
        "total": total_general,
        "rango": {
            "inicio": inicio.isoformat(),
            "fin": fin.isoformat(),
            "anio": año,
            "mes": mes,
        },
    })