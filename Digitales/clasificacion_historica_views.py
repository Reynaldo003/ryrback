"""Clasificación única y auditada de expedientes anteriores a CRM V3.

No equivale a registrar una venta, cita o cotización nueva. No modifica
el estado histórico. Los datos declarados requieren confirmación humana.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from CrmConformidad.jwt_authentication import CRMJWTAuthentication
from .actividades_views import (
    _autorizado, _usuario_en_piloto_o_general, _agencia_clave,
    _resolver_propietario_historico_v3,
)
from .actividades_service import MOTIVOS_LEAD_PERDIDO_V3
from .models import ActividadComercialDigital, BitacoraAsesorDigital, ExpedienteDigital

_ETAPAS = frozenset({
    "nuevo_prospecto", "en_seguimiento", "cotizacion_enviada", "cita_agendada",
    "cita_asistida", "documentos_enviados", "autorizado_no_formalizado",
    "compra_futura", "lead_perdido",
})  # Facturado EXCLUIDO: solo se obtiene mediante su flujo automático VIN.
_MEDIOS = frozenset({"llamada", "facebook", "presencial", "whatsapp_externo", "otro"})
_CLAVE = re.compile(r"^[A-Za-z0-9._:\-]{8,120}$")
_CAMPOS = {
    "nuevo_prospecto": set(),
    "en_seguimiento": {"medio", "fecha_contacto", "observacion"},
    "cotizacion_enviada": {"fecha_envio", "vehiculo", "referencia"},
    "cita_agendada": {"fecha_hora_cita"},
    "cita_asistida": {"fecha_hora_cita", "fecha_asistencia_real"},
    "documentos_enviados": {"fecha_recepcion", "documentos"},
    "autorizado_no_formalizado": {"fecha_autorizacion", "referencia_autorizacion"},
    "compra_futura": {"fecha_prevista_compra", "proximo_contacto", "observacion"},
    "lead_perdido": {"motivo", "detalle_motivo"},
}


def _fecha(datos, clave, no_futura=True):
    valor = datos.get(clave)
    if not isinstance(valor, str):
        raise ValueError(f"{clave}: indica una fecha válida.")
    try:
        fecha = date.fromisoformat(valor)
    except ValueError as exc:
        raise ValueError(f"{clave}: fecha inválida.") from exc
    if no_futura and fecha > timezone.localdate():
        raise ValueError(f"{clave}: no puede ser futura.")
    return fecha.isoformat()


def _fecha_hora(datos):
    bruto = datos.get("fecha_hora_cita")
    if not isinstance(bruto, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", bruto):
        raise ValueError("Indica fecha y hora programadas de la cita.")
    try:
        fecha = datetime.fromisoformat(bruto)
    except ValueError as exc:
        raise ValueError("Fecha u hora programada inválida.") from exc
    if fecha.year < 2000:
        raise ValueError("La fecha de cita es inválida.")
    return fecha


def _texto(datos, clave, minimo=1, maximo=600):
    valor = datos.get(clave)
    if not isinstance(valor, str) or not minimo <= len(valor.strip()) <= maximo:
        raise ValueError(f"{clave}: escribe entre {minimo} y {maximo} caracteres.")
    limpio = valor.strip()
    if any(ord(caracter) < 32 and caracter not in "\n\t" for caracter in limpio):
        raise ValueError(f"{clave}: contiene caracteres inválidos.")
    return limpio


def validar_datos(etapa, datos, expediente):
    """Lista blanca de campos. Todos los registros son declaraciones históricas."""
    if not isinstance(datos, dict):
        raise ValueError("Faltan datos o hay campos que no corresponden a la etapa seleccionada.")
    # La referencia del crédito es opcional, también cuando el navegador
    # no incluye la clave. Para las demás etapas mantenemos lista blanca estricta.
    if etapa == "autorizado_no_formalizado" and "referencia_autorizacion" not in datos:
        datos = {**datos, "referencia_autorizacion": ""}
    if set(datos) != _CAMPOS[etapa]:
        raise ValueError("Faltan datos o hay campos que no corresponden a la etapa seleccionada.")
    salida = {}
    if etapa == "en_seguimiento":
        medio = datos.get("medio")
        if medio not in _MEDIOS:
            raise ValueError("Selecciona el medio del contacto realizado.")
        salida = {"medio": medio, "fecha_contacto": _fecha(datos, "fecha_contacto"),
                  "observacion": _texto(datos, "observacion", 8, 600)}
    elif etapa == "cotizacion_enviada":
        salida = {"fecha_envio": _fecha(datos, "fecha_envio"),
                  "vehiculo": _texto(datos, "vehiculo", 2, 180),
                  "referencia": _texto(datos, "referencia", 2, 120)}
    elif etapa in {"cita_agendada", "cita_asistida"}:
        programada = _fecha_hora(datos)
        salida = {"fecha_hora_cita": programada.isoformat(timespec="minutes"),
                  "sucursal": expediente.agencia}
        if etapa == "cita_asistida":
            fecha_real = _fecha(datos, "fecha_asistencia_real")
            if date.fromisoformat(fecha_real) < programada.date():
                raise ValueError("La fecha real no puede ser anterior a la fecha programada.")
            if programada.date() > timezone.localdate():
                raise ValueError("No puedes confirmar una cita futura como asistida.")
            salida["fecha_asistencia_real"] = fecha_real
    elif etapa == "documentos_enviados":
        bruto = datos.get("documentos")
        if not isinstance(bruto, list) or not 1 <= len(bruto) <= 30:
            raise ValueError("Indica los documentos recibidos (1 a 30).")
        documentos = []
        for item in bruto:
            if not isinstance(item, str) or not 1 <= len(item.strip()) <= 160:
                raise ValueError("Cada documento debe tener un nombre válido.")
            documentos.append(item.strip())
        salida = {"fecha_recepcion": _fecha(datos, "fecha_recepcion"), "documentos": documentos}
    elif etapa == "autorizado_no_formalizado":
        salida = {"fecha_autorizacion": _fecha(datos, "fecha_autorizacion"),
                  "referencia_autorizacion": _texto(datos, "referencia_autorizacion", 0, 120),
                  "credito_autorizado": True}
    elif etapa == "compra_futura":
        prevista = _fecha(datos, "fecha_prevista_compra", no_futura=False)
        contacto = _fecha(datos, "proximo_contacto", no_futura=False)
        if prevista < timezone.localdate().isoformat() or contacto < timezone.localdate().isoformat():
            raise ValueError("Las fechas futuras de compra y próximo contacto no deben estar vencidas.")
        salida = {"fecha_prevista_compra": prevista, "proximo_contacto": contacto,
                  "observacion": _texto(datos, "observacion", 8, 600)}
    elif etapa == "lead_perdido":
        motivo = datos.get("motivo")
        if motivo not in MOTIVOS_LEAD_PERDIDO_V3:
            raise ValueError("Selecciona un motivo válido de descarte.")
        detalle = datos.get("detalle_motivo")
        if not isinstance(detalle, str) or len(detalle.strip()) > 1000:
            raise ValueError("La explicación del descarte no es válida.")
        if motivo == "otro_motivo" and len(detalle.strip()) < 5:
            raise ValueError("Especifica el otro motivo con al menos cinco caracteres.")
        salida = {"motivo": motivo, "motivo_etiqueta": MOTIVOS_LEAD_PERDIDO_V3[motivo],
                  "detalle_motivo": detalle.strip()}
    return salida


def disponible_para_clasificacion(expediente):
    """Corte de inclusión controlado; no sirve para reabrir ventas facturadas."""
    if (expediente.etapa_comercial_v3 or "").strip():
        return False
    if _agencia_clave(expediente.estado) == "facturado" or expediente.vin_facturado:
        return False
    try:
        corte = date.fromisoformat(str(getattr(settings, "CRM_ETAPAS_V3_CORTE_HISTORICOS", "2026-10-16")))
    except ValueError:
        return False
    return expediente.creado is not None and expediente.creado.date() < corte


@api_view(["POST"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def clasificar_expediente_historico_v3_view(request):
    if not getattr(settings, "CRM_ETAPAS_V3_API_HABILITADA", False):
        return Response({"codigo": "v3_desactivado"}, status=status.HTTP_404_NOT_FOUND)
    if not _usuario_en_piloto_o_general(request.user):
        return Response({"codigo": "sin_permiso"}, status=status.HTTP_403_FORBIDDEN)
    entrada = request.data
    if not isinstance(entrada, dict) or set(entrada) != {
        "expediente_id", "etapa_destino", "datos", "motivo", "confirmado", "clave_idempotencia"
    }:
        return Response({"detalle": "Formulario de clasificación inválido."}, status=400)
    if type(entrada.get("expediente_id")) is not int or entrada["expediente_id"] <= 0:
        return Response({"detalle": "Expediente inválido."}, status=400)
    etapa = entrada.get("etapa_destino")
    if etapa not in _ETAPAS:
        return Response({"detalle": "Etapa no permitida para clasificación histórica."}, status=400)
    clave = entrada.get("clave_idempotencia")
    if not isinstance(clave, str) or not _CLAVE.fullmatch(clave):
        return Response({"detalle": "Identificador de operación inválido."}, status=400)
    if entrada.get("confirmado") is not True:
        return Response({"detalle": "Debes confirmar la clasificación."}, status=400)
    motivo = entrada.get("motivo")
    if not isinstance(motivo, str) or not 10 <= len(motivo.strip()) <= 500:
        return Response({"detalle": "Explica la clasificación en 10 a 500 caracteres."}, status=400)
    if len(json.dumps(entrada, ensure_ascii=False, default=str)) > 6000:
        return Response({"detalle": "Formulario demasiado extenso."}, status=400)
    with transaction.atomic(using="default"):
        expediente = (ExpedienteDigital.objects.select_for_update()
                      .select_related("cliente")
                      .filter(pk=entrada["expediente_id"]).first())
        if expediente is None or not _autorizado(request.user, expediente):
            return Response({"codigo": "expediente_no_disponible"}, status=404)
        actor = str(request.user.usuario or "").strip()
        anterior_intento = ActividadComercialDigital.objects.filter(clave_idempotencia=clave).first()
        if anterior_intento:
            d = anterior_intento.detalle or {}
            if (anterior_intento.expediente_id == expediente.pk and anterior_intento.usuario_crm == actor
                    and anterior_intento.etapa_resultante == etapa and d.get("evento") == "clasificacion_historica_v3"
                    and d.get("datos_declarados") == entrada["datos"] and d.get("motivo") == motivo.strip()):
                return Response({"etapa_comercial_v3": etapa, "duplicado": True}, status=200)
            return Response({"codigo": "idempotencia_en_conflicto"}, status=409)
        if not disponible_para_clasificacion(expediente):
            return Response({"codigo": "clasificacion_no_disponible",
                             "detalle": "El expediente ya tiene una etapa comercial o no corresponde a la clasificación histórica."}, status=409)
        if _agencia_clave(expediente.estado) == "descalificado" and etapa != "lead_perdido":
            return Response({"detalle": "Un descartado histórico debe conservar la clasificación de pérdida."}, status=409)
        try:
            datos_validados = validar_datos(etapa, entrada["datos"], expediente)
        except (ValueError, TypeError) as exc:
            return Response({"detalle": str(exc)}, status=400)
        # Si la titularidad histórica se verificó de manera inequívoca,
        # conservarla al clasificar. De lo contrario, el asesor perdería
        # acceso a la etapa recién registrada al salir de esta excepción.
        propietario_verificado = ""
        if not (expediente.usuario_crm_asignado or "").strip():
            propietario_verificado = _resolver_propietario_historico_v3(
                expediente, _agencia_clave(expediente.agencia)
            )

        actividad = ActividadComercialDigital.objects.create(
            expediente=expediente, tipo="correccion", origen="correccion",
            agencia=expediente.agencia, asesor_digital=expediente.asesor_digital,
            usuario_crm=actor, etapa_anterior="", etapa_resultante=etapa,
            clave_idempotencia=clave,
            # Intencionadamente sin fecha_actividad: no infla KPIs históricos.
            detalle={"evento": "clasificacion_historica_v3", "estado_historico": expediente.estado,
                     "etapa_declarada": etapa, "datos": datos_validados,
                     "datos_declarados": entrada["datos"], "motivo": motivo.strip(),
                     "captura_explicita": True, "no_contabilizar_evento_nuevo": True,
                     "agencia": expediente.agencia, "cliente_id": expediente.cliente_id,
                     "propietario_crm_verificado": propietario_verificado or None},
        )
        expediente.etapa_comercial_v3 = etapa
        campos_guardar = ["etapa_comercial_v3", "actualizado"]
        if propietario_verificado:
            expediente.usuario_crm_asignado = propietario_verificado
            campos_guardar.append("usuario_crm_asignado")
        expediente.save(update_fields=campos_guardar)
        BitacoraAsesorDigital.objects.create(
            expediente=expediente, cliente=expediente.cliente,
            asesor_digital=expediente.asesor_digital, usuario_crm=actor,
            tipo="actualizacion", accion="Clasificación histórica CRM V3",
            detalle=f"{expediente.estado} => {etapa}: {motivo.strip()}"[:1000],
            resultado="no_aplica", metadata={
                "crm_etapas_version": 3, "evento": "clasificacion_historica_v3",
                "actividad_id": actividad.pk, "estado_legacy": expediente.estado,
                "etapa_resultante": etapa, "no_contabilizar_evento_nuevo": True,
                "propietario_crm_verificado": propietario_verificado or None,
            },
        )
    return Response({"etapa_comercial_v3": etapa, "actividad_id": actividad.pk,
                     "duplicado": False}, status=status.HTTP_201_CREATED)
