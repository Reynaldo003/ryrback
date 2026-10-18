"""Alta de cita desde Contacto y registro de etapa V3 en una misma transacción.

El frontend nunca elige cliente, asesor digital, dueño CRM ni etapa destino.
La cita, actividad, vínculo e información operativa se guardan juntos o
no se guarda nada. Disponible solo para usuarios comerciales autorizados.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from CrmConformidad.jwt_authentication import CRMJWTAuthentication
from citas.models import Cita
from citas.serializers import CitaSerializer
from .actividades_views import _autorizado, _usuario_en_piloto_o_general, _agencia_clave
from .actividades_service import ErrorActividadComercial, registrar_actividad_v3
from .models import ActividadComercialDigital, ExpedienteDigital

_IDEM = re.compile(r"^[A-Za-z0-9._:\-]{8,120}$")
logger = logging.getLogger(__name__)


class AltaCitaChatV3Serializer(serializers.Serializer):
    expediente_id = serializers.IntegerField(min_value=1)
    clave_idempotencia = serializers.CharField(max_length=120)
    fecha_hora_cita = serializers.DateTimeField()
    agencia = serializers.CharField(max_length=100)
    asesor_piso = serializers.CharField(max_length=160)
    comentarios = serializers.CharField(required=False, allow_blank=True, max_length=2000)

    def validate_clave_idempotencia(self, value):
        if not _IDEM.fullmatch(value):
            raise serializers.ValidationError("Clave de operación inválida.")
        return value


def _error(codigo, mensaje, http_status):
    return Response({"codigo": codigo, "detalle": mensaje}, status=http_status)


@api_view(["POST"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def agendar_cita_chat_v3_view(request):
    if not getattr(settings, "CRM_ETAPAS_V3_API_HABILITADA", False):
        return _error("v3_desactivado", "Las etapas comerciales no están habilitadas.", 404)
    usuario = request.user
    if not _usuario_en_piloto_o_general(usuario):
        return _error("usuario_no_autorizado", "No tienes permiso para gestionar etapas comerciales.", 403)

    # Rechazar cualquier metadato de identidad/propiedad enviado desde React.
    permitidos = {"expediente_id", "clave_idempotencia", "fecha_hora_cita",
                  "agencia", "asesor_piso", "comentarios"}
    if not isinstance(request.data, dict) or set(request.data) - permitidos:
        return _error("campos_no_permitidos", "Datos inesperados al agendar.", 400)
    formulario = AltaCitaChatV3Serializer(data=request.data)
    if not formulario.is_valid():
        return Response({"codigo": "validacion", "errores": formulario.errors}, status=400)
    datos = formulario.validated_data
    cuando = datos["fecha_hora_cita"]
    # timezone.now() es naive si USE_TZ=False y aware si USE_TZ=True.
    # Igualamos la naturaleza de las fechas ANTES de compararlas o guardarlas.
    ahora = timezone.now()
    if timezone.is_aware(ahora):
        if timezone.is_naive(cuando):
            cuando = timezone.make_aware(cuando, timezone.get_current_timezone())
    elif timezone.is_aware(cuando):
        cuando = timezone.make_naive(cuando, timezone.get_current_timezone())
    if cuando < ahora:
        return _error("fecha_cita_pasada", "La nueva cita debe programarse a futuro.", 400)
    sucursal = datos["agencia"].strip()
    piso = datos["asesor_piso"].strip()
    nota = (datos.get("comentarios") or "").strip()
    if not sucursal or not piso:
        return _error("datos_cita_incompletos", "Selecciona agencia y asesor de piso.", 400)

    firma = hashlib.sha256(json.dumps({
        "fecha_hora_cita": cuando.isoformat(), "agencia": sucursal.casefold(),
        "asesor_piso": piso.casefold(), "comentarios": nota,
    }, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    try:
        with transaction.atomic(using="default"):
            expediente = (ExpedienteDigital.objects.select_for_update()
                          .select_related("cliente")
                          .filter(pk=datos["expediente_id"]).first())
            if expediente is None:
                return _error("expediente_inexistente", "Expediente no disponible.", 404)
            if not _autorizado(usuario, expediente):
                return _error("sin_permiso_expediente", "No tienes acceso a este expediente.", 403)
            if _agencia_clave(sucursal) != _agencia_clave(expediente.agencia) or not _agencia_clave(sucursal):
                return _error("agencia_no_coincide", "La cita debe corresponder a la agencia del expediente.", 409)

            # Un reintento idéntico devuelve el vínculo anterior sin crear otra cita.
            anterior = (ActividadComercialDigital.objects
                        .filter(clave_idempotencia=datos["clave_idempotencia"]).first())
            if anterior:
                guardado = (anterior.detalle or {}).get("solicitud_cita_chat_v3")
                actor = str(getattr(usuario, "usuario", "") or "").strip().casefold()
                if (anterior.expediente_id != expediente.pk
                        or str(anterior.usuario_crm or "").strip().casefold() != actor
                        or not anterior.cita_id or guardado != firma):
                    return _error("idempotencia_en_conflicto", "La operación ya existe con otros datos.", 409)
                return Response({"codigo": "reintento_idempotente", "duplicado": True,
                                 "cita_id": anterior.cita_id,
                                 "actividad_id": anterior.pk,
                                 "etapa_resultante": anterior.etapa_resultante}, status=200)

            if expediente.etapa_comercial_v3 != "cotizacion_enviada":
                return _error("etapa_no_permitida",
                              "Para agendar una cita nueva debe estar en Cotización enviada.", 409)
            if not str(expediente.asesor_digital or "").strip():
                return _error("asesor_digital_faltante", "Asigna primero un asesor digital al expediente.", 409)

            # Evitar cita pendiente duplicada, también si aún no está vinculada a V3.
            pendientes = Cita.objects.filter(
                cliente_id=expediente.cliente_id, agencia__iexact=sucursal,
                asistencia=False, fecha_hora_cita__gte=timezone.now(),
            ).filter(Q(estado_asistencia__isnull=True) |
                     Q(estado_asistencia="") | Q(estado_asistencia="pendiente"))
            if pendientes.exists():
                return _error("cita_pendiente_existente",
                              "Ya hay una cita pendiente de este cliente en la sucursal; revísala antes de registrar otra.", 409)

            # Cliente, agencia y asesor digital provienen exclusivamente de BD.
            payload = {
                "cliente_id": expediente.cliente_id,
                "agencia": expediente.agencia.strip(),
                "fecha_hora_cita": cuando,
                "asesor_piso": piso,
                "asesor_digital": expediente.asesor_digital.strip(),
                "auto_interes": expediente.auto_interes or "",
                "fuente_prospeccion": expediente.pauta or expediente.canal_contacto or "",
                "tipo_cita": "Digital", "motivo_cita": "Digital",
                "asistencia": False, "comentarios": nota,
            }
            cita_form = CitaSerializer(data=payload, context={"request": request})
            if not cita_form.is_valid():
                # Aún no se ha escrito la cita.
                return Response({"codigo": "validacion_cita", "errores": cita_form.errors}, status=400)
            campo_reg = Cita._meta.get_field("registrada_por_crm")
            valor_reg = (True if campo_reg.get_internal_type() == "BooleanField"
                         else str(getattr(usuario, "usuario", "") or "crm")[:120])
            cita = cita_form.save(registrada_por_crm=valor_reg)

            resultado = registrar_actividad_v3(
                expediente_id=expediente.pk, evento="cita_registrada",
                datos={"confirmado": True}, actor=usuario,
                clave_idempotencia=datos["clave_idempotencia"], cita_id=cita.pk,
            )
            # Adjuntar firma del formulario original para validar reintentos.
            actividad = ActividadComercialDigital.objects.get(pk=resultado.actividad_id)
            detalle = dict(actividad.detalle or {})
            detalle["solicitud_cita_chat_v3"] = firma
            actividad.detalle = detalle
            actividad.save(update_fields=["detalle"])

            ExpedienteDigital.objects.filter(pk=expediente.pk).update(
                ultima_cita_id=cita.pk,
                ultima_cita_agendada=cita.fecha_hora_cita,
                asesor_ventas=piso,
            )
            return Response({
                "codigo": "cita_v3_registrada", "duplicado": False,
                "cita_id": cita.pk, "actividad_id": resultado.actividad_id,
                "etapa_resultante": resultado.etapa_resultante,
            }, status=status.HTTP_201_CREATED)
    except ErrorActividadComercial as exc:
        return _error(exc.codigo, str(exc), 409)
    except IntegrityError:
        logger.warning("Conflicto de integridad al agendar cita comercial para expediente %s",
                       datos["expediente_id"], exc_info=True)
        return _error("conflicto_concurrencia",
                      "Hubo una operación simultánea. Actualiza el expediente antes de reintentar.", 409)
    except Exception:
        # Fuera de atomic(): PostgreSQL habrá revertido cita, actividad y cambio
        # de etapa. El traceback se conserva en los logs, no en la respuesta.
        logger.exception("Error inesperado al agendar cita comercial para expediente %s",
                         datos["expediente_id"])
        return _error("error_interno_cita",
                      "No se pudo registrar la cita. Comunica el error a soporte para revisar el registro del servidor.", 500)
