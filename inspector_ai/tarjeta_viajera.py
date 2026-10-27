
from datetime import datetime
from pathlib import Path
import unicodedata
from zoneinfo import ZoneInfo

import fitz


RUTA_PLANTILLA = Path(__file__).resolve().parent / "plantillas" / "tarjeta_viajera.pdf"
COLOR_TEXTO = (0.02, 0.20, 0.38)


def preparar_texto(valor):
    texto = str(valor or "").strip().replace("\n", " ")
    return texto.encode("cp1252", errors="replace").decode("cp1252")


def escribir(pagina, x, y, valor, ancho, tamano=8):
    texto = preparar_texto(valor)
    if not texto:
        return

    while tamano > 5 and fitz.get_text_length(
        texto, fontname="helv", fontsize=tamano
    ) > ancho:
        tamano -= 0.5

    while texto and fitz.get_text_length(
        texto, fontname="helv", fontsize=tamano
    ) > ancho:
        texto = texto[:-4].rstrip() + "..."

    pagina.insert_text(
        (x, y), texto,
        fontname="helv",
        fontsize=tamano,
        color=COLOR_TEXTO
    )


def marcar(pagina, x, y):
    pagina.draw_line(
        (x - 2, y - 2), (x + 2, y + 2),
        color=COLOR_TEXTO, width=1.1
    )
    pagina.draw_line(
        (x - 2, y + 2), (x + 2, y - 2),
        color=COLOR_TEXTO, width=1.1
    )


def escribir_observaciones(pagina, valor):
    texto = preparar_texto(valor)
    if not texto:
        return

    if len(texto) > 190:
        texto = texto[:187].rstrip() + "..."

    while texto:
        resultado = pagina.insert_textbox(
            fitz.Rect(75, 207, 570, 225),
            texto,
            fontname="helv",
            fontsize=7,
            lineheight=1.05,
            color=COLOR_TEXTO
        )
        if resultado >= 0:
            return
        texto = texto[:-23].rstrip(". ") + "..." if len(texto) > 26 else ""


def fecha_local(valor):
    if not valor:
        return None

    if isinstance(valor, datetime) and valor.tzinfo is not None and valor.utcoffset() is not None:
        return valor.astimezone(ZoneInfo("America/Mexico_City"))

    return valor

def escribir_caja(pagina, rectangulo, valor):
    texto = preparar_texto(valor)

    if not texto:
        return

    for tamano in (8, 7, 6, 5):
        resultado = pagina.insert_textbox(
            rectangulo,
            texto,
            fontname="helv",
            fontsize=tamano,
            color=COLOR_TEXTO,
            lineheight=1.1
        )

        if resultado >= 0:
            return

def generar_tarjeta_viajera(cita):
    cliente = cita.cliente

    nombre = getattr(cliente, "nombre", "") or cita.nombre_cliente
    telefono = getattr(cliente, "telefono", "") or ""
    correo = getattr(cliente, "correo", "") or getattr(cliente, "correo_electronico", "") or ""

    modelo = " ".join(
        parte for parte in (cita.anio_vehiculo, cita.modelo) if parte
    )

    fecha_cita = fecha_local(cita.fecha_ingreso)
    hora_promesa = fecha_local(cita.hora_promesa)

    with fitz.open(str(RUTA_PLANTILLA)) as documento:
        pagina = documento[0]

        escribir(pagina, 111, 148, nombre, 207, 8.5)
        escribir(pagina, 383, 148, cita.vin, 194, 8.5)
        escribir(pagina, 98, 187, telefono, 70, 7.5)
        escribir(pagina, 247, 187, correo, 126, 7.2)
        escribir(pagina, 439, 187, modelo, 38, 7)
        escribir(pagina, 89, 170, cita.no_orden, 120, 7)
        escribir(pagina, 290, 127, cita.diss, 87, 7)

        if fecha_cita:
            escribir(pagina, 138, 105, fecha_cita.strftime("%d/%m/%Y"), 71, 7)
            escribir(pagina, 138, 128, fecha_cita.strftime("%H:%M"), 27, 7)

        if hora_promesa:
            escribir(pagina, 176, 128, hora_promesa.strftime("%H:%M"), 31, 7)

        tipo_cita = unicodedata.normalize("NFD", cita.tipo_cita or "")
        tipo_cita = "".join(
            c for c in tipo_cita if unicodedata.category(c) != "Mn"
        ).lower()

        if "mantenimiento" in tipo_cita:
            marcar(pagina, 125, 93)

        if "reparacion" in tipo_cita and "repetida" not in tipo_cita:
            marcar(pagina, 125, 105)

        if "diagnostico" in tipo_cita:
            marcar(pagina, 125, 116)

        if "repetida" in tipo_cita:
            marcar(pagina, 125, 128)

        if cita.long_drive is not None:
            marcar(pagina, 305 if cita.long_drive else 352, 93)

        marcar(pagina, 414 if cita.pre_picking_hecho else 460, 120)

        observaciones = cita.declaracion_textual_cliente or cita.comentarios
        escribir_observaciones(pagina, observaciones)

        taller = getattr(cita, "taller", None)
        if taller:
            escribir(pagina, 485, 534, taller.tecnico, 95, 7)

        if cita.no_orden:
            escribir(documento[2], 46, 92, cita.no_orden, 85, 8)

        detalle = getattr(cita, "tarjeta_viajera_detalle", None)
        datos = detalle.datos if detalle else {}

        if datos:
            escribir_caja(pagina,fitz.Rect(80, 730, 450, 755),datos.get("observaciones_taller", ""))
            escribir(documento[1],69,119,datos.get("km_inicial_prueba_1"),75,8)
            escribir(documento[1],166,119,datos.get("km_final_prueba_1"),75,8)

        return documento.tobytes(garbage=4, deflate=True)
