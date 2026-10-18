"""API HTTP piloto de actividades CRM V3. NO habilitada por defecto.

Ruta prevista: POST /digitales/api/etapas-v3/actividades/

Seguridad:
- Autenticación JWT real del CRM; nunca AllowAny.
- Feature flag, permisos efectivos y lista de IDs opcional para piloto.
- Control exacto de agencia asignada, agencia habilitada y responsable del expediente.
- No permite iniciar V3, facturar, corregir etapas ni simular mensajes humanos.
- Bloqueo de expediente durante autorización y registro (misma transacción).
- Rechaza datos desconocidos y no acepta usuario/agencia desde el navegador.

Despliegue general sujeto a pruebas con roles reales y agencias existentes.
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
from CrmConformidad.views import permisos_por_usuario
from CrmConformidad.models import Usuario
from .actividades_service import ErrorActividadComercial, registrar_actividad_v3
from .models import ActividadComercialDigital, ExpedienteDigital, MensajeWhatsApp
from .sett import WHATSAPP_LINES
from .asignacion_asesores import obtener_asesores_activos, resolver_usuario_crm_por_linea
from .permisos_comerciales_v3 import puede_supervisar_comercial
from citas.models import normaliza_tel_mx


# Únicamente confirmaciones explícitas, sin eventos generados por el backend.
_EVENTOS_HTTP = frozenset({
    "contacto_externo_confirmado",  # Llamada, Facebook, presencial u otro medio declarado.
    "cotizacion_confirmada",
    "cita_registrada",
    "asistencia_confirmada",
    "documentos_recibidos_confirmados",
    "seleccion_manual",  # Autorización, compra futura y lead perdido, por destino.
    "reactivacion",  # Desde compra futura o lead perdido a En seguimiento.
})

_CAMPOS_DATOS = {
    "contacto_externo_confirmado": frozenset({
        "confirmado", "medio", "fecha_contacto", "observacion",
    }),
    "cotizacion_confirmada": frozenset({
        "confirmado", "fecha_envio", "vehiculo", "referencia", "archivo_id",
    }),
    "cita_registrada": frozenset({"confirmado"}),
    "asistencia_confirmada": frozenset({"confirmado", "fecha_asistencia_real", "fecha_hora_cita", "sucursal"}),
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
        if evento == "contacto_externo_confirmado":
            if datos.get("confirmado") is not True:
                raise serializers.ValidationError({"datos": "Confirma el contacto real antes de avanzar."})
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
                    "datos": "La acción permite autorización, compra futura y lead perdido."
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
        hay_cita = attrs.get("cita_id") is not None
        if evento == "cita_registrada" and not hay_cita:
            raise serializers.ValidationError({"cita_id": "Primero debe seleccionarse o guardarse la cita del prospecto."})
        if evento == "asistencia_confirmada":
            captura_historica = "fecha_hora_cita" in datos or "sucursal" in datos
            if hay_cita and captura_historica:
                raise serializers.ValidationError({"datos": "La fecha histórica solo se captura si no existe una cita vinculada."})
            if not hay_cita and not (datos.get("fecha_hora_cita") and datos.get("sucursal")):
                raise serializers.ValidationError({"datos": "Para una asistencia histórica sin cita, registra fecha, hora y sucursal programadas."})
        if evento not in {"cita_registrada", "asistencia_confirmada"} and hay_cita:
            raise serializers.ValidationError({"cita_id": "Este evento no admite referencias a citas."})
        return attrs


def _agencia_clave(valor):
    """Normaliza el nombre de la agencia sin inferir divisiones."""
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(texto.casefold().split())


def _agencias_usuario(usuario):
    agencias = {
        _agencia_clave(a)
        for a in str(usuario.agencia or "").split("|")
        if a.strip()
    }

    # Acceso explícito a la división de seminuevos/usados.
    equivalencias = {
        "vw cordoba": {"vw cordoba usados"},
        "vw orizaba": {"vw orizaba usados"},
    }

    autorizadas = set(agencias)

    for agencia in agencias:
        autorizadas.update(equivalencias.get(agencia, set()))

    return autorizadas


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


def _permisos_efectivos_v3(usuario):
    # Los permisos salen de la BD usando la política existente del CRM;
    # jamás de claims JWT enviados por el navegador.
    return set(permisos_por_usuario(usuario))


def _usuario_con_permiso_comercial_v3(usuario):
    """Autoriza por ROL + permisos reales, no solo por una interfaz visible.

    Algunos asesores tienen `interfaces` configuradas manualmente. La interfaz
    `comercial` o el submódulo `comercial:bandeja` dan acceso explícito a la
    bandeja, pero el catálogo legacy puede emitir CRM_COORDINADOR_DIGITAL.
    NUNCA se interpreta ese permiso como rol supervisor para un asesor.
    """
    if not usuario or not getattr(usuario, "is_authenticated", False):
        return False
    rol = _rol_clave_usuario(usuario)
    permisos = _permisos_efectivos_v3(usuario)
    if rol in {"admin", "administrador"}:
        return "ALL" in permisos
    if rol == "coordinador digital":
        return "CRM_COORDINADOR_DIGITAL" in permisos
    if rol in {"asesor digital", "asesor general"}:
        if "CRM_DIGITALES" in permisos:
            return True
        interfaces = getattr(usuario, "interfaces", None)
        return isinstance(interfaces, list) and any(
            clave in interfaces for clave in ("comercial", "comercial:bandeja")
        )
    return False


def _es_admin_o_coordinador_digital(usuario):
    # Misma política que utilizan los listados/chats de Digitales/views.py.
    return puede_supervisar_comercial(usuario)


def _usuario_en_piloto_o_general(usuario):
    # La lista de pilotos solo restringe más; nunca concede permisos.
    if not _usuario_con_permiso_comercial_v3(usuario):
        return False
    ids_piloto = {
        str(valor).strip() for valor in (
            getattr(settings, "CRM_ETAPAS_V3_USUARIOS_PILOTO_IDS", ()) or ()
        ) if str(valor).strip()
    }
    if not ids_piloto or "*" in ids_piloto:
        return True
    return str(usuario.pk) in ids_piloto



def _identidad_asesor_legacy_v3(usuario):
    """Alias V3 explicitamente aprobado + linea individual en el perfil CRM.

    Retorna (nombre_comercial, linea, agencias_validas), o None.
    No escribe expedientes, no concede acceso por un nombre libre y nunca
    interpreta una linea compartida como prueba de titularidad individual.
    """
    if not getattr(settings, "CRM_ETAPAS_V3_API_HABILITADA", False):
        return None
    if not _usuario_en_piloto_o_general(usuario):
        return None
    if _rol_clave_usuario(usuario) not in {"asesor digital", "asesor general"}:
        return None

    mapa = getattr(settings, "CRM_ETAPAS_V3_ASESORES_LEGACY", {}) or {}
    if not isinstance(mapa, dict):
        return None
    nombre = str(mapa.get(usuario.pk, mapa.get(str(usuario.pk), "")) or "").strip()
    if not nombre:
        return None

    # Una identidad historica no debe estar asignada a dos cuentas.
    if sum(_agencia_clave(v) == _agencia_clave(nombre) for v in mapa.values()) != 1:
        return None

    telefonos = {
        normaliza_tel_mx(parte)
        for parte in re.split(r"[|,;\n]+", str(getattr(usuario, "telefono", "") or ""))
        if parte.strip()
    }
    telefonos.discard("")
    if not telefonos:
        return None

    agencias_usuario = _agencias_usuario(usuario)
    candidatas = []
    for numero, cfg in WHATSAPP_LINES.items():
        # No emplear equivalencias de nombres sobre reparto entre asesores.
        if not isinstance(cfg, dict) or cfg.get("asesores"):
            continue
        linea = normaliza_tel_mx(numero)
        if not linea or linea not in telefonos:
            continue
        if _agencia_clave(cfg.get("asesor_digital")) != _agencia_clave(nombre):
            continue

        agencia_linea = _agencia_clave(cfg.get("agencia"))
        agencias_linea = {agencia_linea} if agencia_linea else set()
        if agencia_linea == "vw cordoba":
            agencias_linea.add("vw cordoba usados")
        elif agencia_linea == "vw orizaba":
            agencias_linea.add("vw orizaba usados")
        agencias_linea.intersection_update(agencias_usuario)
        if agencias_linea:
            candidatas.append((nombre, linea, frozenset(agencias_linea)))

    # Denegar cuando hay mas de una linea candidata.
    return candidatas[0] if len(candidatas) == 1 else None


def _autorizado_alias_legacy_v3(usuario, expediente, agencia):
    """Compatibilidad V3 solo para expedientes sin login CRM ya asignado."""
    if not expediente.cliente_id or str(expediente.usuario_crm_asignado or "").strip():
        return False
    identidad = _identidad_asesor_legacy_v3(usuario)
    if identidad is None:
        return False
    nombre, linea, agencias = identidad
    if agencia not in agencias or _agencia_clave(expediente.asesor_digital) != _agencia_clave(nombre):
        return False
    # No inferir propiedad con una linea si el cliente tambien tiene mensajes
    # en otra. Los casos manuales sin mensajes son posibles bajo alias explicito.
    return not MensajeWhatsApp.objects.filter(
        cliente_id=expediente.cliente_id
    ).exclude(numero_asesor=linea).exists()

def _resolver_propietario_historico_v3(expediente, agencia):
    """Devuelve el usuario CRM único de un expediente histórico, o "".

    Los mensajes identifican líneas del CLIENTE, no necesariamente la línea
    responsable de cada EXPEDIENTE. Una línea ajena no invalida la evidencia
    positiva de una línea individual propia. Una línea compartida, por sí
    sola, nunca prueba que un expediente sin asignación tenga propietario.
    La función no modifica ningún registro.
    """
    if not expediente.cliente_id or not _agencia_clave(expediente.asesor_digital):
        return ""

    responsable = _agencia_clave(expediente.asesor_digital)
    candidatos = []
    for cuenta in Usuario.objects.select_related("rol").all():
        if _rol_clave_usuario(cuenta) not in {"asesor general", "asesor digital"}:
            continue
        if agencia not in _agencias_usuario(cuenta):
            continue
        if _agencia_clave(f"{cuenta.nombre or ''} {cuenta.apellidos or ''}") != responsable:
            continue
        if not _usuario_con_permiso_comercial_v3(cuenta):
            continue
        candidatos.append(str(cuenta.usuario or "").strip())
        if len(candidatos) > 1:
            return ""
    if len(candidatos) != 1 or not candidatos[0]:
        return ""
    candidato = candidatos[0]

    numeros = (MensajeWhatsApp.objects.filter(cliente_id=expediente.cliente_id)
               .exclude(numero_asesor__isnull=True)
               .exclude(numero_asesor="")
               .values_list("numero_asesor", flat=True).distinct())
    lineas = {normaliza_tel_mx(numero) for numero in numeros if numero}
    lineas.discard("")
    if not lineas:
        # Un histórico sin líneas asociadas mantiene la compatibilidad
        # anterior: identidad inequívoca por nombre completo + agencia.
        return candidato

    # Una etapa V3 homologada no invalida la titularidad historica. Exigir
    # evidencia POSITIVA de una linea individual vinculada a la cuenta CRM.
    # Las otras lineas del cliente no conceden acceso a sus asesoras.

    for numero in lineas:
        # Una línea con reparto entre varios asesores carece de evidencia
        # de titularidad individual sin usuario_crm_asignado explícito.
        if len(obtener_asesores_activos(numero)) > 1:
            continue
        login_linea = resolver_usuario_crm_por_linea(
            numero, expediente.asesor_digital, expediente.agencia
        )
        if login_linea and login_linea.strip().casefold() == candidato.casefold():
            return candidato
    return ""


def _autorizado_historico_sin_whatsapp(usuario, expediente, agencia):
    """Compatibilidad para históricos no asignados, sin dar acceso por nombre libre."""
    propietario = _resolver_propietario_historico_v3(expediente, agencia)
    login = str(getattr(usuario, "usuario", "") or "").strip()
    return bool(propietario and login and propietario.casefold() == login.casefold())

def _autorizado_legacy_por_linea(usuario, expediente, agencia):
    """Identifica al dueño histórico usando una sola línea WhatsApp verificable.

    Prioridad: configuración actual inequívoca + cuenta CRM real. Conserva la
    equivalencia administrativa antigua únicamente como fallback explícito en
    líneas individuales. Nunca escribe el expediente ni permite línea ambigua.
    """
    if not expediente.cliente_id:
        return False
    numeros = MensajeWhatsApp.objects.filter(cliente_id=expediente.cliente_id).exclude(
        numero_asesor__isnull=True
    ).exclude(numero_asesor="").values_list("numero_asesor", flat=True).distinct()
    lineas = {normaliza_tel_mx(numero) for numero in numeros if numero}
    lineas.discard("")
    if len(lineas) != 1:
        return False
    numero = next(iter(lineas))
    configuracion = WHATSAPP_LINES.get(numero)
    if not isinstance(configuracion, dict):
        return False
    agencia_linea = _agencia_clave(configuracion.get("agencia"))
    equivalencias = {
        "vw cordoba": {"vw cordoba", "vw cordoba usados"},
        "vw orizaba": {"vw orizaba", "vw orizaba usados"},
    }
    if agencia not in equivalencias.get(agencia_linea, {agencia_linea}):
        return False

    identificador = str(getattr(usuario, "usuario", "") or "").strip().casefold()
    if not identificador:
        return False

    # Funciona para líneas individuales y compartidas únicamente cuando el
    # nombre y la cuenta están vinculados de forma inequívoca en su configuración.
    login_resuelto = resolver_usuario_crm_por_linea(
        numero, expediente.asesor_digital, agencia
    )
    if login_resuelto:
        return login_resuelto.casefold() == identificador

    # Compatibilidad explícita con excepciones históricas preexistentes.
    # Solo en líneas INDIVIDUALES; nunca amplía el acceso de reparto compartido.
    if obtener_asesores_activos(numero):
        return False
    mapa = getattr(settings, "CRM_ETAPAS_V3_ASESORES_LEGACY", {}) or {}
    if not isinstance(mapa, dict):
        return False
    nombre_esperado = str(mapa.get(usuario.pk, mapa.get(str(usuario.pk), "")) or "").strip()
    if not nombre_esperado:
        return False
    return (
        _agencia_clave(expediente.asesor_digital) == _agencia_clave(nombre_esperado)
        and _agencia_clave(configuracion.get("asesor_digital")) == _agencia_clave(nombre_esperado)
    )


def _autorizado(usuario, expediente):
    if not _usuario_en_piloto_o_general(usuario):
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
    # Sin agencias habilitadas: denegar todo (fail closed).
    if not habilitadas or not agencia or agencia not in habilitadas or agencia not in _agencias_usuario(usuario):
        return False

    es_supervisor = _es_admin_o_coordinador_digital(usuario)
    asignado = str(expediente.usuario_crm_asignado or "").strip().casefold()
    identificador = str(getattr(usuario, "usuario", "") or getattr(usuario, "username", "") or "").strip().casefold()
    if es_supervisor:
        return True
    if asignado:
        return asignado == identificador
    return (_autorizado_historico_sin_whatsapp(usuario, expediente, agencia)
            or _autorizado_legacy_por_linea(usuario, expediente, agencia)
            or _autorizado_alias_legacy_v3(usuario, expediente, agencia))


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
        return _error("usuario_no_autorizado", "El usuario no tiene autorización para gestionar etapas comerciales.", status.HTTP_403_FORBIDDEN)

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
                          .only("id", "cliente_id", "agencia", "asesor_digital", "usuario_crm_asignado", "etapa_comercial_v3")
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
