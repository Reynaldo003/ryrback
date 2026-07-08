# citas/views.py
from io import BytesIO
from pathlib import Path
from html import escape

from django.conf import settings
from django.http import FileResponse
from django.utils import timezone
from django.utils.text import slugify

from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny, IsAuthenticated

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
)

from CrmConformidad.jwt_authentication import CRMJWTAuthentication

from .models import (
    ClienteComercial,
    Cita,
    RegistroPiso,
    PruebaManejo,
    EvidenciaPruebaManejo,
    Entregas,
)
from .serializers import (
    ClienteComercialSerializer,
    CitaSerializer,
    RegistroPisoSerializer,
    PruebaManejoSerializer,
    EvidenciaPruebaManejoSerializer,
    EntregasSerializer,
)

NEGRO = colors.black
BLANCO = colors.white
GRIS_BORDE = HexColor("#BDBDBD")
GRIS_CLARO = HexColor("#F0F0F0")


def texto(valor, default="No capturado"):
    if valor is None:
        return default

    valor = str(valor).strip()
    return valor if valor else default


def parrafo(valor, estilo):
    valor = texto(valor)
    valor = escape(valor).replace("\n", "<br/>")
    return Paragraph(valor, estilo)


def fecha_legible(valor):
    if not valor:
        return "No capturada"

    try:
        if timezone.is_aware(valor):
            valor = timezone.localtime(valor)
    except Exception:
        pass

    return valor.strftime("%d/%m/%Y %H:%M")


def buscar_logo(nombre_archivo):
    media_root = Path(getattr(settings, "MEDIA_ROOT", ""))

    candidatos = [
        media_root / "logos" / nombre_archivo,
    ]

    for ruta in candidatos:
        if ruta.exists() and ruta.is_file():
            return ruta

    return None


def convertir_imagen_a_grises(ruta):
    try:
        from PIL import Image as PILImage
        from PIL import ImageOps

        imagen = PILImage.open(str(ruta)).convert("RGBA")

        canal_alpha = imagen.getchannel("A")
        imagen_rgb = imagen.convert("RGB")
        imagen_gris = ImageOps.grayscale(imagen_rgb)

        imagen_final = PILImage.merge("LA", (imagen_gris, canal_alpha))

        buffer = BytesIO()
        imagen_final.save(buffer, format="PNG")
        buffer.seek(0)

        return buffer
    except Exception:
        return str(ruta)


def imagen_proporcional(ruta, ancho_maximo, alto_maximo):
    lector = ImageReader(str(ruta))
    ancho_original, alto_original = lector.getSize()

    escala = min(
        ancho_maximo / float(ancho_original),
        alto_maximo / float(alto_original),
    )

    ancho = ancho_original * escala
    alto = alto_original * escala

    fuente_imagen = convertir_imagen_a_grises(ruta)

    logo = Image(fuente_imagen, width=ancho, height=alto)
    logo._fuente_imagen = fuente_imagen

    return logo


def crear_estilos_pdf():
    estilos = getSampleStyleSheet()

    estilos.add(ParagraphStyle(
        name="TituloBlanco",
        parent=estilos["Normal"],
        textColor=NEGRO,
        fontName="Helvetica-Bold",
        fontSize=17,
        leading=21,
        alignment=1,
    ))

    estilos.add(ParagraphStyle(
        name="SubtituloBlanco",
        parent=estilos["Normal"],
        textColor=NEGRO,
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        alignment=1,
    ))

    estilos.add(ParagraphStyle(
        name="TituloSeccion",
        parent=estilos["Normal"],
        textColor=NEGRO,
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
    ))

    estilos.add(ParagraphStyle(
        name="Etiqueta",
        parent=estilos["Normal"],
        textColor=NEGRO,
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=11,
    ))

    estilos.add(ParagraphStyle(
        name="Valor",
        parent=estilos["Normal"],
        textColor=NEGRO,
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        wordWrap="CJK",
    ))

    estilos.add(ParagraphStyle(
        name="ValorGrande",
        parent=estilos["Normal"],
        textColor=NEGRO,
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        wordWrap="CJK",
    ))

    estilos.add(ParagraphStyle(
        name="LogoTexto",
        parent=estilos["Normal"],
        textColor=NEGRO,
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=12,
        alignment=1,
    ))

    return estilos


def celda_logo(
    nombre_archivo,
    texto_respaldo,
    ancho_maximo,
    alto_maximo,
    estilos,
    alineacion="CENTER",
):
    ruta = buscar_logo(nombre_archivo)

    if ruta:
        try:
            logo = imagen_proporcional(ruta, ancho_maximo, alto_maximo)

            tabla_logo = Table(
                [[logo]],
                colWidths=[ancho_maximo],
                rowHeights=[alto_maximo],
            )

            tabla_logo.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), alineacion),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]))

            return tabla_logo
        except Exception:
            pass

    return Paragraph(escape(texto_respaldo), estilos["LogoTexto"])


def tabla_encabezado(entrega, ancho_doc, estilos):
    logo_vw = celda_logo(
        "vw_dark.png",
        "VOLKSWAGEN",
        ancho_doc * 0.20,
        0.55 * inch,
        estilos,
        alineacion="LEFT",
    )

    logo_ryr = celda_logo(
        "ryr_blue.png",
        "R&R",
        ancho_doc * 0.20,
        0.55 * inch,
        estilos,
        alineacion="RIGHT",
    )

    titulo = Paragraph(
        "Programacion de Entregas<br/>Volkswagen",
        estilos["TituloBlanco"],
    )

    subtitulo = Paragraph(
        f"Folio interno: #{entrega.id} &nbsp;&nbsp;|&nbsp;&nbsp; Generado por Grupo Automotriz R&R",
        estilos["SubtituloBlanco"],
    )

    centro = Table(
        [
            [titulo],
            [subtitulo],
        ],
        colWidths=[ancho_doc * 0.56],
    )

    centro.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))

    tabla = Table(
        [[logo_vw, centro, logo_ryr]],
        colWidths=[
            ancho_doc * 0.22,
            ancho_doc * 0.56,
            ancho_doc * 0.22,
        ],
        rowHeights=[0.95 * inch],
    )

    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BLANCO),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, 0), "LEFT"),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ("ALIGN", (2, 0), (2, 0), "RIGHT"),
        ("LEFTPADDING", (0, 0), (0, 0), 16),
        ("RIGHTPADDING", (0, 0), (0, 0), 4),
        ("LEFTPADDING", (1, 0), (1, 0), 4),
        ("RIGHTPADDING", (1, 0), (1, 0), 4),
        ("LEFTPADDING", (2, 0), (2, 0), 4),
        ("RIGHTPADDING", (2, 0), (2, 0), 16),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))

    return tabla


def titulo_seccion(titulo, ancho_doc, estilos):
    tabla = Table(
        [[parrafo(titulo.upper(), estilos["TituloSeccion"])]],
        colWidths=[ancho_doc],
    )

    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BLANCO),
        ("BOX", (0, 0), (-1, -1), 0.7, BLANCO),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    return tabla


def tabla_datos(filas, ancho_doc, estilos):
    data = []

    for etiqueta, valor in filas:
        data.append([
            parrafo(etiqueta, estilos["Etiqueta"]),
            parrafo(valor, estilos["Valor"]),
        ])

    tabla = Table(
        data,
        colWidths=[ancho_doc * 0.30, ancho_doc * 0.70],
    )

    tabla.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, GRIS_BORDE),
        ("BACKGROUND", (0, 0), (0, -1), GRIS_CLARO),
        ("BACKGROUND", (1, 0), (1, -1), BLANCO),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))

    return tabla


def tabla_comentarios(comentarios, ancho_doc, estilos):
    tabla = Table(
        [[parrafo(comentarios or "Sin comentarios.", estilos["ValorGrande"])]],
        colWidths=[ancho_doc],
    )

    tabla.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, GRIS_BORDE),
        ("BACKGROUND", (0, 0), (-1, -1), BLANCO),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))

    return tabla


def pie_pagina(canvas, doc):
    canvas.saveState()

    ancho, _alto = letter

    canvas.setFillColor(BLANCO)
    canvas.rect(0, 0, ancho, 0.38 * inch, fill=True, stroke=False)

    canvas.setFillColor(NEGRO)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(
        doc.leftMargin,
        0.15 * inch,
        "Documento generado por CRM Grupo Automotriz R&R",
    )
    canvas.drawRightString(
        ancho - doc.rightMargin,
        0.15 * inch,
        f"Pagina {doc.page}",
    )

    canvas.restoreState()


def generar_pdf_entrega(entrega):
    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.45 * inch,
        leftMargin=0.45 * inch,
        topMargin=0.45 * inch,
        bottomMargin=0.65 * inch,
        title=f"Programacion de Entrega #{entrega.id}",
        author="Grupo Automotriz R&R",
    )

    estilos = crear_estilos_pdf()
    story = []

    cliente = entrega.cliente

    story.append(tabla_encabezado(entrega, doc.width, estilos))
    story.append(Spacer(1, 14))

    story.append(titulo_seccion("Datos del cliente", doc.width, estilos))
    story.append(tabla_datos([
        ("Nombre del cliente", texto(cliente.nombre)),
        ("Telefono", texto(cliente.telefono)),
        ("Correo", texto(cliente.correo)),
    ], doc.width, estilos))
    story.append(Spacer(1, 12))

    story.append(titulo_seccion("Datos de la entrega", doc.width, estilos))
    story.append(tabla_datos([
        ("Dealer", texto(entrega.agencia)),
        ("Tipo de venta", texto(entrega.tipo_venta)),
        ("Modelo", texto(entrega.modelo_version)),
        ("Version", texto(entrega.version)),
        ("Color", texto(entrega.color)),
        ("Kilometraje", f"{entrega.kilometraje or 0} km"),
        ("VIN / Chasis", texto(entrega.vin)),
        ("Fecha y hora de entrega", fecha_legible(entrega.fecha_hora_entrega)),
        ("Asesor de ventas", texto(entrega.asesor_ventas)),
        ("Fecha de captura", fecha_legible(entrega.creado_en)),
    ], doc.width, estilos))
    story.append(Spacer(1, 12))

    story.append(titulo_seccion("Comentarios", doc.width, estilos))
    story.append(tabla_comentarios(entrega.comentarios, doc.width, estilos))

    story.append(Spacer(1, 16))

    doc.build(
        story,
        onFirstPage=pie_pagina,
        onLaterPages=pie_pagina,
    )

    buffer.seek(0)
    return buffer


class ClienteComercialViewSet(ModelViewSet):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    queryset = ClienteComercial.objects.all().order_by("-id_cliente")
    serializer_class = ClienteComercialSerializer

    @action(detail=True, methods=["get"])
    def agenda(self, request, pk=None):
        cliente = self.get_object()

        citas = Cita.objects.filter(cliente=cliente).order_by("fecha_hora_cita", "id")
        piso = RegistroPiso.objects.filter(cliente=cliente).order_by("fecha_hora_cita", "id")
        pruebas = PruebaManejo.objects.filter(cliente=cliente).order_by("fecha_hora_cita", "id")
        entregas = Entregas.objects.filter(cliente=cliente).order_by("fecha_hora_entrega", "id")

        data = []

        for x in citas:
            data.append({
                "tipo": "CITA",
                "id": x.id,
                "fecha_hora": x.fecha_hora_cita,
                "agencia": x.agencia,
                "auto_interes": x.auto_interes,
                "asistencia": x.asistencia,
                "detalle": CitaSerializer(x, context={"request": request}).data,
            })

        for x in piso:
            data.append({
                "tipo": "REGISTRO_PISO",
                "id": x.id,
                "fecha_hora": x.fecha_hora_cita,
                "agencia": x.agencia,
                "auto_interes": x.auto_interes,
                "asistencia": x.asistencia,
                "detalle": RegistroPisoSerializer(x, context={"request": request}).data,
            })

        for x in pruebas:
            data.append({
                "tipo": "PRUEBA_MANEJO",
                "id": x.id,
                "fecha_hora": x.fecha_hora_cita,
                "agencia": x.agencia,
                "auto_interes": x.auto_interes,
                "asistencia": x.asistencia,
                "detalle": PruebaManejoSerializer(x, context={"request": request}).data,
            })

        for x in entregas:
            data.append({
                "tipo": "ENTREGA",
                "id": x.id,
                "fecha_hora": x.fecha_hora_entrega,
                "agencia": x.agencia,
                "modelo_version": x.modelo_version,
                "entrega_reportada": x.entrega_reportada,
                "detalle": EntregasSerializer(x, context={"request": request}).data,
            })

        data.sort(key=lambda r: (r["fecha_hora"] is None, r["fecha_hora"], r["id"]))
        return Response(data)


class CitasViewSet(ModelViewSet):
    authentication_classes = [CRMJWTAuthentication]

    queryset = Cita.objects.select_related("cliente").all().order_by("-id")
    serializer_class = CitaSerializer

    acciones_publicas = {
        "create",
    }

    def get_authenticators(self):
        if getattr(self, "action", None) in self.acciones_publicas:
            return []

        return [CRMJWTAuthentication()]

    def get_permissions(self):
        if getattr(self, "action", None) in self.acciones_publicas:
            return [AllowAny()]

        return [IsAuthenticated()]

class RegistroPisoViewSet(ModelViewSet):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    queryset = RegistroPiso.objects.select_related("cliente").all().order_by("-id")
    serializer_class = RegistroPisoSerializer


class PruebasManejoViewSet(ModelViewSet):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    queryset = (
        PruebaManejo.objects.select_related("cliente")
        .prefetch_related("evidencias")
        .all()
        .order_by("-id")
    )
    serializer_class = PruebaManejoSerializer


class EvidenciasPruebaManejoViewSet(ModelViewSet):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    queryset = (
        EvidenciaPruebaManejo.objects.select_related(
            "prueba_manejo",
            "prueba_manejo__cliente",
        )
        .all()
        .order_by("-id")
    )
    serializer_class = EvidenciaPruebaManejoSerializer
    parser_classes = [MultiPartParser, FormParser]


class EntregasViewSet(ModelViewSet):
    authentication_classes = [CRMJWTAuthentication]

    queryset = Entregas.objects.select_related("cliente").all().order_by("-id")
    serializer_class = EntregasSerializer

    acciones_publicas = {
        "list",
        "retrieve",
        "create",
        "pdf",
    }

    def get_authenticators(self):
        if getattr(self, "action", None) in self.acciones_publicas:
            return []

        return [CRMJWTAuthentication()]

    def get_permissions(self):
        if getattr(self, "action", None) in self.acciones_publicas:
            return [AllowAny()]

        return [IsAuthenticated()]

    @action(detail=True, methods=["get"], url_path="pdf")
    def pdf(self, request, pk=None):
        entrega = self.get_object()
        buffer = generar_pdf_entrega(entrega)

        cliente_slug = slugify(entrega.cliente.nombre or "cliente") or "cliente"
        filename = f"encuesta_entrega_{entrega.id}_{cliente_slug}.pdf"

        response = FileResponse(
            buffer,
            as_attachment=False,
            filename=filename,
            content_type="application/pdf",
        )
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response