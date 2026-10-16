"""Correcciones auditadas y sin retroceso de etapas para CRM comercial V3.

El original permanece intacto; el registro de corrección enlaza `corrige_a`.
Cada consumidor analítico debe aplicar la última corrección efectiva, no sumar
correcciones como nuevas cotizaciones/asistencias.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework import serializers, status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from CrmConformidad.jwt_authentication import CRMJWTAuthentication
from .actividades_views import (_autorizado, _usuario_en_piloto_o_general,
                                _es_admin_o_coordinador_digital, _agencia_clave)
from .models import ActividadComercialDigital, BitacoraAsesorDigital, ExpedienteDigital
from citas.models import Cita


# Los asesores solo corrigen sus registros. Las correcciones delicadas exigen
# coordinación o administración. No existe corrección libre de etapa o VIN.
_CAMPOS = {
    "cotizacion_enviada": frozenset({"fecha_envio", "vehiculo", "referencia"}),
    "documentos_recibidos": frozenset({"fecha_recepcion", "documentos"}),
    "cita_agendada": frozenset({"fecha_hora_cita"}),
    "cita_asistida": frozenset({"fecha_asistencia_real"}),
}
_RESTRINGIDOS = frozenset({"cita_asistida"})
_TOKEN = re.compile(r"^[A-Za-z0-9._:\-]{8,120}$")


class CorreccionV3Serializer(serializers.Serializer):
    expediente_id = serializers.IntegerField(min_value=1)
    actividad_id = serializers.IntegerField(min_value=1)
    motivo = serializers.CharField(min_length=8, max_length=1000, trim_whitespace=True)
    clave_idempotencia = serializers.RegexField(regex=_TOKEN, max_length=120)
    cambios = serializers.DictField(child=serializers.JSONField(), allow_empty=False)


def _fecha_efectiva(valor, nombre):
    fecha = parse_date(valor) if isinstance(valor, str) else None
    if fecha is None or fecha > timezone.localdate():
        raise serializers.ValidationError({nombre: "Indica una fecha válida que no sea futura."})
    return fecha.isoformat()


def _cita_fecha(valor):
    fecha = parse_datetime(valor) if isinstance(valor, str) else None
    if fecha is None:
        raise serializers.ValidationError({"fecha_hora_cita": "Se requiere fecha y hora ISO válidas."})
    if timezone.is_naive(fecha):
        fecha = timezone.make_aware(fecha, ZoneInfo(settings.TIME_ZONE))
    return fecha


def _normalizar(cambios, tipo, cita):
    extras = set(cambios) - _CAMPOS[tipo]
    if extras:
        raise serializers.ValidationError({"cambios": "Campos no autorizados: " + ", ".join(sorted(extras))})
    nuevos = {}
    for clave, valor in cambios.items():
        if clave in {"fecha_envio", "fecha_recepcion", "fecha_asistencia_real"}:
            nuevos[clave] = _fecha_efectiva(valor, clave)
        elif clave == "fecha_hora_cita":
            nuevos[clave] = _cita_fecha(valor).isoformat()
        elif clave == "vehiculo":
            if not isinstance(valor, str) or len(valor.strip()) > 255:
                raise serializers.ValidationError({clave: "Vehículo inválido."})
            nuevos[clave] = valor.strip()
        elif clave == "referencia":
            if not isinstance(valor, str) or len(valor.strip()) > 120:
                raise serializers.ValidationError({clave: "Referencia inválida."})
            nuevos[clave] = valor.strip()
        elif clave == "documentos":
            if (not isinstance(valor, list) or not (1 <= len(valor) <= 30)
                    or any(not isinstance(v, str) or not (1 <= len(v.strip()) <= 160) for v in valor)):
                raise serializers.ValidationError({clave: "Indica entre 1 y 30 documentos válidos."})
            nuevos[clave] = [v.strip() for v in valor]
    if tipo == "cita_asistida":
        if cita is None or cita.fecha_hora_cita is None:
            raise serializers.ValidationError({"actividad_id": "No se encontró la cita asociada."})
        dia_programado = timezone.localtime(
            cita.fecha_hora_cita if timezone.is_aware(cita.fecha_hora_cita)
            else timezone.make_aware(cita.fecha_hora_cita, ZoneInfo(settings.TIME_ZONE)),
            ZoneInfo(settings.TIME_ZONE),
        ).date()
        if date.fromisoformat(nuevos["fecha_asistencia_real"]) < dia_programado:
            raise serializers.ValidationError({"fecha_asistencia_real": "Anterior a la fecha de cita."})
    return nuevos


def _tipo_corregible(actividad):
    if actividad.tipo in _CAMPOS and not actividad.corrige_a_id:
        return actividad.tipo
    detalle = actividad.detalle or {}
    if (actividad.tipo == "correccion" and not actividad.corrige_a_id
            and actividad.usuario_crm == "migracion_historica_v3"
            and detalle.get("evento") == "homologacion_historica_v3"
            and actividad.etapa_resultante in {"cotizacion_enviada", "cita_agendada"}):
        return actividad.etapa_resultante
    return None


def puede_corregir_actividad(usuario, actividad):
    tipo = _tipo_corregible(actividad)
    if tipo is None:
        return False
    if _es_admin_o_coordinador_digital(usuario):
        return True
    if tipo in _RESTRINGIDOS:
        return False
    if actividad.usuario_crm == "migracion_historica_v3":
        # La homologación no tiene actor comercial: exigir titularidad actual
        # verificable, nunca comparar con el usuario técnico de migración.
        return _autorizado(usuario, actividad.expediente)
    return (actividad.usuario_crm.strip().casefold()
            == str(getattr(usuario, "usuario", "") or "").strip().casefold())


@api_view(["POST"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def corregir_actividad_comercial_v3_view(request):
    if not getattr(settings, "CRM_ETAPAS_V3_API_HABILITADA", False):
        return Response({"codigo": "v3_desactivado"}, status=status.HTTP_404_NOT_FOUND)
    if not _usuario_en_piloto_o_general(request.user):
        return Response({"codigo": "sin_permiso"}, status=status.HTTP_403_FORBIDDEN)

    entrada = CorreccionV3Serializer(data=request.data)
    entrada.is_valid(raise_exception=True)
    datos = entrada.validated_data
    usuario = str(request.user.usuario or "").strip()
    # Firma del intento original, independientemente de cambios posteriores.
    firma = hashlib.sha256(json.dumps({
        "expediente_id": datos["expediente_id"],
        "actividad_id": datos["actividad_id"],
        "motivo": datos["motivo"], "cambios": datos["cambios"],
    }, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()

    with transaction.atomic(using="default"):
        exp = ExpedienteDigital.objects.select_for_update().filter(pk=datos["expediente_id"]).first()
        if exp is None or not _autorizado(request.user, exp):
            return Response({"codigo": "expediente_no_disponible"}, status=status.HTTP_404_NOT_FOUND)
        original = ActividadComercialDigital.objects.select_for_update().filter(
            pk=datos["actividad_id"], expediente=exp,
        ).first()
        if original is None:
            return Response({"codigo": "actividad_no_disponible"}, status=status.HTTP_404_NOT_FOUND)
        if not puede_corregir_actividad(request.user, original):
            return Response({"codigo": "correccion_no_autorizada"}, status=status.HTTP_403_FORBIDDEN)
        tipo_objetivo = _tipo_corregible(original)
        es_historico = original.usuario_crm == "migracion_historica_v3"
        if es_historico and exp.etapa_comercial_v3 != original.etapa_resultante:
            # Evitar regularizar el episodio equivocado después de nuevos avances.
            return Response({"codigo": "historial_desactualizado"}, status=status.HTTP_409_CONFLICT)

        existente = ActividadComercialDigital.objects.filter(clave_idempotencia=datos["clave_idempotencia"]).first()
        if existente:
            detalle = existente.detalle or {}
            if (existente.expediente_id != exp.pk or existente.corrige_a_id != original.pk
                    or existente.usuario_crm != usuario or detalle.get("firma_operacion") != firma):
                return Response({"codigo": "idempotencia_en_conflicto"}, status=status.HTTP_409_CONFLICT)
            return Response({"correccion_id": existente.pk, "duplicado": True})

        cita = None
        if tipo_objetivo in {"cita_agendada", "cita_asistida"}:
            cita_id = original.cita_id or (exp.ultima_cita_id if es_historico else None)
            cita = Cita.objects.select_for_update().filter(pk=cita_id).first()
            if cita is None or cita.cliente_id != exp.cliente_id or _agencia_clave(cita.agencia) != _agencia_clave(exp.agencia):
                return Response({"codigo": "cita_no_vinculada"}, status=status.HTTP_409_CONFLICT)
            if tipo_objetivo == "cita_agendada" and (cita.asistencia or cita.estado_asistencia not in (None, "pendiente")):
                return Response({"codigo": "cita_ya_clasificada"}, status=status.HTTP_409_CONFLICT)

        cambios = _normalizar(datos["cambios"], tipo_objetivo, cita)
        if es_historico and tipo_objetivo == "cotizacion_enviada":
            if not cambios.get("fecha_envio") or not cambios.get("vehiculo") or not cambios.get("referencia"):
                raise serializers.ValidationError({"cambios": "Confirma fecha, vehículo y referencia de la cotización histórica."})
        previa = original.correcciones.filter(tipo="correccion").order_by("-registrado_at", "-pk").first()
        anterior = ((previa.detalle or {}).get("datos_despues") if previa else None)
        if not isinstance(anterior, dict):
            anterior = (original.detalle or {}).get("datos") or {}
        if not isinstance(anterior, dict):
            anterior = {}
        if es_historico and not previa and tipo_objetivo == "cotizacion_enviada":
            anterior = {"referencia_historica": exp.id_cotizacion or "", "sin_fecha_v3_verificada": True}
        despues = {**anterior, **cambios}
        if despues == anterior:
            return Response({"codigo": "sin_cambios"}, status=status.HTTP_409_CONFLICT)

        # Cambiar la entidad operativa solo cuando la corrección lo necesita.
        # Nada modifica etapa_comercial_v3, VIN ni facturado_at.
        if cita and "fecha_hora_cita" in cambios:
            cita.fecha_hora_cita = _cita_fecha(cambios["fecha_hora_cita"])
            cita.save(update_fields=["fecha_hora_cita"])
        if cita and "fecha_asistencia_real" in cambios:
            cita.fecha_asistencia_real = date.fromisoformat(cambios["fecha_asistencia_real"])
            cita.save(update_fields=["fecha_asistencia_real"])

        clave_fecha = {
            "cotizacion_enviada": "fecha_envio", "documentos_recibidos": "fecha_recepcion",
            "cita_asistida": "fecha_asistencia_real",
        }.get(tipo_objetivo)
        fecha_efectiva = date.fromisoformat(despues[clave_fecha]) if clave_fecha and despues.get(clave_fecha) else original.fecha_actividad
        correccion = ActividadComercialDigital.objects.create(
            expediente=exp, cita=cita, corrige_a=original, tipo="correccion", origen="correccion",
            agencia=exp.agencia, usuario_crm=usuario, asesor_digital=exp.asesor_digital,
            fecha_actividad=fecha_efectiva, etapa_anterior=exp.etapa_comercial_v3 or "",
            etapa_resultante=exp.etapa_comercial_v3 or "", clave_idempotencia=datos["clave_idempotencia"],
            detalle={"evento": ("regularizacion_historica_v3" if es_historico else "correccion_actividad"),
                     "actividad_original_id": original.pk, "tipo_original": tipo_objetivo,
                     "fuente": ("homologacion_historica_v3" if es_historico else "actividad_v3"),
                     "motivo": datos["motivo"],
                     "cambios": cambios, "datos_antes": anterior, "datos_despues": despues,
                     "firma_operacion": firma},
        )
        BitacoraAsesorDigital.objects.create(
            expediente=exp, cliente=exp.cliente, asesor_digital=exp.asesor_digital,
            usuario_crm=usuario, numero_asesor="", tipo="actualizacion",
            accion="Corrección comercial CRM V3", resultado="no_aplica",
            detalle=f"Corrección actividad #{original.pk}: {datos['motivo']}"[:1000],
            metadata={"crm_etapas_version": 3, "evento": "correccion_actividad",
                      "actividad_original_id": original.pk, "correccion_id": correccion.pk,
                      "cambios": cambios},
        )
        return Response({"correccion_id": correccion.pk, "actividad_original_id": original.pk,
                         "etapa_comercial_v3": exp.etapa_comercial_v3, "duplicado": False},
                        status=status.HTTP_201_CREATED)
