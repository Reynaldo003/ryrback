#gestion_inversion/views.py
from __future__ import annotations

import json
import logging
import re

from datetime import datetime
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date

from google import genai
from google.genai import types

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

from rest_framework.permissions import (
    IsAuthenticated,
)

from rest_framework.response import Response

from CrmConformidad.jwt_authentication import (
    CRMJWTAuthentication,
)

from .models import (
    FacturaMarketing,
    ConceptoFactura,
)

from .serializers import (
    FacturaMarketingSerializer,
    FacturaUploadSerializer,
    ConceptoFacturaSerializer,
)


logger = logging.getLogger(__name__)


# ============================================================
# SCHEMA GEMINI
# ============================================================

GEMINI_FACTURA_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "es_factura": {
            "type": "BOOLEAN",
        },

        "emisor": {
            "type": "OBJECT",
            "properties": {
                "razon_social": {
                    "type": "STRING",
                },
                "rfc": {
                    "type": "STRING",
                },
                "regimen_fiscal": {
                    "type": "STRING",
                },
                "domicilio": {
                    "type": "STRING",
                },
            },
            "required": [
                "razon_social",
                "rfc",
                "regimen_fiscal",
                "domicilio",
            ],
        },

        "receptor": {
            "type": "OBJECT",
            "properties": {
                "razon_social": {
                    "type": "STRING",
                },
                "rfc": {
                    "type": "STRING",
                },
                "uso_cfdi": {
                    "type": "STRING",
                },
            },
            "required": [
                "razon_social",
                "rfc",
                "uso_cfdi",
            ],
        },

        "comprobante": {
            "type": "OBJECT",
            "properties": {
                "uuid": {
                    "type": "STRING",
                },
                "folio": {
                    "type": "STRING",
                },
                "fecha": {
                    "anyOf": [
                        {
                            "type": "STRING",
                        },
                        {
                            "type": "NULL",
                        },
                    ]
                },
                "moneda": {
                    "type": "STRING",
                },
                "metodo_pago": {
                    "type": "STRING",
                },
                "forma_pago": {
                    "type": "STRING",
                },
            },
            "required": [
                "uuid",
                "folio",
                "fecha",
                "moneda",
                "metodo_pago",
                "forma_pago",
            ],
        },

        "totales": {
            "type": "OBJECT",
            "properties": {
                "subtotal": {
                    "anyOf": [
                        {
                            "type": "NUMBER",
                        },
                        {
                            "type": "NULL",
                        },
                    ]
                },
                "impuestos": {
                    "anyOf": [
                        {
                            "type": "NUMBER",
                        },
                        {
                            "type": "NULL",
                        },
                    ]
                },
                "total": {
                    "anyOf": [
                        {
                            "type": "NUMBER",
                        },
                        {
                            "type": "NULL",
                        },
                    ]
                },
            },
            "required": [
                "subtotal",
                "impuestos",
                "total",
            ],
        },

        "conceptos": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "clave": {
                        "type": "STRING",
                    },
                    "descripcion": {
                        "type": "STRING",
                    },
                    "cantidad": {
                        "anyOf": [
                            {
                                "type": "NUMBER",
                            },
                            {
                                "type": "NULL",
                            },
                        ]
                    },
                    "unidad": {
                        "type": "STRING",
                    },
                    "precio_unitario": {
                        "anyOf": [
                            {
                                "type": "NUMBER",
                            },
                            {
                                "type": "NULL",
                            },
                        ]
                    },
                    "importe": {
                        "anyOf": [
                            {
                                "type": "NUMBER",
                            },
                            {
                                "type": "NULL",
                            },
                        ]
                    },
                },
                "required": [
                    "clave",
                    "descripcion",
                    "cantidad",
                    "unidad",
                    "precio_unitario",
                    "importe",
                ],
            },
        },

        "observaciones": {
            "type": "STRING",
        },
    },

    "required": [
        "es_factura",
        "emisor",
        "receptor",
        "comprobante",
        "totales",
        "conceptos",
        "observaciones",
    ],
}


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
3. Si un dato no existe, utiliza una cadena vacía o null según corresponda.
4. Los importes deben devolverse como números, sin símbolos de moneda ni separadores.
5. La fecha debe devolverse como YYYY-MM-DD cuando pueda identificarse.
6. Detecta todos los conceptos o partidas de la factura.
7. Mantén cada concepto como una partida independiente.
8. No combines partidas diferentes.
9. No clasifiques gastos de Marketing.
10. No determines Social Media, Posicionamiento, Consumo Interno ni Eventos.
11. No determines sitio, rubro ni motivo.
12. La clasificación administrativa será realizada manualmente posteriormente.
13. Si el documento no parece una factura, establece es_factura=false.
14. Si existen IVA, impuestos trasladados u otros impuestos, coloca en "impuestos"
    el total de impuestos mostrado por el documento.
15. No recalcules importes cuando estos aparezcan explícitamente en la factura.
16. El campo observaciones solo debe mencionar problemas importantes de lectura.

Devuelve exclusivamente el JSON solicitado por el esquema.
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
        if isinstance(
            valor,
            str,
        ):
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

    # Primer intento:
    # YYYY-MM-DD
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


def _json_seguro(texto):
    texto = str(
        texto or ""
    ).strip()

    if not texto:
        return {}

    try:
        return json.loads(
            texto
        )
    except Exception:
        pass

    texto = re.sub(
        r"```(?:json)?\s*",
        "",
        texto,
    )

    texto = re.sub(
        r"```\s*$",
        "",
        texto,
    ).strip()

    try:
        return json.loads(
            texto
        )
    except Exception:
        pass

    match = re.search(
        r"\{.*\}",
        texto,
        flags=re.DOTALL,
    )

    if not match:
        return {}

    fragmento = match.group(0)

    try:
        return json.loads(
            fragmento
        )
    except Exception:
        return {}


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
# GEMINI
# ============================================================

@lru_cache(maxsize=1)
def _get_gemini_client():
    api_key = str(
        getattr(
            settings,
            "GEMINI_API_KEY",
            "",
        )
        or ""
    ).strip()

    if not api_key:
        raise RuntimeError(
            "Falta configurar GEMINI_API_KEY."
        )

    return genai.Client(
        api_key=api_key,
    )


def analizar_pdf_con_gemini(
    blob: bytes,
) -> dict[str, Any]:

    if not blob:
        raise ValueError(
            "El PDF está vacío."
        )

    max_bytes = int(
        getattr(
            settings,
            "GEMINI_MAX_INLINE_MEDIA_BYTES",
            18 * 1024 * 1024,
        )
    )

    if len(blob) > max_bytes:
        raise ValueError(
            "El PDF supera el límite configurado para Gemini."
        )

    client = _get_gemini_client()

    modelo = getattr(
        settings,
        "GEMINI_FACTURAS_MODEL",
        getattr(
            settings,
            "GEMINI_MULTIMODAL_MODEL",
            "gemini-2.5-flash",
        ),
    )

    respuesta = client.models.generate_content(
        model=modelo,

        contents=[
            types.Part.from_bytes(
                data=blob,
                mime_type="application/pdf",
            ),
            PROMPT_ANALISIS_FACTURA,
        ],

        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=GEMINI_FACTURA_SCHEMA,

            thinking_config=types.ThinkingConfig(
                thinking_budget=0,
            ),

            temperature=0.1,

            # Algunas facturas pueden contener muchas partidas.
            max_output_tokens=8192,
        ),
    )

    usage = getattr(
        respuesta,
        "usage_metadata",
        None,
    )

    if usage:
        logger.info(
            (
                "GEMINI FACTURA | modelo=%s "
                "entrada=%s salida=%s total=%s"
            ),
            modelo,
            getattr(
                usage,
                "prompt_token_count",
                None,
            ),
            getattr(
                usage,
                "candidates_token_count",
                None,
            ),
            getattr(
                usage,
                "total_token_count",
                None,
            ),
        )

    resultado = _json_seguro(
        getattr(
            respuesta,
            "text",
            "",
        )
    )

    if not resultado:
        raise ValueError(
            "Gemini no devolvió datos estructurados."
        )

    return resultado


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
        ),
    )

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

    factura.resultado_ia = resultado

    factura.estado = (
        FacturaMarketing.Estado.PROCESADA
    )

    factura.error_analisis = ""

    factura.analizado = timezone.now()

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

    # Preservamos las clasificaciones manuales si se vuelve
    # a ejecutar Gemini sobre la misma factura.
    clasificaciones_anteriores = {
        concepto.orden: {
            "clasificacion":
                concepto.clasificacion,
            "sitio":
                concepto.sitio,
            "motivo":
                concepto.motivo,
        }
        for concepto in factura.conceptos.all()
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
                    ),
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
        queryset = (
            FacturaMarketing.objects
            .prefetch_related(
                "conceptos"
            )
            .all()
        )

        q = str(
            self.request.query_params.get(
                "q",
                "",
            )
            or ""
        ).strip()

        clasificacion = str(
            self.request.query_params.get(
                "clasificacion",
                "",
            )
            or ""
        ).strip()

        sitio = str(
            self.request.query_params.get(
                "sitio",
                "",
            )
            or ""
        ).strip()

        estado = str(
            self.request.query_params.get(
                "estado",
                "",
            )
            or ""
        ).strip()

        if q:
            queryset = queryset.filter(
                Q(
                    nombre_original__icontains=q
                )
                | Q(
                    emisor_razon_social__icontains=q
                )
                | Q(
                    emisor_rfc__icontains=q
                )
                | Q(
                    receptor_razon_social__icontains=q
                )
                | Q(
                    receptor_rfc__icontains=q
                )
                | Q(
                    uuid_cfdi__icontains=q
                )
                | Q(
                    folio__icontains=q
                )
                | Q(
                    conceptos__descripcion__icontains=q
                )
            )

        if clasificacion:
            queryset = queryset.filter(
                conceptos__clasificacion=
                clasificacion
            )

        if sitio:
            queryset = queryset.filter(
                conceptos__sitio=sitio
            )

        if estado:
            queryset = queryset.filter(
                estado=estado
            )

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

    # --------------------------------------------------------
    # POST /facturas/analizar/
    # --------------------------------------------------------

    @action(
        detail=False,
        methods=["post"],
        url_path="analizar",
        parser_classes=[
            MultiPartParser,
            FormParser,
        ],
    )
    def analizar(self, request):
        serializer = (
            FacturaUploadSerializer(
                data=request.data
            )
        )

        serializer.is_valid(
            raise_exception=True
        )

        archivo = (
            serializer.validated_data[
                "archivo"
            ]
        )

        factura = (
            FacturaMarketing.objects.create(
                archivo=archivo,

                nombre_original=(
                    getattr(
                        archivo,
                        "name",
                        "",
                    )
                    or ""
                ),

                tipo_mime=(
                    getattr(
                        archivo,
                        "content_type",
                        "",
                    )
                    or "application/pdf"
                ),

                tamano_bytes=(
                    getattr(
                        archivo,
                        "size",
                        0,
                    )
                    or 0
                ),

                creado_por=(
                    nombre_usuario_crm(
                        request.user
                    )
                ),

                estado=(
                    FacturaMarketing
                    .Estado
                    .PROCESANDO
                ),
            )
        )

        try:
            factura.archivo.open(
                "rb"
            )

            try:
                blob = (
                    factura.archivo.read()
                )
            finally:
                factura.archivo.close()

            resultado = (
                analizar_pdf_con_gemini(
                    blob
                )
            )

            if (
                resultado.get(
                    "es_factura"
                )
                is False
            ):
                raise ValueError(
                    "El documento cargado no parece ser una factura."
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

            salida = (
                self.get_serializer(
                    factura
                )
            )

            return Response(
                {
                    "message":
                        "Factura analizada correctamente.",
                    "data":
                        salida.data,
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception as exc:
            logger.exception(
                "ERROR ANALIZANDO FACTURA | factura=%s archivo=%s",
                factura.pk,
                factura.nombre_original,
            )

            factura.estado = (
                FacturaMarketing
                .Estado
                .ERROR
            )

            factura.error_analisis = (
                str(exc)[:2000]
            )

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

            factura = (
                self.get_queryset()
                .get(
                    pk=factura.pk
                )
            )

            salida = (
                self.get_serializer(
                    factura
                )
            )

            return Response(
                {
                    "detail":
                        "La factura se guardó, pero no pudo analizarse correctamente.",
                    "data":
                        salida.data,
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

    # --------------------------------------------------------
    # POST /facturas/{id}/reanalisar/
    # --------------------------------------------------------

    @action(
        detail=True,
        methods=["post"],
        url_path="reanalisar",
    )
    def reanalizar(self, request, pk=None):
        factura = self.get_object()

        if not factura.archivo:
            return Response(
                {
                    "detail":
                        "La factura no tiene un PDF asociado."
                },
                status=status.HTTP_400_BAD_REQUEST,
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
            factura.archivo.open(
                "rb"
            )

            try:
                blob = (
                    factura.archivo.read()
                )
            finally:
                factura.archivo.close()

            resultado = (
                analizar_pdf_con_gemini(
                    blob
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
                status=status.HTTP_200_OK,
            )

        except Exception as exc:
            logger.exception(
                "ERROR REANALIZANDO FACTURA | factura=%s",
                factura.pk,
            )

            factura.estado = (
                FacturaMarketing
                .Estado
                .ERROR
            )

            factura.error_analisis = (
                str(exc)[:2000]
            )

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

            return Response(
                {
                    "detail":
                        "No fue posible volver a analizar la factura.",
                    "data":
                        self.get_serializer(
                            factura
                        ).data,
                },
                status=status.HTTP_502_BAD_GATEWAY,
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