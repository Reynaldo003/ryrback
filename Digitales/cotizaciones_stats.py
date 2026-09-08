# Digitales/cotizaciones_stats.py
import logging
from datetime import date

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from CrmConformidad.jwt_authentication import CRMJWTAuthentication
from citas.models import Cita

from .models import ExpedienteDigital
from .prospectos_stats import _filtro_por_agencia, _mes_anterior, _parse_int, _rango_mes

logger = logging.getLogger(__name__)

ESTADOS_TERMINADOS = {"descalificado", "descalificada", "no show", "no asistió", "no asistio", "facturado", "entregado"}


def _porcentaje(parte, total):
    if not total:
        return 0.0
    return round((parte / total) * 100, 1)


@api_view(["GET"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def cotizaciones_stats_view(request):
    año = _parse_int(request.query_params, "anio", None) or _parse_int(request.query_params, "year", date.today().year)
    mes = _parse_int(request.query_params, "mes", None) or _parse_int(request.query_params, "month", date.today().month)
    agencia = str(request.query_params.get("agencia", "") or "").strip()
    meta = request.query_params.get("meta", "")
    limite_modelos = _parse_int(request.query_params, "limite_modelos", 6) or 6

    if not (1 <= mes <= 12):
        return Response({"detail": "Parámetro 'mes' inválido."}, status=400)

    inicio, fin = _rango_mes(año, mes)
    filtro_agencia = _filtro_por_agencia(agencia)

    anio_prev, mes_prev = _mes_anterior(año, mes)
    inicio_prev, fin_prev = _rango_mes(anio_prev, mes_prev)

    def base_activa(d_inicio, d_fin):
        queryset = (
            ExpedienteDigital.objects
            .filter(creado__gte=d_inicio, creado__lt=d_fin)
            .filter(filtro_agencia)
            .filter(Q(id_cotizacion__gt="") | Q(cotizacion_pendiente=True))
        )
        terminados = [estado for estado in ESTADOS_TERMINADOS]
        query_terminado = Q()
        for estado in terminados:
            query_terminado |= Q(estado__iexact=estado)
        return queryset.exclude(query_terminado)

    total_actual = base_activa(inicio, fin).count()
    total_anterior = base_activa(inicio_prev, fin_prev).count()

    if total_anterior > 0:
        variacion = round(((total_actual - total_anterior) / total_anterior) * 100, 1)
    else:
        variacion = None

    valor_acumulado = (
        base_activa(inicio, fin)
        .aggregate(total=Sum("presupuesto_mensual"))
        .get("total") or 0
    )

    # Citas realizadas (atendidas) en el periodo y cuántas generaron cotización
    citas_realizadas = (
        Cita.objects
        .filter(fecha_hora_cita__gte=inicio, fecha_hora_cita__lt=fin)
        .filter(filtro_agencia)
        .filter(asistencia=True)
        .count()
    )
    citas_con_cotizacion = (
        Cita.objects
        .filter(fecha_hora_cita__gte=inicio, fecha_hora_cita__lt=fin)
        .filter(filtro_agencia)
        .filter(asistencia=True)
        .filter(cliente__expediente_digital__id_cotizacion__gt="")
        .count()
    )
    efectividad = _porcentaje(citas_con_cotizacion, citas_realizadas)

    # Meta mensual (param auto) -> avance
    meta_valor = None
    avance_meta = None
    if meta:
        try:
            meta_valor = float(meta)
        except (TypeError, ValueError):
            meta_valor = None
    if meta_valor:
        avance_meta = round((total_actual / meta_valor) * 100, 1)

    # Desglose por modelo
    filas_modelo = list(
        base_activa(inicio, fin)
        .exclude(auto_interes__in=["", None])
        .values("auto_interes")
        .annotate(total=Count("id"))
        .order_by("-total", "auto_interes")
    )
    otros_total = 0
    modelos = []
    for i, fila in enumerate(filas_modelo):
        if i < limite_modelos:
            modelos.append({
                "modelo": str(fila["auto_interes"] or "").strip(),
                "total": int(fila["total"] or 0),
                "porcentaje": _porcentaje(int(fila["total"] or 0), total_actual),
            })
        else:
            otros_total += int(fila["total"] or 0)
    if otros_total > 0:
        modelos.append({
            "modelo": "Otros modelos",
            "total": otros_total,
            "porcentaje": _porcentaje(otros_total, total_actual),
        })

    # Ritmo de cotización por día (creado del expediente)
    filas_ritmo = list(
        base_activa(inicio, fin)
        .annotate(dia=TruncDate("creado"))
        .values("dia")
        .annotate(total=Count("id"))
        .order_by("dia")
    )
    ritmo = [
        {
            "dia": fila["dia"].strftime("%Y-%m-%d") if fila["dia"] else "",
            "dia_mes": fila["dia"].day if fila["dia"] else 0,
            "total": int(fila["total"] or 0),
        }
        for fila in filas_ritmo
    ]

    return Response({
        "cotizaciones_activas": total_actual,
        "variacion": variacion,
        "valor_acumulado": valor_acumulado,
        "efectividad": {
            "porcentaje": efectividad,
            "citas_con_cotizacion": citas_con_cotizacion,
            "citas_realizadas": citas_realizadas,
        },
        "meta": {
            "definida": meta_valor is not None,
            "valor": meta_valor,
            "avance": avance_meta,
        },
        "modelos": modelos,
        "ritmo": ritmo,
        "rango": {
            "inicio": inicio.isoformat(),
            "fin": fin.isoformat(),
            "anio": año,
            "mes": mes,
        },
    })