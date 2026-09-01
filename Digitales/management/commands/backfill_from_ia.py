#Digitales/management/commands/backfill_from_ia.py
"""Backfill: marca MensajeWhatsApp.from_ia según raw.ia_provider.

Uso:
    python manage.py backfill_from_ia
    python manage.py backfill_from_ia --dry-run
    python manage.py backfill_from_ia --batch-size 2000
"""
from django.core.management.base import BaseCommand
from django.db.models import Q

from Digitales.models import MensajeWhatsApp

IA_RAW_KEYS = ("ia_provider", "ia_model", "openai_model", "gemini_model")


class Command(BaseCommand):
    help = "Backfill de from_ia en MensajeWhatsApp a partir de raw.ia_provider."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Solo contar, no actualizar.")
        parser.add_argument("--batch-size", type=int, default=2000, help="Tamaño de lote.")

    def handle(self, *args, **opts):
        dry = opts["dry_run"]
        batch = opts["batch_size"]

        q_pendientes = Q(from_ia=False) & Q(
            Q(raw__ia_provider__isnull=False)
            | Q(raw__ia_model__isnull=False)
            | Q(raw__openai_model__isnull=False)
            | Q(raw__gemini_model__isnull=False)
        )

        total_candidatos = MensajeWhatsApp.objects.filter(q_pendientes).count()
        self.stdout.write(f"Candidatos IA sin marcar: {total_candidatos}")

        if dry:
            self.stdout.write("DRY RUN: no se actualizó nada.")
            return

        ids = list(
            MensajeWhatsApp.objects.filter(q_pendientes)
            .values_list("id", flat=True)
            .order_by("id")
        )
        total = len(ids)
        self.stdout.write(f"Total a marcar: {total}")

        actualizados = 0
        for i in range(0, max(total, 1), batch):
            lote = ids[i:i + batch]
            if not lote:
                continue
            n = MensajeWhatsApp.objects.filter(id__in=lote).update(from_ia=True)
            actualizados += n
            self.stdout.write(f"Lote {i // batch + 1}: {n} actualizados (acumulado {actualizados}/{total})")

        self.stdout.write(f"Backfill terminado. Marcados: {actualizados}")