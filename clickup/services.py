from django.conf import settings
from django.core.mail import send_mail

def send_team_invite_email(email: str, invite_url: str, team_name: str):
    """
    Si no tienes SMTP configurado, esto no romperá si lo proteges desde settings.
    Ideal: configurar EMAIL_BACKEND en dev para console backend.
    """
    subject = f"Invitación a equipo: {team_name}"
    message = (
        f"Te invitaron a unirte al equipo '{team_name}'.\n\n"
        f"Abre este enlace para aceptar:\n{invite_url}\n\n"
        "Si no esperabas esto, ignora el correo."
    )

    if getattr(settings, "EMAIL_HOST", None):
        send_mail(
            subject,
            message,
            getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@crm.local"),
            [email],
            fail_silently=True,
        )