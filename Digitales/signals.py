#Digitales/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver

from citas.models import ClienteComercial
from .models import ExpedienteDigital, MensajeWhatsApp

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
    ExpedienteDigital.objects.filter(
        cliente__telefono=instance.telefono,
        estado=ESTADO_SIN_CONTACTAR,
    ).update(estado=ESTADO_CONTACTADO)


@receiver(post_save, sender=ClienteComercial)
def crear_expediente_digital_si_no_existe(sender, instance, created, **kwargs):
    if not created:
        return
    ExpedienteDigital.objects.get_or_create(
        cliente=instance,
        defaults={"agencia": "", "asesor_digital": ""},
    )
