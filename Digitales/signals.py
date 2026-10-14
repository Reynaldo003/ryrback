#Digitales/signals.py
import logging
from types import SimpleNamespace

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from citas.models import ClienteComercial
from .models import ExpedienteDigital, MensajeWhatsApp

logger = logging.getLogger(__name__)

ESTADO_SIN_CONTACTAR = "Sin Contactar"
ESTADO_CONTACTADO = "Contactado"


@receiver(post_save, sender=MensajeWhatsApp)
def marcar_primer_contacto_humano(sender, instance, created, **kwargs):
    if not created:
        return
    if instance.direction != "out" or instance.from_ia:
        return
    existe = MensajeWhatsApp.objects.filter(
        telefono=instance.telefono,
        numero_asesor=instance.numero_asesor,
        direction="out",
        from_ia=False,
        id__lt=instance.id,
    ).exists()
    if existe:
        return
    # Compatibilidad: conservar la transición histórica existente.
    ExpedienteDigital.objects.filter(
        cliente__telefono=instance.telefono,
        estado=ESTADO_SIN_CONTACTAR,
    ).update(estado=ESTADO_CONTACTADO)

    # V3 es optativo y solo está activo para agencias habilitadas.
    # No se inicializan expedientes antiguos ni se fuerza una etapa.
    if not getattr(settings, "CRM_ETAPAS_V3_API_HABILITADA", False):
        return

    from .etapas_alta_v3 import _clave_agencia
    from .actividades_service import registrar_actividad_v3, ErrorActividadComercial

    agencias = {
        _clave_agencia(valor)
        for valor in (getattr(settings, "CRM_ETAPAS_V3_AGENCIAS_HABILITADAS", ()) or ())
        if str(valor).strip()
    }
    if not agencias:
        return

    # Resolver por cliente cuando exista relación directa; el teléfono es
    # un recurso de compatibilidad con mensajes históricos no vinculados.
    qs = ExpedienteDigital.objects.select_related("cliente").filter(
        etapa_comercial_v3__isnull=False,
    )
    if instance.cliente_id is not None:
        qs = qs.filter(cliente_id=instance.cliente_id)
    else:
        from citas.models import normaliza_tel_mx
        qs = qs.filter(cliente__telefono=normaliza_tel_mx(instance.telefono))

    candidatos = [exp for exp in qs if _clave_agencia(exp.agencia) in agencias]
    if len(candidatos) != 1:
        # No asociar un mensaje a varios expedientes ni adivinar la agencia.
        return
    expediente = candidatos[0]
    if expediente.etapa_comercial_v3 != "nuevo_prospecto":
        # Un evento tardío no puede hacer retroceder o reactivar otra etapa.
        return

    # El guardado del mensaje es un evento interno del servidor, no un POST
    # enviado por el navegador. El servicio vuelve a verificar mensaje y cliente.
    actor_sistema = SimpleNamespace(usuario="sistema_wa", is_authenticated=True)
    try:
        with transaction.atomic(using="default"):
            registrar_actividad_v3(
                expediente_id=expediente.pk,
                evento="respuesta_humana_registrada",
                datos={"mensaje_id": instance.pk},
                actor=actor_sistema,
                clave_idempotencia=f"wa_humano_msg:{instance.pk}",
            )
    except ErrorActividadComercial as exc:
        # Reglas de negocio V3 nunca deben impedir guardar un mensaje real.
        logger.warning("WhatsApp V3 no avanzó expediente %s: %s", expediente.pk, exc)
    except Exception:
        logger.exception("Error registrando avance WhatsApp V3, mensaje %s", instance.pk)


@receiver(post_save, sender=ClienteComercial)
def crear_expediente_digital_si_no_existe(sender, instance, created, **kwargs):
    if not created:
        return
    ExpedienteDigital.objects.get_or_create(
        cliente=instance,
        defaults={"agencia": "", "asesor_digital": ""},
    )
