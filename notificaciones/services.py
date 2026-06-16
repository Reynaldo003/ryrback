# notificaciones/services.py
import requests

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from citas.models import normaliza_tel_mx
from CrmConformidad.models import FirebaseToken, Usuario


def normalizar_numero_asesor(numero):
    """
    Convierte cualquier teléfono a formato:
    52 + 10 dígitos

    Ejemplos:
    2711872907       -> 522711872907
    52711872907      -> 522711872907
    522711872907     -> 522711872907
    +52 271 187 2907 -> 522711872907
    +52 1 271...     -> 522711872907
    """
    digits = "".join(c for c in str(numero or "") if c.isdigit())

    if not digits:
        return ""

    # Caso antiguo WhatsApp México: 521 + 10 dígitos
    if digits.startswith("521") and len(digits) == 13:
        return "52" + digits[3:]

    # Número nacional de 10 dígitos
    if len(digits) == 10:
        return "52" + digits

    # Ya viene como 52 + 10 dígitos
    if digits.startswith("52") and len(digits) == 12:
        return digits

    return normaliza_tel_mx(digits)


def buscar_usuario_por_numero_asesor(numero_asesor):
    """
    Busca al usuario asesor por teléfono.

    Como tú confirmaste que en BD se guarda así:
    522711872907

    Primero intentamos búsqueda exacta.
    Si no aparece, hacemos fallback normalizando todos los teléfonos.
    """
    numero_normalizado = normalizar_numero_asesor(numero_asesor)

    if not numero_normalizado:
        return None

    usuario = Usuario.objects.filter(telefono=numero_normalizado).first()

    if usuario:
        return usuario

    # Fallback por si algún usuario tiene el teléfono con espacios,
    # +52, 521, guiones o diferente formato.
    for usuario in Usuario.objects.all():
        telefono_usuario = normalizar_numero_asesor(
            getattr(usuario, "telefono", "") or ""
        )

        if telefono_usuario == numero_normalizado:
            return usuario

    return None


def token_expo_valido(token):
    """
    Expo Push Service usa el ExpoPushToken obtenido con
    Notifications.getExpoPushTokenAsync().
    Algunos proyectos devuelven ExponentPushToken[...] y otros ExpoPushToken[...].
    Aceptamos ambos para no descartar tokens válidos.
    """
    token = (token or "").strip()

    return (
        token.startswith("ExponentPushToken[")
        or token.startswith("ExpoPushToken[")
    )


def notificar_mensaje_whatsapp(
    *,
    numero_asesor: str,
    telefono: str,
    nombre: str = "",
    mensaje: str = "",
    wa_message_id: str = "",
    expediente_id=None,
    created_at=None,
):
    numero_asesor = normalizar_numero_asesor(numero_asesor)
    telefono = normaliza_tel_mx(telefono)

    if not numero_asesor or not telefono:
        print("NOTIFICACION OMITIDA: faltan datos", {
            "numero_asesor": numero_asesor,
            "telefono": telefono,
        }, flush=True)
        return False

    payload_ws = {
        "type": "whatsapp_mensaje",
        "telefono": telefono,
        "numero_asesor": numero_asesor,
        "nombre": nombre or "Prospecto",
        "mensaje": mensaje or "Nuevo mensaje de WhatsApp",
        "wa_message_id": wa_message_id or "",
        "expediente_id": expediente_id,
        "created_at": created_at.isoformat() if created_at else "",
        "url": f"/comercial/prospectos/contacto?tel={telefono}&direct=1",
    }

    # 1. WebSocket para app/web abierta.
    channel_layer = get_channel_layer()

    if channel_layer is None:
        print("NOTIFICACION WS OMITIDA: channel_layer None", flush=True)
    else:
        grupos = [
            f"whatsapp_linea_{numero_asesor}",
            "whatsapp_todas_las_lineas",
        ]

        for grupo in grupos:
            print("NOTIFICACION WS ENVIANDO:", {
                "grupo": grupo,
                "telefono": telefono,
                "numero_asesor": numero_asesor,
                "nombre": payload_ws["nombre"],
                "mensaje": payload_ws["mensaje"],
                "wa_message_id": payload_ws["wa_message_id"],
            }, flush=True)

            async_to_sync(channel_layer.group_send)(
                grupo,
                payload_ws,
            )

            print("NOTIFICACION WS ENVIADA:", {
                "grupo": grupo,
                "wa_message_id": wa_message_id,
            }, flush=True)

    # 2. Push notification para app cerrada / segundo plano.
    try:
        usuario = buscar_usuario_por_numero_asesor(numero_asesor)

        if not usuario:
            print("PUSH OMITIDO: no se encontró usuario con telefono normalizado", {
                "numero_asesor": numero_asesor,
            }, flush=True)
            return True

        resultado = enviar_notificacion_push(
            usuario=usuario,
            titulo=f"💬 {nombre or 'Nuevo mensaje'}",
            mensaje=mensaje or "Tienes un mensaje nuevo de WhatsApp",
            data_extra={
                "tipo": "whatsapp_mensaje",
                "pantalla": "ChatDetail",
                "telefono": telefono,
                "numero_asesor": numero_asesor,
                "wa_message_id": wa_message_id or "",
                "expediente_id": str(expediente_id or ""),
            },
        )

        print("RESULTADO PUSH:", {
            "usuario": getattr(usuario, "usuario", str(usuario)),
            "telefono_usuario": getattr(usuario, "telefono", ""),
            "resultado": resultado,
        }, flush=True)

    except Exception as e:
        print(f"PUSH OMITIDO por excepción: {e}", flush=True)

    return True


def enviar_notificacion_push(usuario, titulo, mensaje, data_extra=None):
    """
    Envía una push usando Expo Push API.

    Importante:
    Este flujo usa ExpoPushToken, no FCM token nativo.
    Expo recomienda enviar al endpoint de Expo Push Service el token
    obtenido con getExpoPushTokenAsync().
    """
    tokens_queryset = FirebaseToken.objects.filter(usuario=usuario)

    if not tokens_queryset.exists():
        print("PUSH OMITIDO: usuario sin tokens registrados", {
            "usuario": getattr(usuario, "usuario", str(usuario)),
            "telefono": getattr(usuario, "telefono", ""),
        }, flush=True)

        return {
            "status": "error",
            "message": "El usuario no tiene dispositivos registrados.",
        }

    listado_tokens = []

    for registro in tokens_queryset:
        token = (registro.token or "").strip()

        if token_expo_valido(token):
            listado_tokens.append(token)
        else:
            print("PUSH TOKEN OMITIDO: formato inválido", {
                "usuario": getattr(usuario, "usuario", str(usuario)),
                "token_inicio": token[:35],
            }, flush=True)

    if not listado_tokens:
        print("PUSH OMITIDO: sin tokens Expo válidos", {
            "usuario": getattr(usuario, "usuario", str(usuario)),
            "telefono": getattr(usuario, "telefono", ""),
        }, flush=True)

        return {
            "status": "error",
            "message": "No se encontraron tokens Expo válidos.",
        }

    url_expo = "https://exp.host/--/api/v2/push/send"

    data_extra = data_extra or {}

    # Expo recomienda que data sea un objeto simple serializable.
    data_limpia = {
        str(k): str(v)
        for k, v in data_extra.items()
        if v is not None
    }

    payload = []

    for token in listado_tokens:
        payload.append({
            "to": token,
            "title": titulo,
            "body": mensaje,
            "sound": "default",
            "priority": "high",
            "channelId": "default",
            "data": data_limpia,
        })

    print("PUSH ENVIANDO:", {
        "usuario": getattr(usuario, "usuario", str(usuario)),
        "telefono_usuario": getattr(usuario, "telefono", ""),
        "tokens": len(listado_tokens),
        "titulo": titulo,
        "mensaje": mensaje,
    }, flush=True)

    try:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
        }

        response = requests.post(
            url_expo,
            json=payload,
            headers=headers,
            timeout=10,
        )

        try:
            response_data = response.json()
        except Exception:
            response_data = {
                "raw": response.text,
            }

        print("PUSH RESPUESTA EXPO:", {
            "status_code": response.status_code,
            "response": response_data,
        }, flush=True)

        if response.status_code == 200:
            return {
                "status": "success",
                "detalles": response_data,
            }

        return {
            "status": "error",
            "message": "Expo respondió con error.",
            "detalles": response_data,
        }

    except requests.exceptions.RequestException as e:
        print("PUSH ERROR conexión Expo:", str(e), flush=True)

        return {
            "status": "error",
            "message": f"Falló la conexión con Expo: {str(e)}",
        }