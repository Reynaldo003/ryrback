# Digitales/negocio_stats.py
import calendar
import math
from datetime import date
from statistics import mean, median

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from CrmConformidad.jwt_authentication import CRMJWTAuthentication

from .lineas_negocio import _canal_normalizado
from .models import ExpedienteDigital, MensajeWhatsApp
from .prospectos_stats import _filtro_por_agencia, _mes_anterior, _parse_int, _rango_mes


CANALES = {
    "whatsapp": "WhatsApp",
    "vw_direct": "VW Concesionaria/VW",
    "facebook": "Facebook Ads",
    "llamada": "Llamada entrante",
    "sin_clasificar": "Sin clasificar",
}

CAMPOS_COHORTE = (
    "id",
    "canal_contacto",
    "asesor_digital",
    "estado",
    "primer_mensaje_cliente",
    "primer_contacto_asesor",
    "ultima_cita_id",
    "ultima_cita_agendada",
    "asistencia",
    "id_cotizacion",
    "cotizacion_pendiente",
    "folio_solicitud_credito",
    "solicitud_credito_estado",
    "vin_facturado",
    "facturado_at",
    "vin_estatus_entrega",
    "auto_interes",
    "forma_pago",
    "plazo_compra",
    "business",
)


def _texto(valor):
    return str(valor or "").strip()


def _normaliza(valor):
    return _texto(valor).casefold()


def _porcentaje(parte, total):
    if not total:
        return 0.0
    return round((parte / total) * 100, 1)


def _percentil(valores, percentil):
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    indice = max(0, min(len(ordenados) - 1, math.ceil((percentil / 100) * len(ordenados)) - 1))
    return round(ordenados[indice], 1)


def _es_descalificado(fila):
    return "descalificad" in _normaliza(fila.get("estado"))


def _tiene_cita(fila):
    return bool(fila.get("ultima_cita_id") or fila.get("ultima_cita_agendada"))


def _tiene_cotizacion(fila):
    return bool(_texto(fila.get("id_cotizacion")))


def _tiene_solicitud(fila):
    return bool(_texto(fila.get("folio_solicitud_credito")))


def _es_aprobada(fila):
    return _normaliza(fila.get("solicitud_credito_estado")) in {"autorizado", "autorizada", "aprobado", "aprobada", "preaprobado", "preaprobada"}


def _es_rechazada(fila):
    return _normaliza(fila.get("solicitud_credito_estado")) in {"rechazado", "rechazada", "declinado", "declinada"}


def _es_facturado(fila):
    return bool(_texto(fila.get("vin_facturado")) or fila.get("facturado_at"))


def _es_entregado(fila):
    return _normaliza(fila.get("vin_estatus_entrega")) == "entregado"


def _perfil_completo(fila):
    return all(_texto(fila.get(campo)) for campo in ("auto_interes", "forma_pago", "plazo_compra"))


def _respuesta_minutos(fila):
    inicio = fila.get("primer_mensaje_cliente")
    fin = fila.get("primer_contacto_asesor")
    if not inicio or not fin or fin < inicio:
        return None
    return round((fin - inicio).total_seconds() / 60, 2)


def _acumular_grupo(grupo, fila):
    grupo["prospectos"] += 1
    grupo["descalificados"] += int(_es_descalificado(fila))
    grupo["citas"] += int(_tiene_cita(fila))
    grupo["citas_efectivas"] += int(bool(fila.get("asistencia")))
    grupo["cotizaciones"] += int(_tiene_cotizacion(fila))
    grupo["solicitudes"] += int(_tiene_solicitud(fila))
    grupo["facturados"] += int(_es_facturado(fila))


def _grupo_vacio(nombre=""):
    return {
        "nombre": nombre,
        "prospectos": 0,
        "descalificados": 0,
        "citas": 0,
        "citas_efectivas": 0,
        "cotizaciones": 0,
        "solicitudes": 0,
        "facturados": 0,
    }


def _cerrar_grupo(grupo):
    total = grupo["prospectos"]
    grupo["tasa_cita"] = _porcentaje(grupo["citas"], total)
    grupo["tasa_cotizacion"] = _porcentaje(grupo["cotizaciones"], total)
    grupo["tasa_facturacion"] = _porcentaje(grupo["facturados"], total)
    grupo["tasa_descarte"] = _porcentaje(grupo["descalificados"], total)
    return grupo


def _resumen_cohorte(filas, incluir_detalle=True):
    total = len(filas)
    contactados = 0
    descalificados = 0
    citas = 0
    citas_efectivas = 0
    cotizaciones = 0
    cotizaciones_pendientes = 0
    solicitudes = 0
    aprobadas = 0
    rechazadas = 0
    facturados = 0
    entregados = 0
    perfilados = 0
    mensajes_cliente = 0
    sin_respuesta = 0
    minutos_respuesta = []
    canales = {}
    asesores = {}

    calidad = {
        "sin_canal": 0,
        "sin_asesor": 0,
        "sin_modelo": 0,
        "sin_linea": 0,
        "perfil_incompleto": 0,
    }

    for fila in filas:
        tiene_contacto = bool(fila.get("primer_contacto_asesor"))
        tiene_mensaje = bool(fila.get("primer_mensaje_cliente"))
        descalificado = _es_descalificado(fila)
        tiene_cita = _tiene_cita(fila)
        efectiva = bool(fila.get("asistencia"))
        tiene_cotizacion = _tiene_cotizacion(fila)
        tiene_solicitud = _tiene_solicitud(fila)
        aprobada = _es_aprobada(fila)
        rechazada = _es_rechazada(fila)
        facturado = _es_facturado(fila)
        entregado = _es_entregado(fila)
        perfil_completo = _perfil_completo(fila)

        contactados += int(tiene_contacto)
        mensajes_cliente += int(tiene_mensaje)
        descalificados += int(descalificado)
        citas += int(tiene_cita)
        citas_efectivas += int(efectiva)
        cotizaciones += int(tiene_cotizacion)
        cotizaciones_pendientes += int(bool(fila.get("cotizacion_pendiente")) and not tiene_cotizacion)
        solicitudes += int(tiene_solicitud)
        aprobadas += int(aprobada)
        rechazadas += int(rechazada)
        facturados += int(facturado)
        entregados += int(entregado)
        perfilados += int(perfil_completo)

        if tiene_mensaje and not tiene_contacto:
            sin_respuesta += 1

        minutos = _respuesta_minutos(fila)
        if minutos is not None:
            minutos_respuesta.append(minutos)

        canal_id = _canal_normalizado(fila.get("canal_contacto"))
        canal = canales.setdefault(canal_id, _grupo_vacio(CANALES.get(canal_id, canal_id.replace("_", " ").title())))
        _acumular_grupo(canal, fila)

        asesor = _texto(fila.get("asesor_digital"))
        if asesor:
            grupo_asesor = asesores.setdefault(asesor, _grupo_vacio(asesor))
            _acumular_grupo(grupo_asesor, fila)

        calidad["sin_canal"] += int(not _texto(fila.get("canal_contacto")))
        calidad["sin_asesor"] += int(not asesor)
        calidad["sin_modelo"] += int(not _texto(fila.get("auto_interes")))
        calidad["sin_linea"] += int(not _texto(fila.get("business")))
        calidad["perfil_incompleto"] += int(not perfil_completo)

    respondidos = len(minutos_respuesta)
    sla_5 = sum(1 for valor in minutos_respuesta if valor <= 5)
    sla_15 = sum(1 for valor in minutos_respuesta if valor <= 15)
    sla_30 = sum(1 for valor in minutos_respuesta if valor <= 30)

    etapas = [
        {"id": "prospectos", "nombre": "Prospectos", "total": total},
        {"id": "contactados", "nombre": "Contactados", "total": contactados},
        {"id": "citas", "nombre": "Con cita", "total": citas},
        {"id": "citas_efectivas", "nombre": "Cita efectiva", "total": citas_efectivas},
        {"id": "cotizaciones", "nombre": "Cotizados", "total": cotizaciones},
        {"id": "solicitudes", "nombre": "Solicitud crédito", "total": solicitudes},
        {"id": "aprobadas", "nombre": "Crédito aprobado", "total": aprobadas},
        {"id": "facturados", "nombre": "Facturados", "total": facturados},
        {"id": "entregados", "nombre": "Entregados", "total": entregados},
    ]

    anterior = None
    for etapa in etapas:
        etapa["conversion_origen"] = _porcentaje(etapa["total"], total)
        etapa["conversion_anterior"] = 100.0 if anterior is None else _porcentaje(etapa["total"], anterior)
        anterior = etapa["total"]

    resultado = {
        "prospectos": total,
        "contactados": contactados,
        "descalificados": descalificados,
        "citas": citas,
        "citas_efectivas": citas_efectivas,
        "cotizaciones": cotizaciones,
        "cotizaciones_pendientes": cotizaciones_pendientes,
        "solicitudes": solicitudes,
        "aprobadas": aprobadas,
        "rechazadas": rechazadas,
        "facturados": facturados,
        "entregados": entregados,
        "perfilados": perfilados,
        "metricas": {
            "tasa_contacto": _porcentaje(contactados, total),
            "tasa_descarte": _porcentaje(descalificados, total),
            "tasa_cita": _porcentaje(citas, total),
            "tasa_asistencia": _porcentaje(citas_efectivas, citas),
            "tasa_cotizacion_sobre_efectivas": _porcentaje(cotizaciones, citas_efectivas),
            "tasa_solicitud_sobre_cotizacion": _porcentaje(solicitudes, cotizaciones),
            "tasa_aprobacion": _porcentaje(aprobadas, solicitudes),
            "tasa_facturacion": _porcentaje(facturados, total),
            "tasa_cierre_sobre_cotizacion": _porcentaje(facturados, cotizaciones),
            "tasa_entrega": _porcentaje(entregados, facturados),
            "tasa_perfilamiento": _porcentaje(perfilados, total),
        },
        "respuesta": {
            "con_mensaje_cliente": mensajes_cliente,
            "respondidos": respondidos,
            "sin_respuesta": sin_respuesta,
            "tasa_respuesta": _porcentaje(respondidos, mensajes_cliente),
            "promedio_min": round(mean(minutos_respuesta), 1) if minutos_respuesta else 0.0,
            "mediana_min": round(median(minutos_respuesta), 1) if minutos_respuesta else 0.0,
            "p90_min": _percentil(minutos_respuesta, 90),
            "sla_5": {"total": sla_5, "porcentaje": _porcentaje(sla_5, respondidos)},
            "sla_15": {"total": sla_15, "porcentaje": _porcentaje(sla_15, respondidos)},
            "sla_30": {"total": sla_30, "porcentaje": _porcentaje(sla_30, respondidos)},
        },
        "calidad": {
            **calidad,
            "perfil_completo": perfilados,
            "perfil_completo_pct": _porcentaje(perfilados, total),
            "asignacion_asesor_pct": _porcentaje(total - calidad["sin_asesor"], total),
            "canal_identificado_pct": _porcentaje(total - calidad["sin_canal"], total),
            "modelo_identificado_pct": _porcentaje(total - calidad["sin_modelo"], total),
        },
        "oportunidades": {
            "sin_respuesta": sin_respuesta,
            "cotizacion_pendiente": cotizaciones_pendientes,
            "solicitud_sin_resolver": sum(1 for fila in filas if _tiene_solicitud(fila) and not _texto(fila.get("solicitud_credito_estado"))),
            "aprobados_sin_facturar": sum(1 for fila in filas if _es_aprobada(fila) and not _es_facturado(fila)),
            "facturados_sin_entregar": sum(1 for fila in filas if _es_facturado(fila) and not _es_entregado(fila)),
        },
        "embudo": etapas,
    }

    if incluir_detalle:
        resultado["canales"] = sorted((_cerrar_grupo(item) for item in canales.values()), key=lambda item: (-item["facturados"], -item["tasa_facturacion"], -item["prospectos"], item["nombre"]))
        resultado["asesores"] = sorted((_cerrar_grupo(item) for item in asesores.values()), key=lambda item: (-item["facturados"], -item["tasa_facturacion"], -item["cotizaciones"], -item["prospectos"], item["nombre"]))

    return resultado


def _filas_cohorte(año, mes, agencia):
    inicio, fin = _rango_mes(año, mes)
    queryset = (
        ExpedienteDigital.objects
        .filter(creado__gte=inicio, creado__lt=fin)
        .filter(_filtro_por_agencia(agencia))
        .values(*CAMPOS_COHORTE)
    )
    return list(queryset), inicio, fin


def _ritmo_periodo(total, año, mes):
    hoy = date.today()
    dias_mes = calendar.monthrange(año, mes)[1]

    if (año, mes) < (hoy.year, hoy.month):
        dias_transcurridos = dias_mes
    elif (año, mes) == (hoy.year, hoy.month):
        dias_transcurridos = hoy.day
    else:
        dias_transcurridos = 0

    promedio_dia = round(total / dias_transcurridos, 2) if dias_transcurridos else 0.0
    proyeccion = round(promedio_dia * dias_mes) if dias_transcurridos and (año, mes) == (hoy.year, hoy.month) else total

    return {
        "dias_mes": dias_mes,
        "dias_transcurridos": dias_transcurridos,
        "prospectos_dia": promedio_dia,
        "proyeccion_cierre": proyeccion,
    }


@api_view(["GET"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def negocio_stats_view(request):
    año = _parse_int(request.query_params, "anio", None) or _parse_int(request.query_params, "year", date.today().year)
    mes = _parse_int(request.query_params, "mes", None) or _parse_int(request.query_params, "month", date.today().month)
    agencia = _texto(request.query_params.get("agencia", ""))

    if not (1 <= mes <= 12):
        return Response({"detail": "Parámetro 'mes' inválido."}, status=400)

    filas, inicio, fin = _filas_cohorte(año, mes, agencia)
    actual = _resumen_cohorte(filas, incluir_detalle=True)

    mensajes_ia = MensajeWhatsApp.objects.filter(created_at__gte=inicio, created_at__lt=fin, from_ia=True)
    if agencia:
        mensajes_ia = mensajes_ia.filter(cliente__expediente_digital__agencia__icontains=agencia)
    conversaciones_ia = mensajes_ia.filter(cliente__expediente_digital__isnull=False).values("cliente_id").distinct().count()

    año_prev, mes_prev = _mes_anterior(año, mes)
    filas_prev, _, _ = _filas_cohorte(año_prev, mes_prev, agencia)
    anterior = _resumen_cohorte(filas_prev, incluir_detalle=False)

    total_actual = actual["prospectos"]
    total_anterior = anterior["prospectos"]
    variacion_prospectos = round(((total_actual - total_anterior) / total_anterior) * 100, 1) if total_anterior else (100.0 if total_actual else 0.0)

    tasa_fact_actual = actual["metricas"]["tasa_facturacion"]
    tasa_fact_prev = anterior["metricas"]["tasa_facturacion"]
    mediana_actual = actual["respuesta"]["mediana_min"]
    mediana_prev = anterior["respuesta"]["mediana_min"]

    return Response({
        **actual,
        "ritmo": _ritmo_periodo(total_actual, año, mes),
        "actividad_periodo": {
            "conversaciones_ia": conversaciones_ia,
        },
        "comparativo": {
            "prospectos_anterior": total_anterior,
            "variacion_prospectos": variacion_prospectos,
            "tasa_facturacion_anterior": tasa_fact_prev,
            "variacion_tasa_facturacion_pp": round(tasa_fact_actual - tasa_fact_prev, 1),
            "mediana_respuesta_anterior_min": mediana_prev,
            "variacion_mediana_respuesta_min": round(mediana_actual - mediana_prev, 1),
        },
        "rango": {
            "inicio": inicio.isoformat(),
            "fin": fin.isoformat(),
            "anio": año,
            "mes": mes,
            "agencia": agencia,
        },
    })
