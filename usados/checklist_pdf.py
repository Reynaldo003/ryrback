# usados/checklist_pdf.py
"""PDF de la Lista de verificación CPO (114 puntos).

Replica la pestaña "Lista de verificación" de ChecklistVerificacion.jsx:

  - Sección A: datos del vehículo (formulario).
  - Sección B: documentación → columnas "Verificado" y "N/A" con fechas,
    KM, textos y sub-elementos (herramientas de abordo).
  - Secciones C–I → columnas "Primer control" y "Estado definitivo" (P / O / NA).

Los datos provienen de avaluo.checklist_cpo (snapshot JSON que guarda el
frontend). Si el avalúo no tiene checklist, se imprime en blanco para
llenar a mano.
"""

import os
from io import BytesIO
from xml.sax.saxutils import escape

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

AZUL = colors.HexColor("#131E5C")
AZUL_CLARO = colors.HexColor("#EEF1FA")
BORDE = colors.HexColor("#C9D0DE")
GRIS = colors.HexColor("#64748B")
GRIS_CLARO = colors.HexColor("#F8FAFC")
TEXTO = colors.HexColor("#0F172A")
BLANCO = colors.white

# Útil a letter con margen de 0.6 cm por lado (expresado en cm).
ANCHO = (letter[0] - 1.2 * cm) / cm

ANCHO_NUM = 0.8
ANCHO_CHECK = 0.85
ANCHO_ITEM_CONTROL = ANCHO - ANCHO_NUM - 6 * ANCHO_CHECK

CAMPOS_VEHICULO = [
    ("numInterno", "Número interno del vehículo"),
    ("matricula", "Matrícula"),
    ("vinCampo", "Número de identificación del vehículo"),
    ("fecha", "Fecha"),
    ("modeloTipo", "Modelo / Tipo"),
    ("km", "KM"),
    ("fechaPrimera", "Fecha de primera matriculación"),
    ("ordenRep", "Orden de Reparación"),
]

NEUMATICOS = [
    ("di", "Delantera izquierda"),
    ("dd", "Delantera derecha"),
    ("ti", "Trasera izquierda"),
    ("td", "Trasera derecha"),
]

NOTA_NEUMATICOS = (
    "Los neumáticos deben corresponder al índice de velocidad, carga y "
    "especificaciones recomendadas. Antigüedad máxima: 6 años (verano) y "
    "4 años (invierno)."
)

PREGUNTA_DANOS = (
    "¿Hay daños reconocibles en el vehículo de daños anteriores?"
)

# ── Lista oficial VW CPO 114 puntos (secciones C–I) + documentación (B) ──
SECCIONES_CPO = [
    {
        "key": "B",
        "titulo": "Documentación",
        "tipo": "checklist",
        "puntos": [
            ("B1", "Documentos (Factura de Origen, Alta/Baja de placas, Tenencias)", {}),
            ("B2", "Consulta Reporte de Robo (PGJ/OCRA)", {}),
            ("B3", "Documentos de Matriculación", {}),
            ("B4", "Ninguna acción de servicio pendiente (campañas)", {}),
            ("B5", "Cuadernillo de garantía y mantenimiento", {}),
            ("B6", "Elaborar el protocolo de análisis del vehículo.", {}),
            ("B7", "Manual de instrucciones.", {}),
            ("B8", "Comprobar verosimilitud del cuentakilómetros.", {}),
            ("B9", "Manual de radio/sistema de navegación", {}),
            ("B10", "Sustitución de cuadro de instrumentos", {"fecha_km": True}),
            ("B11", "Código de radio", {"texto": True, "placeholder": "Código"}),
            ("B12", "Reparación por accidente", {"fecha_km": True}),
            ("B13", "Versión de navegación", {"texto": True, "placeholder": "Versión"}),
            ("B14", "Justificante de sustitución de motor", {"fecha_km": True}),
            ("B15", "Número de llaves", {"texto": True, "placeholder": "Ej. 2"}),
            ("B16", "Sustitución de caja de cambios", {"fecha_km": True}),
            ("B17", "Herramientas de abordo", {"sub_checks": [
                "gato", "botiquin", "compresor", "birlo",
                "llanta de refaccion", "Triangulo de emergencia",
                "herramienta", "juego de reparacion",
            ]}),
            ("B18", "Análisis general", {"fecha": True}),
            ("B19", "Análisis de gases de escape", {"fecha": True}),
            ("B20", "Todos los mantenimientos realizados en concesionario (marca correspondiente).", {}),
            ("B21", "Ausencia de piezas adosadas ajenas en el vehículo", {}),
        ],
    },
    {
        "key": "C",
        "titulo": "Exterior del vehículo (funcionamiento y estado)",
        "tipo": "control",
        "danos": True,
        "puntos": [
            (1, "Carrocería / Capota Cabrio", {}),
            (2, "Pintura", {}),
            (3, "Puertas / Capó", {}),
            (4, "Alumbrado exterior", {}),
            (5, "Regulador de altura de los faros", {}),
            (6, "Faros y bombilla", {}),
            (7, "Bajos", {}),
            (8, "Llantas", {}),
            (9, "Enganche de remolque", {}),
            (10, "Spoiler", {}),
            (11, "Tequipment / Exclusive", {}),
        ],
    },
    {
        "key": "D",
        "titulo": "Ruedas y neumáticos",
        "tipo": "control",
        "neumaticos": True,
        "nota": NOTA_NEUMATICOS,
        "puntos": [
            (12, "Profundidad de dibujo del neumático, mínimo 4 mm", {}),
            (13, "Homologación de neumáticos", {}),
            (14, "Dimensión de neumáticos", {}),
            (15, "Marca", {}),
            (16, "DOT", {}),
            (17, "Presión de neumáticos", {}),
            (18, "Sistema de control de presión de neumáticos", {}),
        ],
    },
    {
        "key": "E",
        "titulo": "Sistema de propulsión / bajos",
        "tipo": "control",
        "puntos": [
            (19, "Sistema de gases de escape", {"detalle": [
                "Tubo de escape sin fugas.",
                "Catalizador en buenas condiciones.",
                "Silenciador sin fugas.",
            ]}),
            (20, "Chasis / suspensión de ruedas —amortiguadores y muelles—", {}),
            (21, "Suspensión neumática", {"detalle": [
                "Bujes de orquilla.",
                "Brazos de suspensión.",
                "Amortiguadores.",
            ]}),
            (22, "Cojinetes de barra estabilizadora", {}),
            (23, "Articulación de eje", {}),
            (24, "Ejes motrices", {}),
            (25, "Caja de transferencia", {}),
            (26, "Caja de dirección", {}),
            (27, "Cojinete de rueda", {}),
            (28, "Tuberías / latiguillos de freno", {}),
            (29, "Pastillas de freno —máximo 50 % de desgaste y grosor mínimo de 4 mm—", {}),
            (30, "Discos de freno —menos de 1 mm de desgaste—", {}),
            (31, "Cilindro / mordaza de freno / conducciones de aire / chapas cobertoras", {}),
            (32, "Sistema de combustible", {}),
            (33, "Radiador / ventilador", {}),
            (34, "Tuberías de radiador —fugas—", {}),
        ],
    },
    {
        "key": "F",
        "titulo": "Compartimiento del motor",
        "tipo": "control",
        "puntos": [
            (35, "Sistema de encendido", {}),
            (36, "Alternador / tensión a bordo", {}),
            (37, "Compresor del sistema de aire acondicionado", {}),
            (38, "Correas / bandas", {"detalle": [
                "Banda de distribución.",
                "Banda de accesorios.",
            ]}),
            (39, "Motor —sin deficiencias visibles, pérdidas de líquido o inestanqueidades—", {"detalle": [
                "Presencia de fugas.",
                "Ruido anormal en frío / al arranque.",
                "Ruido anormal en caliente.",
            ]}),
            (40, "Conexiones y fusibles", {}),
            (41, "Batería", {"sub_campos": [
                ("carga", "Estado de carga/tensión"),
                ("potencia", "Funcionamiento/Potencia"),
            ]}),
            (42, "Batería adicional", {}),
        ],
    },
    {
        "key": "G",
        "titulo": "Líquidos",
        "tipo": "control",
        "puntos": [
            (43, "Batería", {}),
            (44, "Batería adicional", {}),
            (45, "Aceite de motor", {"detalle": [
                "Nivel de depósito de aceite.",
                "Prueba de degradación de aceite.",
                "Presencia de partículas metálicas.",
                "Contaminación del aceite.",
            ]}),
            (46, "Barra estabilizadora todo terreno", {}),
            (47, "Aceite del diferencial del eje delantero / trasero", {}),
            (48, "Aceite de la caja de cambio", {"detalle": [
                "Presencia de partículas metálicas.",
                "Contaminación del aceite.",
            ]}),
            (49, "Líquido de refrigeración / protección anticongelante", {}),
            (50, "Aceite hidráulico de la servodirección", {}),
            (51, "Líquido de frenos / líquido de embrague", {}),
            (52, "Líquido lavaparabrisas y lavafaros", {}),
        ],
    },
    {
        "key": "H",
        "titulo": "Habitáculo interior",
        "tipo": "control",
        "puntos": [
            (53, "Sistema de cierre de puertas —seguro infantil—", {}),
            (54, "Mando a distancia", {}),
            (55, "Sistema de alarma e inmovilizador", {}),
            (56, "Encendido / cerradura de encendido", {}),
            (57, "Bloqueo del volante", {}),
            (58, "Bocina", {}),
            (59, "Sistema de airbags —desactivación para asiento infantil—", {}),
            (60, "Limpiaparabrisas delantero / trasero", {}),
            (61, "Sistema limpia-lavafaros y limpiaparabrisas", {}),
            (62, "Ajuste de la columna de dirección", {"detalle": [
                "Presencia de ruido anormal.",
            ]}),
            (63, "Cinturones de seguridad y ajuste de altura de los cinturones", {}),
            (64, "Ajuste de asientos / memoria de posición / asientos calefactables", {"detalle": [
                "Ruido anormal en la estructura del asiento.",
                "Ruido anormal al mover el asiento.",
                "Condición de la tapicería.",
            ]}),
            (65, "Acolchado de asiento y reposacabezas", {}),
            (66, "Viseras parasol", {}),
            (67, "Galería de techo", {}),
            (68, "Alfombrillas y moqueta", {}),
            (69, "Revestimiento interior y espacio de equipajes", {}),
            (70, "Guantera", {}),
            (71, "Sujetavasos", {}),
            (72, "Cenicero", {}),
            (73, "Encendedor / tomas de corriente de 12 V", {}),
            (74, "Cuadro de instrumentos —inspección en parado—", {}),
            (75, "Testigos y señales de aviso", {}),
            (76, "Reloj de a bordo", {}),
            (77, "Ordenador de a bordo", {}),
            (78, "Sistema de alta fidelidad —altavoces—", {}),
            (79, "PCM —radio, teléfono, sistema de navegación—", {}),
            (80, "Entrada USB", {}),
            (81, "Iluminación interior", {}),
            (82, "Calefacción, ventilación, AC/AC", {}),
            (83, "Ajuste de retrovisores exteriores / interiores", {}),
            (84, "Elevalunas —función de retroceso—", {}),
            (85, "Desbloqueo de capós —delantero / trasero—", {}),
            (86, "Techo —Cabriolet / techo corredizo—", {}),
            (87, "Cabriolet: panel cortaviento", {}),
            (88, "Equipamiento Tequipment / Exclusive", {}),
        ],
    },
    {
        "key": "I",
        "titulo": "Recorrido de prueba",
        "tipo": "control",
        "puntos": [
            (89, "Comportamiento de arranque", {"detalle": [
                "Arranque en frío.",
                "Arranque en caliente.",
            ]}),
            (90, "Efecto de freno —freno de pie y freno de mano—", {}),
            (91, "ABS", {}),
            (92, "Sistema de suspensión", {"detalle": [
                "Ruido extraño al circular en terreno irregular.",
                "Ruido extraño al pasar baches y/o topes.",
            ]}),
            (93, "PASM / suspensión neumática", {}),
            (94, "Sistema electrónico de estabilidad —PSM, etc.—", {}),
            (95, "Servodirección / Servotronic", {}),
            (96, "Centraje del volante", {}),
            (97, "Circulación en línea recta", {}),
            (98, "Comportamiento / maniobrabilidad en circulación", {}),
            (99, "Prestaciones del vehículo", {}),
            (100, "Holgura del embrague", {}),
            (101, "Cambio de marcha", {}),
            (102, "Calefacción adicional", {}),
            (103, "Sistema de calefacción / ventilación / aire acondicionado", {}),
            (104, "Luneta y retrovisores calefactables", {}),
            (105, "Parkassistent / cámara de visión trasera", {}),
            (106, "PCM —radio, teléfono, CD, DVD, sistema de navegación—", {}),
            (107, "Control de velocidad —todas las funciones—", {}),
            (108, "Bloqueos del diferencial / tracción total", {}),
            (109, "Cuadro de instrumentos —en circulación—", {}),
            (110, "Ausencia de ruidos extraños / vibraciones", {}),
            (111, "Comportamiento de arranque en caliente / al ralentí", {}),
            (112, "Ruidos extraños al viraje brusco del volante", {}),
            (113, "Ruidos extraños al virar en “U”", {}),
            (114, "Prueba de crucero para detección de humos —blanco, azul o negro—", {}),
        ],
    },
]

TOTAL_PUNTOS = sum(
    len(sec["puntos"]) for sec in SECCIONES_CPO if sec["tipo"] == "control"
)


# ───────────────────────── utilidades ─────────────────────────

def _texto(valor, default="—"):
    valor = "" if valor is None else str(valor).strip()
    return valor or default


def _fecha_corta(valor):
    """'2024-05-01' → '01/05/2024'; datetime → fecha local."""
    if not valor:
        return ""

    try:
        if hasattr(valor, "strftime"):
            if timezone.is_aware(valor):
                valor = timezone.localtime(valor)
            return valor.strftime("%d/%m/%Y")
        texto = str(valor).strip()
        if len(texto) >= 10 and texto[4] == "-" and texto[7] == "-":
            return f"{texto[8:10]}/{texto[5:7]}/{texto[0:4]}"
        return texto[:10]
    except Exception:
        return str(valor)


def _fecha_hora(valor):
    if not valor:
        return "—"

    try:
        if timezone.is_aware(valor):
            valor = timezone.localtime(valor)
        return valor.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(valor)


def _obtener_datos(avaluo):
    datos = getattr(avaluo, "checklist_cpo", None) or {}

    if not isinstance(datos, dict):
        datos = {}

    estados = datos.get("estados")
    if not isinstance(estados, dict):
        estados = {}

    comentarios = datos.get("comentarios")
    if not isinstance(comentarios, dict):
        comentarios = {}

    datos_vehiculo = datos.get("datosVehiculo")
    if not isinstance(datos_vehiculo, dict):
        datos_vehiculo = {}

    mediciones = datos.get("mediciones")
    if not isinstance(mediciones, dict):
        mediciones = {}

    return {
        "estados": estados,
        "comentarios": comentarios,
        "datosVehiculo": datos_vehiculo,
        "mediciones": mediciones,
        "danosAnteriores": str(datos.get("danosAnteriores") or ""),
        "folio": str(datos.get("folio") or ""),
        "vin": str(datos.get("vin") or ""),
    }


def _estado_de(estados, clave_id):
    valor = estados.get(clave_id, {})
    return valor if isinstance(valor, dict) else {}


def _ruta_logo_vw():
    rutas_base = []

    media_root = getattr(settings, "MEDIA_ROOT", "")
    base_dir = getattr(settings, "BASE_DIR", "")

    if media_root:
        rutas_base.append(str(media_root))

    if base_dir:
        rutas_base.append(os.path.join(str(base_dir), "media"))

    nombres = ["volkswagen.png", "vw.png", "volkswagen_logo.png", "vw_logo.png"]

    for ruta_base in rutas_base:
        for nombre in nombres:
            for ruta in (
                os.path.join(ruta_base, nombre),
                os.path.join(ruta_base, "logos", nombre),
            ):
                if os.path.exists(ruta):
                    return ruta

    return None


def _pdf_response(story, filename, on_page):
    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.6 * cm,
        leftMargin=0.6 * cm,
        topMargin=0.6 * cm,
        bottomMargin=0.95 * cm,
    )
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)

    buffer.seek(0)

    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


# ───────────────────────── estilos ─────────────────────────

def _estilos():
    return {
        "titulo": ParagraphStyle(
            name="CpoTitulo",
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=17,
            textColor=AZUL,
            alignment=TA_RIGHT,
        ),
        "subtitulo": ParagraphStyle(
            name="CpoSubtitulo",
            fontName="Helvetica",
            fontSize=8.5,
            leading=10,
            textColor=GRIS,
            alignment=TA_RIGHT,
        ),
        "logo_texto": ParagraphStyle(
            name="CpoLogoTexto",
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=12,
            textColor=AZUL,
        ),
        "label": ParagraphStyle(
            name="CpoLabel",
            fontName="Helvetica",
            fontSize=6.3,
            leading=7.3,
            textColor=GRIS,
            alignment=TA_CENTER,
        ),
        "valor": ParagraphStyle(
            name="CpoValor",
            fontName="Helvetica-Bold",
            fontSize=7.6,
            leading=9,
            textColor=TEXTO,
            alignment=TA_CENTER,
        ),
        "seccion": ParagraphStyle(
            name="CpoSeccion",
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=10,
            textColor=BLANCO,
        ),
        "col_header": ParagraphStyle(
            name="CpoColHeader",
            fontName="Helvetica-Bold",
            fontSize=6.4,
            leading=7.2,
            alignment=TA_CENTER,
            textColor=BLANCO,
        ),
        "item": ParagraphStyle(
            name="CpoItem",
            fontName="Helvetica",
            fontSize=7.2,
            leading=8.6,
            textColor=TEXTO,
        ),
        "detalle": ParagraphStyle(
            name="CpoDetalle",
            fontName="Helvetica-Oblique",
            fontSize=6.5,
            leading=7.6,
            textColor=GRIS,
        ),
        "extra": ParagraphStyle(
            name="CpoExtra",
            fontName="Helvetica",
            fontSize=6.5,
            leading=7.6,
            textColor=AZUL,
        ),
        "check": ParagraphStyle(
            name="CpoCheck",
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=9,
            alignment=TA_CENTER,
            textColor=AZUL,
        ),
        "nota": ParagraphStyle(
            name="CpoNota",
            fontName="Helvetica-Oblique",
            fontSize=6.8,
            leading=8,
            textColor=GRIS,
        ),
        "comentario": ParagraphStyle(
            name="CpoComentario",
            fontName="Helvetica",
            fontSize=7.5,
            leading=9,
            textColor=TEXTO,
        ),
        "comentario_titulo": ParagraphStyle(
            name="CpoComentarioTitulo",
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=9,
            textColor=AZUL,
        ),
        "firma": ParagraphStyle(
            name="CpoFirma",
            fontName="Helvetica-Bold",
            fontSize=7.2,
            leading=9,
            textColor=TEXTO,
            alignment=TA_CENTER,
        ),
    }


def _barra(titulo, estilos, ancho=None):
    t = Table(
        [[Paragraph(escape(titulo), estilos["seccion"])]],
        colWidths=[(ancho or ANCHO) * cm],
    )
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), AZUL),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]))
    return t


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 6.5)
    canvas.setFillColor(GRIS)
    canvas.drawString(
        0.6 * cm,
        0.45 * cm,
        f"VW CPO · Lista de verificación de {TOTAL_PUNTOS} puntos",
    )
    canvas.drawRightString(
        letter[0] - 0.6 * cm,
        0.45 * cm,
        f"Página {doc.page}",
    )
    canvas.restoreState()


# ───────────────────────── encabezado y datos ─────────────────────────

def _header(estilos):
    logo_path = _ruta_logo_vw()

    if logo_path:
        try:
            img = Image(logo_path)
            alto = 0.7 * cm
            if img.imageWidth and img.imageHeight:
                img.drawHeight = alto
                img.drawWidth = alto * (img.imageWidth / img.imageHeight)
                img.hAlign = "LEFT"
                bloque_izq = [img, Spacer(1, 2)]
            else:
                bloque_izq = []
        except Exception:
            bloque_izq = []
    else:
        bloque_izq = []

    if not bloque_izq:
        bloque_izq = [
            Paragraph("VOLKSWAGEN", estilos["logo_texto"]),
            Spacer(1, 2),
        ]

    bloque_izq.append(Paragraph("SEMINUEVOS CPO", estilos["logo_texto"]))

    bloque_der = [
        Paragraph(
            f"Lista de verificación de {TOTAL_PUNTOS} puntos",
            estilos["titulo"],
        ),
        Paragraph(
            "Certificación CPO · Revisión y estado del vehículo",
            estilos["subtitulo"],
        ),
    ]

    header = Table(
        [[bloque_izq, bloque_der]],
        colWidths=[8.5 * cm, (ANCHO - 8.5) * cm],
    )
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -1), 1.1, AZUL),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return header


def _celda_dato(etiqueta, valor, ancho_cm, estilos):
    etiqueta_tbl = Table(
        [[Paragraph(escape(etiqueta), estilos["label"])]],
        colWidths=[ancho_cm * cm],
    )
    etiqueta_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), AZUL_CLARO),
        ("BOX", (0, 0), (-1, -1), 0.4, BORDE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]))

    valor_tbl = Table(
        [[Paragraph(escape(valor), estilos["valor"])]],
        colWidths=[ancho_cm * cm],
    )
    valor_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BLANCO),
        ("BOX", (0, 0), (-1, -1), 0.4, BORDE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]))

    contenedor = Table([[etiqueta_tbl], [valor_tbl]], colWidths=[ancho_cm * cm])
    contenedor.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    return contenedor


def _fila_datos(campos, estilos):
    """campos: lista de (etiqueta, valor, ancho_cm)."""
    celdas = [_celda_dato(etq, val, ancho, estilos) for etq, val, ancho in campos]
    t = Table([celdas], colWidths=[ancho * cm for _, _, ancho in campos])
    t.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def _datos_generales(avaluo, datos, estilos):
    cliente = getattr(avaluo, "cliente", None)

    folio = datos["folio"]
    if not folio and getattr(avaluo, "id", None):
        folio = f"UC-{avaluo.id:05d}"

    vin = datos["vin"] or _texto(getattr(avaluo, "serie", ""))

    fila1 = _fila_datos([
        ("Folio", _texto(folio), 3.0),
        ("VIN", _texto(vin), 6.0),
        ("Cliente", _texto(getattr(cliente, "nombre", "")), 6.5),
        ("Teléfono", _texto(getattr(cliente, "telefono", "")), 4.89),
    ], estilos)

    fila2 = _fila_datos([
        ("Fecha de valuación", _fecha_hora(getattr(avaluo, "fecha_avaluo", None)), 4.0),
        ("Distribuidor", _texto(getattr(avaluo, "agencia", "")), 5.5),
        ("Marca", _texto(getattr(avaluo, "marca_auto", "")), 2.6),
        ("Año", _texto(getattr(avaluo, "anio_modelo", "")), 2.0),
        ("KM", _texto(getattr(avaluo, "kilometraje", "")), 2.6),
        ("Color", _texto(getattr(avaluo, "color", "")), 2.6),
        ("Vendedor", _texto(
            getattr(avaluo, "vendedor", "") or getattr(avaluo, "asesor_ventas", "")
        ), 3.09),
    ], estilos)

    return [fila1, Spacer(1, 2), fila2]


# ───────────────────────── sección A ─────────────────────────

def _seccion_datos_vehiculo(avaluo, datos, estilos):
    captura = datos["datosVehiculo"]

    modelo = " ".join(filter(None, [
        _texto(getattr(avaluo, "marca_auto", ""), ""),
        _texto(getattr(avaluo, "modelo", ""), ""),
        _texto(getattr(avaluo, "anio_modelo", ""), ""),
    ]))

    fallbacks = {
        "vinCampo": _texto(getattr(avaluo, "serie", ""), ""),
        "modeloTipo": modelo,
        "km": _texto(getattr(avaluo, "kilometraje", ""), ""),
        "fecha": _fecha_corta(getattr(avaluo, "fecha_avaluo", None)),
    }

    valores = []
    for key, label in CAMPOS_VEHICULO:
        valor = str(captura.get(key) or "").strip()
        if not valor:
            valor = fallbacks.get(key, "")
        if key in ("fecha", "fechaPrimera") and valor:
            valor = _fecha_corta(valor)
        valores.append((label, valor or "—"))

    ancho_etiqueta = 4.1
    ancho_valor = (ANCHO - 2 * ancho_etiqueta) / 2

    filas = []
    for i in range(0, len(valores), 2):
        par = valores[i:i + 2]
        celdas = []
        anchos = []
        for label, valor in par:
            celdas.append(Paragraph(escape(label), estilos["label"]))
            celdas.append(Paragraph(escape(valor), estilos["valor"]))
            anchos.extend([ancho_etiqueta * cm, ancho_valor * cm])
        if len(par) == 1:
            celdas.append("")
            anchos.extend([ancho_etiqueta * cm, ancho_valor * cm])
        filas.append(celdas)

    t = Table(filas, colWidths=anchos)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, BORDE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (0, -1), AZUL_CLARO),
        ("BACKGROUND", (2, 0), (2, -1), AZUL_CLARO),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))

    return [
        _barra("A. DATOS DEL VEHÍCULO", estilos),
        Spacer(1, 2),
        t,
    ]


# ───────────────────────── celdas de marca ─────────────────────────

def _caja_marca(marcada, estilos):
    caja = Table(
        [[Paragraph("X" if marcada else "", estilos["check"])]],
        colWidths=[0.36 * cm],
        rowHeights=[0.34 * cm],
    )
    caja.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.4, BORDE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return caja


def _marca(valor, esperado, estilos):
    return _caja_marca(str(valor or "").strip().lower() == esperado, estilos)


# ───────────────────────── sección B (documentación) ─────────────────────────

def _lineas_extra_checklist(punto, estado, estilos):
    lineas = []

    if punto.get("fecha_km"):
        fecha = _fecha_corta(estado.get("fecha")) or "__________"
        km = str(estado.get("km") or "").strip() or "________"
        lineas.append(f"Fecha: {fecha}   ·   KM: {km}")

    if punto.get("fecha"):
        fecha = _fecha_corta(estado.get("fecha")) or "__________"
        lineas.append(f"Fecha: {fecha}")

    if punto.get("texto"):
        placeholder = punto.get("placeholder") or "Valor"
        valor = str(estado.get("texto") or "").strip() or "________"
        lineas.append(f"{placeholder}: {valor}")

    if punto.get("sub_checks"):
        subs = estado.get("subs") or {}
        partes = [
            f"{nombre} [{'X' if subs.get(nombre) else ' '}]"
            for nombre in punto["sub_checks"]
        ]
        lineas.append("Elementos: " + ", ".join(partes))

    if not lineas:
        return []

    return [Paragraph(escape(linea), estilos["extra"]) for linea in lineas]


def _tabla_documentacion(seccion, estados, estilos):
    ancho_item = ANCHO - ANCHO_NUM - 3.1 - 3.1

    encabezado = [
        Paragraph("#", estilos["col_header"]),
        Paragraph("Elemento", estilos["col_header"]),
        Paragraph("Verificado", estilos["col_header"]),
        Paragraph("N/A", estilos["col_header"]),
    ]

    filas = [encabezado]

    for num, texto, flags in seccion["puntos"]:
        estado = _estado_de(estados, f"{seccion['key']}{num}")

        contenido = [Paragraph(
            f"<b>{escape(str(num))}.-</b> {escape(texto)}",
            estilos["item"],
        )]
        contenido += _lineas_extra_checklist(flags, estado, estilos)

        filas.append([
            Paragraph(f"<b>{escape(str(num))}</b>", estilos["item"]),
            contenido,
            _caja_marca(bool(estado.get("check")) and not estado.get("na"), estilos),
            _caja_marca(bool(estado.get("na")), estilos),
        ])

    t = Table(
        filas,
        colWidths=[ANCHO_NUM * cm, ancho_item * cm, 3.1 * cm, 3.1 * cm],
        repeatRows=1,
    )
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("GRID", (0, 0), (-1, -1), 0.35, BORDE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BLANCO, GRIS_CLARO]),
        ("ALIGN", (2, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    return t


# ───────────────────────── secciones C–I (control P / O / NA) ─────────────────────────

def _celda_item_control(num, texto, flags, estado, estilos):
    contenido = [Paragraph(
        f"<b>{escape(str(num))}.-</b> {escape(texto)}",
        estilos["item"],
    )]

    for linea in flags.get("detalle") or []:
        contenido.append(Paragraph(f"— {escape(linea)}", estilos["detalle"]))

    sub_campos = flags.get("sub_campos")
    if sub_campos:
        partes = []
        for key, label in sub_campos:
            valor = str(estado.get(key) or "").strip() or "______"
            partes.append(f"{label}: {valor}")
        contenido.append(Paragraph(escape("   ·   ".join(partes)), estilos["extra"]))

    return contenido


def _tabla_control(seccion, estados, estilos):
    encabezado_1 = [
        Paragraph("#", estilos["col_header"]),
        Paragraph("Elemento", estilos["col_header"]),
        Paragraph("Primer control", estilos["col_header"]),
        "",
        "",
        Paragraph("Estado definitivo", estilos["col_header"]),
        "",
        "",
    ]

    encabezado_2 = [
        "", "",
        Paragraph("P", estilos["col_header"]),
        Paragraph("O", estilos["col_header"]),
        Paragraph("NA", estilos["col_header"]),
        Paragraph("P", estilos["col_header"]),
        Paragraph("O", estilos["col_header"]),
        Paragraph("NA", estilos["col_header"]),
    ]

    filas = [encabezado_1, encabezado_2]

    for num, texto, flags in seccion["puntos"]:
        estado = _estado_de(estados, f"{seccion['key']}{num}")
        primer = str(estado.get("primer") or "").strip().lower()
        final = str(estado.get("final") or "").strip().lower()

        filas.append([
            Paragraph(f"<b>{escape(str(num))}</b>", estilos["item"]),
            _celda_item_control(num, texto, flags, estado, estilos),
            _marca(primer, "p", estilos),
            _marca(primer, "o", estilos),
            _marca(primer, "na", estilos),
            _marca(final, "p", estilos),
            _marca(final, "o", estilos),
            _marca(final, "na", estilos),
        ])

    col_widths = [
        ANCHO_NUM * cm,
        ANCHO_ITEM_CONTROL * cm,
    ] + [ANCHO_CHECK * cm] * 6

    t = Table(filas, colWidths=col_widths, repeatRows=2)
    t.setStyle(TableStyle([
        ("SPAN", (2, 0), (4, 0)),
        ("SPAN", (5, 0), (7, 0)),
        ("BACKGROUND", (0, 0), (-1, 1), AZUL),
        ("GRID", (0, 0), (-1, -1), 0.35, BORDE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 2), (-1, -1), [BLANCO, GRIS_CLARO]),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("TOPPADDING", (0, 0), (-1, 1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, 1), 3),
    ]))
    return t


def _tabla_neumaticos(datos, estilos):
    mediciones = datos["mediciones"]

    encabezado = [
        Paragraph("Rueda", estilos["col_header"]),
        Paragraph("Lateral exterior (mm)", estilos["col_header"]),
        Paragraph("Centro (mm)", estilos["col_header"]),
        Paragraph("Lateral interior (mm)", estilos["col_header"]),
        Paragraph("Presión (bar)", estilos["col_header"]),
    ]

    filas = [encabezado]

    for key, label in NEUMATICOS:
        filas.append([
            Paragraph(escape(label), estilos["item"]),
            Paragraph(escape(str(mediciones.get(f"{key}-ext") or "—")), estilos["valor"]),
            Paragraph(escape(str(mediciones.get(f"{key}-cen") or "—")), estilos["valor"]),
            Paragraph(escape(str(mediciones.get(f"{key}-int") or "—")), estilos["valor"]),
            Paragraph(escape(str(mediciones.get(f"{key}-bar") or "—")), estilos["valor"]),
        ])

    ancho_rueda = 5.0
    ancho_col = (ANCHO - ancho_rueda) / 4

    t = Table(
        filas,
        colWidths=[ancho_rueda * cm] + [ancho_col * cm] * 4,
        repeatRows=1,
    )
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("GRID", (0, 0), (-1, -1), 0.35, BORDE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [BLANCO, GRIS_CLARO]),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    return t


def _renglon_pregunta_danos(datos, estilos):
    respuesta = datos["danosAnteriores"].strip().lower()

    tabla = Table([[
        Paragraph(escape(PREGUNTA_DANOS), estilos["item"]),
        Paragraph(
            f"Sí [{'X' if respuesta == 'si' else ' '}]",
            estilos["item"],
        ),
        Paragraph(
            f"No [{'X' if respuesta == 'no' else ' '}]",
            estilos["item"],
        ),
    ]], colWidths=[ANCHO * cm - 3.4 * cm, 1.7 * cm, 1.7 * cm])

    tabla.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.4, BORDE),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, BORDE),
        ("BACKGROUND", (0, 0), (0, 0), AZUL_CLARO),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return tabla


# ───────────────────────── comentarios y firmas ─────────────────────────

def _bloque_comentarios(datos, estilos):
    comentarios = datos["comentarios"]

    filas = []
    for sec in SECCIONES_CPO:
        texto = str(comentarios.get(sec["key"]) or "").strip()
        if texto:
            filas.append([
                Paragraph(
                    f"{sec['key']}. {escape(sec['titulo'])}",
                    estilos["comentario_titulo"],
                ),
                Paragraph(escape(texto), estilos["comentario"]),
            ])

    if not filas:
        filas.append([
            Paragraph("Secciones", estilos["comentario_titulo"]),
            Paragraph("Sin comentarios registrados.", estilos["comentario"]),
        ])

    t = Table(filas, colWidths=[5.4 * cm, (ANCHO - 5.4) * cm])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.4, BORDE),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, BORDE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _firmas(estilos):
    etiquetas = [
        "TÉCNICO CERTIFICADO VW<br/><font size='6'>Nombre y firma</font>",
        "GERENTE DE SEMINUEVOS<br/><font size='6'>Nombre y firma</font>",
        "VALUADOR - COMPRADOR<br/><font size='6'>Nombre y firma</font>",
    ]

    ancho = ANCHO / 3

    filas = [
        ["", "", ""],
        [Paragraph(etiqueta, estilos["firma"]) for etiqueta in etiquetas],
    ]

    t = Table(filas, colWidths=[ancho * cm] * 3, rowHeights=[0.85 * cm, 0.7 * cm])
    t.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEABOVE", (0, 1), (0, 1), 0.8, TEXTO),
        ("LINEABOVE", (1, 1), (1, 1), 0.8, TEXTO),
        ("LINEABOVE", (2, 1), (2, 1), 0.8, TEXTO),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 1), (-1, 1), 4),
    ]))
    return t


# ───────────────────────── generador principal ─────────────────────────

def generar_checklist_cpo_pdf(avaluo):
    estilos = _estilos()
    datos = _obtener_datos(avaluo)
    estados = datos["estados"]

    story = [_header(estilos), Spacer(1, 5)]
    story += _datos_generales(avaluo, datos, estilos)
    story.append(Spacer(1, 7))
    story += _seccion_datos_vehiculo(avaluo, datos, estilos)
    story.append(Spacer(1, 7))

    for seccion in SECCIONES_CPO:
        story.append(_barra(f"{seccion['key']}. {seccion['titulo'].upper()}", estilos))

        if seccion.get("nota"):
            story.append(Spacer(1, 1.5))
            story.append(Paragraph(escape(seccion["nota"]), estilos["nota"]))

        if seccion.get("danos"):
            story.append(Spacer(1, 3))
            story.append(_renglon_pregunta_danos(datos, estilos))

        story.append(Spacer(1, 3))

        if seccion["tipo"] == "checklist":
            story.append(_tabla_documentacion(seccion, estados, estilos))
        else:
            story.append(_tabla_control(seccion, estados, estilos))

        if seccion.get("neumaticos"):
            story.append(Spacer(1, 4))
            story.append(_tabla_neumaticos(datos, estilos))

        story.append(Spacer(1, 8))

    story.append(_barra("COMENTARIOS POR SECCIÓN", estilos))
    story.append(Spacer(1, 2))
    story.append(_bloque_comentarios(datos, estilos))
    story.append(Spacer(1, 10))
    story.append(_firmas(estilos))

    folio = datos["folio"] or (
        f"{avaluo.id}" if getattr(avaluo, "id", None) else "nuevo"
    )

    return _pdf_response(
        story,
        f"checklist_cpo_avaluo_{folio}.pdf",
        _footer,
    )
