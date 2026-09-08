# Digitales/facturados_stats.py
import logging
import re
from datetime import date

from django.db.models import Q, Sum
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from CrmConformidad.jwt_authentication import CRMJWTAuthentication
from retencion.models import OrdenServicioVentaVW

from .prospectos_stats import _parse_int, _rango_mes

logger = logging.getLogger(__name__)

_PATRON_VIN = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")


def _normaliza_provincia(valor):
    return str(valor or "").strip()


def _vin_valido(valor):
    v = str(valor or "").strip().upper()
    return bool(_PATRON_VIN.fullmatch(v))


def _porcentaje(parte, total):
    if not total:
        return 0.0
    return round((parte / total) * 100, 1)


@api_view(["GET"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def facturados_stats_view(request):
    año = _parse_int(request.query_params, "anio", None) or _parse_int(request.query_params, "year", date.today().year)
    mes = _parse_int(request.query_params, "mes", None) or _parse_int(request.query_params, "month", date.today().month)
    agencia = str(request.query_params.get("agencia", "") or "").strip()

    if not (1 <= mes <= 12):
        return Response({"detail": "Parámetro 'mes' inválido."}, status=400)

    inicio, fin = _rango_mes(año, mes)

    query = Q(fecha_venta__gte=inicio, fecha_venta__lt=fin)
    if agencia:
        query &= Q(agencia_venta__icontains=agencia)

    # Factura válida: nota con importe > 0 (excluye nulos/anuladas).
    filas = list(
        OrdenServicioVentaVW.objects
        .filter(query)
        .exclude(total_nota=None)
        .filter(total_nota__gt=0)
        .values("vin", "agencia_venta", "fecha_venta", "numero_nota", "total_nota", "modelo_nombre", "segmento", "marca")
    )

    total_unidades = len(filas)
    importe_total = sum(float(f["total_nota"] or 0) for f in filas)

    # Meta / base configurables (no hay modelo de configuración aún)
    raw_meta = request.query_params.get("meta", "").strip()
    meta_valor = None
    if raw_meta:
        try:
            meta_valor = float(raw_meta)
        except (TypeError, ValueError):
            meta_valor = None
    base = _parse_int(request.query_params, "base", 0) or 0
    incluir_base = str(request.query_params.get("incluir_base", "") or "").strip().lower() in ("1", "true", "si", "yes")

    base_contribuyente = base if incluir_base else 0
    cumplimiento = None
    unidades_restantes = None
    meta_cumplida = False
    if meta_valor and meta_valor > 0:
        cumplimiento = round(((total_unidades + base_contribuyente) / meta_valor) * 100, 1)
        unidades_restantes = max(meta_valor - total_unidades - base_contribuyente, 0)
        meta_cumplida = (total_unidades + base_contribuyente) >= meta_valor

    # VIN validado en unidades facturadas
    validados = sum(1 for f in filas if _vin_valido(f.get("vin")))
    pendientes_vin = total_unidades - validados
    porcentaje_vin = _porcentaje(validados, total_unidades)

    # Segmentos -> modelos
    por_segmento = {}
    for f in filas:
        seg = _normaliza_provincia(f.get("segmento")) or "Sin clasificar"
        modelo = _normaliza_provincia(f.get("modelo_nombre")) or "Sin modelo"
        grupo = por_segmento.setdefault(seg, {"unidades": 0, "modelos": {}})
        grupo["unidades"] += 1
        grupo["modelos"][modelo] = grupo["modelos"].get(modelo, 0) + 1

    # Entregas: unidades con fecha de salida dentro del periodo
    query_entrega = Q(fecha_salida__gte=inicio, fecha_salida__lt=fin)
    if agencia:
        query_entrega &= Q(agencia_venta__icontains=agencia)
    unidades_entregadas = (
        OrdenServicioVentaVW.objects
        .filter(query_entrega)
        .exclude(total_nota=None)
        .filter(total_nota__gt=0)
        .count()
    )

    segmentos = []
    for nombre, grupo in por_segmento.items():
        modelos = [
            {"modelo": m, "unidades": u, "porcentaje": _porcentaje(u, grupo["unidades"])}
            for m, u in sorted(grupo["modelos"].items(), key=lambda x: (-x[1], x[0].casefold()))
        ]
        segmentos.append({
            "segmento": nombre,
            "unidades": grupo["unidades"],
            "porcentaje": _porcentaje(grupo["unidades"], total_unidades),
            "modelos": modelos,
        })
    segmentos.sort(key=lambda s: (-s["unidades"], s["segmento"].casefold()))

    return Response({
        "unidades_facturadas": total_unidades,
        "unidades_entregadas": unidades_entregadas,
        "importe_facturado": importe_total,
        "meta": {
            "definida": meta_valor is not None,
            "valor": meta_valor,
            "base": base,
            "incluir_base": incluir_base,
        },
        "cumplimiento": cumplimiento,
        "unidades_restantes": unidades_restantes,
        "meta_cumplida": meta_cumplida,
        "vin": {
            "validados": validados,
            "pendientes": pendientes_vin,
            "porcentaje": porcentaje_vin,
            "estado": "validado" if pendientes_vin == 0 and total_unidades > 0 else "pendiente",
        },
        "segmentos": segmentos,
        "rango": {
            "inicio": inicio.isoformat(),
            "fin": fin.isoformat(),
            "anio": año,
            "mes": mes,
        },
    })