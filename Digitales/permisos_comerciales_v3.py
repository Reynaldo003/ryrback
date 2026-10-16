"""Política única de supervisión comercial para bandeja y API V3.

Permisos efectivos leídos del usuario persistido, nunca de claims del navegador.
NO sustituye los filtros de agencia y titularidad del expediente.
"""
from __future__ import annotations

from CrmConformidad.views import permisos_por_usuario


def _rol(usuario):
    nombre = getattr(getattr(usuario, "rol", None), "nombre", "") or ""
    return " ".join(str(nombre).casefold().split())


def _permisos(usuario):
    if not usuario or not getattr(usuario, "is_authenticated", False):
        return set()
    return set(permisos_por_usuario(usuario))


def es_administrador_comercial(usuario):
    return _rol(usuario) in {"administrador", "admin"} and "ALL" in _permisos(usuario)


def puede_supervisar_comercial(usuario):
    permisos = _permisos(usuario)
    rol = _rol(usuario)
    return (rol in {"administrador", "admin"} and "ALL" in permisos) or (
        rol == "coordinador digital" and "CRM_COORDINADOR_DIGITAL" in permisos
    )
