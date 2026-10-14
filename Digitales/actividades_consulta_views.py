"""Consulta de etapas comerciales V3 para el piloto.

Instalar en: Digitales/actividades_consulta_views.py
Ruta: GET /digitales/api/etapas-v3/expedientes/<expediente_id>/

- Solo lectura. No migra ni inicializa expedientes.
- Reutiliza el mismo control de JWT, whitelist, agencia y responsable del POST V3.
- Desactivado por defecto (CRM_ETAPAS_V3_API_HABILITADA=False).
- No expone el JSON `detalle` ni información privada del cliente.
"""

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from CrmConformidad.jwt_authentication import CRMJWTAuthentication
from .actividades_views import _autorizado, _usuario_en_piloto_o_general
from .models import ActividadComercialDigital, ExpedienteDigital


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
            {"codigo": "usuario_no_autorizado", "detalle": "Usuario fuera del piloto."},
            status=status.HTTP_403_FORBIDDEN,
        )

    expediente = (
        ExpedienteDigital.objects
        .only("id", "agencia", "usuario_crm_asignado", "etapa_comercial_v3")
        .filter(pk=expediente_id).first()
    )
    # No revelar a usuarios no autorizados si existe o no un expediente ajeno.
    if expediente is None or not _autorizado(request.user, expediente):
        return Response(
            {"codigo": "expediente_no_disponible", "detalle": "Expediente no disponible."},
            status=status.HTTP_404_NOT_FOUND,
        )

    actividades = (
        ActividadComercialDigital.objects
        .filter(expediente_id=expediente.pk)
        .order_by("-registrado_at", "-id")
        .values("id", "tipo", "origen", "cita_id", "fecha_actividad", "registrado_at",
                "usuario_crm", "etapa_anterior", "etapa_resultante")[:30]
    )
    historial = [
        {
            "id": item["id"],
            "tipo": item["tipo"],
            "origen": item["origen"],
            "cita_id": item["cita_id"],
            "fecha_actividad": item["fecha_actividad"].isoformat() if item["fecha_actividad"] else None,
            "registrado_at": item["registrado_at"].isoformat() if item["registrado_at"] else None,
            "usuario_crm": item["usuario_crm"],
            "etapa_anterior": item["etapa_anterior"] or None,
            "etapa_resultante": item["etapa_resultante"] or None,
        }
        for item in actividades
    ]
    cita_vinculada_id = next(
        (item["cita_id"] for item in historial if item["tipo"] == "cita_agendada" and item["cita_id"]),
        None,
    )

    recordatorio = None
    if expediente.etapa_comercial_v3 == "compra_futura":
        registro = (ActividadComercialDigital.objects
                    .filter(expediente_id=expediente.pk, tipo="compra_futura")
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
        datos_perdida = ((registro_perdido or {}).get("detalle") or {}).get("datos") or {}
        if isinstance(datos_perdida, dict):
            perdida = {
                "motivo": datos_perdida.get("motivo"),
                "etiqueta": datos_perdida.get("motivo_etiqueta"),
                "detalle": datos_perdida.get("detalle_motivo"),
            }

    return Response({
        "motivo_lead_perdido": perdida,
        "recordatorio_compra_futura": recordatorio,
        "cita_vinculada_id": cita_vinculada_id,
        "expediente_id": expediente.pk,
        "iniciado": expediente.etapa_comercial_v3 is not None,
        "etapa_comercial_v3": expediente.etapa_comercial_v3,
        "actividades": historial,
    })
