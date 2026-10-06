# CompraRefacciones/views.py
from datetime import timedelta

from django.core.cache import cache
from django.db import connections
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from CrmConformidad.jwt_authentication import CRMJWTAuthentication
from .serializers import (
    CompraRefaccionesSerializer,
    CompraRefaccionPiezaSerializer,
)


DB_ALIAS = "tdsql"

# PostgreSQL / tdsql_vw
TABLA = "matriz_facturasref"
TABLA_PIEZAS = "matriz_compraref"

CACHE_OPCIONES = "compra_refacciones_facturas_postgresql_v1"


# ============================================================
# HELPERS
# ============================================================

def texto_parametro(request, nombre):
    return str(
        request.query_params.get(nombre, "") or ""
    ).strip()


def entero_parametro(
    request,
    nombre,
    default,
    minimo=None,
    maximo=None,
):
    try:
        valor = int(
            request.query_params.get(
                nombre,
                default,
            )
        )
    except (TypeError, ValueError):
        valor = default

    if minimo is not None:
        valor = max(minimo, valor)

    if maximo is not None:
        valor = min(maximo, valor)

    return valor


def validar_fecha(valor, nombre):
    if not valor:
        return None

    fecha = parse_date(valor)

    if not fecha:
        raise ValueError(
            f"El parámetro '{nombre}' debe tener formato YYYY-MM-DD."
        )

    return fecha


def cursor_a_dicts(cursor):
    columnas = [
        columna[0]
        for columna in cursor.description
    ]

    return [
        dict(zip(columnas, fila))
        for fila in cursor.fetchall()
    ]


# ============================================================
# FILTROS
#
# TpItensNFE = '1'
# SitNF = 'V'
#
# Siempre se aplican desde el backend.
# ============================================================

def construir_filtros(request):
    agencia = texto_parametro(
        request,
        "agencia",
    )

    fecha_desde_texto = texto_parametro(
        request,
        "fecha_desde",
    )

    fecha_hasta_texto = texto_parametro(
        request,
        "fecha_hasta",
    )

    busqueda = texto_parametro(
        request,
        "q",
    )

    fecha_desde = validar_fecha(
        fecha_desde_texto,
        "fecha_desde",
    )

    fecha_hasta = validar_fecha(
        fecha_hasta_texto,
        "fecha_hasta",
    )

    if (
        fecha_desde
        and fecha_hasta
        and fecha_desde > fecha_hasta
    ):
        raise ValueError(
            "'fecha_desde' no puede ser mayor que 'fecha_hasta'."
        )

    condiciones = [
        '"TpItensNFE"::text = %s',
        '"SitNF"::text = %s',
    ]

    parametros = [
        "1",
        "V",
    ]

    # ========================================================
    # AGENCIA
    # ========================================================

    if agencia:
        condiciones.append(
            '"Agencia" = %s'
        )

        parametros.append(
            agencia
        )

    # ========================================================
    # FECHA DESDE
    # ========================================================

    if fecha_desde:
        condiciones.append(
            '"DtEntrada" >= %s'
        )

        parametros.append(
            fecha_desde
        )

    # ========================================================
    # FECHA HASTA
    #
    # Se usa límite exclusivo para soportar tanto DATE como
    # TIMESTAMP.
    # ========================================================

    if fecha_hasta:
        fecha_hasta_exclusiva = (
            fecha_hasta
            + timedelta(days=1)
        )

        condiciones.append(
            '"DtEntrada" < %s'
        )

        parametros.append(
            fecha_hasta_exclusiva
        )

    # ========================================================
    # BUSCADOR
    #
    # SQL Server:
    # CONVERT(VARCHAR(50), NrNota)
    #
    # PostgreSQL:
    # "NrNota"::text
    # ========================================================

    if busqueda:
        termino = f"%{busqueda}%"

        condiciones.append(
            """
            (
                COALESCE("Agencia"::text, '') ILIKE %s
                OR COALESCE("NrNota"::text, '') ILIKE %s
                OR COALESCE("Serie"::text, '') ILIKE %s
                OR COALESCE("NrPedUnPar"::text, '') ILIKE %s
                OR COALESCE("Proveedor"::text, '') ILIKE %s
            )
            """
        )

        parametros.extend([
            termino,
            termino,
            termino,
            termino,
            termino,
        ])

    where_sql = (
        "WHERE "
        + " AND ".join(condiciones)
    )

    return where_sql, parametros


# ============================================================
# LISTADO DE FACTURAS
# ============================================================

class CompraRefaccionesListView(APIView):
    authentication_classes = [
        CRMJWTAuthentication,
    ]

    permission_classes = [
        IsAuthenticated,
    ]

    def get(self, request):
        pagina = entero_parametro(
            request,
            "page",
            1,
            minimo=1,
        )

        tamano_pagina = entero_parametro(
            request,
            "page_size",
            50,
            minimo=1,
            maximo=150000,
        )

        offset = (
            pagina - 1
        ) * tamano_pagina

        try:
            (
                where_sql,
                parametros,
            ) = construir_filtros(
                request
            )

        except ValueError as exc:
            return Response(
                {
                    "detail": str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        consulta = f"""
            SELECT
                "rowid__" AS rowid__,

                "Agencia" AS agencia,

                "NrNota" AS nrnota,

                "Serie" AS serie,

                "NrPedUnPar" AS nrpedunpar,

                "QtProdutos" AS qtprodutos,

                "Proveedor" AS proveedor,

                "DtEmissao"::date AS dtemissao,

                "DtEntrada"::date AS dtentrada,

                "Subtotal" AS subtotal,

                "Total" AS total,

                COUNT(*) OVER ()
                    AS total_registros,

                COALESCE(
                    SUM(
                        COALESCE(
                            "QtProdutos",
                            0
                        )
                    ) OVER (),
                    0
                ) AS cantidad_total,

                COALESCE(
                    SUM(
                        COALESCE(
                            "Subtotal",
                            0
                        )
                    ) OVER (),
                    0
                ) AS subtotal_general,

                COALESCE(
                    SUM(
                        COALESCE(
                            "Total",
                            0
                        )
                    ) OVER (),
                    0
                ) AS total_general

            FROM {TABLA}

            {where_sql}

            ORDER BY
                "DtEntrada" DESC NULLS LAST,
                "NrNota" DESC NULLS LAST,
                "rowid__" DESC NULLS LAST

            LIMIT %s
            OFFSET %s
        """

        parametros_consulta = [
            *parametros,
            tamano_pagina,
            offset,
        ]

        with connections[DB_ALIAS].cursor() as cursor:
            cursor.execute(
                consulta,
                parametros_consulta,
            )

            registros = cursor_a_dicts(
                cursor
            )

        # ====================================================
        # MÉTRICAS
        # ====================================================

        if registros:
            primero = registros[0]

            total_registros = int(
                primero.get(
                    "total_registros",
                    0,
                )
                or 0
            )

            metricas = {
                "registros":
                    total_registros,

                "cantidad_total":
                    primero.get(
                        "cantidad_total",
                        0,
                    )
                    or 0,

                "subtotal":
                    primero.get(
                        "subtotal_general",
                        0,
                    )
                    or 0,

                "total":
                    primero.get(
                        "total_general",
                        0,
                    )
                    or 0,
            }

        else:
            total_registros = 0

            metricas = {
                "registros": 0,
                "cantidad_total": 0,
                "subtotal": 0,
                "total": 0,
            }

        # Quitamos las columnas auxiliares de las ventanas.
        for registro in registros:
            registro.pop(
                "total_registros",
                None,
            )

            registro.pop(
                "cantidad_total",
                None,
            )

            registro.pop(
                "subtotal_general",
                None,
            )

            registro.pop(
                "total_general",
                None,
            )

        serializer = CompraRefaccionesSerializer(
            registros,
            many=True,
        )

        return Response(
            {
                "count":
                    total_registros,

                "page":
                    pagina,

                "page_size":
                    tamano_pagina,

                "metricas":
                    metricas,

                "results":
                    serializer.data,
            }
        )


# ============================================================
# OPCIONES / AGENCIAS
# ============================================================

class CompraRefaccionesOpcionesView(APIView):
    authentication_classes = [
        CRMJWTAuthentication,
    ]

    permission_classes = [
        IsAuthenticated,
    ]

    def get(self, request):
        resultado_cache = cache.get(
            CACHE_OPCIONES
        )

        if resultado_cache:
            return Response(
                resultado_cache
            )

        consulta = f"""
            SELECT DISTINCT
                TRIM("Agencia"::text) AS agencia

            FROM {TABLA}

            WHERE
                "TpItensNFE"::text = %s

                AND "SitNF"::text = %s

                AND "Agencia" IS NOT NULL

                AND TRIM("Agencia"::text) <> ''

            ORDER BY
                agencia
        """

        with connections[DB_ALIAS].cursor() as cursor:
            cursor.execute(
                consulta,
                [
                    "1",
                    "V",
                ],
            )

            agencias = [
                fila[0]
                for fila in cursor.fetchall()
                if fila[0]
            ]

        resultado = {
            "agencias":
                agencias,
        }

        cache.set(
            CACHE_OPCIONES,
            resultado,
            3600,
        )

        return Response(
            resultado
        )


# ============================================================
# PIEZAS DE UNA FACTURA
# ============================================================

class CompraRefaccionesPiezasView(APIView):
    authentication_classes = [
        CRMJWTAuthentication,
    ]

    permission_classes = [
        IsAuthenticated,
    ]

    def get(self, request):
        agencia = texto_parametro(
            request,
            "agencia",
        )

        nrnota_texto = texto_parametro(
            request,
            "nrnota",
        )

        if not agencia:
            return Response(
                {
                    "detail":
                        "El parámetro 'agencia' es obligatorio."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not nrnota_texto:
            return Response(
                {
                    "detail":
                        "El parámetro 'nrnota' es obligatorio."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            nrnota = int(
                nrnota_texto
            )

        except (TypeError, ValueError):
            return Response(
                {
                    "detail":
                        "El parámetro 'nrnota' debe ser numérico."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        consulta = f"""
            SELECT
                cr."rowid__" AS rowid__,

                cr."Agencia" AS agencia,

                cr."NrNota" AS nrnota,

                cr."Serie" AS serie,

                cr."SeqItem" AS seqitem,

                cr."ProdServ" AS prodserv,

                cr."DescrProd" AS descrprod,

                cr."Unidade" AS unidade,

                cr."QtProdutos" AS qtprodutos,

                cr."VrUnitLiq" AS vrunitliq,

                cr."VrUnitBruto" AS vrunitbruto,

                cr."VrLiqTotal" AS vrliqtotal,

                cr."DtEntrada"::date AS dtentrada,

                cr."NrPedCompra" AS nrpedcompra,

                COUNT(*) OVER ()
                    AS total_partidas,

                COALESCE(
                    SUM(
                        COALESCE(
                            cr."QtProdutos",
                            0
                        )
                    ) OVER (),
                    0
                ) AS cantidad_total,

                COALESCE(
                    SUM(
                        COALESCE(
                            cr."VrLiqTotal",
                            0
                        )
                    ) OVER (),
                    0
                ) AS importe_total

            FROM {TABLA_PIEZAS} cr

            WHERE
                cr."Agencia" = %s

                AND cr."NrNota" = %s

                AND (
                    cr."Unidade" <> 'UN'
                    OR cr."QtProdutos" <> 1
                )

                AND EXISTS (
                    SELECT
                        1

                    FROM {TABLA} fr

                    WHERE
                        fr."Agencia" = cr."Agencia"

                        AND fr."NrNota" = cr."NrNota"

                        AND fr."TpItensNFE"::text = '1'

                        AND fr."SitNF"::text = 'V'
                )

            ORDER BY
                cr."SeqItem" ASC NULLS LAST,
                cr."rowid__" ASC NULLS LAST
        """

        with connections[DB_ALIAS].cursor() as cursor:
            cursor.execute(
                consulta,
                [
                    agencia,
                    nrnota,
                ],
            )

            registros = cursor_a_dicts(
                cursor
            )

        # ====================================================
        # TOTALES
        # ====================================================

        if registros:
            primero = registros[0]

            resumen = {
                "partidas":
                    int(
                        primero.get(
                            "total_partidas",
                            0,
                        )
                        or 0
                    ),

                "cantidad_total":
                    float(
                        primero.get(
                            "cantidad_total",
                            0,
                        )
                        or 0
                    ),

                "importe_total":
                    float(
                        primero.get(
                            "importe_total",
                            0,
                        )
                        or 0
                    ),
            }

        else:
            resumen = {
                "partidas": 0,
                "cantidad_total": 0,
                "importe_total": 0,
            }

        for registro in registros:
            registro.pop(
                "total_partidas",
                None,
            )

            registro.pop(
                "cantidad_total",
                None,
            )

            registro.pop(
                "importe_total",
                None,
            )

        serializer = CompraRefaccionPiezaSerializer(
            registros,
            many=True,
        )

        return Response(
            {
                "factura": {
                    "agencia":
                        agencia,

                    "nrnota":
                        nrnota,
                },

                "resumen":
                    resumen,

                "results":
                    serializer.data,
            }
        )