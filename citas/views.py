# citas/views.py
from io import BytesIO
from pathlib import Path
from datetime import datetime
from html import escape

from django.conf import settings
from django.db.models import Count
from django.http import FileResponse
from django.utils import timezone
from django.utils.text import slugify

from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny, IsAuthenticated

from .pagination import CitasPagination

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
    ClienteComercialListSerializer,
    CitaSerializer,
    CitaListSerializer,
    RegistroPisoSerializer,
    RegistroPisoListSerializer,
    PruebaManejoSerializer,
    PruebaManejoListSerializer,
    EvidenciaPruebaManejoSerializer,
    EntregasSerializer,
    EntregasListSerializer,
)

NEGRO = colors.black
BLANCO = colors.white
GRIS_BORDE = HexColor("#BDBDBD")
GRIS_CLARO = HexColor("#F0F0F0")


def _param_bool(valor):
    return str(valor or "").strip().casefold() in {"1", "true", "si", "sí", "yes", "on"}


def _rango_mes(valor):
    texto_mes = str(valor or "").strip()
    if not texto_mes:
        return None

    try:
        anio_texto, mes_texto = texto_mes.split("-", 1)
        anio, mes = int(anio_texto), int(mes_texto)
        if len(anio_texto) != 4 or len(mes_texto) != 2 or not 1 <= mes <= 12:
            return False
        inicio = datetime(anio, mes, 1)
        fin = datetime(anio + 1, 1, 1) if mes == 12 else datetime(anio, mes + 1, 1)
        if settings.USE_TZ:
            zona = timezone.get_current_timezone()
            inicio = timezone.make_aware(inicio, zona)
            fin = timezone.make_aware(fin, zona)
        return inicio, fin
    except (TypeError, ValueError):
        return False


def _filtrar_por_mes(queryset, campo, valor):
    rango = _rango_mes(valor)
    if rango is None:
        return queryset
    if rango is False:
        return queryset.none()
    inicio, fin = rango
    return queryset.filter(**{f"{campo}__gte": inicio, f"{campo}__lt": fin})


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
    pagination_class = CitasPagination

    queryset = ClienteComercial.objects.all().order_by("-id_cliente")
    serializer_class = ClienteComercialSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return ClienteComercialListSerializer
        return ClienteComercialSerializer

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
    pagination_class = CitasPagination
    acciones_publicas = {"list", "retrieve", "create"}

    def get_serializer_class(self):
        if self.action == "list":
            return CitaListSerializer
        return CitaSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params
        queryset = _filtrar_por_mes(queryset, "fecha_hora_cita", params.get("mes"))

        if _param_bool(params.get("solo_digital")):
            queryset = queryset.exclude(asesor_digital="").exclude(asesor_digital__isnull=True)

        asesor_digital = str(params.get("asesor_digital") or "").strip()
        agencia = str(params.get("agencia") or "").strip()
        asesor_piso = str(params.get("asesor_piso") or "").strip()
        asistencia = params.get("asistencia")

        if asesor_digital:
            queryset = queryset.filter(asesor_digital__iexact=asesor_digital)
        if agencia:
            queryset = queryset.filter(agencia__iexact=agencia)
        if asesor_piso:
            queryset = queryset.filter(asesor_piso__iexact=asesor_piso)
        if asistencia not in (None, ""):
            queryset = queryset.filter(asistencia=_param_bool(asistencia))

        search = str(params.get("search") or "").strip()
        if search:
            from django.db.models import Q
            queryset = queryset.filter(
                Q(cliente__nombre__icontains=search)
                | Q(cliente__telefono__icontains=search)
                | Q(agencia__icontains=search)
                | Q(auto_interes__icontains=search)
                | Q(tipo_cita__icontains=search)
                | Q(asesor_digital__icontains=search)
                | Q(asesor_piso__icontains=search)
                | Q(comentarios__icontains=search)
            )

        fecha_desde = str(params.get("fecha_desde") or "").strip()
        fecha_hasta = str(params.get("fecha_hasta") or "").strip()
        if fecha_desde:
            queryset = queryset.filter(fecha_hora_cita__date__gte=fecha_desde)
        if fecha_hasta:
            queryset = queryset.filter(fecha_hora_cita__date__lte=fecha_hasta)

        return queryset

    def get_authenticators(self):
        return [] if getattr(self, "action", None) in self.acciones_publicas else [CRMJWTAuthentication()]

    def get_permissions(self):
        return [AllowAny()] if getattr(self, "action", None) in self.acciones_publicas else [IsAuthenticated()]

class RegistroPisoViewSet(ModelViewSet):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]
    pagination_class = CitasPagination

    queryset = RegistroPiso.objects.select_related("cliente").all().order_by("-id")
    serializer_class = RegistroPisoSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return RegistroPisoListSerializer
        return RegistroPisoSerializer


class PruebasManejoViewSet(ModelViewSet):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]
    pagination_class = CitasPagination

    queryset = (
        PruebaManejo.objects.select_related("cliente")
        .prefetch_related("evidencias")
        .annotate(evidencias_count=Count("evidencias"))
        .all()
        .order_by("-id")
    )
    serializer_class = PruebaManejoSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return PruebaManejoListSerializer
        return PruebaManejoSerializer


    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params

        agencia = str(params.get("agencia") or "").strip()

        if agencia:
            queryset = queryset.filter(agencia__iexact=agencia)

        search = str(params.get("search") or "").strip()

        if search:
            from django.db.models import Q

            queryset = queryset.filter(
                Q(cliente__nombre__icontains=search)
                | Q(cliente__telefono__icontains=search)
                | Q(cliente__correo__icontains=search)
                | Q(agencia__icontains=search)
                | Q(auto_interes__icontains=search)
                | Q(asesor_piso__icontains=search)
                | Q(num_serie__icontains=search)
                | Q(folio_salida__icontains=search)
                | Q(comentarios_cliente__icontains=search)
            )

        fecha_desde = str(params.get("fecha_desde") or "").strip()
        fecha_hasta = str(params.get("fecha_hasta") or "").strip()

        if fecha_desde:
            queryset = queryset.filter(
                fecha_hora_cita__date__gte=fecha_desde
            )

        if fecha_hasta:
            queryset = queryset.filter(
                fecha_hora_cita__date__lte=fecha_hasta
            )

        return queryset


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
    pagination_class = CitasPagination
    acciones_publicas = {"list", "retrieve", "create", "pdf"}

    def get_serializer_class(self):
        if self.action == "list":
            return EntregasListSerializer
        return EntregasSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params

        queryset = _filtrar_por_mes(
            queryset,
            "fecha_hora_entrega",
            params.get("mes"),
        )

        agencia = str(params.get("agencia") or "").strip()
        asesor_ventas = str(params.get("asesor_ventas") or "").strip()
        tipo_venta = str(params.get("tipo_venta") or "").strip()

        if agencia:
            queryset = queryset.filter(
                agencia__iexact=agencia
            )

        if tipo_venta:
            queryset = queryset.filter(
                tipo_venta__iexact=tipo_venta
            )

        if asesor_ventas:
            queryset = queryset.filter(
                asesor_ventas__iexact=asesor_ventas
            )

        if _param_bool(params.get("solo_reportadas")):
            queryset = queryset.filter(
                entrega_reportada=True
            )

        search = str(params.get("search") or "").strip()

        if search:
            from django.db.models import Q

            queryset = queryset.filter(
                Q(cliente__nombre__icontains=search)
                | Q(cliente__telefono__icontains=search)
                | Q(agencia__icontains=search)
                | Q(vin__icontains=search)
                | Q(modelo_version__icontains=search)
                | Q(version__icontains=search)
                | Q(color__icontains=search)
                | Q(asesor_ventas__icontains=search)
                | Q(preparada_por__icontains=search)
                | Q(id_cliente_sf_nadin__icontains=search)
                | Q(id_cliente_sf_dms__icontains=search)
                | Q(comentarios__icontains=search)
            )

        fecha_desde = str(
            params.get("fecha_desde") or ""
        ).strip()

        fecha_hasta = str(
            params.get("fecha_hasta") or ""
        ).strip()

        if fecha_desde:
            queryset = queryset.filter(
                fecha_hora_entrega__date__gte=fecha_desde
            )

        if fecha_hasta:
            queryset = queryset.filter(
                fecha_hora_entrega__date__lte=fecha_hasta
            )

        return queryset
   
    def get_authenticators(self):
        return [] if getattr(self, "action", None) in self.acciones_publicas else [CRMJWTAuthentication()]

    def get_permissions(self):
        return [AllowAny()] if getattr(self, "action", None) in self.acciones_publicas else [IsAuthenticated()]

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