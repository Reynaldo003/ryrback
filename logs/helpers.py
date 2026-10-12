# logs/helpers.py
"""
Helpers de captura de logs de actividad por usuario.

La captura es asíncrona al request: se encola JSON en Redis
(llave `crm_ryr:logs:queue`) y un worker (`python manage.py drainlogs`)
vuelca en lotes contra la base de datos. Si Redis no responde se escribe
directo (fallback) para no perder eventos ni bloquear la petición.
"""
import json
import time

from .models import LogActividad

QUEUE_KEY = "crm_ryr:logs:queue"
REDIS_HOST = "127.0.0.1"
REDIS_PORT = 6380
REDIS_DB = 1
REDIS_TIMEOUT = 0.4

TIPOS = {
    "CREAR": "crear",
    "EDITAR": "editar",
    "ELIMINAR": "eliminar",
    "LOGIN": "login",
    "LOGIN_FALLIDO": "login_fallido",
}

TIPOS_DISPONIBLES = [
    {"key": "CREAR", "label": "Creación"},
    {"key": "EDITAR", "label": "Edición"},
    {"key": "ELIMINAR", "label": "Eliminación"},
    {"key": "LOGIN", "label": "Inicio de sesión"},
    {"key": "LOGIN_FALLIDO", "label": "Intento fallido de sesión"},
]

# Prefijos de URL -> clave de módulo.
PREFIJOS_A_MODULO = {
    "conformidad": "calidad",
    "digitales": "digitales",
    "flujo": "calidad",
    "citas": "citas",
    "clickup": "clickup",
    "financieros": "financieros",
    "usados": "usados",
    "trafico-piso": "trafico_piso",
    "campanas-meta": "campanas_meta",
    "retencion": "retencion",
    "jdpower": "jdpower",
    "inventario": "inventario",
    "hojaingresos": "hoja_ingresos",
    "notificaciones": "notificaciones",
    "bitacoramantenimiento": "bitacora_mantenimiento",
    "documentacion": "documentacion",
    "gestion_inversion": "gestion_inversion",
    "ventas-vn": "ventas_vn",
    "refacciones-obsolescencia": "refacciones_obsolescencia",
    "presupuestos": "presupuestos",
    "compra-refacciones": "compra_refacciones",
    "gota": "gota",
    "ordenes-facturadas": "ordenes_facturadas",
    "venta-refacciones": "venta_refacciones",
}

MODULOS_ETIQUETAS = {
    "auth": "Autenticación",
    "calidad": "Calidad",
    "digitales": "Digitales",
    "citas": "Citas",
    "clickup": "ClickUp",
    "financieros": "Financieros",
    "usados": "Autos Usados",
    "trafico_piso": "Tráfico de Piso",
    "campanas_meta": "Campañas Meta",
    "retencion": "Retención",
    "jdpower": "JD Power",
    "inventario": "Inventario",
    "hoja_ingresos": "Hoja de Ingresos",
    "notificaciones": "Notificaciones",
    "bitacora_mantenimiento": "Bitácora Mantenimiento",
    "documentacion": "Documentación",
    "gestion_inversion": "Gestión de Inversión",
    "ventas_vn": "Ventas VN",
    "refacciones_obsolescencia": "Obsolescencia Refacciones",
    "presupuestos": "Presupuestos",
    "compra_refacciones": "Compra Refacciones",
    "gota": "GOTA",
    "ordenes_facturadas": "Órdenes Facturadas",
    "venta_refacciones": "Venta Refacciones",
    "rrhh": "RRHH",
    "safety": "Safety",
    "encuestas": "Encuestas",
    "pedidos_piezas": "Pedidos de Piezas",
    "otros": "Otros",
}


def etiqueta_modulo(clave):
    return MODULOS_ETIQUETAS.get(clave, clave or "Otros")


def modulos_disponibles():
    """Claves únicas usables: los prefijos mapeados + 'auth'."""
    claves = set(PREFIJOS_A_MODULO.values())
    claves.add("auth")
    return [
        {"key": clave, "label": etiqueta_modulo(clave)}
        for clave in sorted(claves)
    ]


def inferir_modulo(path):
    """Deriva la clave de módulo a partir del prefijo de la URL."""
    segmentos = [s for s in (path or "").split("/") if s]

    if not segmentos:
        return "otros"

    primero = segmentos[0].lower()

    if primero == "api" and len(segmentos) > 1:
        segundo = segmentos[1].lower()
        if segundo == "notificaciones":
            return "notificaciones"
        if segundo.startswith("bitacora"):
            return "bitacora_mantenimiento"
        # Encuestas / PedidosPiezas / Safety / rrhh viven bajo /api/
        for clave, nombres in (
            ("encuestas", ("encuesta", "encuestas")),
            ("pedidos_piezas", ("pedidos-piezas", "pedidos_piezas", "piezas")),
            ("safety", ("safety",)),
            ("rrhh", ("rrhh",)),
        ):
            if segundo in nombres or segundo.startswith(tuple(nombres)):
                return clave

    return PREFIJOS_A_MODULO.get(primero, "otros")


def _redis_cliente():
    try:
        import redis
    except Exception:
        return None

    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        socket_connect_timeout=REDIS_TIMEOUT,
        socket_timeout=REDIS_TIMEOUT,
        decode_responses=True,
    )


def registrar_log(*, usuario, tipo, modulo="otros", entidad="", cambio="", ip=None):
    """Encola un evento de log por usuario.

    `usuario` puede ser una instancia, un id (int) o None.
    El encolado a Redis falla silenciosamente a escritura directa para no
    romper la petición ni perder el evento.
    """
    usuario_id = getattr(usuario, "id_usuario", usuario) if usuario is not None else None

    if tipo not in TIPOS:
        tipo = "EDITAR"

    payload = {
        "usuario_id": usuario_id,
        "tipo": tipo,
        "modulo": modulo,
        "entidad": str(entidad or "")[:250],
        "cambio": str(cambio or ""),
        "ip": ip,
        "fecha": int(time.time()),
    }

    try:
        cliente = _redis_cliente()
        if cliente is not None:
            cliente.rpush(QUEUE_KEY, json.dumps(payload, ensure_ascii=False))
            return True
    except Exception:
        pass

    try:
        LogActividad.objects.create(
            usuario_id=usuario_id,
            tipo=tipo,
            modulo=modulo,
            entidad=payload["entidad"],
            cambio=payload["cambio"],
            ip=ip,
        )
    except Exception:
        return False

    return True


def esperar_cola():
    """Tamaño actual de la cola (para monitoreo)."""
    try:
        cliente = _redis_cliente()
        if cliente is None:
            return 0
        return int(cliente.llen(QUEUE_KEY))
    except Exception:
        return 0