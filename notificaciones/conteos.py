# notificaciones/conteos.py
"""Conteos de notificaciones por usuario, cacheados en el servidor.

Usar un backend de caché compartido (Redis) si hay varios procesos Gunicorn.
"""
from django.core.cache import cache
from django.db import transaction

from .models import Notificacion

CONTEOS_TTL_SEGUNDOS = 30


def _clave_conteos(usuario_id):
    return f"notificaciones:conteos:v1:usuario:{usuario_id}"


def obtener_conteos(usuario_id):
    clave = _clave_conteos(usuario_id)
    datos = cache.get(clave)
    if datos is not None:
        return datos

    qs = Notificacion.objects.filter(usuario_id=usuario_id)
    datos = {
        "no_leidas": qs.filter(leida=False).count(),
        "total": qs.count(),
    }
    cache.set(clave, datos, timeout=CONTEOS_TTL_SEGUNDOS)
    return datos


def invalidar_conteos(usuario_id):
    clave = _clave_conteos(usuario_id)
    transaction.on_commit(lambda: cache.delete(clave))
