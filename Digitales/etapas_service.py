"""Motor de decisiones de etapas comerciales, sin acceso a la base de datos.

Instalar en ``Digitales/etapas_service.py`` junto a ``etapas_crm_v3.py``.

Este módulo NO ejecuta transiciones, NO guarda actividades y NO escribe en la
bitácora. Solo decide si un evento VALIDADO por el backend podría cambiar la
etapa. La operación Django posterior deberá guardar actividad, etapa y auditoría
atómicamente, comprobar permisos y deduplicar eventos.

Convención importante:
    - ``automatico``: evento validado por el servidor (no por el navegador).
    - ``registro_manual``: botón confirmado por la asesora, actividad guardada.
    - ``seleccion_manual``: elección explícita de la asesora.
    - ``reactivacion`` y ``correccion``: operaciones explícitas y auditables.

La propuesta comercial distingue etapas de avance y etapas de situación
(``compra_futura`` / ``lead_perdido``). No se debe comparar su posición visual
como si todas representaran progreso lineal.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping

from .etapas_crm_v3 import obtener_etapa, normalizar_etapa


# Orden comercial de avance. Compra futura y Lead perdido NO son posiciones de
# este orden; su salida requiere una decisión explícita.
AVANCE_ETAPAS = (
    "nuevo_prospecto",
    "en_seguimiento",
    "cotizacion_enviada",
    "cita_agendada",
    "cita_asistida",
    "documentos_enviados",
    "autorizado_no_formalizado",
    "facturado",
)
NIVEL_AVANCE = {clave: indice for indice, clave in enumerate(AVANCE_ETAPAS)}
ETAPAS_SITUACION = frozenset({"compra_futura", "lead_perdido"})
ETAPAS_CERRADAS = frozenset({"lead_perdido", "facturado"})

# Evento externo -> etapa nueva, tipo exigido según catálogo V3.
REGLAS_EVENTO = {
    "alta_prospecto": ("nuevo_prospecto", "automatico"),
    "respuesta_humana_registrada": ("en_seguimiento", "automatico"),
    "cotizacion_confirmada": ("cotizacion_enviada", "registro_manual"),
    "cita_registrada": ("cita_agendada", "registro_manual"),
    "asistencia_confirmada": ("cita_asistida", "registro_manual"),
    "documentos_recibidos_confirmados": ("documentos_enviados", "registro_manual"),
    "factura_registrada": ("facturado", "automatico"),
    "vin_facturado_registrado": ("facturado", "automatico"),
}

# Solo estas tres etapas se pueden elegir mediante selección manual normal.
SELECCIONES_MANUALES = frozenset({
    "autorizado_no_formalizado", "compra_futura", "lead_perdido",
})


@dataclass(frozen=True)
class DecisionTransicion:
    permitida: bool
    cambiar_etapa: bool
    etapa_anterior: str | None   # Clave V3, no texto libre de base de datos.
    etapa_resultante: str | None # Clave V3, no texto libre de base de datos.
    codigo: str
    detalle: str
    registrar_actividad: bool = False


def _texto(valor: Any) -> str:
    return str(valor or "").strip()


def _existe(valor: Any) -> bool:
    if isinstance(valor, (list, tuple, set)):
        return bool(valor) and any(_texto(elemento) for elemento in valor)
    return bool(_texto(valor))


def _fecha_valida(valor: Any, *, con_hora: bool = False) -> bool:
    """Formato ISO: YYYY-MM-DD o YYYY-MM-DDTHH:MM[:SS][zona]."""
    if isinstance(valor, datetime):
        return True
    if not isinstance(valor, str):
        return False
    valor = valor.strip()
    if not valor or len(valor) < 10:
        return False
    try:
        if con_hora:
            # Evita aceptar solo fecha cuando la cita necesita hora.
            if "T" not in valor and " " not in valor:
                return False
            datetime.fromisoformat(valor.replace("Z", "+00:00"))
        else:
            # Admitimos fecha de calendario o fecha-hora ISO.
            if "T" in valor or " " in valor:
                datetime.fromisoformat(valor.replace("Z", "+00:00"))
            else:
                date.fromisoformat(valor)
    except ValueError:
        return False
    return True


def _denegar(actual: str | None, codigo: str, detalle: str) -> DecisionTransicion:
    return DecisionTransicion(False, False, actual, actual, codigo, detalle)


def _aceptar(actual: str | None, destino: str, *, codigo: str = "transicion_valida") -> DecisionTransicion:
    cambio = actual != destino
    return DecisionTransicion(
        True, cambio, actual, destino,
        codigo if cambio or codigo != "transicion_valida" else "actividad_sin_cambio_de_etapa",
        "Registrar actividad y cambio de etapa." if cambio else
        "Registrar la actividad sin retroceder ni duplicar un cambio de etapa.",
        registrar_actividad=True,
    )


def _validar_datos(evento: str, datos: Mapping[str, Any]) -> str | None:
    """Devuelve un error o None. 'registrado/confirmado' debe venir de lógica servidor.

    Los responsables, IDs de actividad, sucursal y momento de registro se
    incorporarán y verificarán al guardar la transacción en Django; nunca deben
    confiarse únicamente a campos que envíe React.
    """
    if evento == "respuesta_humana_registrada":
        if not (
            _existe(datos.get("mensaje_id"))
            and datos.get("direccion") == "out"
            and datos.get("es_humano") is True
            and datos.get("registrado") is True
        ):
            return "Se necesita un mensaje saliente humano ya registrado en el servidor."
    elif evento == "cotizacion_confirmada":
        if not (
            datos.get("confirmado") is True
            and _fecha_valida(datos.get("fecha_envio"))
            and _existe(datos.get("vehiculo"))
        ):
            return "Confirma la cotización e indica fecha y vehículo."
    elif evento == "cita_registrada":
        if not (
            datos.get("confirmado") is True
            and _existe(datos.get("cita_id"))
            and _fecha_valida(datos.get("fecha_hora_cita"), con_hora=True)
            and _existe(datos.get("sucursal"))
        ):
            return "La cita debe estar guardada y confirmada, con fecha, hora y sucursal."
    elif evento == "asistencia_confirmada":
        if not (
            datos.get("confirmado") is True
            and _existe(datos.get("cita_id"))
            and datos.get("asistio") is True
            and _fecha_valida(datos.get("fecha_asistencia_real"))
        ):
            return "Confirma asistencia y registra la fecha real; una inasistencia no activa esta etapa."
    elif evento == "documentos_recibidos_confirmados":
        if not (
            datos.get("confirmado") is True
            and _fecha_valida(datos.get("fecha_recepcion"))
            and _existe(datos.get("documentos"))
        ):
            return "Confirma recepción e indica fecha y documentos recibidos."
    elif evento == "factura_registrada":
        if not (
            datos.get("registrado") is True
            and _fecha_valida(datos.get("fecha_factura"))
            and _existe(datos.get("folio_factura"))
            and _existe(datos.get("vehiculo"))
        ):
            return "La factura debe estar validada y registrada con fecha, folio y vehículo."
    elif evento == "vin_facturado_registrado":
        # Solo para el piloto: reproduce la regla operativa del CRM heredado.
        # No indica que exista una factura fiscal verificada.
        if not (
            datos.get("registrado") is True
            and _fecha_valida(datos.get("fecha_registro_vin"))
            and _existe(datos.get("vehiculo"))
            and datos.get("fuente") == "crm_vin_facturado"
        ):
            return "Se requiere un VIN facturado persistido por el CRM y fecha de registro del servidor."
    elif evento == "seleccion_manual":
        destino = normalizar_etapa(datos.get("etapa_destino"))
        if destino == "autorizado_no_formalizado" and not (
            datos.get("credito_autorizado") is True
            and datos.get("confirmado") is True
            and _fecha_valida(datos.get("fecha_autorizacion"))
        ):
            return "Confirma la autorización de crédito e indica su fecha efectiva."
        if destino == "compra_futura" and not (
            datos.get("confirmado") is True
            and _fecha_valida(datos.get("fecha_prevista_compra"))
            and _fecha_valida(datos.get("proximo_contacto"))
            and _existe(datos.get("observacion"))
        ):
            return "Compra futura requiere fecha prevista, próximo contacto y observación."
        if destino == "lead_perdido":
            motivo = _texto(datos.get("motivo"))
            if not motivo:
                return "Lead perdido requiere motivo obligatorio."
            if normalizar_etapa(motivo) in {"otro", "otro_motivo"} and not _existe(datos.get("detalle_motivo")):
                return "Para Otro motivo se necesita una explicación escrita."
    return None


def evaluar_transicion(
    etapa_actual: str | None,
    evento: str,
    *,
    datos: Mapping[str, Any] | None = None,
) -> DecisionTransicion:
    """Evalúa sin persistir. TODOS los campos de `datos` deben validarse en Django.

    Los estados históricos NO se interpretan silenciosamente como nuevas etapas.
    `etapa_actual=None` o "" solo se acepta con `alta_prospecto`.

    Eventos ordinarios:
       alta_prospecto, respuesta_humana_registrada, cotizacion_confirmada,
       cita_registrada, asistencia_confirmada,
       documentos_recibidos_confirmados, factura_registrada,
       vin_facturado_registrado, seleccion_manual.

    Eventos excepcionales:
       reactivacion: desde Compra futura/Lead perdido, motivo obligatorio y
                     opcional etapa_destino (por defecto En seguimiento).
       correccion: requiere autorizada=True y motivo; permite rectificar una
                   etapa, dejando la auditoría como obligación del llamador.
    """
    datos = dict(datos or {})
    evento = _texto(evento)
    actual_obj = obtener_etapa(etapa_actual)
    actual = actual_obj.clave if actual_obj else None

    if _texto(etapa_actual) and actual is None:
        return _denegar(None, "estado_historico_no_reconocido",
                       "Primero se requiere correspondencia/migración explícita del estado histórico.")

    if evento == "alta_prospecto":
        if actual is not None:
            return _denegar(actual, "alta_repetida", "El prospecto ya tiene una etapa.")
        return _aceptar(None, "nuevo_prospecto")

    if actual is None:
        return _denegar(None, "sin_etapa_inicial", "Primero debe registrarse el alta del prospecto.")

    if evento == "correccion":
        destino_obj = obtener_etapa(datos.get("etapa_destino"))
        if not destino_obj:
            return _denegar(actual, "destino_invalido", "La etapa de corrección no existe en el catálogo comercial.")
        if datos.get("autorizada") is not True or not _existe(datos.get("motivo")):
            return _denegar(actual, "correccion_no_autorizada",
                           "La corrección exige autorización del servidor y justificación auditable.")
        return _aceptar(actual, destino_obj.clave, codigo="correccion_autorizada")

    if evento == "reactivacion":
        if actual not in ETAPAS_SITUACION:
            return _denegar(actual, "no_requiere_reactivacion",
                           "Solo Compra futura y Lead perdido requieren reactivación explícita.")
        if not _existe(datos.get("motivo")):
            return _denegar(actual, "motivo_reactivacion_requerido", "Especifica motivo de reactivación.")
        destino_obj = obtener_etapa(datos.get("etapa_destino") or "en_seguimiento")
        destino = destino_obj.clave if destino_obj else None
        if destino not in NIVEL_AVANCE or destino in {"nuevo_prospecto", "facturado"}:
            return _denegar(actual, "destino_reactivacion_invalido",
                           "Reactiva hacia una etapa comercial activa (no Nuevo prospecto ni Facturado).")
        return _aceptar(actual, destino, codigo="reactivacion_manual")

    # Estados especiales no se abandonan por una automatización o por
    # modificar campos ajenos. Facturado es terminal mientras no se rectifique.
    if actual == "facturado":
        return _denegar(actual, "facturado_protegido",
                       "Una venta facturada solo cambia mediante corrección autorizada.")
    if actual == "lead_perdido":
        return _denegar(actual, "lead_perdido_protegido",
                       "Reactiva explícitamente antes de cambiar una oportunidad perdida.")
    if actual == "compra_futura":
        return _denegar(actual, "compra_futura_protegida",
                       "Reactiva explícitamente antes de reanudar las etapas de avance.")

    if evento == "seleccion_manual":
        destino_obj = obtener_etapa(datos.get("etapa_destino"))
        destino = destino_obj.clave if destino_obj else None
        if destino not in SELECCIONES_MANUALES:
            return _denegar(actual, "seleccion_no_permitida",
                           "Solo Autorizado no formalizado, Compra futura y Lead perdido son selecciones manuales.")
        error = _validar_datos(evento, datos)
        if error:
            return _denegar(actual, "datos_incompletos", error)
        if destino == "autorizado_no_formalizado":
            # No aceptar que el usuario pase desde prospecto/cita directamente a
            # crédito autorizado. La etapa 6 puede cumplirse sin asistencia.
            if actual != "documentos_enviados":
                return _denegar(actual, "documentos_requeridos_credito",
                               "Primero registra Documentos recibidos antes de autorizar el crédito.")
            if NIVEL_AVANCE[destino] < NIVEL_AVANCE[actual]:
                return _denegar(actual, "retroceso_no_permitido",
                               "Para retroceder una etapa avanzada se necesita una corrección autorizada.")
        return _aceptar(actual, destino)

    # La documentación puede recibirse ANTES de la asistencia, pero no antes
    # de agendar una cita. Este control también protege llamadas que no usan HTTP.
    if (evento == "documentos_recibidos_confirmados"
            and actual not in {"cita_agendada", "cita_asistida", "documentos_enviados"}):
        return _denegar(
            actual, "cita_requerida_documentos",
            "Primero debe existir una cita agendada antes de avanzar a Documentos recibidos.",
        )

    regla = REGLAS_EVENTO.get(evento)
    if regla is None:
        return _denegar(actual, "evento_desconocido", "No existe una regla para ese evento.")
    destino, tipo_esperado = regla
    # Verifica que el catálogo (fuente de verdad) no cambió sin adaptar reglas.
    catalogo = obtener_etapa(destino)
    if not catalogo or catalogo.tipo_movimiento != tipo_esperado:
        return _denegar(actual, "configuracion_inconsistente",
                       "La regla no coincide con el catálogo de etapas comerciales.")
    error = _validar_datos(evento, datos)
    if error:
        return _denegar(actual, "datos_incompletos", error)

    # Un registro válido siempre debe conservarse como ACTIVIDAD, aunque la
    # etapa actual sea más avanzada. Las transiciones automáticas regresivas
    # o generadas por botones no reemplazan etapas ya alcanzadas.
    if NIVEL_AVANCE[destino] < NIVEL_AVANCE[actual]:
        return _aceptar(actual, actual, codigo="actividad_sin_regresion")
    return _aceptar(actual, destino)
