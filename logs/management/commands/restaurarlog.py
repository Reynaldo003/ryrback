# logs/management/commands/restaurarlog.py
"""
Restaura lo que se eliminó en un log ELIMINAR (a partir del snapshot).

Uso:
  python manage.py restaurarlog <log_id>            # restaura
  python manage.py restaurarlog <log_id> --dry-run  # solo muestra qué se restauraría
"""
from django.core.management.base import BaseCommand, CommandError

from logs.models import LogActividad
from logs.snapshots import restaurar_snapshot


class Command(BaseCommand):
    help = "Restaura el registro eliminado en un log ELIMINAR (snapshot en datos)."

    def add_arguments(self, parser):
        parser.add_argument("log_id", type=int, help="ID del LogActividad a restaurar.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra el snapshot sin restaurar nada.",
        )

    def handle(self, *args, **options):
        log_id = options["log_id"]
        dry_run = options["dry_run"]

        try:
            log = LogActividad.objects.get(pk=log_id)
        except LogActividad.DoesNotExist:
            raise CommandError(f"No existe el log #{log_id}.")

        if log.tipo != "ELIMINAR":
            raise CommandError(
                f"El log #{log_id} es tipo {log.tipo}, no ELIMINAR; no hay nada que restaurar."
            )

        datos = log.datos
        if not datos:
            raise CommandError(
                f"El log #{log_id} no tiene snapshot (datos vacío); no se puede restaurar. "
                "Solo los logs creados después de desplegar el snapshot lo incluyen."
            )

        self.stdout.write(f"Log #{log.id} · {log.fecha} · {log.entidad}")
        self.stdout.write(f"Acción: {log.cambio}")
        self.stdout.write(f"Modelo: {datos.get('modelo')} #{datos.get('pk')}")

        if dry_run:
            self.stdout.write(self.style.WARNING("--dry-run: no se restaura nada."))
            self._imprimir_snapshot(datos)
            return

        ok, mensajes = restaurar_snapshot(datos)
        for mensaje in mensajes:
            if ok:
                self.stdout.write(self.style.SUCCESS(mensaje))
            else:
                self.stdout.write(self.style.ERROR(mensaje))

        if not ok:
            raise CommandError("No se pudo restaurar.")

    def _imprimir_snapshot(self, datos):
        campos = datos.get("campos") or {}
        self.stdout.write("Campos:")
        for nombre, valor in campos.items():
            self.stdout.write(f"  {nombre}: {valor}")
        for hijo in datos.get("hijos") or []:
            self.stdout.write(
                f"Hijo {hijo.get('modelo')} ({len(hijo.get('registros') or [])}):"
            )
            for registro in hijo.get("registros") or []:
                self.stdout.write(f"  #{registro.get('pk')}: {registro.get('campos')}")
