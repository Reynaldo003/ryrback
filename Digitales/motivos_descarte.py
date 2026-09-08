# Digitales/motivos_descarte.py
import logging
from datetime import date

from django.db.models import Count, Q
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from CrmConformidad.jwt_authentication import CRMJWTAuthentication

from .models import ExpedienteDigital
from .prospectos_stats import _filtro_por_agencia, _parse_int, _rango_mes

logger = logging.getLogger(__name__)


def _porcentaje(parte, total):
    if not total:
        return 0.0
    return round((parte / total) * 100, 1)


@api_view(["GET"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def motivos_descarte_view(request):
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
        .filter(
            Q(estado__iexact="Descalificado")
            | Q(estado__icontains="descalificad")
        )
        .exclude(motivo_descalificacion__in=["", None])
    )

    total_descalificados = base.count()

    filas = list(
        base
        .values("motivo_descalificacion")
        .annotate(total=Count("id"))
        .order_by("-total", "motivo_descalificacion")
    )

    motivos = [
        {
            "motivo": str(fila["motivo_descalificacion"] or "").strip() or "Sin motivo",
            "total": int(fila["total"] or 0),
            "porcentaje": _porcentaje(int(fila["total"] or 0), total_descalificados),
        }
        for fila in filas
    ]

    return Response({
        "motivos": motivos,
        "total_descalificados": total_descalificados,
        "rango": {
            "inicio": inicio.isoformat(),
            "fin": fin.isoformat(),
            "anio": año,
            "mes": mes,
        },
    })