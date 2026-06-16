# notificaciones/consumers.py
from urllib.parse import parse_qs

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from CrmConformidad.jwt_authentication import CRMJWTAuthentication
from citas.models import normaliza_tel_mx
from Digitales.sett import WHATSAPP_LINES


@sync_to_async
def obtener_usuario_desde_jwt(token: str):
    token = (token or "").strip()

    if not token:
        return None

    try:
        auth = CRMJWTAuthentication()
        validated_token = auth.get_validated_token(token)
        return auth.get_user(validated_token)
    except Exception as e:
        print("WS JWT INVALIDO:", str(e), flush=True)
        return None


def usuario_es_admin_sync(usuario) -> bool:
    try:
        rol = (getattr(usuario.rol, "nombre", "") or "").strip().lower()
        return rol == "administrador"
    except Exception:
        return False


@sync_to_async
def usuario_es_admin(usuario) -> bool:
    return usuario_es_admin_sync(usuario)


@sync_to_async
def obtener_numero_usuario(usuario) -> str:
    if not usuario:
        return ""

    numero = normaliza_tel_mx(getattr(usuario, "telefono", "") or "")

    if numero in WHATSAPP_LINES:
        return numero

    return ""


class WhatsAppNotificacionesConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.usuario = ""
        self.numero_asesor = ""
        self.grupo = None

        query_string = self.scope.get("query_string", b"").decode("utf-8")
        params = parse_qs(query_string)

        token = (params.get("token", [""])[0] or "").strip()
        numero_asesor_param = normaliza_tel_mx(params.get("numero_asesor", [""])[0])
        todas = params.get("todas", ["0"])[0] == "1"

        usuario_obj = await obtener_usuario_desde_jwt(token)

        if not usuario_obj:
            print("WS CERRADO: JWT faltante o inválido", {
                "query_string": query_string,
            }, flush=True)
            await self.close(code=4401)
            return

        self.usuario = getattr(usuario_obj, "usuario", "") or ""

        es_admin = await usuario_es_admin(usuario_obj)

        print("WS INTENTO CONEXION:", {
            "usuario": self.usuario,
            "numero_asesor_recibido": numero_asesor_param,
            "todas": todas,
            "es_admin": es_admin,
        }, flush=True)

        if todas:
            if not es_admin:
                print("WS CERRADO GLOBAL: usuario no admin", {
                    "usuario": self.usuario,
                }, flush=True)
                await self.close(code=4403)
                return

            self.numero_asesor = "TODAS"
            self.grupo = "whatsapp_todas_las_lineas"

        else:
            numero_usuario = await obtener_numero_usuario(usuario_obj)

            if es_admin and numero_asesor_param:
                numero_asesor = numero_asesor_param
            else:
                numero_asesor = numero_usuario

            if not numero_asesor:
                print("WS CERRADO: usuario sin línea válida", {
                    "usuario": self.usuario,
                    "numero_asesor": numero_asesor,
                }, flush=True)
                await self.close(code=4401)
                return

            if numero_asesor not in WHATSAPP_LINES:
                print("WS CERRADO: numero_asesor no existe en WHATSAPP_LINES", {
                    "usuario": self.usuario,
                    "numero_asesor": numero_asesor,
                }, flush=True)
                await self.close(code=4403)
                return

            self.numero_asesor = numero_asesor
            self.grupo = f"whatsapp_linea_{numero_asesor}"

        await self.accept()

        await self.channel_layer.group_add(
            self.grupo,
            self.channel_name,
        )

        print("WS CONECTADO:", {
            "usuario": self.usuario,
            "numero_asesor": self.numero_asesor,
            "grupo": self.grupo,
            "channel_name": self.channel_name,
        }, flush=True)

        await self.send_json({
            "tipo": "conexion_establecida",
            "numero_asesor": self.numero_asesor,
            "grupo": self.grupo,
        })

    async def disconnect(self, close_code):
        if self.grupo:
            await self.channel_layer.group_discard(
                self.grupo,
                self.channel_name,
            )

        print("WS DESCONECTADO:", {
            "usuario": getattr(self, "usuario", ""),
            "numero_asesor": getattr(self, "numero_asesor", ""),
            "grupo": getattr(self, "grupo", ""),
            "close_code": close_code,
        }, flush=True)

    async def receive_json(self, content, **kwargs):
        print("WS MENSAJE RECIBIDO DESDE FRONT:", content, flush=True)

    async def whatsapp_mensaje(self, event):
        print("WS ENVIANDO MENSAJE A FRONT:", {
            "grupo": getattr(self, "grupo", ""),
            "telefono": event.get("telefono", ""),
            "numero_asesor": event.get("numero_asesor", ""),
            "mensaje": event.get("mensaje", ""),
        }, flush=True)

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