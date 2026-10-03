from datetime import timedelta

from django.core.cache import cache
from django.db import connections
from django.utils.dateparse import parse_date

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from CrmConformidad.jwt_authentication import CRMJWTAuthentication

from .serializers import OrdenFacturadaSerializer


DB_ALIAS = "sqlserver_inv"

TABLA_HEADER = "dbo.Matriz_OS_ReqHeader"
TABLA_OS = "dbo.Matriz_OS"
TABLA_ITEMS = "dbo.Matriz_OS_ReqItensLojas"
TABLA_PRODUCTOS = "dbo.Matriz_ProdutosAtivos_5vw"

CACHE_OPCIONES = "ordenes_facturadas_opciones_v1"


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
        valor = max(
            minimo,
            valor,
        )

    if maximo is not None:
        valor = min(
            maximo,
            valor,
        )

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
        dict(
            zip(
                columnas,
                fila,
            )
        )
        for fila in cursor.fetchall()
    ]


# ============================================================
# FILTROS
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

    condiciones = []
    parametros = []

    # ========================================================
    # AGENCIA
    # Solo se aplica cuando viene desde el frontend.
    # ========================================================

    if agencia:
        condiciones.append(
            "fac.Agencia = %s"
        )

        parametros.append(
            agencia
        )

    # ========================================================
    # FECHA DESDE
    # Se filtra por fecha de cierre de la OS.
    # ========================================================

    if fecha_desde:
        condiciones.append(
            "os.DtFechamento >= %s"
        )

        parametros.append(
            fecha_desde
        )

    # ========================================================
    # FECHA HASTA
    #
    # Se suma un día para hacer inclusivo el día enviado
    # desde el frontend.
    #
    # fecha_hasta=2026-09-30
    #
    # se convierte internamente en:
    #
    # os.DtFechamento < 2026-10-01
    # ========================================================

    if fecha_hasta:
        fecha_hasta_exclusiva = (
            fecha_hasta
            + timedelta(days=1)
        )

        condiciones.append(
            "os.DtFechamento < %s"
        )

        parametros.append(
            fecha_hasta_exclusiva
        )

    # ========================================================
    # BUSCADOR GENERAL
    # ========================================================

    if busqueda:
        termino = f"%{busqueda}%"

        condiciones.append(
            """
            (
                fac.Agencia LIKE %s
                OR CONVERT(VARCHAR(50), fac.NrOS) LIKE %s
                OR CONVERT(VARCHAR(50), fac.NrReq) LIKE %s
                OR ref.CodProd LIKE %s
                OR prod.NmProduto LIKE %s
                OR fac.FuncResp LIKE %s
            )
            """
        )

        parametros.extend([
            termino,
            termino,
            termino,
            termino,
            termino,
            termino,
        ])

    if not condiciones:
        return "", parametros

    where_sql = (
        "WHERE "
        + " AND ".join(condiciones)
    )

    return (
        where_sql,
        parametros,
    )


# ============================================================
# LISTADO DE ÓRDENES FACTURADAS
# ============================================================

class OrdenesFacturadasListView(APIView):
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
                fac.Agencia AS agencia,
                fac.NrOS AS nros,
                fac.NrReq AS nrreq,
                fac.DtEmissao AS dtemissao,
                fac.FuncResp AS funcresp,
                fac.QtdeItens AS qtdeitens,
                fac.QtdeAtend AS qtdeatend,

                ref.CodProd AS codprod,
                prod.NmProduto AS nmproduto,
                ref.PrecoUnit AS precounit,
                ref.PercDesc AS percdesc,
                ref.VrDesc AS vrdesc,
                ref.VrProd AS vrprod,

                os.VrAdicionais AS vradicionais,
                os.VrDescPeca AS vrdescpeca,
                os.VrTotalPecas AS vrtotalpecas,
                os.TpOS AS tpos,
                os.DtFechamento AS dtfechamento,
                os.DtAbertura AS dtabertura,
                os.Situacao AS situacao,
                os.CodCondPgto AS codcondpgto,
                os.CodOperFiscal AS codoperfiscal,
                os.SitGarantia AS sitgarantia,
                os.SubtipoOS AS subtipoos,

                COUNT(*) OVER ()
                    AS total_registros,

                COALESCE(
                    SUM(
                        COALESCE(
                            ref.VrProd,
                            0
                        )
                    ) OVER (),
                    0
                ) AS valor_productos

            FROM {TABLA_HEADER} fac

            INNER JOIN {TABLA_OS} os
                ON os.Agencia = fac.Agencia
                AND os.NrOS = fac.NrOS
                AND os.NrAtendimento = fac.NrAtendim

            INNER JOIN {TABLA_ITEMS} ref
                ON ref.Agencia = fac.Agencia
                AND ref.NrOS = fac.NrOS
                AND ref.NrReq = fac.NrReq

            INNER JOIN {TABLA_PRODUCTOS} prod
                ON ref.CodProd = prod.CodProduto
                AND ref.Agencia = prod.Agencia

            {where_sql}

            ORDER BY
                fac.Agencia,
                fac.NrOS DESC,
                fac.NrReq DESC,
                ref.CodProd

            OFFSET %s ROWS

            FETCH NEXT %s ROWS ONLY
        """

        parametros_consulta = [
            *parametros,
            offset,
            tamano_pagina,
        ]

        with connections[
            DB_ALIAS
        ].cursor() as cursor:
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
                "registros": total_registros,
                "valor_productos": float(
                    primero.get(
                        "valor_productos",
                        0,
                    )
                    or 0
                ),
            }

        else:
            total_registros = 0

            metricas = {
                "registros": 0,
                "valor_productos": 0,
            }

        # Quitamos los campos auxiliares utilizados
        # únicamente para paginación/métricas.
        for registro in registros:
            registro.pop(
                "total_registros",
                None,
            )

            registro.pop(
                "valor_productos",
                None,
            )

        serializer = OrdenFacturadaSerializer(
            registros,
            many=True,
        )

        return Response(
            {
                "count": total_registros,
                "page": pagina,
                "page_size": tamano_pagina,
                "metricas": metricas,
                "results": serializer.data,
            }
        )


# ============================================================
# OPCIONES PARA FILTROS
# ============================================================

class OrdenesFacturadasOpcionesView(APIView):
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
                fac.Agencia

            FROM {TABLA_HEADER} fac

            INNER JOIN {TABLA_OS} os
                ON os.Agencia = fac.Agencia
                AND os.NrOS = fac.NrOS
                AND os.NrAtendimento = fac.NrAtendim

            WHERE
                fac.Agencia IS NOT NULL

                AND LTRIM(
                    RTRIM(
                        fac.Agencia
                    )
                ) <> ''

            ORDER BY
                fac.Agencia
        """

        with connections[
            DB_ALIAS
        ].cursor() as cursor:
            cursor.execute(
                consulta
            )

            agencias = [
                fila[0]
                for fila in cursor.fetchall()
                if fila[0]
            ]

        resultado = {
            "agencias": agencias,
        }

        cache.set(
            CACHE_OPCIONES,
            resultado,
            3600,
        )

        return Response(
            resultado
        )