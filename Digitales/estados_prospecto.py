#volkswagen
# Digitales/estados_prospecto.py
from django.db.models import Exists, OuterRef, Q


def qs_con_estado_sin_contactar(queryset):

    mensaje_humano_saliente = (
        Q(mensajes_whatsapp__direction="out")
        & ~Q(mensajes_whatsapp__raw__icontains='"ia_provider"')
    )

    subq_humano = Exists(
        MensajeWhatsApp.objects.filter(
            cliente_id=OuterRef("cliente_id"),
        ).filter(mensaje_humano_saliente)
    )

    return queryset.annotate(_sin_contactar=~subq_humano)


def esta_sin_contactar(expediente) -> bool:

    from .models import MensajeWhatsApp

    return not MensajeWhatsApp.objects.filter(
        cliente_id=expediente.cliente_id,
        direction="out",
    ).exclude(
        raw__icontains='"ia_provider"'
    ).exists()
