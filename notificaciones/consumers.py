# notificaciones/consumers.py
import re
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from CrmConformidad.jwt_authentication import CRMJWTAuthentication
from citas.models import normaliza_tel_mx
from Digitales.sett import WHATSAPP_LINES


def normalizar_numero(numero):
    digits = "".join(c for c in str(numero or "") if c.isdigit())

    if not digits:
        return ""

    if digits.startswith("521") and len(digits) == 13:
        return "52" + digits[3:]

    if len(digits) == 10:
        return "52" + digits

    if digits.startswith("52") and len(digits) == 12:
        return digits

    return normaliza_tel_mx(digits)


def obtener_numeros_telefono(raw_telefono):
    partes = re.split(r"[|,;\n]+", str(raw_telefono or ""))
    numeros = []

    for parte in partes:
        numero = normalizar_numero(parte)

        if numero and numero in WHATSAPP_LINES and numero not in numeros:
            numeros.append(numero)

    return numeros


def obtener_token_scope(scope):
    """
    El JWT viaja preferentemente mediante Sec-WebSocket-Protocol
    para evitar que aparezca en los access logs de Apache.

    Frontend:
        new WebSocket(url, ["crm-jwt", token])

    Se conserva token por query string únicamente como compatibilidad.
    """
    protocolos = scope.get("subprotocols", []) or []

    if len(protocolos) >= 2 and protocolos[0] == "crm-jwt":
        token = str(protocolos[1] or "").strip()

        if token:
            return token, "crm-jwt"

    query_string = (
        scope.get("query_string", b"")
        .decode("utf-8", errors="ignore")
    )

    params = parse_qs(query_string)
    token = (params.get("token", [""])[0] or "").strip()

    return token, None


@database_sync_to_async
def obtener_contexto_usuario_desde_jwt(token):
    token = str(token or "").strip()

    if not token:
        return None

    try:
        auth = CRMJWTAuthentication()
        validated_token = auth.get_validated_token(token)
        usuario = auth.get_user(validated_token)

        if not usuario:
            return None

        return {
            "usuario": getattr(usuario, "usuario", "") or "",
            "rol": getattr(
                getattr(usuario, "rol", None),
                "nombre",
                "",
            ) or "",
            "telefono": getattr(usuario, "telefono", "") or "",
        }

    except Exception:
        return None


class WhatsAppNotificacionesConsumer(AsyncJsonWebsocketConsumer):
    async def aceptar_y_cerrar(self, codigo, subprotocol=None):
        if subprotocol:
            await self.accept(subprotocol=subprotocol)
        else:
            await self.accept()

        await self.close(code=codigo)

    async def connect(self):
        self.usuario = ""
        self.numero_asesor = ""
        self.grupos = []

        token, subprotocol = obtener_token_scope(self.scope)

        query_string = (
            self.scope.get("query_string", b"")
            .decode("utf-8", errors="ignore")
        )

        params = parse_qs(query_string)

        numero_param = normalizar_numero(
            params.get("numero_asesor", [""])[0]
        )

        todas = params.get("todas", ["0"])[0] == "1"

        contexto = await obtener_contexto_usuario_desde_jwt(token)

        if not contexto:
            await self.aceptar_y_cerrar(
                4401,
                subprotocol=subprotocol,
            )
            return

        self.usuario = contexto["usuario"]

        rol = str(contexto["rol"] or "").strip().lower()
        es_admin = rol == "administrador"

        numeros_usuario = obtener_numeros_telefono(
            contexto["telefono"]
        )

        if todas:
            if not es_admin:
                await self.aceptar_y_cerrar(
                    4403,
                    subprotocol=subprotocol,
                )
                return

            self.numero_asesor = "TODAS"
            self.grupos = [
                "whatsapp_todas_las_lineas"
            ]

        else:
            if es_admin and numero_param in WHATSAPP_LINES:
                numeros = [numero_param]

            elif (
                numero_param
                and numero_param in numeros_usuario
            ):
                numeros = [numero_param]

            else:
                numeros = numeros_usuario

            if not numeros:
                await self.aceptar_y_cerrar(
                    4403,
                    subprotocol=subprotocol,
                )
                return

            self.numero_asesor = (
                numeros[0]
                if len(numeros) == 1
                else "|".join(numeros)
            )

            self.grupos = [
                f"whatsapp_linea_{numero}"
                for numero in numeros
            ]

        if subprotocol:
            await self.accept(subprotocol=subprotocol)
        else:
            await self.accept()

        for grupo in self.grupos:
            await self.channel_layer.group_add(
                grupo,
                self.channel_name,
            )

        await self.send_json({
            "tipo": "conexion_establecida",
            "numero_asesor": self.numero_asesor,
            "grupos": self.grupos,
        })

    async def disconnect(self, close_code):
        for grupo in getattr(self, "grupos", []):
            try:
                await self.channel_layer.group_discard(
                    grupo,
                    self.channel_name,
                )
            except Exception:
                pass

    async def receive_json(self, content, **kwargs):
        if content.get("tipo") == "ping":
            await self.send_json({
                "tipo": "pong",
            })

    async def whatsapp_mensaje(self, event):
        await self.send_json({
            "tipo": "whatsapp_mensaje_recibido",
            "telefono": event.get("telefono", ""),
            "numero_asesor": event.get("numero_asesor", ""),
            "nombre": event.get("nombre", "Prospecto"),
            "mensaje": event.get("mensaje", ""),
            "wa_message_id": event.get("wa_message_id", ""),
            "expediente_id": event.get("expediente_id"),
            "created_at": event.get("created_at", ""),
            "url": event.get("url", ""),
        })

    async def whatsapp_mensaje_recibido(self, event):
        await self.whatsapp_mensaje(event)