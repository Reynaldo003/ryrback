"""Consulta de etapas comerciales V3 para el piloto.

Instalar en: Digitales/actividades_consulta_views.py
Ruta: GET /digitales/api/etapas-v3/expedientes/<expediente_id>/

- Solo lectura. No migra ni inicializa expedientes.
- Reutiliza permisos efectivos, control de agencia y responsable del POST V3.
- Desactivado por defecto (CRM_ETAPAS_V3_API_HABILITADA=False).
- No expone el JSON `detalle` ni información privada del cliente.
"""

from django.conf import settings
from django.utils import timezone
from zoneinfo import ZoneInfo
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from CrmConformidad.jwt_authentication import CRMJWTAuthentication
from .actividades_views import _autorizado, _usuario_en_piloto_o_general, _agencia_clave
from .models import ActividadComercialDigital, ExpedienteDigital
from .correcciones_views import puede_corregir_actividad, _tipo_corregible
from .clasificacion_historica_views import disponible_para_clasificacion
from citas.models import Cita


@api_view(["GET"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def disponibilidad_etapas_comerciales_v3_view(request):
    """Estado de V3 para el usuario autenticado; no consulta expedientes ni escribe."""
    if not getattr(settings, "CRM_ETAPAS_V3_API_HABILITADA", False):
        return Response({"codigo": "v3_desactivado"}, status=status.HTTP_404_NOT_FOUND)
    if not _usuario_en_piloto_o_general(request.user):
        return Response({"codigo": "usuario_no_autorizado"}, status=status.HTTP_403_FORBIDDEN)
    return Response({"habilitada": True}, status=status.HTTP_200_OK)


@api_view(["GET"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def consultar_etapas_comerciales_v3_view(request, expediente_id):
    """Retorna la etapa V3 y las últimas 30 actividades del expediente autorizado."""
    if not getattr(settings, "CRM_ETAPAS_V3_API_HABILITADA", False):
        return Response(
            {"codigo": "v3_desactivado", "detalle": "Función no habilitada."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if not _usuario_en_piloto_o_general(request.user):
        return Response(
            {"codigo": "usuario_no_autorizado", "detalle": "El usuario no tiene autorización para consultar etapas comerciales."},
            status=status.HTTP_403_FORBIDDEN,
        )

    expediente = (
        ExpedienteDigital.objects
        .only(
            "id", "cliente_id", "agencia", "asesor_digital", "usuario_crm_asignado",
            "etapa_comercial_v3", "ultima_cita_id", "estado", "creado", "vin_facturado",
        )
        .filter(pk=expediente_id).first()
    )
    # No revelar a usuarios no autorizados si existe o no un expediente ajeno.
    if expediente is None or not _autorizado(request.user, expediente):
        return Response(
            {"codigo": "expediente_no_disponible", "detalle": "Expediente no disponible."},
            status=status.HTTP_404_NOT_FOUND,
        )

    actividades = list(
        ActividadComercialDigital.objects
        .filter(expediente_id=expediente.pk)
        .order_by("-registrado_at", "-id")[:30]
    )
    originales = [a.pk for a in actividades if _tipo_corregible(a) is not None]
    # La actividad original no se modifica; exponer su versión efectiva a la UI.
    ultimas = {}
    for corregida in (ActividadComercialDigital.objects
                       .filter(corrige_a_id__in=originales, tipo="correccion")
                       .order_by("registrado_at", "id")):
        ultimas[corregida.corrige_a_id] = corregida

    historial = []
    for actividad in actividades:
        reciente = ultimas.get(actividad.pk)
        datos_originales = (actividad.detalle or {}).get("datos") or {}
        datos_efectivos = ((reciente.detalle or {}).get("datos_despues") if reciente else None)
        if not isinstance(datos_efectivos, dict):
            datos_efectivos = datos_originales if isinstance(datos_originales, dict) else {}
        tipo_corregible = _tipo_corregible(actividad)
        es_historico = actividad.tipo == "correccion" and (actividad.detalle or {}).get("evento") in {"homologacion_historica_v3", "clasificacion_historica_v3"}
        # Validar la cita antigua real antes de ofrecer el editor.
        cita_historica = None
        if es_historico and tipo_corregible == "cita_agendada" and expediente.ultima_cita_id:
            cita_historica = Cita.objects.filter(
                pk=expediente.ultima_cita_id, cliente_id=expediente.cliente_id,
            ).first()
            if cita_historica and _agencia_clave(cita_historica.agencia) != _agencia_clave(expediente.agencia):
                cita_historica = None
        puede_corregir = puede_corregir_actividad(request.user, actividad)
        if es_historico and expediente.etapa_comercial_v3 != actividad.etapa_resultante:
            puede_corregir = False
        if es_historico and tipo_corregible == "cita_agendada" and (
                cita_historica is None or cita_historica.asistencia
                or cita_historica.estado_asistencia not in (None, "pendiente")):
            puede_corregir = False
        clave_fecha = {"cotizacion_enviada": "fecha_envio", "documentos_recibidos": "fecha_recepcion",
                       "cita_asistida": "fecha_asistencia_real"}.get(tipo_corregible)
        if es_historico and (actividad.detalle or {}).get("evento") == "clasificacion_historica_v3":
            clave_fecha = {
                "en_seguimiento": "fecha_contacto",
                "cotizacion_enviada": "fecha_envio",
                "cita_asistida": "fecha_asistencia_real",
                "documentos_enviados": "fecha_recepcion",
                "autorizado_no_formalizado": "fecha_autorizacion",
            }.get(actividad.etapa_resultante)
        fecha_efectiva = (datos_efectivos.get(clave_fecha) if clave_fecha else None)
        valores_ui = {clave: datos_efectivos.get(clave) for clave in (
            "fecha_envio", "vehiculo", "referencia", "fecha_recepcion", "documentos",
            "fecha_hora_cita", "fecha_asistencia_real", "fecha_contacto", "fecha_autorizacion") if clave in datos_efectivos}
        if cita_historica and cita_historica.fecha_hora_cita and not reciente:
            fecha_cita = cita_historica.fecha_hora_cita
            zona = ZoneInfo(settings.TIME_ZONE)
            if timezone.is_naive(fecha_cita):
                fecha_cita = timezone.make_aware(fecha_cita, zona)
            valores_ui["fecha_hora_cita"] = fecha_cita.astimezone(zona).strftime("%Y-%m-%dT%H:%M")
        historial.append({
            "id": actividad.pk,
            "tipo": actividad.tipo,
            "origen": actividad.origen,
            "cita_id": actividad.cita_id,
            "fecha_actividad": (fecha_efectiva or (None if es_historico and reciente is None else
                (actividad.fecha_actividad.isoformat() if actividad.fecha_actividad else None))),
            "fecha_actividad_original": actividad.fecha_actividad.isoformat() if actividad.fecha_actividad else None,
            "registrado_at": actividad.registrado_at.isoformat() if actividad.registrado_at else None,
            "usuario_crm": actividad.usuario_crm,
            "etapa_anterior": actividad.etapa_anterior or None,
            "etapa_resultante": actividad.etapa_resultante or None,
            "datos_efectivos": valores_ui,
            "es_homologacion_historica": es_historico,
            "es_clasificacion_historica": (actividad.detalle or {}).get("evento") == "clasificacion_historica_v3",
            "tipo_correccion": tipo_corregible,
            "tiene_correccion": reciente is not None,
            "puede_corregir": puede_corregir,
        })
    homologacion_cita_historica = (
        expediente.etapa_comercial_v3 in {"cita_agendada", "documentos_enviados"}
        and ActividadComercialDigital.objects.filter(
            expediente_id=expediente.pk,
            tipo="correccion",
            etapa_resultante__in={"cita_agendada", "documentos_enviados"},
            detalle__evento__in=["homologacion_historica_v3", "clasificacion_historica_v3"],
        ).exists()
    )

    cita_vinculada_id = next(
        (
            item["cita_id"]
            for item in historial
            if item["tipo"] == "cita_agendada" and item["cita_id"]
        ),
        None,
    )

    # Recuperar una cita histórica únicamente si su identidad es válida.
    if (
        not cita_vinculada_id
        and homologacion_cita_historica
        and expediente.ultima_cita_id
    ):
        cita_historica = (
            Cita.objects
            .only("id", "cliente_id", "agencia")
            .filter(pk=expediente.ultima_cita_id)
            .first()
        )

        if (
            cita_historica is not None
            and cita_historica.cliente_id == expediente.cliente_id
            and _agencia_clave(cita_historica.agencia) == _agencia_clave(expediente.agencia)
            and bool((expediente.agencia or "").strip())
        ):
            cita_vinculada_id = cita_historica.pk

    recordatorio = None
    if expediente.etapa_comercial_v3 == "compra_futura":
        registro = (ActividadComercialDigital.objects
                    .filter(expediente_id=expediente.pk, tipo="compra_futura")
                    .order_by("-registrado_at", "-id")
                    .values("detalle").first())
        if not registro:
            registro = (ActividadComercialDigital.objects
                        .filter(expediente_id=expediente.pk, tipo="correccion",
                                etapa_resultante="compra_futura",
                                detalle__evento="clasificacion_historica_v3")
                        .order_by("-registrado_at", "-id")
                        .values("detalle").first())
        datos_compra = (registro or {}).get("detalle") or {}
        datos_compra = datos_compra.get("datos") or {}
        if isinstance(datos_compra, dict):
            recordatorio = {
                "fecha_prevista_compra": datos_compra.get("fecha_prevista_compra"),
                "proximo_contacto": datos_compra.get("proximo_contacto"),
                "observacion": datos_compra.get("observacion"),
            }

    perdida = None
    if expediente.etapa_comercial_v3 == "lead_perdido":
        registro_perdido = (ActividadComercialDigital.objects
                            .filter(expediente_id=expediente.pk, tipo="lead_perdido")
                            .order_by("-registrado_at", "-id")
                            .values("detalle").first())
        if not registro_perdido:
            registro_perdido = (ActividadComercialDigital.objects
                                .filter(expediente_id=expediente.pk, tipo="correccion",
                                        etapa_resultante="lead_perdido",
                                        detalle__evento="clasificacion_historica_v3")
                                .order_by("-registrado_at", "-id")
                                .values("detalle").first())
        datos_perdida = ((registro_perdido or {}).get("detalle") or {}).get("datos") or {}
        if isinstance(datos_perdida, dict):
            perdida = {
                "motivo": datos_perdida.get("motivo"),
                "etiqueta": datos_perdida.get("motivo_etiqueta"),
                "detalle": datos_perdida.get("detalle_motivo"),
            }

    # Mostrar citas verificadas del prospecto por fecha/sucursal;
    # el identificador solo viaja como referencia interna del selector.
    def agencia_key(texto):
        return _agencia_clave(texto)
    citas_disponibles = []
    if expediente.cliente_id and expediente.agencia:
        # Reutilizar la misma evidencia de vinculación que exige el POST.
        # No basta con que la cita pertenezca al mismo cliente y sucursal.
        citas_vinculadas_v3 = set(
            ActividadComercialDigital.objects.filter(
                expediente_id=expediente.pk,
                cita_id__isnull=False,
                detalle__evento="cita_registrada",
            ).values_list("cita_id", flat=True)
        )
        citas_candidatas = (Cita.objects.filter(cliente_id=expediente.cliente_id)
            .only("id", "agencia", "fecha_hora_cita", "asistencia", "estado_asistencia")
            .order_by("-fecha_hora_cita", "-id")[:100])
        for cita in citas_candidatas:
            if agencia_key(cita.agencia) != agencia_key(expediente.agencia) or not cita.fecha_hora_cita:
                continue
            fecha_cita = cita.fecha_hora_cita
            zona = ZoneInfo(settings.TIME_ZONE)
            if timezone.is_naive(fecha_cita):
                fecha_cita = timezone.make_aware(fecha_cita, zona)
            citas_disponibles.append({
                "id": cita.pk,
                "agencia": cita.agencia,
                "fecha_hora_cita": fecha_cita.astimezone(zona).strftime("%Y-%m-%dT%H:%M"),
                "asistencia": bool(cita.asistencia),
                "estado_asistencia": cita.estado_asistencia,
                "vinculada_v3": cita.pk in citas_vinculadas_v3,
                "vinculada_historica": bool(
                    homologacion_cita_historica and expediente.ultima_cita_id == cita.pk
                ),
            })

    return Response({
        "citas_disponibles": citas_disponibles,
        "motivo_lead_perdido": perdida,
        "recordatorio_compra_futura": recordatorio,
        "cita_vinculada_id": cita_vinculada_id,
        "expediente_id": expediente.pk,
        "iniciado": bool(expediente.etapa_comercial_v3),
        "clasificacion_historica": {
            "permitida": disponible_para_clasificacion(expediente),
            "estado_anterior": expediente.estado if not expediente.etapa_comercial_v3 else None,
            "agencia": expediente.agencia if not expediente.etapa_comercial_v3 else None,
        },
        "etapa_comercial_v3": expediente.etapa_comercial_v3,
        "actividades": historial,
        "homologacion_cita_historica": homologacion_cita_historica,
    })
