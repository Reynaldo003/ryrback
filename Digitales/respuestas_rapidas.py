#volkswagen
# Digitales/respuestas_rapidas.py
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from CrmConformidad.jwt_authentication import CRMJWTAuthentication

from .models import RespuestaRapidaAsesor


TITULO_MAX = 120
TEXTO_MAX = 2000


def _serializar_respuesta(respuesta) -> dict:
    return {
        "id": respuesta.id,
        "usuario_id": respuesta.usuario_id,
        "titulo": respuesta.titulo,
        "texto": respuesta.texto,
        "creado": respuesta.creado.isoformat() if respuesta.creado else None,
        "actualizado": respuesta.actualizado.isoformat() if respuesta.actualizado else None,
    }


def _obtener_usuario(request):
    user = getattr(request, "user", None)

    if user and getattr(user, "is_authenticated", False) and getattr(user, "pk", None):
        return user

    return None


def _limpiar_payload(request) -> tuple[str, str]:
    data = getattr(request, "data", {}) or {}

    titulo = str(data.get("titulo", "") or "").strip()
    texto = str(data.get("texto", "") or "").strip()

    if len(titulo) > TITULO_MAX:
        titulo = titulo[:TITULO_MAX]

    if len(texto) > TEXTO_MAX:
        texto = texto[:TEXTO_MAX]

    return titulo, texto


@api_view(["GET", "POST"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def respuestas_rapidas_view(request):
    usuario = _obtener_usuario(request)

    if not usuario:
        return Response(
            {"ok": False, "error": "No autenticado."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    if request.method == "GET":
        respuestas = RespuestaRapidaAsesor.objects.filter(usuario=usuario)
        return Response(
            {"ok": True, "items": [_serializar_respuesta(r) for r in respuestas]},
            status=status.HTTP_200_OK,
        )

    # POST — crear
    titulo, texto = _limpiar_payload(request)

    if not texto:
        return Response(
            {"ok": False, "error": "El texto del mensaje es obligatorio."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    respuesta = RespuestaRapidaAsesor.objects.create(
        usuario=usuario,
        titulo=titulo or texto[:25],
        texto=texto,
    )

    return Response(
        {"ok": True, "item": _serializar_respuesta(respuesta)},
        status=status.HTTP_201_CREATED,
    )


@api_view(["PATCH", "PUT", "DELETE"])
@authentication_classes([CRMJWTAuthentication])
@permission_classes([IsAuthenticated])
def respuesta_rapida_detail_view(request, respuesta_id: int):
    usuario = _obtener_usuario(request)

    if not usuario:
        return Response(
            {"ok": False, "error": "No autenticado."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    respuesta = RespuestaRapidaAsesor.objects.filter(
        id=respuesta_id,
        usuario=usuario,
    ).first()

    if not respuesta:
        return Response(
            {"ok": False, "error": "No existe la respuesta rápida."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "DELETE":
        respuesta.delete()
        return Response({"ok": True}, status=status.HTTP_200_OK)

    # PATCH / PUT — editar
    titulo, texto = _limpiar_payload(request)

    if not texto:
        return Response(
            {"ok": False, "error": "El texto del mensaje es obligatorio."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    respuesta.titulo = titulo or texto[:25]
    respuesta.texto = texto
    respuesta.save()

    return Response(
        {"ok": True, "item": _serializar_respuesta(respuesta)},
        status=status.HTTP_200_OK,
    )
