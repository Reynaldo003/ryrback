from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from citas.models import Cita
from Digitales.models import ExpedienteDigital


def _recalcular_ultima_cita(cliente_id: int):
    exp, _ = ExpedienteDigital.objects.get_or_create(cliente_id=cliente_id)

    latest = (
        Cita.objects
        .filter(cliente_id=cliente_id)
        .order_by("-fecha_hora_cita", "-id")
        .first()
    )

    if not latest:
        exp.ultima_cita_id = None
        exp.ultima_cita_agendada = None
        exp.asistencia = False
        exp.save(update_fields=["ultima_cita", "ultima_cita_agendada", "asistencia", "actualizado"])
        return

    exp.ultima_cita_id = latest.id
    exp.ultima_cita_agendada = latest.fecha_hora_cita
    exp.asistencia = bool(latest.asistencia)

    campos = ["ultima_cita", "ultima_cita_agendada", "asistencia"]

    if not str(exp.agencia or "").strip() and str(latest.agencia or "").strip():
        exp.agencia = latest.agencia
        campos.append("agencia")

    if not str(exp.asesor_digital or "").strip() and str(latest.asesor_digital or "").strip():
        exp.asesor_digital = latest.asesor_digital
        campos.append("asesor_digital")

    campos.append("actualizado")
    exp.save(update_fields=campos)


@receiver(post_save, sender=Cita)
def cita_post_save(sender, instance: Cita, **kwargs):
    _recalcular_ultima_cita(instance.cliente_id)


@receiver(post_delete, sender=Cita)
def cita_post_delete(sender, instance: Cita, **kwargs):
    _recalcular_ultima_cita(instance.cliente_id)