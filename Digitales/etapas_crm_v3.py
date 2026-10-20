#Digitales/etapas_crm_v3.py
"""Catálogo de etapas comerciales V3 (propuesta, aún NO conectado al CRM).

Distingue tres orígenes de transición:
- automatico: el CRM detecta un evento validado, sin acción adicional del asesor.
- registro_manual: el asesor confirma/guarda una actividad mediante un botón;
  después del registro válido, el CRM actualiza la etapa automáticamente.
- seleccion_manual: el asesor elige explícitamente una etapa y captura sus datos.

Este módulo no guarda datos, no modifica expedientes y no ejecuta migraciones.
No impone todavía prioridades, regresiones ni reactivaciones de etapas.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal


TipoMovimiento = Literal["automatico", "registro_manual", "seleccion_manual"]


@dataclass(frozen=True)
class EtapaCRM:
    clave: str
    etiqueta: str
    tipo_movimiento: TipoMovimiento
    condicion: str


ETAPAS_CRM = (
    EtapaCRM("nuevo_prospecto", "Nuevo prospecto", "automatico",
             "Alta inicial de un prospecto nuevo"),
    EtapaCRM("en_seguimiento", "En seguimiento", "automatico",
             "Primera respuesta humana enviada por la asesora y registrada correctamente"),
    EtapaCRM("cotizacion_enviada", "Cotización enviada", "registro_manual",
             "Confirmar envío de cotización y registrar fecha, vehículo y referencia o archivo"),
    EtapaCRM("cita_agendada", "Cita agendada", "registro_manual",
             "Registrar cita con fecha, hora y sucursal"),
    EtapaCRM("cita_asistida", "Cita asistida", "registro_manual",
             "Confirmar asistencia y registrar la fecha real de visita"),
    EtapaCRM("documentos_enviados", "Documentos recibidos", "registro_manual",
             "Confirmar recepción de documentación por el asesor y su fecha"),
    EtapaCRM("autorizado_no_formalizado", "Autorizado no formalizado", "seleccion_manual",
             "Seleccionar etapa al confirmar crédito autorizado sin formalizar"),
    EtapaCRM("compra_futura", "Compra futura", "seleccion_manual",
             "Seleccionar etapa y registrar fecha prevista, próximo contacto y observación"),
    EtapaCRM("facturado", "Facturado", "automatico",
             "Registro comercial de VIN facturado según la regla heredada; comprobación fiscal pendiente"),
    EtapaCRM("lead_perdido", "Lead perdido", "seleccion_manual",
             "Seleccionar etapa y registrar motivo obligatorio (detalle si elige Otro)"),
)

ETAPAS_POR_CLAVE = {etapa.clave: etapa for etapa in ETAPAS_CRM}
ETAPAS_AUTOMATICAS = frozenset(
    etapa.clave for etapa in ETAPAS_CRM if etapa.tipo_movimiento == "automatico"
)
ETAPAS_REGISTRO_MANUAL = frozenset(
    etapa.clave for etapa in ETAPAS_CRM if etapa.tipo_movimiento == "registro_manual"
)
ETAPAS_SELECCION_MANUAL = frozenset(
    etapa.clave for etapa in ETAPAS_CRM if etapa.tipo_movimiento == "seleccion_manual"
)
ETAPAS_MANUALES = ETAPAS_REGISTRO_MANUAL | ETAPAS_SELECCION_MANUAL


def normalizar_etapa(valor: object) -> str:
    """Normaliza clave/etiqueta para consulta, sin alterar datos persistidos."""
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^a-z0-9]+", "_", texto.casefold())
    return texto.strip("_")


def obtener_etapa(valor: object) -> EtapaCRM | None:
    """Reconoce solo las 10 etapas V3; estados históricos ajenos devuelven None."""
    return ETAPAS_POR_CLAVE.get(normalizar_etapa(valor))


def es_movimiento_manual(valor: object) -> bool:
    etapa = obtener_etapa(valor)
    return bool(etapa and etapa.clave in ETAPAS_MANUALES)


def es_movimiento_automatico(valor: object) -> bool:
    etapa = obtener_etapa(valor)
    return bool(etapa and etapa.clave in ETAPAS_AUTOMATICAS)


def requiere_registro_manual(valor: object) -> bool:
    etapa = obtener_etapa(valor)
    return bool(etapa and etapa.clave in ETAPAS_REGISTRO_MANUAL)


def requiere_seleccion_manual(valor: object) -> bool:
    etapa = obtener_etapa(valor)
    return bool(etapa and etapa.clave in ETAPAS_SELECCION_MANUAL)
