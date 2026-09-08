# Digitales/solicitudes_stats.py
import logging
from datetime import date

from django.db.models import Q
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from CrmConformidad.jwt_authentication import CRMJWTAuthentication
from Financieros.models import SolicitudCredito

from .prospectos_stats import _filtro_por_agencia, _parse_int, _rango_mes

logger = logging.getLogger(__name__)

COLOR_ESTATUS = {
    "aprobadas": "#25D6A8",
    "en_dictamen": "#1555C7",
    "declinadas": "#E02424",
    "otros": "#94A3B8",
}
NOMBRES_ESTATUS = {
    "aprobadas": "Aprobadas",
    "en_dictamen": "En dictamen",
    "declinadas": "Declinadas",
    "otros": "Otros",
}
PALETA_FINANCIERAS = ["#1555C7", "#25D6A8", "#8A6DFF", "#F59E0B", "#0EA5E9", "#E02424", "#8430CE", "#10B981", "#EC4899", "#84CC16"]


def _grupo_financiamiento(estado):
    e = str(estado or "").strip().casefold()
    if not e:
        return "en_dictamen"
    declinadas = ("no autorizad", "rechaz", "declin", "denegad", "negad", "no aprobad", "no preaprob", "perdida", "cancelad")
    if any(k in e for k in declinadas):
        return "declinadas"
    aprobadas = ("autorizad", "aprobad", "preaprob", "ejercido", "condicionad")
    if any(k in e for k in aprobadas):
        return "aprobadas"
    dictamen = ("revisi", "analis", "validaci", "proceso", "estudio", "dictamen", "pendiente", "documentaci", "recopilaci", "recibid", "enviad")
    if any(k in e for k in dictamen):
        return "en_dictamen"
    return "otros"


def _formato_duracion(segundos):
    if segundos is None or segundos < 0:
        return "Sin datos"
    if segundos >= 86400:
        return f"{round(segundos / 86400, 1):g} días"
    if segundos >= 3600:
        return f"{round(segundos / 3600, 1):g} horas"
    if segundos >= 60:
        return f"{round(segundos / 60, 1):g} minutos"
    return f"{round(segundos, 0):g} segundos"


def _porcentaje(parte, total):
    if not total:
        return 0.0
    return round((parte / total) * 100, 1)


@api_view(["GET"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def solicitudes_financiamiento_view(request):
    año = _parse_int(request.query_params, "anio", None) or _parse_int(request.query_params, "year", date.today().year)
    mes = _parse_int(request.query_params, "mes", None) or _parse_int(request.query_params, "month", date.today().month)
    agencia = str(request.query_params.get("agencia", "") or "").strip()
    asesor = str(request.query_params.get("asesor", "") or "").strip()

    if not (1 <= mes <= 12):
        return Response({"detail": "Parámetro 'mes' inválido."}, status=400)

    inicio, fin = _rango_mes(año, mes)

    queryset = (
        SolicitudCredito.objects
        .filter(creado__gte=inicio, creado__lt=fin)
        .filter(_filtro_por_agencia(agencia))
    )
    if asesor:
        queryset = queryset.filter(asesor_ventas__icontains=asesor)

    filas = list(
        queryset.values(
            "id", "id_soli_cred", "estado_financiamiento", "producto_financiero", "creado", "fecha_respuesta"
        )
    )

    # Dedupe por folio: un folio cuenta una sola vez (se usa la fila más reciente).
    folios = {}
    orden = 0
    for fila in filas:
        folio = str(fila.get("id_soli_cred") or "").strip()
        clave = folio if folio else f"__pk__{fila['id']}"
        actual = folios.get(clave)
        if actual is None or fila["creado"] > actual["creado"]:
            fila["orden"] = orden
            orden += 1
            folios[clave] = fila
    unicos = list(folios.values())

    total_folios = len(unicos)

    contadores = {"aprobadas": 0, "en_dictamen": 0, "declinadas": 0, "otros": 0}
    financieras = {}
    resoluciones = []
    for fila in unicos:
        grupo = _grupo_financiamiento(fila.get("estado_financiamiento"))
        contadores[grupo] += 1

        financiera = str(fila.get("producto_financiero") or "").strip()
        financiera = financiera if financiera else "Sin financiera asignada"
        financieras[financiera] = financieras.get(financiera, 0) + 1

        creado = fila.get("creado")
        respuesta = fila.get("fecha_respuesta")
        if creado and respuesta and respuesta >= creado:
            resoluciones.append((respuesta - creado).total_seconds())

    if resoluciones:
        prom_seg = sum(resoluciones) / len(resoluciones)
        promedio = {
            "segundos": prom_seg,
            "texto": _formato_duracion(prom_seg),
            "solicitudes_resueltas": len(resoluciones),
        }
    else:
        promedio = {"segundos": None, "texto": "Sin datos", "solicitudes_resueltas": 0}

    estatus = []
    for grupo in ("aprobadas", "en_dictamen", "declinadas", "otros"):
        if grupo == "otros" and contadores[grupo] == 0:
            continue
        estatus.append({
            "nombre": NOMBRES_ESTATUS[grupo],
            "clave": grupo,
            "folios": contadores[grupo],
            "porcentaje": _porcentaje(contadores[grupo], total_folios),
            "color": COLOR_ESTATUS[grupo],
        })

    financieras_lista = [
        {"nombre": nombre, "folios": conteo, "porcentaje": _porcentaje(conteo, total_folios)}
        for nombre, conteo in sorted(financieras.items(), key=lambda x: -x[1])
    ]
    for i, financiera in enumerate(financieras_lista):
        financiera["color"] = PALETA_FINANCIERAS[i % len(PALETA_FINANCIERAS)]

    return Response({
        "total_folios": total_folios,
        "solicitudes_aprobadas": contadores["aprobadas"],
        "solicitudes_dictamen": contadores["en_dictamen"],
        "solicitudes_declinadas": contadores["declinadas"],
        "otros": contadores["otros"],
        "porcentaje_aprobacion": _porcentaje(contadores["aprobadas"], total_folios),
        "tasa_rechazo": _porcentaje(contadores["declinadas"], total_folios),
        "promedio_resolucion": promedio,
        "estatus": estatus,
        "financieras": financieras_lista,
        "rango": {
            "inicio": inicio.isoformat(),
            "fin": fin.isoformat(),
            "anio": año,
            "mes": mes,
        },
    })