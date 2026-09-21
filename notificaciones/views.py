# notificaciones/views.py
from django.utils import timezone

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from CrmConformidad.jwt_authentication import CRMJWTAuthentication
from .consumers import (
    _detalle_lineas_asesor,
    _es_asesor_digital,
    _agencias_usuario,
    _usuario_con_acceso_total,
    _lineas_del_asesor,
    _texto,
    obtener_numeros_telefono,
)
from .serializers import FirebaseTokenSerializer
from .services import notificar_mensaje_whatsapp


def _contexto_desde_request(request):
    user = getattr(request, "user", None)

    return {
        "usuario": _texto(getattr(user, "usuario", "")),
        "rol": _texto(
            getattr(getattr(user, "rol", None), "nombre", "")
        ),
        "agencia": _texto(getattr(user, "agencia", "")),
        "telefono": _texto(getattr(user, "telefono", "")),
    }


class RegistrarTokenView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = FirebaseTokenSerializer(
            data=request.data,
            context={"request": request},
        )

        if serializer.is_valid():
            serializer.save()
            return Response(
                {"message": "Token procesado con éxito."},
                status=status.HTTP_200_OK,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class DiagnosticarNotificacionesView(APIView):
    """
    Devuelve qué líneas recibiría el usuario autenticado y los motivos
    por los que podría estar quedando fuera de las notificaciones.

    Uso: GET /api/notificaciones/diagnostico/
    """

    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        contexto = _contexto_desde_request(request)

        lineas = _detalle_lineas_asesor(contexto)
        permitidas = [
            linea["numero"]
            for linea in lineas
            if linea["permitida"]
        ]

        acceso_total = _usuario_con_acceso_total(contexto)

        motivos = []

        if not acceso_total and not _es_asesor_digital(contexto["rol"]):
            motivos.append(
                "El rol del usuario no es 'asesor digital' "
                f"(actual: '{contexto['rol'] or 'vacío'}')."
            )

        if not acceso_total:
            if not _agencias_usuario(contexto["agencia"]):
                motivos.append(
                    "El usuario no tiene ninguna agencia configurada "
                    "(esperado por ejemplo: 'VW Cordoba')."
                )

            if not obtener_numeros_telefono(contexto["telefono"]):
                motivos.append(
                    "El usuario no tiene ningún teléfono que coincida con "
                    "WHATSAPP_LINES."
                )
            elif not permitidas:
                motivos.append(
                    "Hay teléfono(s) y agencia, pero ninguna línea coincide "
                    "con ambos al mismo tiempo."
                )

        return Response({
            "ok": bool(permitidas),
            "usuario": contexto["usuario"],
            "rol": contexto["rol"],
            "agencia": contexto["agencia"],
            "telefono": contexto["telefono"],
            "es_asesor_digital": _es_asesor_digital(contexto["rol"]),
            "es_acceso_total": acceso_total,
            "lineas": lineas,
            "lineas_permitidas": permitidas,
            "motivos": motivos,
        })


class ProbarNotificacionesView(APIView):
    """
    Dispara una notificación de prueba real a las líneas del usuario
    autenticado, usando la misma función del webhook de Meta.

    Útil para validar la entrega por WebSocket en local
    (runserver) o en producción sin esperar un mensaje real.

    Uso: GET /api/notificaciones/probar/
    """

    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        contexto = _contexto_desde_request(request)
        lineas = _lineas_del_asesor(contexto)

        if not lineas:
            return Response(
                {
                    "ok": False,
                    "error": "El usuario no tiene líneas autorizadas "
                             "para notificaciones.",
                    "contexto": contexto,
                    "motivos": [],
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        enviadas = []

        for linea in lineas:
            notificar_mensaje_whatsapp(
                numero_asesor=linea,
                telefono="2711234567",
                nombre="Asesor R&R",
                mensaje="Notificación de prueba local",
                wa_message_id=f"test-local-{linea}-{int(timezone.now().timestamp() * 1000)}",
                created_at=timezone.now(),
            )
            enviadas.append(linea)

        return Response({
            "ok": True,
            "lineas_enviadas": enviadas,
        })