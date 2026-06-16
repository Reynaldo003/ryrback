import hashlib
import json
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import segno
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage

try:
    from PIL import Image, ImageOps, ImageDraw
    PIL_DISPONIBLE = True
    try:
        RESAMPLE = Image.Resampling.LANCZOS
    except AttributeError:
        RESAMPLE = Image.LANCZOS
except Exception:
    PIL_DISPONIBLE = False
    Image = None
    ImageOps = None
    ImageDraw = None
    RESAMPLE = None


def validar_url_http(url):
    url = str(url or "").strip()
    partes = urlparse(url)

    if partes.scheme not in ("http", "https") or not partes.netloc:
        raise ValidationError("Debes enviar un link válido que inicie con http:// o https://")

    return url


def a_bool(valor, default=False):
    if valor is None:
        return default
    return str(valor).strip().lower() in ("1", "true", "yes", "si", "sí", "on")


def a_int(valor, default, minimo=None, maximo=None):
    try:
        numero = int(valor)
    except Exception:
        numero = default

    if minimo is not None and numero < minimo:
        numero = minimo
    if maximo is not None and numero > maximo:
        numero = maximo

    return numero


def normalizar_color(valor, default=None):
    valor = str(valor or "").strip()
    if not valor:
        return default

    if valor.lower() in ("transparent", "none"):
        return None

    return valor


def leer_opciones(data):
    formato = str(data.get("formato") or "png").strip().lower()
    if formato not in ("png", "svg"):
        formato = "png"

    error = str(data.get("error") or "h").strip().lower()
    if error not in ("l", "m", "q", "h"):
        error = "h"

    return {
        "nombre_archivo": str(data.get("nombre_archivo") or "qr").strip(),
        "formato": formato,
        "escala": a_int(data.get("escala"), 8, 1, 40),
        "borde": a_int(data.get("borde"), 4, 0, 20),
        "error": error,
        "dark": normalizar_color(data.get("dark"), "#000000"),
        "light": normalizar_color(data.get("light"), "#FFFFFF"),
        "finder_dark": normalizar_color(data.get("finder_dark")),
        "finder_light": normalizar_color(data.get("finder_light")),
        "data_dark": normalizar_color(data.get("data_dark")),
        "data_light": normalizar_color(data.get("data_light")),
        "alignment_dark": normalizar_color(data.get("alignment_dark")),
        "alignment_light": normalizar_color(data.get("alignment_light")),
        "quiet_zone": normalizar_color(data.get("quiet_zone")),
        "logo_size": a_int(data.get("logo_size"), 20, 10, 30),
        "fondo_opacidad": a_int(data.get("fondo_opacidad"), 170, 0, 255),
        "usar_micro": a_bool(data.get("usar_micro"), False),
    }


def leer_archivo_bytes(archivo):
    if not archivo:
        return None
    data = archivo.read()
    try:
        archivo.seek(0)
    except Exception:
        pass
    return data


def hash_bytes(data):
    if not data:
        return None
    return hashlib.sha256(data).hexdigest()


def construir_firma(url, opciones, logo_bytes=None, fondo_bytes=None):
    opciones_firma = dict(opciones)
    opciones_firma.pop("nombre_archivo", None)

    payload = {
        "url": url,
        "opciones": opciones_firma,
        "logo_sha256": hash_bytes(logo_bytes),
        "fondo_sha256": hash_bytes(fondo_bytes),
    }

    crudo = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(crudo).hexdigest()


def obtener_storage(subcarpeta):
    relativa = Path("encuestas") / "qr" / subcarpeta
    location = Path(settings.MEDIA_ROOT) / relativa
    location.mkdir(parents=True, exist_ok=True)

    base_url = f"{settings.MEDIA_URL.rstrip('/')}/{relativa.as_posix()}/"

    storage = FileSystemStorage(
        location=str(location),
        base_url=base_url,
    )
    return storage, relativa.as_posix()


def crear_qr(url, error="h", usar_micro=False):
    return segno.make(url, error=error, micro=usar_micro)


def kwargs_colores(opciones, light_override="_usar_normal"):
    kwargs = {
        "dark": opciones["dark"],
        "scale": opciones["escala"],
        "border": opciones["borde"],
    }

    if light_override != "_usar_normal":
        kwargs["light"] = light_override
    else:
        kwargs["light"] = opciones["light"]

    opcionales = [
        "finder_dark",
        "finder_light",
        "data_dark",
        "data_light",
        "alignment_dark",
        "alignment_light",
        "quiet_zone",
    ]

    for clave in opcionales:
        valor = opciones.get(clave)
        if valor is not None:
            kwargs[clave] = valor

    return kwargs


def generar_qr_simple_bytes(url, opciones):
    qr = crear_qr(url, error=opciones["error"], usar_micro=opciones["usar_micro"])
    salida = BytesIO()

    qr.save(
        salida,
        kind=opciones["formato"],
        **kwargs_colores(opciones),
    )

    salida.seek(0)
    contenido = salida.getvalue()
    extension = opciones["formato"]
    mime = "image/png" if extension == "png" else "image/svg+xml"

    return contenido, extension, mime


def abrir_imagen_desde_bytes(data):
    if not PIL_DISPONIBLE:
        raise ValidationError("Para usar logo o fondo necesitas instalar Pillow: pip install Pillow")

    try:
        return Image.open(BytesIO(data)).convert("RGBA")
    except Exception:
        raise ValidationError("No se pudo procesar una de las imágenes enviadas.")


def qr_png_transparente(url, opciones):
    qr = crear_qr(url, error=opciones["error"], usar_micro=opciones["usar_micro"])
    salida = BytesIO()

    kwargs = kwargs_colores(opciones, light_override=None)
    qr.save(salida, kind="png", **kwargs)

    salida.seek(0)
    return Image.open(salida).convert("RGBA")


def aplicar_fondo(url, opciones, fondo_bytes):
    qr_img = qr_png_transparente(url, opciones)
    fondo_img = abrir_imagen_desde_bytes(fondo_bytes)

    fondo_img = ImageOps.fit(fondo_img, qr_img.size, method=RESAMPLE)

    velo = Image.new("RGBA", qr_img.size, (255, 255, 255, opciones["fondo_opacidad"]))
    base = Image.alpha_composite(fondo_img, velo)
    base.alpha_composite(qr_img)

    return base


def aplicar_logo(imagen_base, logo_bytes, logo_size_pct):
    logo_img = abrir_imagen_desde_bytes(logo_bytes)

    lado_max = int(min(imagen_base.size) * (logo_size_pct / 100.0))
    lado_max = max(40, lado_max)

    logo_img.thumbnail((lado_max, lado_max), RESAMPLE)

    padding = max(8, int(lado_max * 0.18))
    caja_w = logo_img.width + padding * 2
    caja_h = logo_img.height + padding * 2

    fondo_logo = Image.new("RGBA", (caja_w, caja_h), (255, 255, 255, 0))
    mascara = Image.new("L", (caja_w, caja_h), 0)
    draw = ImageDraw.Draw(mascara)
    radio = max(10, int(min(caja_w, caja_h) * 0.18))
    draw.rounded_rectangle((0, 0, caja_w - 1, caja_h - 1), radius=radio, fill=235)
    fondo_logo.putalpha(mascara)

    pos_fondo = ((imagen_base.width - caja_w) // 2, (imagen_base.height - caja_h) // 2)
    pos_logo = ((imagen_base.width - logo_img.width) // 2, (imagen_base.height - logo_img.height) // 2)

    imagen_base.alpha_composite(fondo_logo, pos_fondo)
    imagen_base.alpha_composite(logo_img, pos_logo)

    return imagen_base


def generar_qr_personalizado_bytes(url, opciones, logo_bytes=None, fondo_bytes=None):
    if not PIL_DISPONIBLE:
        raise ValidationError("Para generar QR con logo o fondo necesitas Pillow: pip install Pillow")

    if fondo_bytes:
        imagen = aplicar_fondo(url, opciones, fondo_bytes)
    else:
        imagen = qr_png_transparente(url, opciones)

        if opciones["light"] is not None:
            base = Image.new("RGBA", imagen.size, opciones["light"])
            base.alpha_composite(imagen)
            imagen = base

    if logo_bytes:
        imagen = aplicar_logo(imagen, logo_bytes, opciones["logo_size"])

    salida = BytesIO()
    imagen.save(salida, format="PNG")
    salida.seek(0)

    return salida.getvalue(), "png", "image/png"


def construir_url_publica(request, relative_url):
    if request is None:
        return relative_url
    return request.build_absolute_uri(relative_url)


def generar_qr_permanente(data, files, request=None):
    url = validar_url_http(data.get("url"))
    opciones = leer_opciones(data)

    logo_bytes = leer_archivo_bytes(files.get("logo"))
    fondo_bytes = leer_archivo_bytes(files.get("background"))

    es_personalizado = bool(logo_bytes or fondo_bytes)
    subcarpeta = "personalizados" if es_personalizado else "simples"

    if es_personalizado:
        contenido, extension, mime = generar_qr_personalizado_bytes(
            url=url,
            opciones=opciones,
            logo_bytes=logo_bytes,
            fondo_bytes=fondo_bytes,
        )
    else:
        contenido, extension, mime = generar_qr_simple_bytes(url, opciones)

    firma = construir_firma(url, opciones, logo_bytes, fondo_bytes)
    public_id = firma[:24]
    nombre_real = f"{public_id}.{extension}"

    storage, relativa = obtener_storage(subcarpeta)

    ya_existia = storage.exists(nombre_real)
    if not ya_existia:
        storage.save(nombre_real, ContentFile(contenido))

    relative_url = storage.url(nombre_real)
    qr_url = construir_url_publica(request, relative_url)

    return {
        "ok": True,
        "ya_existia": ya_existia,
        "tipo_qr": "personalizado" if es_personalizado else "simple",
        "public_id": public_id,
        "url_destino": url,
        "qr_url": qr_url,
        "qr_path": f"{relativa}/{nombre_real}",
        "mime_type": mime,
        "formato": extension,
    }


def obtener_capacidades_qr():
    return {
        "requiere_bd": False,
        "persistencia": "archivo_en_disco",
        "segno_disponible": True,
        "logo_disponible": PIL_DISPONIBLE,
        "fondo_disponible": PIL_DISPONIBLE,
        "formatos_simples": ["png", "svg"],
        "formatos_personalizados": ["png"],
    }