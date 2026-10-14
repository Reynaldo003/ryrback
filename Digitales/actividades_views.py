"""API HTTP piloto de actividades CRM V3. NO habilitada por defecto.

Ruta prevista: POST /digitales/api/etapas-v3/actividades/

Seguridad:
- Autenticación JWT real del CRM; nunca AllowAny.
- Feature flag y lista explícita de IDs de usuarios piloto (fail closed).
- Control exacto de agencia asignada, agencia habilitada y responsable del expediente.
- No permite iniciar V3, facturar, corregir etapas ni simular mensajes humanos.
- Bloqueo de expediente durante autorización y registro (misma transacción).
- Rechaza datos desconocidos y no acepta usuario/agencia desde el navegador.

No montar el endpoint en producción sin comprobar la política con los roles reales.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping

from django.conf import settings
from django.db import IntegrityError, transaction
from rest_framework import serializers, status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from CrmConformidad.jwt_authentication import CRMJWTAuthentication
from .actividades_service import ErrorActividadComercial, registrar_actividad_v3
from .models import ActividadComercialDigital, ExpedienteDigital


# Únicamente confirmaciones explícitas, sin eventos generados por el backend.
_EVENTOS_HTTP = frozenset({
    "cotizacion_confirmada",
    "cita_registrada",
    "asistencia_confirmada",
    "documentos_recibidos_confirmados",
    "seleccion_manual",  # Autorización, compra futura y lead perdido, por destino.
    "reactivacion",  # Desde compra futura o lead perdido a En seguimiento.
})

_CAMPOS_DATOS = {
    "cotizacion_confirmada": frozenset({
        "confirmado", "fecha_envio", "vehiculo", "referencia", "archivo_id",
    }),
    "cita_registrada": frozenset({"confirmado"}),
    "asistencia_confirmada": frozenset({"confirmado", "fecha_asistencia_real"}),
    "documentos_recibidos_confirmados": frozenset({
        "confirmado", "fecha_recepcion", "documentos",
    }),
    "seleccion_manual": frozenset({
        "etapa_destino", "credito_autorizado", "confirmado",
        "fecha_autorizacion", "referencia_autorizacion",
        "fecha_prevista_compra", "proximo_contacto", "observacion",
        "motivo", "detalle_motivo",
    }),
    "reactivacion": frozenset({"etapa_destino", "motivo", "confirmado"}),
}

# El piloto admite solo autorización, compra futura y lead perdido como selecciones.
# Facturación automática y correcciones siguen fuera del endpoint HTTP.
# La reactivación explícita vuelve a En seguimiento desde ambas situaciones.
_CLAVE_IDEMPOTENCIA = re.compile(r"^[A-Za-z0-9._:\-]{8,120}$")
_CONFLICTOS = frozenset({
    "idempotencia_en_conflicto", "flujo_v3_no_iniciado",
    "facturado_protegido", "lead_perdido_protegido", "compra_futura_protegida",
    "cita_ya_clasificada", "asistencia_ya_registrada",
    "cita_no_vinculada_v3", "cita_aun_no_ocurre", "asistencia_antes_de_cita",
    "retroceso_no_permitido", "alta_repetida", "no_requiere_reactivacion",
    "documentos_requeridos_credito", "solo_compra_futura",
})


class RegistroActividadV3Serializer(serializers.Serializer):
    expediente_id = serializers.IntegerField(min_value=1)
    evento = serializers.ChoiceField(choices=sorted(_EVENTOS_HTTP))
    clave_idempotencia = serializers.RegexField(regex=_CLAVE_IDEMPOTENCIA, max_length=120)
    datos = serializers.DictField(required=True, allow_empty=False)
    cita_id = serializers.IntegerField(required=False, min_value=1, allow_null=True)

    def validate(self, attrs):
        evento = attrs["evento"]
        datos = attrs["datos"]
        extras = sorted(set(datos) - _CAMPOS_DATOS[evento])
        if extras:
            raise serializers.ValidationError({"datos": f"Campos no permitidos: {', '.join(extras)}"})
        if evento == "seleccion_manual":
            destino = datos.get("etapa_destino")
            permitidos = {
                "autorizado_no_formalizado": {
                    "etapa_destino", "credito_autorizado", "confirmado",
                    "fecha_autorizacion", "referencia_autorizacion",
                },
                "compra_futura": {
                    "etapa_destino", "confirmado", "fecha_prevista_compra",
                    "proximo_contacto", "observacion",
                },
                "lead_perdido": {
                    "etapa_destino", "confirmado", "motivo", "detalle_motivo",
                },
            }
            if destino not in permitidos:
                raise serializers.ValidationError({
                    "datos": "El piloto permite autorización, compra futura y lead perdido."
                })
            indebidos = sorted(set(datos) - permitidos[destino])
            if indebidos:
                raise serializers.ValidationError({
                    "datos": "Campos incompatibles con la etapa seleccionada."
                })
        if evento == "reactivacion":
            if datos.get("etapa_destino") != "en_seguimiento" or datos.get("confirmado") is not True:
                raise serializers.ValidationError({
                    "datos": "Solo se permite reactivación confirmada a En seguimiento."
                })
        es_cita = evento in {"cita_registrada", "asistencia_confirmada"}
        if es_cita != (attrs.get("cita_id") is not None):
            raise serializers.ValidationError({"cita_id": "Solo los eventos de cita requieren cita_id."})
        return attrs


def _agencia_clave(valor):
    """Compara agencia EXACTA tras quitar acentos, dobles espacios y mayúsculas.

    Evita que 'VW Cordoba' permita actuar en 'VW Cordoba Usados'.
    """
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(texto.casefold().split())


def _agencias_usuario(usuario):
    return {_agencia_clave(a) for a in str(usuario.agencia or "").split("|") if a.strip()}


_ROLES_EXCLUIDOS_DIGITALES = frozenset({
    "hostess", "servicio", "asesor de servicio", "taller", "refacciones",
    "garantias", "valuador", "caja", "contabilidad",
})


def _rol_clave_usuario(usuario):
    rol_obj = getattr(usuario, "rol", None)
    texto = (
        getattr(rol_obj, "nombre", "")
        or getattr(rol_obj, "name", "")
        or (rol_obj if isinstance(rol_obj, str) else "")
        or ""
    )
    return _agencia_clave(texto)


def _es_admin_o_coordinador_digital(usuario):
    if bool(getattr(usuario, "is_superuser", False)):
        return True
    rol = _rol_clave_usuario(usuario)
    if rol in {"admin", "administrador"}:
        return True
    if "coordinador" in rol and "digital" in rol:
        return True
    return False


def _usuario_en_piloto_o_general(usuario):
    if not usuario or not getattr(usuario, "is_authenticated", False):
        return False
    ids_piloto = {
        str(valor).strip() for valor in (
            getattr(settings, "CRM_ETAPAS_V3_USUARIOS_PILOTO_IDS", ()) or ()
        ) if str(valor).strip()
    }
    if not ids_piloto or "*" in ids_piloto:
        return True
    return str(usuario.pk) in ids_piloto


def _autorizado(usuario, expediente):
    if not usuario or not getattr(usuario, "is_authenticated", False):
        return False
    rol = _rol_clave_usuario(usuario)
    if rol in _ROLES_EXCLUIDOS_DIGITALES:
        return False

    habilitadas = {
        _agencia_clave(a) for a in (
            getattr(settings, "CRM_ETAPAS_V3_AGENCIAS_HABILITADAS", ()) or ()
        ) if str(a).strip()
    }
    agencia = _agencia_clave(expediente.agencia)
    if not agencia or (habilitadas and agencia not in habilitadas) or agencia not in _agencias_usuario(usuario):
        return False

    es_supervisor = _es_admin_o_coordinador_digital(usuario)
    asignado = str(expediente.usuario_crm_asignado or "").strip().casefold()
    identificador = str(getattr(usuario, "usuario", "") or getattr(usuario, "username", "") or "").strip().casefold()
    return bool(es_supervisor or (asignado and asignado == identificador))


def _error(codigo, mensaje, http_status):
    return Response({"codigo": codigo, "detalle": mensaje}, status=http_status)


@api_view(["POST"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def registrar_actividad_comercial_v3_view(request):
    """Registrar una confirmación comercial. No es una API pública general."""
    if not getattr(settings, "CRM_ETAPAS_V3_API_HABILITADA", False):
        return _error("v3_desactivado", "Función no habilitada.", status.HTTP_404_NOT_FOUND)

    usuario = request.user
    if not _usuario_en_piloto_o_general(usuario):
        return _error("usuario_no_autorizado", "Usuario fuera del piloto.", status.HTTP_403_FORBIDDEN)

    if not isinstance(request.data, Mapping):
        return _error("datos_invalidos", "Envía un objeto JSON.", status.HTTP_400_BAD_REQUEST)
    extras_raiz = sorted(set(request.data) - {
        "expediente_id", "evento", "clave_idempotencia", "datos", "cita_id",
    })
    if extras_raiz:
        return _error("campos_no_permitidos", "Se recibieron campos no permitidos.", status.HTTP_400_BAD_REQUEST)
    formulario = RegistroActividadV3Serializer(data=request.data)
    if not formulario.is_valid():
        return Response({"codigo": "validacion", "errores": formulario.errors}, status=status.HTTP_400_BAD_REQUEST)
    valores = formulario.validated_data

    try:
        with transaction.atomic(using="default"):
            # El bloqueo protege la autorización de cambios concurrentes de agencia
            # o asignación, y se conserva mientras opera el servicio interno.
            expediente = (ExpedienteDigital.objects.select_for_update()
                          .only("id", "agencia", "usuario_crm_asignado", "etapa_comercial_v3")
                          .filter(pk=valores["expediente_id"]).first())
            if expediente is None:
                return _error("expediente_inexistente", "Expediente no encontrado.", status.HTTP_404_NOT_FOUND)
            if not _autorizado(usuario, expediente):
                return _error("sin_permiso_expediente", "No tiene acceso a este expediente.", status.HTTP_403_FORBIDDEN)
            # En este piloto, el navegador no puede saltar del alta a cotización
            # sin la primera respuesta humana verificada por el backend.
            if (valores["evento"] == "cotizacion_confirmada"
                    and expediente.etapa_comercial_v3 == "nuevo_prospecto"):
                return _error("seguimiento_requerido",
                              "Registra primero una respuesta humana válida.",
                              status.HTTP_409_CONFLICT)
            if (valores["evento"] == "reactivacion"
                    and expediente.etapa_comercial_v3 not in {"compra_futura", "lead_perdido"}):
                # Si la primera solicitud ya reactivó al cliente, una repetición
                # idéntica debe poder llegar al control de idempotencia del servicio.
                # SOLO un intento anterior del mismo usuario/expediente/tipo
                # puede saltarse este filtro preliminar. El servicio verificará
                # además que coincidan todos los datos y la firma original.
                ya_registrada = ActividadComercialDigital.objects.filter(
                    expediente_id=expediente.pk,
                    clave_idempotencia=valores["clave_idempotencia"],
                    usuario_crm=str(usuario.usuario or "").strip()[:120],
                    tipo="reactivacion",
                ).exists()
                if not ya_registrada:
                    return _error("solo_compra_futura",
                                  "Solo se puede reactivar desde Compra futura o Lead perdido.",
                                  status.HTTP_409_CONFLICT)
            resultado = registrar_actividad_v3(
                expediente_id=expediente.pk,
                evento=valores["evento"],
                datos=valores["datos"],
                actor=usuario,
                clave_idempotencia=valores["clave_idempotencia"],
                cita_id=valores.get("cita_id"),
            )
    except ErrorActividadComercial as exc:
        codigo_estado = (status.HTTP_409_CONFLICT if exc.codigo in _CONFLICTOS
                         else status.HTTP_404_NOT_FOUND if exc.codigo in {"cita_inexistente", "expediente_inexistente"}
                         else status.HTTP_400_BAD_REQUEST)
        return _error(exc.codigo, str(exc), codigo_estado)
    except IntegrityError:
        # Un choque de clave única en reintentos concurrentes se presenta como
        # conflicto. La operación completa ya fue revertida por atomic().
        return _error("conflicto_concurrencia", "Conflicto al registrar la actividad; consulta el resultado anterior.", status.HTTP_409_CONFLICT)

    return Response({
        "actividad_id": resultado.actividad_id,
        "etapa_anterior": resultado.etapa_anterior,
        "etapa_resultante": resultado.etapa_resultante,
        "cambio_etapa": resultado.cambio_etapa,
        "duplicado": resultado.duplicado,
        "codigo": resultado.codigo,
    }, status=status.HTTP_200_OK if resultado.duplicado else status.HTTP_201_CREATED)
