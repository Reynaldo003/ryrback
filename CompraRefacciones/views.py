from django.core.cache import cache
from django.db import connections
from django.utils.dateparse import parse_date

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from CrmConformidad.jwt_authentication import CRMJWTAuthentication

from .serializers import CompraRefaccionesSerializer


DB_ALIAS = "sqlserver_inv"

TABLA = "dbo.Matriz_CompraRef_Tipificada"

CACHE_OPCIONES = "compra_refacciones_opciones_v2"


SERIES_VALIDAS = [
    "P",
    "AP",
    "VWM",
    "AAP40",
    "AN",
]


# ============================================================
# EXPRESIONES DE FECHA
#
# Las columnas originales son VARCHAR(MAX).
#
# Ejemplo esperado:
# 2026-08-31
# 2026-08-31 10:35:00
#
# Tomamos los primeros 10 caracteres y los convertimos
# explícitamente como YYYY-MM-DD.
# ============================================================

SQL_DT_EMISSAO = """
TRY_CONVERT(
    DATE,
    LEFT(
        NULLIF(
            LTRIM(RTRIM(DtEmissao)),
            ''
        ),
        10
    ),
    23
)
"""

SQL_DT_ENTRADA = """
TRY_CONVERT(
    DATE,
    LEFT(
        NULLIF(
            LTRIM(RTRIM(DtEntrada)),
            ''
        ),
        10
    ),
    23
)
"""


def texto_parametro(request, nombre):
    return str(
        request.query_params.get(
            nombre,
            "",
        )
        or ""
    ).strip()


def validar_fecha(valor, nombre):
    if valor and not parse_date(valor):
        raise ValueError(
            f"El parámetro '{nombre}' debe tener formato YYYY-MM-DD."
        )


def cursor_a_dicts(cursor):
    columnas = [
        columna[0]
        for columna in cursor.description
    ]

    return [
        dict(
            zip(
                columnas,
                fila,
            )
        )
        for fila in cursor.fetchall()
    ]


def construir_filtros(request):
    busqueda = texto_parametro(
        request,
        "q",
    )

    agencia = texto_parametro(
        request,
        "agencia",
    )

    serie = texto_parametro(
        request,
        "serie",
    )

    fecha_desde = texto_parametro(
        request,
        "fecha_desde",
    )

    fecha_hasta = texto_parametro(
        request,
        "fecha_hasta",
    )

    validar_fecha(
        fecha_desde,
        "fecha_desde",
    )

    validar_fecha(
        fecha_hasta,
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

    if (
        serie
        and serie not in SERIES_VALIDAS
    ):
        raise ValueError(
            f"La serie '{serie}' no es válida."
        )

    condiciones = []
    parametros = []

    # ========================================================
    # SERIE
    #
    # ESTE ES EL ÚNICO FILTRO POR DEFECTO.
    #
    # Siempre limita la información a:
    #
    # P
    # AP
    # VWM
    # AAP40
    # AN
    # ========================================================

    placeholders_series = ", ".join(
        ["%s"] * len(SERIES_VALIDAS)
    )

    condiciones.append(
        f"Serie IN ({placeholders_series})"
    )

    parametros.extend(
        SERIES_VALIDAS
    )

    # ========================================================
    # AGENCIA
    #
    # Solo se agrega si React la envía.
    # ========================================================

    if agencia:
        condiciones.append(
            "Agencia = %s"
        )

        parametros.append(
            agencia
        )

    # ========================================================
    # SERIE ESPECÍFICA
    #
    # Si React no manda serie:
    # se utilizan las 5 permitidas.
    #
    # Si manda P:
    # además se agrega Serie = P.
    # ========================================================

    if serie:
        condiciones.append(
            "Serie = %s"
        )

        parametros.append(
            serie
        )

    # ========================================================
    # FECHA DESDE
    #
    # Solo existe si React envía fecha_desde.
    # ========================================================

    if fecha_desde:
        condiciones.append(
            f"{SQL_DT_EMISSAO} >= %s"
        )

        parametros.append(
            fecha_desde
        )

    # ========================================================
    # FECHA HASTA
    #
    # Solo existe si React envía fecha_hasta.
    # ========================================================

    if fecha_hasta:
        condiciones.append(
            f"{SQL_DT_EMISSAO} <= %s"
        )

        parametros.append(
            fecha_hasta
        )

    # ========================================================
    # BUSCADOR
    # ========================================================

    if busqueda:
        termino = f"%{busqueda}%"

        condiciones.append("""
            (
                Agencia LIKE %s

                OR CONVERT(
                    VARCHAR(50),
                    NrNota
                ) LIKE %s

                OR Serie LIKE %s

                OR ProdServ LIKE %s

                OR DescrProd LIKE %s

                OR Unidade LIKE %s
            )
        """)

        parametros.extend([
            termino,
            termino,
            termino,
            termino,
            termino,
            termino,
        ])

    where_sql = ""

    if condiciones:
        where_sql = (
            "WHERE "
            + " AND ".join(condiciones)
        )

    return (
        where_sql,
        parametros,
    )


# ============================================================
# LISTADO
# ============================================================

class CompraRefaccionesListView(APIView):
    authentication_classes = [
        CRMJWTAuthentication
    ]

    permission_classes = [
        IsAuthenticated
    ]

    def get(self, request):
        # ====================================================
        # PAGINACIÓN
        # ====================================================

        try:
            pagina = max(
                int(
                    request.query_params.get(
                        "page",
                        1,
                    )
                ),
                1,
            )
        except (TypeError, ValueError):
            pagina = 1

        try:
            tamano_pagina = int(
                request.query_params.get(
                    "page_size",
                    50,
                )
            )
        except (TypeError, ValueError):
            tamano_pagina = 50

        tamano_pagina = max(
            1,
            min(
                tamano_pagina,
                500,
            ),
        )

        offset = (
            pagina - 1
        ) * tamano_pagina

        # ====================================================
        # FILTROS
        # ====================================================

        try:
            where_sql, parametros = construir_filtros(
                request
            )

        except ValueError as exc:
            return Response(
                {
                    "detail": str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ====================================================
        # TOTAL
        # ====================================================

        consulta_total = f"""
            SELECT
                COUNT(*)

            FROM {TABLA}

            {where_sql}
        """

        # ====================================================
        # DATOS
        # ====================================================

        consulta = f"""
            SELECT
                rowid__ AS rowid__,

                Agencia AS agencia,

                NrNota AS nrnota,

                Serie AS serie,

                QtProdutos AS qtprodutos,

                Unidade AS unidade,

                ProdServ AS prodserv,

                DescrProd AS descrprod,

                VrUnitLiq AS vrunitliq,

                {SQL_DT_ENTRADA} AS dtentrada,

                {SQL_DT_EMISSAO} AS dtemissao,

                VrUnitBruto AS vrunitbruto

            FROM {TABLA}

            {where_sql}

            ORDER BY
                {SQL_DT_EMISSAO} DESC,
                NrNota DESC,
                rowid__ DESC

            OFFSET %s ROWS

            FETCH NEXT %s ROWS ONLY
        """

        with connections[DB_ALIAS].cursor() as cursor:
            cursor.execute(
                consulta_total,
                parametros,
            )

            total = cursor.fetchone()[0]

            cursor.execute(
                consulta,
                [
                    *parametros,
                    offset,
                    tamano_pagina,
                ],
            )

            registros = cursor_a_dicts(
                cursor
            )

        serializer = CompraRefaccionesSerializer(
            registros,
            many=True,
        )

        return Response({
            "count": total,
            "page": pagina,
            "page_size": tamano_pagina,
            "results": serializer.data,
        })


# ============================================================
# DASHBOARD
# ============================================================

class CompraRefaccionesDashboardView(APIView):
    authentication_classes = [
        CRMJWTAuthentication
    ]

    permission_classes = [
        IsAuthenticated
    ]

    def get(self, request):
        try:
            where_sql, parametros = construir_filtros(
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
                COUNT(*) AS registros,

                COALESCE(
                    SUM(
                        COALESCE(
                            QtProdutos,
                            0
                        )
                    ),
                    0
                ) AS cantidad_total,

                COALESCE(
                    SUM(
                        COALESCE(
                            VrUnitLiq,
                            0
                        )
                        *
                        COALESCE(
                            QtProdutos,
                            0
                        )
                    ),
                    0
                ) AS valor_unitario_liq,

                COALESCE(
                    SUM(
                        COALESCE(
                            VrUnitBruto,
                            0
                        )
                        *
                        COALESCE(
                            QtProdutos,
                            0
                        )
                    ),
                    0
                ) AS valor_unitario_bruto

            FROM {TABLA}

            {where_sql}
        """

        with connections[DB_ALIAS].cursor() as cursor:
            cursor.execute(
                consulta,
                parametros,
            )

            resultados = cursor_a_dicts(
                cursor
            )

        if resultados:
            metricas = resultados[0]

        else:
            metricas = {
                "registros": 0,
                "cantidad_total": 0,
                "valor_unitario_liq": 0,
                "valor_unitario_bruto": 0,
            }

        return Response({
            "metricas": metricas,
        })


# ============================================================
# OPCIONES DE FILTROS
# ============================================================

class CompraRefaccionesOpcionesView(APIView):
    authentication_classes = [
        CRMJWTAuthentication
    ]

    permission_classes = [
        IsAuthenticated
    ]

    def get(self, request):
        opciones_cache = cache.get(
            CACHE_OPCIONES
        )

        if opciones_cache:
            return Response(
                opciones_cache
            )

        placeholders_series = ", ".join(
            ["%s"] * len(SERIES_VALIDAS)
        )

        consulta_agencias = f"""
            SELECT DISTINCT
                LTRIM(
                    RTRIM(Agencia)
                ) AS agencia

            FROM {TABLA}

            WHERE Agencia IS NOT NULL

              AND LTRIM(
                    RTRIM(Agencia)
                  ) <> ''

              AND Serie IN (
                    {placeholders_series}
              )

            ORDER BY
                agencia
        """

        with connections[DB_ALIAS].cursor() as cursor:
            cursor.execute(
                consulta_agencias,
                SERIES_VALIDAS,
            )

            agencias = [
                fila[0]
                for fila in cursor.fetchall()
                if fila[0]
            ]

        opciones = {
            "agencias": agencias,
            "series": SERIES_VALIDAS,
        }

        cache.set(
            CACHE_OPCIONES,
            opciones,
            300,
        )

        return Response(
            opciones
        )