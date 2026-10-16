"""Los permisos NO dependen de un id enviado por el frontend."""
from django.db.models import Q
from .models import Tablero, Tema


def puede_ver_tablero(usuario, tablero):
    if tablero.eliminado_en:
        return False
    if tablero.propietario_id == usuario.pk:
        return True
    if tablero.colaboraciones.filter(usuario=usuario, estado="aceptada").exists():
        return True
    return Tema.objects.filter(tablero=tablero).filter(
        Q(propietario=usuario) |
        Q(colaboraciones__usuario=usuario, colaboraciones__estado="aceptada")
    ).exists()


def puede_editar_tablero(usuario, tablero):
    if tablero.eliminado_en:
        return False
    return tablero.propietario_id == usuario.pk or tablero.colaboraciones.filter(
        usuario=usuario, estado="aceptada", rol="editor"
    ).exists()


def puede_ver_tema(usuario, tema):
    if tema.tablero.eliminado_en:
        return False
    return (
        tema.tablero.propietario_id == usuario.pk
        or tema.propietario_id == usuario.pk
        or tema.tablero.colaboraciones.filter(usuario=usuario, estado="aceptada").exists()
        or tema.colaboraciones.filter(usuario=usuario, estado="aceptada").exists()
    )


def puede_editar_tema(usuario, tema):
    if tema.tablero.eliminado_en:
        return False
    return (
        tema.tablero.propietario_id == usuario.pk
        or tema.propietario_id == usuario.pk
        or tema.tablero.colaboraciones.filter(
            usuario=usuario, estado="aceptada", rol="editor"
        ).exists()
        or tema.colaboraciones.filter(
            usuario=usuario, estado="aceptada", rol="editor"
        ).exists()
    )


def tableros_visibles(usuario):
    return Tablero.objects.filter(eliminado_en__isnull=True).filter(
        Q(propietario=usuario)
        | Q(colaboraciones__usuario=usuario, colaboraciones__estado="aceptada")
        | Q(temas__propietario=usuario)
        | Q(temas__colaboraciones__usuario=usuario, temas__colaboraciones__estado="aceptada")
    ).distinct().order_by("-id")


def temas_visibles(usuario, tablero):
    consulta = Tema.objects.filter(tablero=tablero)
    if tablero.propietario_id == usuario.pk or tablero.colaboraciones.filter(
        usuario=usuario, estado="aceptada"
    ).exists():
        return consulta.order_by("id")
    return consulta.filter(
        Q(propietario=usuario)
        | Q(colaboraciones__usuario=usuario, colaboraciones__estado="aceptada")
    ).distinct().order_by("id")
