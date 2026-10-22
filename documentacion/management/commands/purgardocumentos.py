# documentacion/management/commands/purgardocumentos.py
"""
Purga definitiva de la papelera de documentos (soft delete > 15 días).

Uso:
  python manage.py purgardocumentos                # purga los vencidos (15 días)
  python manage.py purgardocumentos --dias 30      # retención personalizada
  python manage.py purgardocumentos --dry-run      # solo muestra qué se borraría
"""
from django.core.management.base import BaseCommand, CommandError

from documentacion.tasks import RETENCION_DIAS, purgar_documentos_expirados


class Command(BaseCommand):
    help = "Borra definitivamente los documentos eliminados hace más de N días (default 15)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dias",
            type=int,
            default=RETENCION_DIAS,
            help=f"Días de retención (default {RETENCION_DIAS}).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra lo que se borraría sin ejecutar la purga.",
        )

    def handle(self, *args, **options):
        dias = max(1, int(options["dias"]))
        dry_run = options["dry_run"]

        try:
            eliminados, detalles = purgar_documentos_expirados(dias=dias, dry_run=dry_run)
        except Exception as exc:
            raise CommandError(f"Error al purgar documentos: {exc}")

        if not detalles:
            self.stdout.write(
                f"No hay documentos en la papelera con más de {dias} días."
            )
            return

        for detalle in detalles:
            if dry_run:
                self.stdout.write(self.style.WARNING(detalle))
            else:
                self.stdout.write(self.style.SUCCESS(detalle))

        prefijo = "Se purgarían" if dry_run else "Purgados"
        self.stdout.write(f"{prefijo} {eliminados} documento(s) (retención {dias} días).")
