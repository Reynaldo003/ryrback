# logs/management/commands/purgelogs.py
"""
Retención de logs de actividad: elimina los registros más antiguos que N días.

Uso:
  python manage.py purgelogs                 # borra logs de más de 180 días
  python manage.py purgelogs --dias 90
  python manage.py purgelogs --dias 365 --dry-run
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from logs.models import LogActividad

LOTE = 5000


class Command(BaseCommand):
    help = "Elimina logs de actividad más antiguos que N días (retención)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dias",
            type=int,
            default=180,
            help="Antigüedad mínima a conservar, en días (default 180).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Solo contar cuántos se borrarían, sin borrar.",
        )

    def handle(self, *args, **options):
        dias = max(1, int(options["dias"]))
        corte = timezone.now() - timedelta(days=dias)
        queryset = LogActividad.objects.filter(fecha__lt=corte)

        total = queryset.count()
        if total == 0:
            self.stdout.write(
                f"No hay logs anteriores a {corte:%Y-%m-%d %H:%M} (>{dias} días)."
            )
            return

        if options["dry_run"]:
            self.stdout.write(
                f"[dry-run] Se eliminarían {total} logs anteriores a "
                f"{corte:%Y-%m-%d} (>{dias} días)."
            )
            return

        eliminados = 0
        while True:
            ids = list(queryset.values_list("id", flat=True)[:LOTE])
            if not ids:
                break

            borrados, _ = LogActividad.objects.filter(id__in=ids).delete()
            eliminados += borrados
            self.stdout.write(f"Eliminados {eliminados} de {total}...")

        self.stdout.write(
            self.style.SUCCESS(
                f"Listo. {eliminados} logs eliminados (anteriores a {corte:%Y-%m-%d})."
            )
        )
