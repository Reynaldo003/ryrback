# logs/management/commands/drainlogs.py
"""
Worker que vuelca la cola de logs (Redis) a la base de datos en lotes.

Modos:
  python manage.py drainlogs                 # drena todo y termina
  python manage.py drainlogs --watch         # loop infinito (intervalo configurable)
  python manage.py drainlogs --watch --interval 3
"""
import json
import time

from django.core.management.base import BaseCommand

from logs.helpers import QUEUE_KEY, REDIS_DB, REDIS_HOST, REDIS_PORT, REDIS_TIMEOUT, _redis_cliente
from logs.models import LogActividad


TIPO_Y_USUARIO = {"LOGIN_FALLIDO": 0}


class Command(BaseCommand):
    help = "Procesa la cola de logs de actividad por usuario (Redis -> PostgreSQL)."

    def add_arguments(self, parser):
        parser.add_argument("--watch", action="store_true", help="Loop infinito como worker.")
        parser.add_argument("--interval", type=float, default=2.0, help="Segundos entre ciclos en --watch.")

    def handle(self, *args, **options):
        while True:
            procesados = self._drenar()
            if procesados:
                self.stdout.write(f"Drenados {procesados} eventos de log.")

            if not options["watch"]:
                break

            time.sleep(options["interval"])

    def _drenar(self):
        try:
            cliente = _redis_cliente()
            if cliente is None:
                return 0
        except Exception:
            return 0

        total = 0
        LOTE = 500

        try:
            while True:
                bloque = cliente.lrange(QUEUE_KEY, 0, LOTE - 1)
                if not bloque:
                    break

                registros = []
                for raw in bloque:
                    try:
                        payload = json.loads(raw)
                    except (ValueError, TypeError):
                        continue

                    registros.append(
                        LogActividad(
                            usuario_id=payload.get("usuario_id"),
                            tipo=payload.get("tipo") or "EDITAR",
                            modulo=payload.get("modulo") or "otros",
                            entidad=payload.get("entidad") or "",
                            cambio=payload.get("cambio") or "",
                            ip=payload.get("ip"),
                        )
                    )

                if registros:
                    LogActividad.objects.bulk_create(registros, batch_size=200)
                    total += len(registros)

                cliente.ltrim(QUEUE_KEY, len(bloque), -1)
        except Exception:
            return total

        return total