# notificaciones/consumers.py
import re
import unicodedata
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


AGENCIAS_CONOCIDAS = (
    ("cordoba", "VW Cordoba"),
    ("orizaba", "VW Orizaba"),
    ("poza rica", "VW Poza Rica"),
    ("tuxtepec", "VW Tuxtepec"),
    ("tuxpan", "VW Tuxpan"),
    ("automotriz r&r", "Automotriz R&R"),
)


def _texto(valor):
    return str(valor or "").strip()


def _normaliza_agencia(valor):
    texto = _texto(valor).lower()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(
        c for c in texto if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[^a-z0-9]+", " ", texto).strip()


def _grupo_agencia(valor):
    """
    Unifica variantes de agencia en un grupo canónico.

    "VW Cordoba Usados" y "VW Cordoba" -> "VW Cordoba"
    """
    texto = _normaliza_agencia(valor)

    for token, label in AGENCIAS_CONOCIDAS:
        if _normaliza_agencia(token) in texto:
            return label

    return _texto(valor)


def _agencias_usuario(raw_agencias):
    agencias = set()

    for parte in re.split(r"[|,;\n]+", str(raw_agencias or "")):
        agencia = _grupo_agencia(parte)

        if agencia:
            agencias.add(agencia)

    return agencias


def _agencia_coincide(agencia_linea, agencias_usuario):
    grupo_linea = _grupo_agencia(agencia_linea)

    return any(
        _grupo_agencia(agencia) == grupo_linea
        for agencia in agencias_usuario
    )


def _es_asesor_digital(rol):
    return _texto(rol).lower() == "asesor digital"


# Roles que pueden recibir notificaciones de WhatsApp por WebSocket.
# Los asesores generales/coordinadores siguen la misma regla de líneas
# (agencia + teléfonos propios / WHATSAPP_LINES.asesores): nadie
# amplía su alcance por el solo hecho de tener el rol.
ROLES_NOTIFICACIONES = frozenset({
    "asesor digital",
    "asesor general",
    "coordinador digital",
})


def _es_rol_con_notificaciones(rol):
    return _texto(rol).lower() in ROLES_NOTIFICACIONES


# Logins con acceso total a todas las líneas WhatsApp,
# independientemente de su rol (p. ej. dirección).
USUARIOS_ACCESO_TOTAL = frozenset({
    "rey",
})


def _usuario_con_acceso_total(contexto):
    return (
        _texto(contexto.get("usuario")).casefold()
        in USUARIOS_ACCESO_TOTAL
    )


def _detalle_lineas_asesor(contexto):
    """
    Detalle de cada línea de WHATSAPP_LINES contra el usuario.

    Regla de negocio:
      - Usuarios en USUARIOS_ACCESO_TOTAL (p. ej. "rey"): todas las líneas.
      - Roles con notificaciones: "asesor digital", "asesor general"
        y "coordinador digital".
      - Solo las líneas propias (usuario.telefono o usuario listado
        en WHATSAPP_LINES[].asesores[].usuario).
      - Solo dentro de su(s) agencia(s): un asesor de Córdoba nunca
        recibe notificaciones de Tuxtepec.
    """
    acceso_total = _usuario_con_acceso_total(contexto)

    if not acceso_total and not _es_rol_con_notificaciones(contexto.get("rol")):
        return []

    agencias_usuario = _agencias_usuario(contexto.get("agencia"))
    numeros_propios = obtener_numeros_telefono(contexto.get("telefono"))
    usuario_login = _texto(contexto.get("usuario")).casefold()

    detalle = []

    for numero, cfg in WHATSAPP_LINES.items():
        agencia_linea = cfg.get("agencia", "")
        agencia_ok = _agencia_coincide(agencia_linea, agencias_usuario)

        es_suya = numero in numeros_propios

        if not es_suya:
            for item in cfg.get("asesores") or []:
                if (
                    isinstance(item, dict)
                    and _texto(item.get("usuario")).casefold() == usuario_login
                ):
                    es_suya = True
                    break

        if acceso_total:
            agencia_ok = True
            es_suya = True

        detalle.append({
            "numero": numero,
            "agencia_linea": agencia_linea,
            "agencia_ok": agencia_ok,
            "es_suya": es_suya,
            "permitida": agencia_ok and es_suya,
        })

    return detalle


def _lineas_del_asesor(contexto):
    return [
        linea["numero"]
        for linea in _detalle_lineas_asesor(contexto)
        if linea["permitida"]
    ]


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

        contexto = {
            "usuario": getattr(usuario, "usuario", "") or "",
            "rol": getattr(
                getattr(usuario, "rol", None),
                "nombre",
                "",
            ) or "",
            "agencia": getattr(usuario, "agencia", "") or "",
            "telefono": getattr(usuario, "telefono", "") or "",
        }

        print("WS CONTEXTO:", contexto, flush=True)

        return contexto

    except Exception as e:
        print(
            "WS ERROR obteniendo contexto JWT:",
            f"{type(e).__name__}: {e}",
            flush=True,
        )
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

        contexto = await obtener_contexto_usuario_desde_jwt(token)

        if not contexto:
            await self.aceptar_y_cerrar(
                4401,
                subprotocol=subprotocol,
            )
            return

        self.usuario = contexto["usuario"]

        lineas = _lineas_del_asesor(contexto)

        print(
            "WS LINEAS:",
            {
                "usuario": self.usuario,
                "subprotocol": subprotocol,
                "lineas": lineas,
                "detalle": _detalle_lineas_asesor(contexto),
            },
            flush=True,
        )

        if not lineas:
            await self.aceptar_y_cerrar(
                4403,
                subprotocol=subprotocol,
            )
            return

        numero_param = normalizar_numero(
            params.get("numero_asesor", [""])[0]
        )

        if numero_param:
            if numero_param not in lineas:
                await self.aceptar_y_cerrar(
                    4403,
                    subprotocol=subprotocol,
                )
                return

            lineas = [numero_param]

        self.numero_asesor = (
            lineas[0]
            if len(lineas) == 1
            else "|".join(lineas)
        )

        self.grupos = [
            f"whatsapp_linea_{numero}"
            for numero in lineas
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

        print(
            "WS CONECTADO:",
            {
                "usuario": self.usuario,
                "grupos": self.grupos,
            },
            flush=True,
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