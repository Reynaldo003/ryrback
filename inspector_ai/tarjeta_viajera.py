from datetime import datetime
from pathlib import Path
import unicodedata
from zoneinfo import ZoneInfo
import fitz
from .campos_tarjeta_viajera import CAMPOS_TARJETA_VIAJERA

RUTA_PLANTILLA = Path(__file__).resolve().parent / 'plantillas' / 'tarjeta_viajera.pdf'
COLOR_TEXTO = (0.02, 0.20, 0.38)


def preparar_texto(valor):
    if valor is None:
        return ''
    texto = str(valor).strip().replace('\n', ' ')
    return texto.encode('cp1252', errors='replace').decode('cp1252')


def escribir(pagina, x, y, valor, ancho, tamano=8):
    texto = preparar_texto(valor)
    if not texto:
        return
    while tamano > 5 and fitz.get_text_length(texto, fontname='helv', fontsize=tamano) > ancho:
        tamano -= 0.5
    if fitz.get_text_length(texto, fontname='helv', fontsize=tamano) > ancho:
        while texto and fitz.get_text_length(texto + '...', fontname='helv', fontsize=tamano) > ancho:
            texto = texto[:-1]
        texto = texto.rstrip() + '...' if texto else ''
    if texto:
        pagina.insert_text((x, y), texto, fontname='helv', fontsize=tamano, color=COLOR_TEXTO)


def marcar(pagina, x, y):
    pagina.draw_line((x - 2, y - 2), (x + 2, y + 2), color=COLOR_TEXTO, width=1.1)
    pagina.draw_line((x - 2, y + 2), (x + 2, y - 2), color=COLOR_TEXTO, width=1.1)


def dibujar_nivel_gasolina(pagina, valor):
    """Relleno vertical dentro de la columna del medidor (sin tocar la reserva roja)."""
    niveles = {'reserva': 0.0, '1/4': 0.25, '1/2': 0.5, '3/4': 0.75, 'lleno': 1.0}
    proporcion = niveles.get(str(valor).lower())
    if proporcion is None or proporcion <= 0:
        return
    # Bordes verificados sobre la plantilla PDF de 609 × 794.25 pt.
    izquierda, derecha = 231.5, 243.5
    superior, inferior = 269.0, 368.0
    alto = (inferior - superior) * proporcion
    pagina.draw_rect(
        fitz.Rect(izquierda, inferior - alto, derecha, inferior),
        fill=(0.03, 0.40, 0.75), color=None, overlay=True,
    )
    # Repintar las divisiones del indicador para conservar su lectura.
    for y in (275.5, 300.0, 325.0, 350.0):
        if inferior - alto <= y <= inferior:
            pagina.draw_line((izquierda, y), (derecha, y), color=COLOR_TEXTO, width=0.85, overlay=True)


def escribir_observaciones(pagina, valor):
    escribir_caja(pagina, fitz.Rect(75, 207, 570, 225), valor, tamano_max=7)


def fecha_local(valor):
    if not valor:
        return None
    if isinstance(valor, datetime) and valor.tzinfo is not None and valor.utcoffset() is not None:
        return valor.astimezone(ZoneInfo('America/Mexico_City'))
    return valor


def escribir_caja(pagina, rectangulo, valor, tamano_max=8):
    """Alinea texto con margen dentro de la celda y evita dibujar fuera de ella.

    Usa una página temporal para medir: insert_textbox en PyMuPDF puede insertar
    fragmentos incluso cuando indica insuficiencia de espacio.
    """
    texto = preparar_texto(valor)
    if not texto:
        return
    area = fitz.Rect(rectangulo.x0 + 2.5, rectangulo.y0 + 1.0,
                     rectangulo.x1 - 2.5, rectangulo.y1 - 0.7)
    if area.width <= 2 or area.height <= 3:
        return
    for fuente in (tamano_max, 7, 6, 5):
        with fitz.open() as temporal:
            prueba = temporal.new_page(width=pagina.rect.width, height=pagina.rect.height)
            resultado = prueba.insert_textbox(area, texto, fontname='helv', fontsize=fuente,
                                             color=COLOR_TEXTO, lineheight=1.0)
        if resultado >= 0:
            pagina.insert_textbox(area, texto, fontname='helv', fontsize=fuente,
                                 color=COLOR_TEXTO, lineheight=1.0)
            return
    # Texto muy largo: reducir a una sola línea con elipsis sin invadir otras celdas.
    escribir(pagina, area.x0, area.y0 + min(6, area.height - 1), texto, area.width, 5)


def dibujar_campos_editables(documento, cita):
    detalle = getattr(cita, 'tarjeta_viajera_detalle', None)
    datos = (getattr(detalle, 'datos', None) or {}) if detalle else {}
    for campo in CAMPOS_TARJETA_VIAJERA:
        valor = datos.get(campo['nombre'])
        if valor is None or valor == '':
            continue
        pagina = documento[campo['pagina'] - 1]
        tipo = campo['tipo']
        if campo['nombre'] == 'nivel_gasolina':
            dibujar_nivel_gasolina(pagina, valor)
            continue
        if tipo == 'casilla':
            if valor is True:
                marcar(pagina, campo['x'], campo['y'])
            continue
        if tipo == 'opcion':
            for opcion in campo['opciones']:
                if opcion['valor'] == valor:
                    marcar(pagina, opcion['x'], opcion['y'])
                    break
            continue
        if tipo == 'fecha':
            try:
                valor = datetime.strptime(valor, '%Y-%m-%d').strftime('%d/%m/%Y')
            except (ValueError, TypeError):
                continue
        rectangulo = fitz.Rect(campo['x'], campo['y'],
                              campo['x'] + campo['ancho'], campo['y'] + campo['alto'])
        escribir_caja(pagina, rectangulo, valor)


def generar_tarjeta_viajera(cita):
    cliente = cita.cliente
    nombre = getattr(cliente, 'nombre', '') or cita.nombre_cliente
    telefono = getattr(cliente, 'telefono', '') or ''
    correo = getattr(cliente, 'correo', '') or getattr(cliente, 'correo_electronico', '') or ''
    modelo = ' '.join(str(parte) for parte in (cita.anio_vehiculo, cita.modelo) if parte)
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
            escribir(pagina, 138, 105, fecha_cita.strftime('%d/%m/%Y'), 71, 7)
            escribir(pagina, 138, 128, fecha_cita.strftime('%H:%M'), 27, 7)
        if hora_promesa:
            escribir(pagina, 176, 128, hora_promesa.strftime('%H:%M'), 31, 7)
        tipo_cita = unicodedata.normalize('NFD', cita.tipo_cita or '')
        tipo_cita = ''.join(c for c in tipo_cita if unicodedata.category(c) != 'Mn').lower()
        if 'mantenimiento' in tipo_cita:
            marcar(pagina, 125, 93)
        if 'reparacion' in tipo_cita and 'repetida' not in tipo_cita:
            marcar(pagina, 125, 105)
        if 'diagnostico' in tipo_cita:
            marcar(pagina, 125, 116)
        if 'repetida' in tipo_cita:
            marcar(pagina, 125, 128)
        if cita.long_drive is not None:
            marcar(pagina, 305 if cita.long_drive else 352, 93)
        marcar(pagina, 414 if cita.pre_picking_hecho else 460, 120)
        observaciones = cita.declaracion_textual_cliente or cita.comentarios
        escribir_observaciones(pagina, observaciones)
        taller = getattr(cita, 'taller', None)
        if taller:
            escribir(pagina, 485, 534, taller.tecnico, 95, 7)
        if cita.no_orden:
            escribir(documento[2], 46, 92, cita.no_orden, 85, 8)
        dibujar_campos_editables(documento, cita)
        return documento.tobytes(garbage=4, deflate=True)
