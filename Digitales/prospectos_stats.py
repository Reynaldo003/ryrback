#Digitales/prospectos_stats.py
import logging
from datetime import date

from django.db.models import Count, Q
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from CrmConformidad.jwt_authentication import CRMJWTAuthentication
from citas.models import Cita

from .models import ExpedienteDigital, MensajeWhatsApp

logger = logging.getLogger(__name__)

ESTADOS_DESCALIFICADO = ("descalificado", "descalificada")


def _normaliza(valor):
    return str(valor or "").strip().casefold()


def _parse_int(query_params, nombre, default):
    try:
        return int(query_params.get(nombre, default))
    except (TypeError, ValueError):
        return default


def _rango_mes(año, mes):
    inicio = date(year=año, month=mes, day=1)
    if mes == 12:
        fin = date(year=año + 1, month=1, day=1)
    else:
        fin = date(year=año, month=mes + 1, day=1)
    return inicio, fin


def _mes_anterior(año, mes):
    if mes == 1:
        return año - 1, 12
    return año, mes - 1


def _filtro_por_agencia(agencia):
    if not agencia:
        return Q()
    return Q(agencia__iexact=agencia)


def _motivo_principal_descalificacion(año, mes, agencia):
    filtro_agencia = _filtro_por_agencia(agencia)
    motivo = (
        ExpedienteDigital.objects
        .filter(creado__year=año, creado__month=mes)
        .filter(filtro_agencia)
        .exclude(estado__in=("", None))
        .filter(
            Q(estado__iexact="Descalificado")
            | Q(estado__icontains="descalificad")
        )
        .exclude(motivo_descalificacion__in=("", None))
        .values("motivo_descalificacion")
        .annotate(total=Count("id"))
        .order_by("-total", "motivo_descalificacion")
        .first()
    )
    return (motivo["motivo_descalificacion"] if motivo else ""), int(motivo["total"] if motivo else 0)


@api_view(["GET"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def prospecto_stats_view(request):
    año = _parse_int(request.query_params, "anio", None) or _parse_int(request.query_params, "year", date.today().year)
    mes = _parse_int(request.query_params, "mes", None) or _parse_int(request.query_params, "month", date.today().month)
    agencia = str(request.query_params.get("agencia", "") or "").strip()

    if not (1 <= mes <= 12):
        return Response({"detail": "Parámetro 'mes' inválido."}, status=400)

    inicio, fin = _rango_mes(año, mes)
    filtro_agencia = _filtro_por_agencia(agencia)

    # Prospectos creados en el periodo
    total_prospectos = (
        ExpedienteDigital.objects
        .filter(creado__gte=inicio, creado__lt=fin)
        .filter(filtro_agencia)
        .count()
    )

    # Rango del mes inmediatamente anterior para calcular crecimiento
    anio_prev, mes_prev = _mes_anterior(año, mes)
    inicio_prev, fin_prev = _rango_mes(anio_prev, mes_prev)
    total_prev = (
        ExpedienteDigital.objects
        .filter(creado__gte=inicio_prev, creado__lt=fin_prev)
        .filter(filtro_agencia)
        .count()
    )

    if total_prev > 0:
        crecimiento = round(((total_prospectos - total_prev) / total_prev) * 100, 1)
    else:
        crecimiento = 100.0 if total_prospectos > 0 else 0.0

    # Descalificados
    total_descalificados = (
        ExpedienteDigital.objects
        .filter(creado__gte=inicio, creado__lt=fin)
        .filter(filtro_agencia)
        .filter(
            Q(estado__iexact="Descalificado")
            | Q(estado__icontains="descalificad")
        )
        .count()
    )
    motivo_principal, motivo_total = _motivo_principal_descalificacion(año, mes, agencia)

    # Conversaciones inteligentes (conversaciones del bot): clientes únicos
    # con al menos un mensaje generado por IA en el periodo.
    mensajes_ia = MensajeWhatsApp.objects.filter(
        created_at__gte=inicio,
        created_at__lt=fin,
        from_ia=True,
    )
    if agencia:
        mensajes_ia = mensajes_ia.filter(
            cliente__expediente_digital__agencia__iexact=agencia,
        )
    total_conv_inteligentes = (
        mensajes_ia
        .filter(cliente__expediente_digital__isnull=False)
        .values("cliente_id")
        .distinct()
        .count()
    )

    # Citas concertadas (fecha_hora_cita dentro del periodo)
    citas_concertadas = (
        Cita.objects
        .filter(fecha_hora_cita__gte=inicio, fecha_hora_cita__lt=fin)
        .filter(filtro_agencia)
        .count()
    )

    # Citas efectivas (asistencia True)
    citas_efectivas = (
        Cita.objects
        .filter(fecha_hora_cita__gte=inicio, fecha_hora_cita__lt=fin)
        .filter(filtro_agencia)
        .filter(asistencia=True)
        .count()
    )

    # Conversión total: prospectos -> citas concertadas
    conversion_total = round((citas_concertadas / total_prospectos) * 100, 1) if total_prospectos > 0 else 0.0

    return Response({
        "prospectos": {
            "total": total_prospectos,
            "crecimiento": crecimiento,
        },
        "descalificados": {
            "total": total_descalificados,
            "motivo_principal": motivo_principal,
            "motivo_total": motivo_total,
        },
        "conversiones_inteligentes": total_conv_inteligentes,
        "citas_concertadas": citas_concertadas,
        "citas_efectivas": citas_efectivas,
        "conversion_total": conversion_total,
    })