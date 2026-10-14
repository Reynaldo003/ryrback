"""Inicialización aislada de CRM V3 para ALTAS NUEVAS, no migración retroactiva.

Se llama dentro de la transacción que crea el expediente. No modifica `estado`
histórico, no crea actividades comerciales ficticias y registra auditoría de alta.
"""

import unicodedata

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .etapas_service import evaluar_transicion
from .models import BitacoraAsesorDigital, ExpedienteDigital


def _clave_agencia(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(texto.casefold().split())


def iniciar_alta_v3_si_nuevo(*, expediente, creado, usuario_crm="sistema"):
    """Activa solo un expediente recién creado de agencia explícitamente habilitada.

    Un expediente existente con V3=NULL NO se incorpora de modo silencioso.
    El flag apagado o agencia no autorizada deja el comportamiento legacy intacto.
    """
    if not creado or not getattr(settings, "CRM_ETAPAS_V3_API_HABILITADA", False):
        return False

    habilitadas = {
        _clave_agencia(agencia)
        for agencia in (getattr(settings, "CRM_ETAPAS_V3_AGENCIAS_HABILITADAS", ()) or ())
        if str(agencia).strip()
    }
    agencia = _clave_agencia(expediente.agencia)
    if not agencia or agencia not in habilitadas:
        return False

    # No etiquetar como Nuevo prospecto un registro que ya nace cerrado.
    if (str(expediente.vin_facturado or "").strip()
            or expediente.facturado_at
            or str(expediente.estado or "").strip().casefold() in {
                "facturado", "entregado", "descalificado",
            }):
        return False

    decision = evaluar_transicion(None, "alta_prospecto", datos={})
    if not decision.permitida or decision.etapa_resultante != "nuevo_prospecto":
        raise ValueError("La transición de alta CRM V3 no está disponible.")

    with transaction.atomic(using="default"):
        actualizados = ExpedienteDigital.objects.filter(
            pk=expediente.pk, etapa_comercial_v3__isnull=True,
        ).update(etapa_comercial_v3="nuevo_prospecto", actualizado=timezone.now())
        if not actualizados:
            return False

        usuario = str(usuario_crm or "sistema").strip()[:120]
        BitacoraAsesorDigital.objects.create(
            expediente=expediente,
            cliente=expediente.cliente,
            asesor_digital=str(expediente.asesor_digital or "")[:200],
            usuario_crm=usuario,
            tipo="actualizacion",
            accion="Alta en flujo comercial CRM V3",
            detalle="alta_prospecto: sin etapa V3 -> nuevo_prospecto",
            resultado="no_aplica",
            metadata={
                "grupo_tipo": "operativo",
                "grupo_resultado": "no_aplica",
                "crm_etapas_version": 3,
                "evento": "alta_prospecto",
                "etapa_anterior": None,
                "etapa_resultante": "nuevo_prospecto",
                "origen": "automatico",
            },
        )
    expediente.etapa_comercial_v3 = "nuevo_prospecto"
    return True
