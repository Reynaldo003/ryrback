# logs/middleware.py
"""
Middleware de captura de logs de actividad por usuario.

Registra SOLO peticiones de modificación (POST/PUT/PATCH/DELETE) hechas
por usuarios autenticados y con respuesta exitosa. No loggea lecturas,
endpoints públicos, autenticación (se captura explícitamente en el login)
ni la propia API de logs.
"""
import json
import re

from .contexto import contexto as enriquecer_contexto, snapshot_entidad
from .helpers import (
    TIPOS,
    inferir_modulo,
    etiqueta_modulo,
    registrar_log,
)
from .snapshots import capturar_snapshot

_METODOS_MODIFICACION = {"POST", "PUT", "PATCH", "DELETE"}
_METODO_A_TIPO = {
    "POST": "CREAR",
    "PUT": "EDITAR",
    "PATCH": "EDITAR",
    "DELETE": "ELIMINAR",
}
_VERBO = {
    "CREAR": "Creó",
    "EDITAR": "Actualizó",
    "ELIMINAR": "Eliminó",
}

_EXCLUIR_PREFIJOS = (
    "/admin/",
    "/static/",
    "/media/",
    "/logs/",
    "/conformidad/api/auth/",
)

_PATRON_ENTIDAD = re.compile(r"/(\d+)/?$")

_BODY_MAX_BYTES = 64 * 1024

_DATOS_MAX_BYTES = 200 * 1024

_FORM_MAX_CLAVES = 12
_FORM_MAX_VALOR = 120
_FORM_RUIDO = {"csrfmiddlewaretoken"}


def _campos_form(request):
    """Campos escalares de formularios (multipart/urlencoded), sin archivos.

    Los endpoints que reciben archivos (p.ej. enviar-media) mandan el resto
    de campos (`to`, `text`) como formulario, no como JSON. Django cachea el
    parseo, así que la vista lo reutiliza sin problema. Valores recortados:
    solo se usan para describir la acción, nunca se guarda el payload.
    """
    content_type = (request.META.get("CONTENT_TYPE") or "").lower()
    if not (content_type.startswith("multipart/")
            or content_type.startswith("application/x-www-form-urlencoded")):
        return {}

    try:
        post = request.POST
    except Exception:
        return {}
    if not post:
        return {}

    try:
        claves = list(post.keys())[:_FORM_MAX_CLAVES]
    except Exception:
        return {}

    campos = {}
    for clave in claves:
        if clave in _FORM_RUIDO:
            continue
        try:
            valores = post.getlist(clave)
        except Exception:
            continue
        texto = str(valores[0] if valores else "")
        if len(texto) > _FORM_MAX_VALOR:
            texto = texto[:_FORM_MAX_VALOR] + "…"
        campos[str(clave)] = texto
    return campos


def _names_archivos(request):
    """Nombres de archivos subidos (multipart/form-urlencoded) para describir
    la acción. Leer `request.FILES` aquí es seguro: Django cachea el parseo y
    la vista (p.ej. MultiPartParser de DRF) reutiliza lo ya cargado."""
    content_type = (request.META.get("CONTENT_TYPE") or "").lower()
    if not (content_type.startswith("multipart/")
            or content_type.startswith("application/x-www-form-urlencoded")):
        return []

    try:
        archivos = request.FILES
    except Exception:
        return []

    nombres = []
    for _campo, fileobj in (archivos or {}).items():
        nombre = getattr(fileobj, "name", None)
        if nombre:
            nombres.append(str(nombre))
    return nombres


def _body_json(request):
    """Body JSON de POST/PUT/PATCH antes de que la vista lo consuma.

    Django cachea el body una vez leído, así que la vista sigue pudiendo
    leerlo con normalidad. Solo se lee si es JSON y no excede el límite.
    """
    if getattr(request, "method", "") not in _METODOS_MODIFICACION:
        return None
    if request.method == "DELETE":
        return None

    content_type = (request.META.get("CONTENT_TYPE") or "").lower()
    if not content_type.startswith("application/json"):
        return None

    try:
        length = int(request.META.get("CONTENT_LENGTH") or 0)
    except (TypeError, ValueError):
        length = 0
    if length and length > _BODY_MAX_BYTES:
        return None

    try:
        body = request.body
    except Exception:
        return None
    if not body or len(body) > _BODY_MAX_BYTES:
        return None

    try:
        data = json.loads(body.decode("utf-8", errors="replace"))
    except Exception:
        return None

    if not isinstance(data, dict):
        return None
    return data


def _usuario_autenticado(request):
    """Obtiene el Usuario autenticado vía el JWT del proyecto.

    En middleware no existe request.user del modelo Usuario (el monótono
    usa DRF dentro de las vistas), así que se autentica de nuevo con el
    mismo esquema. Solo corre en peticiones de modificación.
    """
    if not request.META.get("HTTP_AUTHORIZATION"):
        return None

    try:
        from CrmConformidad.jwt_authentication import CRMJWTAuthentication

        resultado = CRMJWTAuthentication().authenticate(request)
        if isinstance(resultado, (tuple, list)):
            return resultado[0]
    except Exception:
        return None

    return None


def _extraer_entidad(path, response):
    match = _PATRON_ENTIDAD.search(path)
    if match:
        return f"#{match.group(1)}"

    # Intenta obtener el id desde el body JSON der respuesta (creaciones/ediciones).
    try:
        content = getattr(response, "content", None) or b""
        if not content or len(content) > 2 * 1024 * 1024:
            return ""
        import json as _json

        data = _json.loads(content.decode("utf-8"))
        if isinstance(data, dict):
            id_valor = data.get("id")
            if id_valor is not None:
                return f"#{id_valor}"
    except Exception:
        pass

    return ""


def _limitar_datos(datos):
    """Snapshot JSON-safe; si excede el tamaño máximo se recortan los hijos
    y, en el peor caso, se descarta para no inflar la cola de logs."""
    if not datos:
        return None
    try:
        if len(json.dumps(datos, ensure_ascii=False).encode("utf-8")) <= _DATOS_MAX_BYTES:
            return datos
        recortado = {k: v for k, v in datos.items() if k != "hijos"}
        if len(json.dumps(recortado, ensure_ascii=False).encode("utf-8")) <= _DATOS_MAX_BYTES:
            return recortado
    except Exception:
        pass
    return None


def _construir_cambio(tipo, modulo, entidad, resumen="", entidad_enrich="", accion=""):
    verbo = _VERBO.get(tipo, "Modificó")
    target = entidad_enrich or entidad or "registro"
    base = accion or f"{verbo} {target}"
    if resumen:
        base += f" — {resumen}"
    elif not accion and not entidad_enrich and not entidad:
        base += f" en {etiqueta_modulo(modulo)}"
    return base


class LogActividadMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Guardar el body y los archivos subidos antes de que la vista los consuma.
        request._logs_body_json = _body_json(request)
        request._logs_form = _campos_form(request)
        request._logs_archivos = _names_archivos(request)
        response = self.get_response(request)
        return self._procesar(request, response)

    def process_view(self, request, view_func, view_args, view_kwargs):
        # Foto pre-borrado: en un DELETE el objeto ya no existe cuando se
        # procesa la respuesta, así que se captura la descripción y el
        # snapshot completo antes de que la vista lo elimine. Barato: solo
        # DELETE con patrón conocido.
        try:
            if getattr(request, "method", "") == "DELETE":
                path = getattr(request, "path", "") or ""
                datos = capturar_snapshot(path)
                if datos:
                    request._logs_snapshot_datos = datos
                    request._logs_snapshot_entidad = datos.get("descripcion") or ""
                else:
                    request._logs_snapshot_entidad = snapshot_entidad(path)
        except Exception:
            pass
        return None

    def _procesar(self, request, response):
        try:
            metodo = getattr(request, "method", "")
            path = getattr(request, "path", "") or ""

            if metodo not in _METODOS_MODIFICACION:
                return response

            status = getattr(response, "status_code", 0)
            if status < 200 or status >= 300:
                return response

            lower = path.lower()
            if any(lower.startswith(prefijo) for prefijo in _EXCLUIR_PREFIJOS):
                return response

            if metodo in _METODO_A_TIPO:
                tipo = _METODO_A_TIPO[metodo]
            else:
                tipo = "EDITAR"

            usuario = _usuario_autenticado(request)
            if usuario is None:
                return response

            modulo = inferir_modulo(path)
            entidad = _extraer_entidad(path, response)

            body_json = getattr(request, "_logs_body_json", None) or {}
            body_form = getattr(request, "_logs_form", None) or {}
            body = {**body_form, **body_json}
            detalle = enriquecer_contexto(
                path=path,
                metodo=metodo,
                body=body,
                snapshot_entidad=(
                    getattr(request, "_logs_snapshot_entidad", "") or ""
                ),
            )
            entidad_enrich = detalle.get("entidad") or ""
            resumen = detalle.get("resumen") or ""
            accion = detalle.get("accion") or ""

            archivos = getattr(request, "_logs_archivos", None) or []
            if archivos:
                texto_archivos = "Archivo(s): " + ", ".join(archivos[:8])
                resumen = f"{resumen}; {texto_archivos}" if resumen else texto_archivos

            cambio = _construir_cambio(
                tipo,
                modulo,
                entidad,
                resumen=resumen,
                entidad_enrich=entidad_enrich,
                accion=accion,
            )
            if entidad_enrich:
                entidad = entidad_enrich

            ip = request.META.get("REMOTE_ADDR")

            datos = None
            if tipo == "ELIMINAR":
                datos = _limitar_datos(
                    getattr(request, "_logs_snapshot_datos", None)
                )

            registrar_log(
                usuario=usuario,
                tipo=tipo,
                modulo=modulo,
                entidad=entidad,
                cambio=cambio,
                ip=ip,
                datos=datos,
            )
        except Exception:
            # Un fallo en el log jamás debe romper la respuesta.
            pass

        return response