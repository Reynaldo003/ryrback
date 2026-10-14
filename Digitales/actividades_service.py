"""Persistencia transaccional CRM V3 (escrituras autenticadas del piloto).

Ubicacion: Digitales/actividades_service.py
Requiere migraciones locales citas.0014, Digitales.0034 y Digitales.0035.

GARANTIAS:
* No modifica ExpedienteDigital.estado ni reinterpreta expedientes V3=NULL.
* El responsable se toma de un actor autenticado del backend, NO del payload.
* Bloquea el expediente con select_for_update y usa una transaccion atomica.
* Guarda actividad, cambio V3 y bitacora en la misma transaccion.
* La clave de idempotencia evita duplicados por reintentos.
* No ofrece aun endpoints publicos ni habilita facturacion/correcciones sin fuente
  y permisos de servidor verificables.

NO LLAMAR desde vistas con AllowAny. Antes de conectar a React hace falta un
endpoint autenticado con permisos por agencia y procedencia verificable de
los eventos. La autorizacion comercial especifica aun no esta resuelta aqui.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from citas.models import Cita, normaliza_tel_mx
from .etapas_service import evaluar_transicion
from .models import (
    ActividadComercialDigital,
    BitacoraAsesorDigital,
    ExpedienteDigital,
    MensajeWhatsApp,
)


class ErrorActividadComercial(ValueError):
    """Rechazo sin escritura parcial. `codigo` es apto para la futura API."""

    def __init__(self, codigo: str, mensaje: str):
        self.codigo = codigo
        super().__init__(mensaje)


@dataclass(frozen=True)
class ResultadoRegistro:
    actividad_id: int
    etapa_anterior: str | None
    etapa_resultante: str
    cambio_etapa: bool
    duplicado: bool
    codigo: str


# Eventos cuyos datos podemos validar contra el modelo o una confirmacion
# realizada por un usuario autenticado. El resto queda DESHABILITADO.
_TIPOS_EVENTO = {
    "respuesta_humana_registrada": "seguimiento",
    "cotizacion_confirmada": "cotizacion_enviada",
    "cita_registrada": "cita_agendada",
    "asistencia_confirmada": "cita_asistida",
    "documentos_recibidos_confirmados": "documentos_recibidos",
    "vin_facturado_registrado": "factura_registrada",  # Etiqueta histórica, evidencia VIN comercial.
    "reactivacion": "reactivacion",
}

_ORIGEN_EVENTO = {
    "respuesta_humana_registrada": "automatico",
    "cotizacion_confirmada": "registro_manual",
    "cita_registrada": "registro_manual",
    "asistencia_confirmada": "registro_manual",
    "documentos_recibidos_confirmados": "registro_manual",
    "vin_facturado_registrado": "automatico",
    "seleccion_manual": "seleccion_manual",
    "reactivacion": "seleccion_manual",
}

_TIPOS_SELECCION = {
    "autorizado_no_formalizado": "credito_autorizado",
    "compra_futura": "compra_futura",
    "lead_perdido": "lead_perdido",
}

_PATRON_CLAVE = re.compile(r"^[a-zA-Z0-9._:\-]{8,120}$")
_PATRON_VIN = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")

# Catálogo fiel a la propuesta comercial; no admite motivos libres en HTTP.
MOTIVOS_LEAD_PERDIDO_V3 = {
    'no_responde': 'No responde',
    'numero_incorrecto': 'Número incorrecto / inexistente',
    'bloqueo_contacto': 'Bloqueó el contacto',
    'compro_otra_marca': 'Compró en otra marca',
    'compro_otra_agencia_vw': 'Compró en otra agencia VW',
    'sin_interes': 'Ya no está interesado',
    'precio_fuera_presupuesto': 'Precio fuera de presupuesto',
    'no_acepta_toma': 'No acepta oferta de toma',
    'mal_buro_credito': 'Mal Buró de Crédito',
    'sin_ingresos_comprobables': 'Sin ingresos comprobables',
    'credito_rechazado': 'Crédito rechazado',
    'enganche_insuficiente': 'Enganche insuficiente',
    'mensualidad_fuera_presupuesto': 'Mensualidad fuera de presupuesto',
    'vehiculo_no_disponible': 'Vehículo no disponible',
    'version_color_no_disponible': 'Versión o color no disponible',
    'tiempo_entrega_no_aceptado': 'No acepta tiempo de entrega',
    'otra_area_empresa': 'Otra área de la empresa',
    'registro_duplicado': 'Registro duplicado',
    'spam': 'Spam',
    'otro_motivo': 'Otro motivo (especificar)',
}


def _texto(valor: Any, maximo: int = 255) -> str:
    return str(valor or "").strip()[:maximo]


def _actor_autenticado(actor: Any) -> str:
    if actor is None or getattr(actor, "is_authenticated", False) is not True:
        raise ErrorActividadComercial("no_autenticado", "Se requiere un usuario CRM autenticado.")
    usuario = _texto(
        getattr(actor, "usuario", "")
        or getattr(actor, "username", "")
        or getattr(actor, "email", ""),
        120,
    )
    if not usuario:
        raise ErrorActividadComercial("usuario_no_identificado", "El usuario autenticado no tiene identificador.")
    return usuario


def _hoy_local() -> date:
    return datetime.now(ZoneInfo(settings.TIME_ZONE)).date()


def _fecha(valor: Any, campo: str, *, no_futura: bool = False) -> date:
    if isinstance(valor, datetime):
        fecha = valor.date()
    elif isinstance(valor, date):
        fecha = valor
    elif isinstance(valor, str):
        try:
            fecha = date.fromisoformat(valor.strip())
        except ValueError as exc:
            raise ErrorActividadComercial("fecha_invalida", f"{campo}: fecha ISO inválida.") from exc
    else:
        raise ErrorActividadComercial("fecha_invalida", f"{campo}: fecha obligatoria.")
    if no_futura and fecha > _hoy_local():
        raise ErrorActividadComercial("fecha_futura", f"{campo} no puede ser futura.")
    return fecha


def _identidad_cita(expediente: ExpedienteDigital, cita: Cita) -> None:
    if cita.cliente_id != expediente.cliente_id:
        raise ErrorActividadComercial("cita_otro_cliente", "La cita no corresponde al cliente del expediente.")
    if not cita.agencia or not expediente.agencia or cita.agencia.strip().casefold() != expediente.agencia.strip().casefold():
        raise ErrorActividadComercial("agencia_no_coincide", "La agencia de la cita no coincide con la del expediente.")


def _obtener_cita_bloqueada(expediente: ExpedienteDigital, cita_id: Any) -> Cita:
    if isinstance(cita_id, bool) or not str(cita_id or "").isdigit():
        raise ErrorActividadComercial("cita_invalida", "Se requiere el ID de una cita existente.")
    cita = Cita.objects.select_for_update().filter(pk=int(cita_id)).first()
    if cita is None:
        raise ErrorActividadComercial("cita_inexistente", "No se encontró la cita.")
    _identidad_cita(expediente, cita)
    return cita


def _preparar(
    *, expediente: ExpedienteDigital, evento: str, datos: Mapping[str, Any],
    cita_id: int | None,
) -> tuple[dict, str, str, date | None, datetime | None, Cita | None]:
    """Solo construir datos a partir de valores permitidos y relaciones verificadas.

    Retorna: payload para motor, tipo, origen, fecha negocio, fecha/hora, cita.
    """
    origen = _ORIGEN_EVENTO[evento]
    cita = None
    fecha_actividad: date | None = None
    fecha_hora: datetime | None = None

    if evento == "vin_facturado_registrado":
        # No usar datos enviados por React: leer solamente el expediente ya guardado.
        vin = str(expediente.vin_facturado or "").strip().upper()
        if not _PATRON_VIN.fullmatch(vin) or not expediente.facturado_at:
            raise ErrorActividadComercial(
                "vin_facturacion_no_valida", "Se requiere un VIN de 17 caracteres y fecha operativa persistidos."
            )
        fecha_actividad = _hoy_local()  # Fecha de captura, NO fecha fiscal del CFDI.
        fecha_hora = timezone.now()
        payload = {
            "registrado": True,
            "fecha_registro_vin": fecha_actividad.isoformat(),
            "vehiculo": vin,
            "fuente": "crm_vin_facturado",
        }
        return payload, _TIPOS_EVENTO[evento], origen, fecha_actividad, fecha_hora, None

    if evento == "respuesta_humana_registrada":
        mensaje_id = datos.get("mensaje_id")
        if isinstance(mensaje_id, bool) or not str(mensaje_id or "").isdigit():
            raise ErrorActividadComercial("mensaje_invalido", "Se requiere un mensaje registrado.")
        mensaje = MensajeWhatsApp.objects.filter(pk=int(mensaje_id)).first()
        if not mensaje or mensaje.direction != "out" or mensaje.from_ia is not False:
            raise ErrorActividadComercial("mensaje_no_humano", "No existe un mensaje saliente humano válido.")
        if ((mensaje.cliente_id is not None and mensaje.cliente_id != expediente.cliente_id)
                or (mensaje.cliente_id is None and
                    normaliza_tel_mx(mensaje.telefono) != expediente.cliente.telefono)):
            raise ErrorActividadComercial("mensaje_otro_cliente", "El mensaje no corresponde al cliente.")
        if mensaje.status.strip().casefold() in {"failed", "error", "deleted"}:
            raise ErrorActividadComercial("mensaje_fallido", "El mensaje no fue enviado correctamente.")
        fecha_hora = mensaje.created_at
        fecha_actividad = mensaje.created_at.date()
        payload = {
            "mensaje_id": mensaje.pk, "direccion": "out", "es_humano": True,
            "registrado": True,
        }
        return payload, _TIPOS_EVENTO[evento], origen, fecha_actividad, fecha_hora, cita

    if evento == "cotizacion_confirmada":
        if datos.get("confirmado") is not True:
            raise ErrorActividadComercial("confirmacion_requerida", "La cotización requiere confirmación explícita.")
        fecha_actividad = _fecha(datos.get("fecha_envio"), "fecha_envio", no_futura=True)
        vehiculo = _texto(datos.get("vehiculo"))
        referencia = _texto(datos.get("referencia"), 120)
        archivo_id = _texto(datos.get("archivo_id"), 120)
        payload = {"confirmado": True, "fecha_envio": fecha_actividad.isoformat(),
                   "vehiculo": vehiculo, "referencia": referencia, "archivo_id": archivo_id}
        return payload, _TIPOS_EVENTO[evento], origen, fecha_actividad, None, None

    if evento in {"cita_registrada", "asistencia_confirmada"}:
        if datos.get("confirmado") is not True:
            raise ErrorActividadComercial("confirmacion_requerida", "La operación de cita debe confirmarse explícitamente.")
        cita = _obtener_cita_bloqueada(expediente, cita_id)
        if evento == "cita_registrada":
            if cita.estado_asistencia not in (None, "pendiente") or cita.asistencia:
                raise ErrorActividadComercial(
                    "cita_ya_clasificada", "Esta cita ya tiene asistencia clasificada."
                )
            if cita.fecha_hora_cita is None:
                raise ErrorActividadComercial("sin_fecha_cita", "La cita no tiene fecha y hora.")
            # Fecha/hora del evento = momento del registro, NO momento futuro
            # de la visita. La fecha programada vive en Cita.fecha_hora_cita.
            fecha_actividad = _hoy_local()
            fecha_hora = timezone.now()
            payload = {"confirmado": True, "cita_id": cita.pk,
                       "fecha_hora_cita": cita.fecha_hora_cita.isoformat(),
                       "sucursal": cita.agencia}
        else:
            if cita.estado_asistencia not in (None, "pendiente") or cita.asistencia:
                raise ErrorActividadComercial("asistencia_ya_registrada",
                                            "La asistencia ya fue clasificada; corregir exige un procedimiento específico.")
            # No aceptar una visita de otra cita del mismo cliente: debe estar
            # vinculada expresamente al expediente mediante la actividad V3.
            # Cita vinculada mediante el flujo nuevo V3.
            vinculada_v3 = ActividadComercialDigital.objects.filter(
                expediente_id=expediente.pk,
                cita_id=cita.pk,
                detalle__evento="cita_registrada",
            ).exists()

            # Excepción controlada para citas heredadas del CRM anterior.
            # La homologación no crea una vinculación ficticia:
            # se exige que el expediente identifique esta cita exacta.
            vinculada_historica = (
                expediente.etapa_comercial_v3 == "cita_agendada"
                and expediente.ultima_cita_id == cita.pk
                and ActividadComercialDigital.objects.filter(
                    expediente_id=expediente.pk,
                    etapa_resultante="cita_agendada",
                    detalle__evento="homologacion_historica_v3",
                ).exists()
            )

            if not (vinculada_v3 or vinculada_historica):
                raise ErrorActividadComercial(
                    "cita_no_vinculada_v3",
                    "La cita debe estar vinculada al expediente mediante "
                    "el flujo V3 o mediante su referencia histórica."
                )
            # Las citas futuras siguen pendientes: la sola programación nunca
            # constituye prueba de asistencia. Normalizar fecha-hora legacy naive.
            if cita.fecha_hora_cita is None:
                raise ErrorActividadComercial("sin_fecha_cita", "La cita no tiene fecha programada.")
            zona = ZoneInfo(settings.TIME_ZONE)
            programada = cita.fecha_hora_cita
            if timezone.is_naive(programada):
                programada = timezone.make_aware(programada, zona)
            programada_local = programada.astimezone(zona)
            if programada_local > datetime.now(zona):
                raise ErrorActividadComercial(
                    "cita_aun_no_ocurre", "La cita programada todavía no sucede; no es posible confirmar asistencia."
                )
            fecha_actividad = _fecha(datos.get("fecha_asistencia_real"),
                                     "fecha_asistencia_real", no_futura=True)
            if fecha_actividad < programada_local.date():
                raise ErrorActividadComercial(
                    "asistencia_antes_de_cita", "La fecha de asistencia es anterior al día programado."
                )
            payload = {"confirmado": True, "cita_id": cita.pk, "asistio": True,
                       "fecha_asistencia_real": fecha_actividad.isoformat()}
        return payload, _TIPOS_EVENTO[evento], origen, fecha_actividad, fecha_hora, cita

    if evento == "documentos_recibidos_confirmados":
        if datos.get("confirmado") is not True:
            raise ErrorActividadComercial("confirmacion_requerida", "La recepción de documentos requiere confirmación explícita.")
        fecha_actividad = _fecha(datos.get("fecha_recepcion"), "fecha_recepcion", no_futura=True)
        bruto = datos.get("documentos")
        if not isinstance(bruto, (list, tuple)) or not 1 <= len(bruto) <= 30:
            raise ErrorActividadComercial("documentos_invalidos", "Indica una lista de 1 a 30 documentos.")
        documentos = [_texto(doc, 160) for doc in bruto]
        if not all(documentos):
            raise ErrorActividadComercial("documentos_invalidos", "Los documentos no pueden estar vacíos.")
        payload = {"confirmado": True, "fecha_recepcion": fecha_actividad.isoformat(),
                   "documentos": documentos}
        return payload, _TIPOS_EVENTO[evento], origen, fecha_actividad, None, None

    if evento == "seleccion_manual":
        destino = _texto(datos.get("etapa_destino"), 40)
        from .etapas_crm_v3 import normalizar_etapa
        clave = normalizar_etapa(destino)
        if clave not in _TIPOS_SELECCION:
            raise ErrorActividadComercial("etapa_manual_invalida", "La selección no está habilitada.")
        payload = {"etapa_destino": clave}
        if clave == "autorizado_no_formalizado":
            # Confirmación independiente del formulario financiero histórico:
            # la asesora declara que recibió evidencia de autorización.
            if datos.get("confirmado") is not True or datos.get("credito_autorizado") is not True:
                raise ErrorActividadComercial(
                    "confirmacion_requerida", "Confirma expresamente que el crédito fue autorizado."
                )
            fecha_actividad = _fecha(datos.get("fecha_autorizacion"),
                                     "fecha_autorizacion", no_futura=True)
            referencia_bruta = datos.get("referencia_autorizacion")
            if not isinstance(referencia_bruta, str) or not (1 <= len(referencia_bruta.strip()) <= 120):
                raise ErrorActividadComercial(
                    "referencia_requerida", "Indica una referencia de autorización de 1 a 120 caracteres."
                )
            if any(ord(c) < 32 for c in referencia_bruta):
                raise ErrorActividadComercial("referencia_invalida", "La referencia contiene caracteres no permitidos.")
            payload.update({
                "credito_autorizado": True,
                "confirmado": True,
                "fecha_autorizacion": fecha_actividad.isoformat(),
                "referencia_autorizacion": referencia_bruta.strip(),
            })
        elif clave == "compra_futura":
            if datos.get("confirmado") is not True:
                raise ErrorActividadComercial(
                    "confirmacion_requerida", "Confirma la intención de compra futura del prospecto."
                )
            prevista = _fecha(datos.get("fecha_prevista_compra"), "fecha_prevista_compra")
            contacto = _fecha(datos.get("proximo_contacto"), "proximo_contacto")
            if prevista <= _hoy_local() or contacto <= _hoy_local():
                raise ErrorActividadComercial(
                    "fecha_no_futura", "La compra prevista y el próximo contacto deben ser posteriores a hoy."
                )
            if contacto > prevista:
                raise ErrorActividadComercial(
                    "contacto_posterior_compra", "El próximo contacto no debe ser después de la compra prevista."
                )
            observacion = datos.get("observacion")
            if not isinstance(observacion, str) or not 1 <= len(observacion.strip()) <= 1000:
                raise ErrorActividadComercial(
                    "observacion_requerida", "Escribe una observación de 1 a 1000 caracteres."
                )
            if any(ord(c) < 32 and c not in "\n\r\t" for c in observacion):
                raise ErrorActividadComercial("observacion_invalida", "La observación contiene caracteres no válidos.")
            payload.update({
                "confirmado": True,
                "fecha_prevista_compra": prevista.isoformat(),
                "proximo_contacto": contacto.isoformat(),
                "observacion": observacion.strip(),
            })
        elif clave == "lead_perdido":
            if datos.get("confirmado") is not True:
                raise ErrorActividadComercial(
                    "confirmacion_requerida", "Confirma expresamente que se descartará el prospecto."
                )
            motivo = datos.get("motivo")
            if not isinstance(motivo, str) or motivo not in MOTIVOS_LEAD_PERDIDO_V3:
                raise ErrorActividadComercial(
                    "motivo_invalido", "Selecciona un motivo del catálogo de descarte."
                )
            detalle = datos.get("detalle_motivo", "")
            if not isinstance(detalle, str) or len(detalle.strip()) > 1000:
                raise ErrorActividadComercial(
                    "detalle_motivo_invalido", "La explicación debe ser texto de hasta 1000 caracteres."
                )
            if any(ord(c) < 32 and c not in "\n\r\t" for c in detalle):
                raise ErrorActividadComercial("detalle_motivo_invalido", "La explicación contiene caracteres no permitidos.")
            if motivo == "otro_motivo" and len(detalle.strip()) < 5:
                raise ErrorActividadComercial(
                    "detalle_motivo_requerido", "Para Otro motivo explica la pérdida en al menos 5 caracteres."
                )
            payload.update({
                "confirmado": True, "motivo": motivo,
                "motivo_etiqueta": MOTIVOS_LEAD_PERDIDO_V3[motivo],
                "detalle_motivo": detalle.strip(),
            })
        return payload, _TIPOS_SELECCION[clave], origen, fecha_actividad or _hoy_local(), None, None

    if evento == "reactivacion":
        from .etapas_crm_v3 import normalizar_etapa
        if datos.get("confirmado") is not True:
            raise ErrorActividadComercial("confirmacion_requerida", "Confirma la reactivación del seguimiento.")
        motivo = datos.get("motivo")
        if not isinstance(motivo, str) or not 5 <= len(motivo.strip()) <= 1000:
            raise ErrorActividadComercial("motivo_requerido", "Explica la reactivación en 5 a 1000 caracteres.")
        payload = {"motivo": motivo.strip(),
                   "etapa_destino": normalizar_etapa(datos.get("etapa_destino") or "en_seguimiento")}
        return payload, _TIPOS_EVENTO[evento], origen, _hoy_local(), None, None

    raise ErrorActividadComercial("evento_desactivado", "Este evento aún no está integrado con una fuente comprobable.")


def _guardar_bitacora(
    *, expediente: ExpedienteDigital, usuario_crm: str, evento: str,
    actividad: ActividadComercialDigital | None, anterior: str | None, resultante: str,
) -> None:
    BitacoraAsesorDigital.objects.create(
        expediente=expediente,
        cliente=expediente.cliente,
        asesor_digital=expediente.asesor_digital,
        usuario_crm=usuario_crm,
        numero_asesor="",
        tipo="actualizacion",
        accion="Actividad comercial CRM V3" if actividad else "Alta en flujo comercial CRM V3",
        detalle=f"{evento}: {anterior or 'sin etapa V3'} -> {resultante}"[:1000],
        resultado="no_aplica",
        metadata={
            "grupo_tipo": "operativo", "grupo_resultado": "no_aplica",
            "tipo_label": "Actualización de prospecto", "resultado_label": "No aplica",
            "crm_etapas_version": 3, "evento": evento,
            "actividad_id": actividad.pk if actividad else None,
            "etapa_anterior": anterior, "etapa_resultante": resultante,
        },
    )


def registrar_actividad_v3(
    *, expediente_id: int, evento: str, datos: Mapping[str, Any] | None,
    actor: Any, clave_idempotencia: str, cita_id: int | None = None,
) -> ResultadoRegistro:
    """Guarda una actividad comercial y, si procede, su avance V3, atómicamente.

    `actor` DEBE ser el usuario autenticado obtenido por el backend.
    `clave_idempotencia` DEBE ser estable entre reintentos del mismo evento.
    No existe ruta HTTP por defecto; falta autorizacion por agencia en la vista.
    """
    usuario = _actor_autenticado(actor)
    evento = str(evento or "").strip()
    if evento not in _ORIGEN_EVENTO:
        raise ErrorActividadComercial("evento_no_habilitado", "El evento todavía no admite escritura V3.")
    if not isinstance(clave_idempotencia, str) or not _PATRON_CLAVE.fullmatch(clave_idempotencia):
        raise ErrorActividadComercial("idempotencia_invalida", "Usa una clave estable de 8 a 120 caracteres.")
    if datos is None:
        datos = {}
    if not isinstance(datos, Mapping):
        raise ErrorActividadComercial("datos_invalidos", "Los datos deben ser un objeto.")
    if isinstance(expediente_id, bool) or not str(expediente_id).isdigit():
        raise ErrorActividadComercial("expediente_invalido", "Identificador de expediente inválido.")

    # La identidad del intento se verifica en los reintentos: la misma clave
    # NO puede reutilizarse con otra cita, otro payload u otro expediente.
    entrada = json.dumps({"evento": evento, "cita_id": cita_id, "datos": dict(datos)},
                         sort_keys=True, ensure_ascii=False, default=str)
    if len(entrada) > 6000:
        raise ErrorActividadComercial("datos_demasiado_grandes", "Los datos superan el límite de 6000 caracteres.")
    firma_operacion = hashlib.sha256(entrada.encode("utf-8")).hexdigest()

    with transaction.atomic(using="default"):
        expediente = (
            ExpedienteDigital.objects.select_for_update()
            .select_related("cliente")
            .filter(pk=int(expediente_id)).first()
        )
        if expediente is None:
            raise ErrorActividadComercial("expediente_inexistente", "No se encontró el expediente.")
        if expediente.etapa_comercial_v3 is None:
            raise ErrorActividadComercial("flujo_v3_no_iniciado",
                                        "El expediente todavía no está incorporado al flujo V3.")
        if not expediente.agencia.strip():
            raise ErrorActividadComercial("agencia_sin_asignar", "Se requiere una agencia en el expediente.")

        existente = ActividadComercialDigital.objects.filter(clave_idempotencia=clave_idempotencia).first()
        if existente:
            if (existente.expediente_id != expediente.pk
                    or existente.usuario_crm != usuario
                    or (existente.detalle or {}).get("evento") != evento
                    or (existente.detalle or {}).get("firma_operacion") != firma_operacion
                    or existente.cita_id != (int(cita_id) if str(cita_id or "").isdigit() else None)):
                raise ErrorActividadComercial("idempotencia_en_conflicto", "La clave ya se utilizó para otra operación.")
            return ResultadoRegistro(
                existente.pk, existente.etapa_anterior or None,
                existente.etapa_resultante, existente.etapa_anterior != existente.etapa_resultante,
                True, "reintento_idempotente",
            )

        payload, tipo, origen, fecha_negocio, hora_negocio, cita = _preparar(
            expediente=expediente, evento=evento, datos=datos, cita_id=cita_id,
        )
        decision = evaluar_transicion(expediente.etapa_comercial_v3, evento, datos=payload)
        if not decision.permitida or not decision.registrar_actividad or not decision.etapa_resultante:
            raise ErrorActividadComercial(decision.codigo, decision.detalle)

        # El registro de cita no cambia asistencia de una cita histórica;
        # para una cita sin clasificar se establece pendiente en la nueva capa.
        if cita is not None and evento == "cita_registrada":
            actualizar = []
            if cita.estado_asistencia is None and not cita.asistencia:
                cita.estado_asistencia = "pendiente"
                actualizar.append("estado_asistencia")
            if not cita.registrada_por_crm:
                cita.registrada_por_crm = usuario
                actualizar.append("registrada_por_crm")
            if actualizar:
                cita.save(update_fields=actualizar)
        elif cita is not None and evento == "asistencia_confirmada":
            cita.estado_asistencia = "asistio"
            cita.asistencia = True  # Compatibilidad temporal con pantallas antiguas.
            cita.fecha_asistencia_real = fecha_negocio
            cita.asistencia_confirmada_por = usuario
            cita.asistencia_confirmada_at = timezone.now()
            cita.save(update_fields=["estado_asistencia", "asistencia", "fecha_asistencia_real",
                                     "asistencia_confirmada_por", "asistencia_confirmada_at"])

        anterior = decision.etapa_anterior
        resultante = decision.etapa_resultante
        actividad = ActividadComercialDigital.objects.create(
            expediente=expediente,
            cita=cita,
            tipo=tipo,
            origen=origen,
            agencia=expediente.agencia.strip(),
            usuario_crm=usuario,
            asesor_digital=expediente.asesor_digital,
            fecha_actividad=fecha_negocio,
            fecha_hora_actividad=hora_negocio,
            vehiculo=_texto(payload.get("vehiculo")),
            folio=_texto(payload.get("referencia") or payload.get("referencia_autorizacion")
                         or payload.get("folio_factura"), 120),
            detalle={"evento": evento, "datos": payload, "decision": decision.codigo,
                     "firma_operacion": firma_operacion},
            etapa_anterior=anterior or "",
            etapa_resultante=resultante,
            clave_idempotencia=clave_idempotencia,
        )
        if decision.cambiar_etapa:
            ExpedienteDigital.objects.filter(pk=expediente.pk).update(
                etapa_comercial_v3=resultante,
                actualizado=timezone.now(),
            )
        _guardar_bitacora(
            expediente=expediente, usuario_crm=usuario, evento=evento,
            actividad=actividad, anterior=anterior, resultante=resultante,
        )
        return ResultadoRegistro(
            actividad.pk, anterior, resultante, decision.cambiar_etapa, False, decision.codigo,
        )
