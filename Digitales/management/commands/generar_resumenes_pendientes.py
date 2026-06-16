from django.core.management.base import BaseCommand
from django.utils import timezone
from Digitales.models import ExpedienteDigital
from Digitales.services import (
    debe_generar_resumen_por_1h_sin_respuesta,
    generar_y_guardar_resumen,
)


class Command(BaseCommand):
    help = "Genera resumen automático para conversaciones con más de 6 mensajes y 1 hora sin actividad."

    def handle(self, *args, **options):
        total_revisados = 0
        total_generados = 0

        qs = ExpedienteDigital.objects.select_related("cliente").all()

        for exp in qs.iterator():
            total_revisados += 1

            try:
                if debe_generar_resumen_por_1h_sin_respuesta(expediente=exp):
                    generar_y_guardar_resumen(expediente=exp, fuente="auto_1h")
                    total_generados += 1
                    self.stdout.write(self.style.SUCCESS(
                        f"Resumen generado para {exp.cliente.telefono}"
                    ))
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f"Error en {exp.cliente.telefono}: {str(e)}"
                ))

        self.stdout.write(self.style.WARNING(
            f"Revisados={total_revisados} | Generados={total_generados} | Fecha={timezone.now().isoformat()}"
        ))