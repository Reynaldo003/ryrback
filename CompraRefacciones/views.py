from django.core.cache import cache
from django.db import connections
from django.utils.dateparse import parse_date
from datetime import datetime, timedelta
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
    'F', 
    'PR', 
    'TX', 
    'EA'
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

    condiciones = [
        """
        Serie IN (
            'P',
            'AP',
            'VWM',
            'AAP40',
            'AN',
            'F', 
            'PR', 
            'TX', 
            'EA'
        )
        """
    ]

    parametros = []

    # =========================================================
    # AGENCIA
    # Solo se aplica si el frontend la envía.
    # =========================================================

    if agencia:
        condiciones.append(
            "Agencia = %s"
        )

        parametros.append(
            agencia
        )

    # =========================================================
    # FECHA DESDE
    # =========================================================

    if fecha_desde:
        condiciones.append(
            "DtEmissao >= %s"
        )

        parametros.append(
            fecha_desde
        )

    # =========================================================
    # FECHA HASTA
    #
    # Utilizamos el día siguiente con <
    # para incluir correctamente todo el último día si
    # DtEmissao contiene hora.
    #
    # Ejemplo:
    #
    # fecha_hasta = 2026-08-31
    #
    # SQL:
    # DtEmissao < 2026-09-01
    # =========================================================

    if fecha_hasta:
        fecha_hasta_date = datetime.strptime(
            fecha_hasta,
            "%Y-%m-%d",
        ).date()

        siguiente_dia = (
            fecha_hasta_date
            + timedelta(days=1)
        )

        condiciones.append(
            "DtEmissao < %s"
        )

        parametros.append(
            siguiente_dia.strftime(
                "%Y-%m-%d"
            )
        )

    # =========================================================
    # BUSCADOR
    # =========================================================

    if busqueda:
        termino = f"%{busqueda}%"

        condiciones.append("""
            (
                Agencia LIKE %s

                OR CONVERT(
                    VARCHAR(50),
                    NrNota
                ) LIKE %s

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
        ])

    where_sql = (
        "WHERE "
        + " AND ".join(
            condiciones
        )
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
        # =====================================================
        # PAGINACIÓN
        # =====================================================

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

        # =====================================================
        # FILTROS
        # =====================================================

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

        # =====================================================
        # CONSULTA
        #
        # Las métricas se calculan con funciones de ventana.
        #
        # Esto evita hacer una segunda consulta para obtener:
        #
        # - registros
        # - cantidad total
        # - valor líquido
        # - valor bruto
        # =====================================================

        consulta = f"""
            SELECT
                rowid__,

                Agencia AS agencia,

                NrNota AS nrnota,

                Serie AS serie,

                QtProdutos AS qtprodutos,

                Unidade AS unidade,

                ProdServ AS prodserv,

                DescrProd AS descrprod,

                VrUnitLiq AS vrunitliq,

                NULLIF(
                    LEFT(
                        LTRIM(
                            RTRIM(DtEntrada)
                        ),
                        10
                    ),
                    ''
                ) AS dtentrada,

                NULLIF(
                    LEFT(
                        LTRIM(
                            RTRIM(DtEmissao)
                        ),
                        10
                    ),
                    ''
                ) AS dtemissao,

                VrUnitBruto AS vrunitbruto,

                COUNT(*) OVER ()
                    AS total_registros,

                COALESCE(
                    SUM(
                        COALESCE(
                            QtProdutos,
                            0
                        )
                    ) OVER (),
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
                    ) OVER (),
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
                    ) OVER (),
                    0
                ) AS valor_unitario_bruto

            FROM {TABLA}

            {where_sql}

            ORDER BY
                DtEmissao DESC,
                NrNota DESC,
                rowid__ DESC

            OFFSET %s ROWS

            FETCH NEXT %s ROWS ONLY
        """

        with connections[DB_ALIAS].cursor() as cursor:
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

        # =====================================================
        # MÉTRICAS
        #
        # Las columnas calculadas vienen repetidas en cada fila,
        # porque son funciones OVER().
        #
        # Tomamos únicamente la primera fila.
        # =====================================================

        if registros:
            primer_registro = registros[0]

            total = int(
                primer_registro.get(
                    "total_registros",
                    0,
                )
                or 0
            )

            metricas = {
                "registros": total,

                "cantidad_total": primer_registro.get(
                    "cantidad_total",
                    0,
                )
                or 0,

                "valor_unitario_liq": primer_registro.get(
                    "valor_unitario_liq",
                    0,
                )
                or 0,

                "valor_unitario_bruto": primer_registro.get(
                    "valor_unitario_bruto",
                    0,
                )
                or 0,
            }

        else:
            total = 0

            metricas = {
                "registros": 0,
                "cantidad_total": 0,
                "valor_unitario_liq": 0,
                "valor_unitario_bruto": 0,
            }

        # =====================================================
        # QUITAR CAMPOS INTERNOS
        #
        # No necesitamos enviar las métricas repetidas dentro
        # de cada registro.
        # =====================================================

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
                "valor_unitario_liq",
                None,
            )

            registro.pop(
                "valor_unitario_bruto",
                None,
            )

        serializer = CompraRefaccionesSerializer(
            registros,
            many=True,
        )

        return Response({
            "count": total,
            "page": pagina,
            "page_size": tamano_pagina,

            "metricas": metricas,

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

        consulta = f"""
            SELECT DISTINCT
                CONVERT(
                    VARCHAR(255),
                    Agencia
                ) AS agencia

            FROM {TABLA}

            WHERE Agencia IS NOT NULL

              AND LTRIM(
                    RTRIM(Agencia)
                  ) <> ''

              AND Serie IN (
                    'P',
                    'AP',
                    'VWM',
                    'AAP40',
                    'AN',
                    'F', 
                    'PR', 
                    'TX', 
                    'EA'
              )
              OR (Serie = 'IN' AND Proveedor = 'AUTOMOTRIZ R&R')

            ORDER BY
                agencia
        """

        with connections[DB_ALIAS].cursor() as cursor:
            cursor.execute(
                consulta
            )

            agencias = [
                fila[0]
                for fila in cursor.fetchall()
                if fila[0]
            ]

        opciones = {
            "agencias": agencias,
        }

        cache.set(
            CACHE_OPCIONES,
            opciones,
            3600,
        )

        return Response(
            opciones
        )