# Digitales/citas_stats.py
import logging
from datetime import date

from django.db.models import Q
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from CrmConformidad.jwt_authentication import CRMJWTAuthentication
from citas.models import Cita

from .prospectos_stats import (
    _filtro_por_agencia,
    _parse_int,
    _rango_mes,
)

logger = logging.getLogger(__name__)


def _porcentaje(parte, total):
    if not total:
        return 0.0

    return round((parte / total) * 100, 1)


def _filtro_cita_digital():
    return (
        Q(tipo_cita__iexact="Digital")
        | Q(tipo_cita__iexact="Digitales")
    )


@api_view(["GET"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def citas_stats_view(request):
    año = (
        _parse_int(request.query_params, "anio", None)
        or _parse_int(
            request.query_params,
            "year",
            date.today().year,
        )
    )

    mes = (
        _parse_int(request.query_params, "mes", None)
        or _parse_int(
            request.query_params,
            "month",
            date.today().month,
        )
    )

    agencia = str(
        request.query_params.get("agencia", "") or ""
    ).strip()

    if not (1 <= mes <= 12):
        return Response(
            {"detail": "Parámetro 'mes' inválido."},
            status=400,
        )

    inicio, fin = _rango_mes(año, mes)
    filtro_agencia = _filtro_por_agencia(agencia)

    # IMPORTANTE:
    # El periodo se determina por la fecha en que la cita
    # fue creada en el CRM, NO por la fecha programada.
    #
    # Además, solamente se consideran citas digitales.
    base = (
        Cita.objects
        .filter(
            creado_en__gte=inicio,
            creado_en__lt=fin,
        )
        .filter(filtro_agencia)
        .filter(_filtro_cita_digital())
    )

    concertadas = base.count()

    efectivas = (
        base
        .filter(asistencia=True)
        .count()
    )

    pendientes = concertadas - efectivas

    tasa_asistencia = _porcentaje(
        efectivas,
        concertadas,
    )

    return Response({
        "citas_concertadas": concertadas,
        "citas_efectivas": efectivas,
        "citas_pendientes": pendientes,
        "tasa_asistencia": tasa_asistencia,
        "rango": {
            "inicio": inicio.isoformat(),
            "fin": fin.isoformat(),
            "anio": año,
            "mes": mes,
        },
    })