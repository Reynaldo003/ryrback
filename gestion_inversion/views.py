#gestion_inversion/views.py
from __future__ import annotations

import base64
import logging

from datetime import datetime
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date

from openai import OpenAI
from pydantic import BaseModel

from rest_framework import (
    mixins,
    status,
    viewsets,
)

from rest_framework.decorators import action

from rest_framework.parsers import (
    FormParser,
    JSONParser,
    MultiPartParser,
)

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from CrmConformidad.jwt_authentication import CRMJWTAuthentication

from .models import (
    FacturaMarketing,
    ConceptoFactura,
)

from .serializers import FacturaMarketingSerializer, FacturaUploadSerializer, ConceptoFacturaSerializer, FacturaAsignacionSerializer


logger = logging.getLogger(__name__)


# ============================================================
# ESTRUCTURA DE RESPUESTA DE OPENAI
# ============================================================

class EmisorFacturaIA(BaseModel):
    razon_social: str
    rfc: str
    regimen_fiscal: str
    domicilio: str


class ReceptorFacturaIA(BaseModel):
    razon_social: str
    rfc: str
    uso_cfdi: str


class ComprobanteFacturaIA(BaseModel):
    uuid: str
    folio: str
    fecha: str | None
    moneda: str
    metodo_pago: str
    forma_pago: str


class TotalesFacturaIA(BaseModel):
    subtotal: float | None
    impuestos: float | None
    total: float | None


class ConceptoFacturaIA(BaseModel):
    clave: str
    descripcion: str
    cantidad: float | None
    unidad: str
    precio_unitario: float | None
    importe: float | None


class ResultadoFacturaIA(BaseModel):
    es_factura: bool
    emisor: EmisorFacturaIA
    receptor: ReceptorFacturaIA
    comprobante: ComprobanteFacturaIA
    totales: TotalesFacturaIA
    conceptos: list[ConceptoFacturaIA]
    observaciones: str


# ============================================================
# PROMPT
# ============================================================

PROMPT_ANALISIS_FACTURA = """
Eres un sistema especializado en extracción estructurada de facturas.

Recibirás un archivo PDF que puede ser:

- CFDI mexicano.
- Factura emitida en México.
- Factura de un proveedor extranjero.
- Factura de plataformas digitales.
- Factura escaneada.
- Factura generada electrónicamente.

Tu tarea es EXCLUSIVAMENTE extraer los datos visibles en el documento.

REGLAS ESTRICTAS

1. No inventes información.
2. No completes RFC, UUID, fechas, conceptos o importes que no aparezcan.
3. Si un dato de texto no existe, utiliza una cadena vacía.
4. Si una fecha o importe no existe, utiliza null.
5. Los importes deben devolverse como números, sin símbolos de moneda ni separadores.
6. La fecha debe devolverse como YYYY-MM-DD cuando pueda identificarse.
7. Detecta todos los conceptos o partidas de la factura.
8. Mantén cada concepto como una partida independiente.
9. No combines partidas diferentes.
10. No clasifiques gastos de Marketing.
11. No determines Social Media, Posicionamiento, Consumo Interno ni Eventos.
12. No determines sitio, rubro ni motivo.
13. La clasificación administrativa será realizada manualmente posteriormente.
14. Si el documento no parece una factura, establece es_factura=false.
15. Si existen IVA, impuestos trasladados u otros impuestos, coloca en "impuestos"
    el total de impuestos mostrado por el documento.
16. No recalcules importes cuando estos aparezcan explícitamente en la factura.
17. El campo observaciones solo debe mencionar problemas importantes de lectura.
18. Respeta exactamente los importes, cantidades y conceptos encontrados.
19. No deduzcas información fiscal que no aparezca explícitamente.
20. El RFC del emisor debe corresponder al emisor y el RFC del receptor al receptor.
21. No confundas subtotal con total.
22. Extrae todos los conceptos aunque existan varias páginas.
23. No resumas los conceptos: conserva la descripción que aparezca en la factura.
24. Si la factura está en una moneda diferente a MXN, conserva la moneda original.

Extrae la información de la factura siguiendo exactamente la estructura solicitada.
""".strip()


# ============================================================
# UTILIDADES
# ============================================================

def _dict(valor):
    return valor if isinstance(valor, dict) else {}


def _texto(valor, max_len=None):
    resultado = str(
        valor or ""
    ).strip()

    if max_len:
        return resultado[:max_len]

    return resultado


def _decimal(valor, default="0"):
    if valor in (
        None,
        "",
    ):
        return Decimal(default)

    try:
        if isinstance(valor, str):
            valor = (
                valor
                .replace("$", "")
                .replace(",", "")
                .strip()
            )

        return Decimal(
            str(valor)
        )

    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):
        return Decimal(default)


def _fecha(valor):
    valor = str(
        valor or ""
    ).strip()

    if not valor:
        return None

    fecha = parse_date(
        valor[:10]
    )

    if fecha:
        return fecha

    formatos = [
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
    ]

    for formato in formatos:
        try:
            return datetime.strptime(
                valor,
                formato,
            ).date()

        except ValueError:
            continue

    return None


def nombre_usuario_crm(usuario):
    return str(
        getattr(
            usuario,
            "nombre_completo",
            "",
        )
        or getattr(
            usuario,
            "nombre",
            "",
        )
        or getattr(
            usuario,
            "username",
            "",
        )
        or getattr(
            usuario,
            "usuario",
            "",
        )
        or getattr(
            usuario,
            "email",
            "",
        )
        or usuario
        or ""
    ).strip()


# ============================================================
# OPENAI
# ============================================================

@lru_cache(maxsize=1)
def _get_openai_client():
    api_key = str(
        getattr(
            settings,
            "OPENAI_API_KEY",
            "",
        )
        or ""
    ).strip()

    if not api_key:
        raise RuntimeError(
            "Falta configurar OPENAI_API_KEY."
        )

    return OpenAI(
        api_key=api_key,
        timeout=90.0,
        max_retries=2,
    )


def analizar_pdf_con_openai(blob: bytes, nombre_archivo: str = "factura.pdf") -> dict[str, Any]:
    if not blob:
        raise ValueError("El PDF está vacío.")

    max_bytes = int(getattr(settings, "OPENAI_MAX_PDF_BYTES", 18 * 1024 * 1024))

    if len(blob) > max_bytes:
        limite_mb = round(max_bytes / 1024 / 1024, 2)
        raise ValueError(f"El PDF supera el límite configurado de {limite_mb} MB.")

    nombre_archivo = str(nombre_archivo or "factura.pdf").strip()

    if not nombre_archivo.lower().endswith(".pdf"):
        nombre_archivo = f"{nombre_archivo}.pdf"

    pdf_base64 = base64.b64encode(blob).decode("utf-8")
    client = _get_openai_client()

    modelo = str(getattr(settings, "OPENAI_MODEL", "gpt-5.6-luna") or "gpt-5.6-luna").strip()

    logger.info("INICIANDO ANALISIS OPENAI | archivo=%s modelo=%s bytes=%s", nombre_archivo, modelo, len(blob))

    response = client.responses.parse(
        model=modelo,
        input=[
            {
                "role": "system",
                "content": PROMPT_ANALISIS_FACTURA,
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_file",
                        "filename": nombre_archivo,
                        "file_data": f"data:application/pdf;base64,{pdf_base64}",
                    },
                    {
                        "type": "input_text",
                        "text": "Analiza completamente esta factura. Extrae los datos fiscales, totales y todos los conceptos o partidas del documento.",
                    },
                ],
            },
        ],
        text_format=ResultadoFacturaIA,
        max_output_tokens=12000,
    )

    resultado = getattr(response, "output_parsed", None)

    if resultado is None:
        output_text = str(getattr(response, "output_text", "") or "").strip()
        logger.error("OPENAI SIN RESPUESTA ESTRUCTURADA | archivo=%s respuesta=%s", nombre_archivo, output_text[:1000])
        raise ValueError("OpenAI no devolvió datos estructurados de la factura.")

    usage = getattr(response, "usage", None)

    if usage:
        logger.info(
            "OPENAI FACTURA | modelo=%s entrada=%s salida=%s total=%s",
            modelo,
            getattr(usage, "input_tokens", None),
            getattr(usage, "output_tokens", None),
            getattr(usage, "total_tokens", None),
        )

    resultado_dict = resultado.model_dump(mode="json")

    logger.info(
        "ANALISIS OPENAI COMPLETADO | archivo=%s es_factura=%s conceptos=%s",
        nombre_archivo,
        resultado_dict.get("es_factura"),
        len(resultado_dict.get("conceptos", [])),
    )

    return resultado_dict

# ============================================================
# LECTURA DEL ARCHIVO
# ============================================================

def leer_pdf_factura(factura):
    if not factura.archivo:
        raise ValueError(
            "La factura no tiene un PDF asociado."
        )

    factura.archivo.open(
        "rb"
    )

    try:
        return factura.archivo.read()

    finally:
        factura.archivo.close()


# ============================================================
# PERSISTENCIA DEL RESULTADO IA
# ============================================================

@transaction.atomic
def guardar_resultado_ia(
    factura_id: int,
    resultado: dict[str, Any],
):
    factura = (
        FacturaMarketing.objects
        .select_for_update()
        .get(
            pk=factura_id
        )
    )

    emisor = _dict(
        resultado.get(
            "emisor"
        )
    )

    receptor = _dict(
        resultado.get(
            "receptor"
        )
    )

    comprobante = _dict(
        resultado.get(
            "comprobante"
        )
    )

    totales = _dict(
        resultado.get(
            "totales"
        )
    )

    conceptos = resultado.get(
        "conceptos"
    )

    if not isinstance(
        conceptos,
        list,
    ):
        conceptos = []

    # ========================================================
    # EMISOR
    # ========================================================

    factura.emisor_razon_social = _texto(
        emisor.get(
            "razon_social"
        ),
        300,
    )

    factura.emisor_rfc = _texto(
        emisor.get(
            "rfc"
        ),
        30,
    )

    factura.emisor_regimen_fiscal = _texto(
        emisor.get(
            "regimen_fiscal"
        ),
        300,
    )

    factura.emisor_domicilio = _texto(
        emisor.get(
            "domicilio"
        )
    )

    # ========================================================
    # RECEPTOR
    # ========================================================

    factura.receptor_razon_social = _texto(
        receptor.get(
            "razon_social"
        ),
        300,
    )

    factura.receptor_rfc = _texto(
        receptor.get(
            "rfc"
        ),
        30,
    )

    factura.receptor_uso_cfdi = _texto(
        receptor.get(
            "uso_cfdi"
        ),
        200,
    )

    # ========================================================
    # COMPROBANTE
    # ========================================================

    factura.uuid_cfdi = _texto(
        comprobante.get(
            "uuid"
        ),
        100,
    )

    factura.folio = _texto(
        comprobante.get(
            "folio"
        ),
        100,
    )

    factura.fecha_factura = _fecha(
        comprobante.get(
            "fecha"
        )
    )

    factura.moneda = (
        _texto(
            comprobante.get(
                "moneda"
            ),
            20,
        )
        or "MXN"
    )

    factura.metodo_pago = _texto(
        comprobante.get(
            "metodo_pago"
        ),
        100,
    )

    factura.forma_pago = _texto(
        comprobante.get(
            "forma_pago"
        ),
        200,
    )

    # ========================================================
    # TOTALES
    # ========================================================

    factura.subtotal = _decimal(
        totales.get(
            "subtotal"
        )
    )

    factura.impuestos = _decimal(
        totales.get(
            "impuestos"
        )
    )

    factura.total = _decimal(
        totales.get(
            "total"
        )
    )

    # ========================================================
    # RESPUESTA IA
    # ========================================================

    factura.resultado_ia = resultado

    factura.estado = (
        FacturaMarketing
        .Estado
        .PROCESADA
    )

    factura.error_analisis = ""

    factura.analizado = (
        timezone.now()
    )

    factura.save(
        update_fields=[
            "emisor_razon_social",
            "emisor_rfc",
            "emisor_regimen_fiscal",
            "emisor_domicilio",
            "receptor_razon_social",
            "receptor_rfc",
            "receptor_uso_cfdi",
            "uuid_cfdi",
            "folio",
            "fecha_factura",
            "moneda",
            "metodo_pago",
            "forma_pago",
            "subtotal",
            "impuestos",
            "total",
            "resultado_ia",
            "estado",
            "error_analisis",
            "analizado",
            "actualizado",
        ]
    )

    # ========================================================
    # CONSERVAR CLASIFICACIÓN MANUAL
    # ========================================================

    clasificaciones_anteriores = {
        concepto.orden: {
            "clasificacion":
                concepto.clasificacion,

            "sitio":
                concepto.sitio,

            "motivo":
                concepto.motivo,
        }

        for concepto
        in factura.conceptos.all()
    }

    factura.conceptos.all().delete()

    conceptos_nuevos = []

    for index, concepto_raw in enumerate(
        conceptos,
        start=1,
    ):
        concepto = _dict(
            concepto_raw
        )

        manual = (
            clasificaciones_anteriores.get(
                index,
                {},
            )
        )

        conceptos_nuevos.append(
            ConceptoFactura(
                factura=factura,

                orden=index,

                clave=_texto(
                    concepto.get(
                        "clave"
                    ),
                    100,
                ),

                descripcion=_texto(
                    concepto.get(
                        "descripcion"
                    )
                ),

                cantidad=_decimal(
                    concepto.get(
                        "cantidad"
                    )
                ),

                unidad=_texto(
                    concepto.get(
                        "unidad"
                    ),
                    100,
                ),

                precio_unitario=_decimal(
                    concepto.get(
                        "precio_unitario"
                    )
                ),

                importe=_decimal(
                    concepto.get(
                        "importe"
                    )
                ),

                clasificacion=manual.get(
                    "clasificacion",
                    "",
                ),

                sitio=manual.get(
                    "sitio",
                    "",
                ),

                motivo=manual.get(
                    "motivo",
                    "",
                ),
            )
        )

    if conceptos_nuevos:
        ConceptoFactura.objects.bulk_create(
            conceptos_nuevos
        )

    return factura


# ============================================================
# MANEJO DE ERRORES DE FACTURA
# ============================================================

def marcar_factura_error(
    factura,
    exc,
):
    factura.estado = (
        FacturaMarketing
        .Estado
        .ERROR
    )

    factura.error_analisis = str(
        exc
    )[:2000]

    factura.analizado = (
        timezone.now()
    )

    factura.save(
        update_fields=[
            "estado",
            "error_analisis",
            "analizado",
            "actualizado",
        ]
    )


# ============================================================
# FACTURAS
# ============================================================

class FacturaMarketingViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    authentication_classes = [
        CRMJWTAuthentication,
    ]

    permission_classes = [
        IsAuthenticated,
    ]

    parser_classes = [
        JSONParser,
        MultiPartParser,
        FormParser,
    ]

    serializer_class = (
        FacturaMarketingSerializer
    )

    def get_queryset(self):
        queryset = FacturaMarketing.objects.prefetch_related("conceptos").all()

        q = str(self.request.query_params.get("q", "") or "").strip()
        clasificacion = str(self.request.query_params.get("clasificacion", "") or "").strip()
        sitio = str(self.request.query_params.get("sitio", "") or "").strip()
        dealer = str(self.request.query_params.get("dealer", "") or "").strip()
        departamento = str(self.request.query_params.get("departamento", "") or "").strip()
        estado = str(self.request.query_params.get("estado", "") or "").strip()

        if q:
            queryset = queryset.filter(
                Q(nombre_original__icontains=q) |
                Q(emisor_razon_social__icontains=q) |
                Q(emisor_rfc__icontains=q) |
                Q(receptor_razon_social__icontains=q) |
                Q(receptor_rfc__icontains=q) |
                Q(uuid_cfdi__icontains=q) |
                Q(folio__icontains=q) |
                Q(dealer__icontains=q) |
                Q(departamento__icontains=q) |
                Q(conceptos__descripcion__icontains=q)
            )

        if clasificacion:
            queryset = queryset.filter(conceptos__clasificacion=clasificacion)

        if sitio:
            queryset = queryset.filter(conceptos__sitio=sitio)

        if dealer:
            queryset = queryset.filter(dealer=dealer)

        if departamento:
            queryset = queryset.filter(departamento=departamento)

        if estado:
            queryset = queryset.filter(estado=estado)

        return queryset.distinct()

    def get_serializer_context(self):
        context = (
            super()
            .get_serializer_context()
        )

        context["request"] = (
            self.request
        )

        return context

    # ========================================================
    # POST /facturas/analizar/
    # ========================================================

    @action(detail=False, methods=["post"], url_path="analizar", parser_classes=[MultiPartParser, FormParser])
    def analizar(self, request):
        serializer = FacturaUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        archivo = serializer.validated_data["archivo"]
        dealer = serializer.validated_data.get("dealer", "")
        departamento = serializer.validated_data.get("departamento", "")

        factura = FacturaMarketing.objects.create(
            archivo=archivo,
            nombre_original=getattr(archivo, "name", "") or "",
            tipo_mime=getattr(archivo, "content_type", "") or "application/pdf",
            tamano_bytes=getattr(archivo, "size", 0) or 0,
            creado_por=nombre_usuario_crm(request.user),
            dealer=dealer,
            departamento=departamento,
            estado=FacturaMarketing.Estado.PROCESANDO,
        )

        try:
            blob = leer_pdf_factura(factura)

            resultado = analizar_pdf_con_openai(
                blob=blob,
                nombre_archivo=factura.nombre_original,
            )

            if resultado.get("es_factura") is False:
                raise ValueError("El documento cargado no parece ser una factura.")

            guardar_resultado_ia(factura.id_factura, resultado)

            factura = self.get_queryset().get(pk=factura.pk)
            salida = self.get_serializer(factura)

            return Response(
                {
                    "message": "Factura analizada correctamente.",
                    "data": salida.data,
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception as exc:
            logger.exception(
                "ERROR ANALIZANDO FACTURA OPENAI | factura=%s archivo=%s",
                factura.pk,
                factura.nombre_original,
            )

            marcar_factura_error(factura, exc)
            factura = self.get_queryset().get(pk=factura.pk)

            return Response(
                {
                    "detail": "La factura se guardó, pero no pudo analizarse correctamente.",
                    "error": str(exc),
                    "data": self.get_serializer(factura).data,
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

    # ========================================================
    # POST /facturas/{id}/reanalizar/
    # ========================================================

    @action(
        detail=True,
        methods=[
            "post",
        ],
        url_path="reanalizar",
    )
    def reanalizar(
        self,
        request,
        pk=None,
    ):
        factura = (
            self.get_object()
        )

        if not factura.archivo:
            return Response(
                {
                    "detail":
                        "La factura no tiene un PDF asociado."
                },
                status=(
                    status.HTTP_400_BAD_REQUEST
                ),
            )

        factura.estado = (
            FacturaMarketing
            .Estado
            .PROCESANDO
        )

        factura.error_analisis = ""

        factura.save(
            update_fields=[
                "estado",
                "error_analisis",
                "actualizado",
            ]
        )

        try:
            blob = leer_pdf_factura(
                factura
            )

            resultado = (
                analizar_pdf_con_openai(
                    blob=blob,
                    nombre_archivo=(
                        factura.nombre_original
                    ),
                )
            )

            if (
                resultado.get(
                    "es_factura"
                )
                is False
            ):
                raise ValueError(
                    "El documento no parece ser una factura."
                )

            guardar_resultado_ia(
                factura.id_factura,
                resultado,
            )

            factura = (
                self.get_queryset()
                .get(
                    pk=factura.pk
                )
            )

            return Response(
                {
                    "message":
                        "Factura analizada nuevamente.",

                    "data":
                        self.get_serializer(
                            factura
                        ).data,
                },
                status=(
                    status.HTTP_200_OK
                ),
            )

        except Exception as exc:
            logger.exception(
                (
                    "ERROR REANALIZANDO FACTURA OPENAI | "
                    "factura=%s archivo=%s"
                ),
                factura.pk,
                factura.nombre_original,
            )

            marcar_factura_error(
                factura,
                exc,
            )

            factura = (
                self.get_queryset()
                .get(
                    pk=factura.pk
                )
            )

            return Response(
                {
                    "detail": (
                        "No fue posible volver a analizar "
                        "la factura."
                    ),

                    "error":
                        str(exc),

                    "data":
                        self.get_serializer(
                            factura
                        ).data,
                },
                status=(
                    status.HTTP_502_BAD_GATEWAY
                ),
            )
        
    @action(detail=True, methods=["patch"], url_path="asignacion")
    def actualizar_asignacion(self, request, pk=None):
        factura = self.get_object()

        serializer = FacturaAsignacionSerializer(
            factura,
            data=request.data,
            partial=True,
        )

        serializer.is_valid(raise_exception=True)
        serializer.save()

        factura = self.get_queryset().get(pk=factura.pk)

        return Response(
            {
                "message": "Asignación actualizada correctamente.",
                "data": self.get_serializer(factura).data,
            },
            status=status.HTTP_200_OK,
        )

# ============================================================
# CONCEPTOS
# ============================================================

class ConceptoFacturaViewSet(
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    authentication_classes = [
        CRMJWTAuthentication,
    ]

    permission_classes = [
        IsAuthenticated,
    ]

    parser_classes = [
        JSONParser,
    ]

    serializer_class = (
        ConceptoFacturaSerializer
    )

    queryset = (
        ConceptoFactura.objects
        .select_related(
            "factura"
        )
        .all()
    )

    http_method_names = [
        "get",
        "patch",
        "put",
        "head",
        "options",
    ]