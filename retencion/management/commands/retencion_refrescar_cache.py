
from time import monotonic

from django.core.management.base import BaseCommand, CommandError
from django.db import connections


VISTAS = (
    "public.retencion_ordenes_ventas_cache_prueba",
    "public.retencion_historial_cache_prueba",
    "public.retencion_sin_venta_cache_prueba",
)

LOCK_ID_1 = 761842
LOCK_ID_2 = 318506


class Command(BaseCommand):
    help = "Actualiza las vistas materializadas de Retención."

    def add_arguments(self, parser):
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Ejecutar las actualizaciones reales.",
        )

    def handle(self, *args, **options):
        conexion = connections["tdsql"]

        if not options["execute"]:
            self.stdout.write(
                self.style.WARNING(
                    "SIMULACIÓN: no se modificará ninguna vista."
                )
            )

            for vista in VISTAS:
                self.stdout.write(
                    f"Se actualizaría: {vista}"
                )

            self.stdout.write(
                "Para ejecutar realmente, usar --execute."
            )
            return

        if conexion.in_atomic_block:
            raise CommandError(
                "No se puede actualizar dentro de una transacción."
            )

        if not conexion.get_autocommit():
            raise CommandError(
                "La conexión debe tener autocommit activado."
            )

        self.stdout.write("Iniciando actualización de Retención.")

        inicio_total = monotonic()

        with conexion.cursor() as cursor:
            cursor.execute(
                "SELECT pg_try_advisory_lock(%s, %s)",
                [LOCK_ID_1, LOCK_ID_2],
            )

            bloqueo_obtenido = cursor.fetchone()[0]

            if not bloqueo_obtenido:
                raise CommandError(
                    "Ya existe otra actualización en ejecución."
                )

            try:
                for vista in VISTAS:
                    self.stdout.write(
                        f"Actualizando: {vista}"
                    )

                    inicio = monotonic()

                    cursor.execute(
                        f"REFRESH MATERIALIZED VIEW CONCURRENTLY {vista}"
                    )

                    duracion = monotonic() - inicio

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"OK: {vista} ({duracion:.2f} segundos)"
                        )
                    )

                total = monotonic() - inicio_total

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Actualización completada en {total:.2f} segundos."
                    )
                )

            except Exception as exc:
                raise CommandError(
                    f"Falló la actualización: {exc}"
                ) from exc

            finally:
                cursor.execute(
                    "SELECT pg_advisory_unlock(%s, %s)",
                    [LOCK_ID_1, LOCK_ID_2],
                )
