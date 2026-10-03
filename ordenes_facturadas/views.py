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
    OrdenFacturadaResumenSerializer,
    OrdenFacturadaDetalleSerializer,
)


DB_ALIAS = "sqlserver_inv"

TABLA_HEADER = "dbo.Matriz_OS_ReqHeader"
TABLA_OS = "dbo.Matriz_OS"
TABLA_ITEMS = "dbo.Matriz_OS_ReqItensLojas"
TABLA_PRODUCTOS = "dbo.Matriz_ProdutosAtivos_5vw"

CACHE_OPCIONES = "ordenes_facturadas_opciones_v3"


# ============================================================
# HELPERS
# ============================================================


def texto_parametro(request, nombre):
    return str(
        request.query_params.get(
            nombre,
            "",
        )
        or ""
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


def validar_fecha(
    valor,
    nombre,
):
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


def valores_parametro(
    request,
    nombre,
):
    """
    Acepta:

    tp_os=CP

    o:

    tp_os__in=CP,GW,REV
    """

    valor_multiple = texto_parametro(
        request,
        f"{nombre}__in",
    )

    if valor_multiple:
        return [
            valor.strip()
            for valor in valor_multiple.split(",")
            if valor.strip()
        ]

    valor_simple = texto_parametro(
        request,
        nombre,
    )

    if valor_simple:
        return [valor_simple]

    return []


def valores_enteros_parametro(
    request,
    nombre,
):
    valores = valores_parametro(
        request,
        nombre,
    )

    resultado = []

    for valor in valores:
        try:
            resultado.append(
                int(valor)
            )
        except (TypeError, ValueError):
            raise ValueError(
                f"El parámetro '{nombre}' debe contener valores numéricos."
            )

    return resultado


def agregar_filtro_in(
    condiciones,
    parametros,
    columna,
    valores,
):
    if not valores:
        return

    placeholders = ", ".join(
        ["%s"] * len(valores)
    )

    condiciones.append(
        f"{columna} IN ({placeholders})"
    )

    parametros.extend(
        valores
    )


# ============================================================
# FILTROS
# ============================================================


def construir_filtros(request):
    condiciones = []
    parametros = []

    # --------------------------------------------------------
    # AGENCIA
    # --------------------------------------------------------

    agencias = valores_parametro(
        request,
        "agencia",
    )

    agregar_filtro_in(
        condiciones,
        parametros,
        "os.Agencia",
        agencias,
    )

    # --------------------------------------------------------
    # FECHAS DE CIERRE
    # --------------------------------------------------------

    fecha_desde = validar_fecha(
        texto_parametro(
            request,
            "fecha_desde",
        ),
        "fecha_desde",
    )

    fecha_hasta = validar_fecha(
        texto_parametro(
            request,
            "fecha_hasta",
        ),
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

    if fecha_desde:
        condiciones.append(
            "os.DtFechamento >= %s"
        )
        parametros.append(
            fecha_desde
        )

    if fecha_hasta:
        condiciones.append(
            "os.DtFechamento < %s"
        )
        parametros.append(
            fecha_hasta
            + timedelta(days=1)
        )

    # --------------------------------------------------------
    # TIPO OS
    # --------------------------------------------------------

    agregar_filtro_in(
        condiciones,
        parametros,
        "os.TpOS",
        valores_parametro(
            request,
            "tp_os",
        ),
    )

    # --------------------------------------------------------
    # SITUACIÓN
    # --------------------------------------------------------

    agregar_filtro_in(
        condiciones,
        parametros,
        "os.Situacao",
        valores_parametro(
            request,
            "situacao",
        ),
    )

    # --------------------------------------------------------
    # SUBTIPO
    # --------------------------------------------------------

    agregar_filtro_in(
        condiciones,
        parametros,
        "os.SubtipoOS",
        valores_parametro(
            request,
            "subtipo_os",
        ),
    )

    # --------------------------------------------------------
    # GARANTÍA
    # --------------------------------------------------------

    agregar_filtro_in(
        condiciones,
        parametros,
        "os.SitGarantia",
        valores_parametro(
            request,
            "sit_garantia",
        ),
    )

    # --------------------------------------------------------
    # CONDICIÓN DE PAGO
    # --------------------------------------------------------

    agregar_filtro_in(
        condiciones,
        parametros,
        "os.CodCondPgto",
        valores_enteros_parametro(
            request,
            "cod_cond_pgto",
        ),
    )

    # --------------------------------------------------------
    # OPERACIÓN FISCAL
    # --------------------------------------------------------

    agregar_filtro_in(
        condiciones,
        parametros,
        "os.CodOperFiscal",
        valores_enteros_parametro(
            request,
            "cod_oper_fiscal",
        ),
    )

    # --------------------------------------------------------
    # RESPONSABLE
    #
    # Está en ReqHeader, por eso usamos EXISTS para no afectar
    # la agregación de todas las partidas de la OS.
    # --------------------------------------------------------

    funcionarios = valores_enteros_parametro(
        request,
        "func_resp",
    )

    if funcionarios:
        placeholders = ", ".join(
            ["%s"]
            * len(funcionarios)
        )

        condiciones.append(
            f"""
            EXISTS (
                SELECT
                    1

                FROM {TABLA_HEADER} fac_func

                INNER JOIN {TABLA_ITEMS} ref_func
                    ON ref_func.Agencia = fac_func.Agencia
                    AND ref_func.NrOS = fac_func.NrOS
                    AND ref_func.NrReq = fac_func.NrReq

                WHERE
                    fac_func.Agencia = os.Agencia
                    AND fac_func.NrOS = os.NrOS
                    AND fac_func.NrAtendim = os.NrAtendimento
                    AND fac_func.FuncResp IN ({placeholders})
            )
            """
        )

        parametros.extend(
            funcionarios
        )

    # --------------------------------------------------------
    # BÚSQUEDA GLOBAL
    #
    # Puede encontrar:
    # - agencia
    # - OS
    # - atención
    # - tipo
    # - situación
    # - subtipo
    # - requisición
    # - funcionario
    # - código producto
    # - nombre producto
    # --------------------------------------------------------

    busqueda = texto_parametro(
        request,
        "q",
    )

    if busqueda:
        patron = f"%{busqueda}%"

        condiciones.append(
            f"""
            (
                CAST(os.NrOS AS varchar(50)) LIKE %s

                OR CAST(
                    os.NrAtendimento AS varchar(50)
                ) LIKE %s

                OR os.Agencia LIKE %s

                OR os.TpOS LIKE %s

                OR os.Situacao LIKE %s

                OR os.SubtipoOS LIKE %s

                OR EXISTS (
                    SELECT
                        1

                    FROM {TABLA_HEADER} fac_q

                    INNER JOIN {TABLA_ITEMS} ref_q
                        ON ref_q.Agencia = fac_q.Agencia
                        AND ref_q.NrOS = fac_q.NrOS
                        AND ref_q.NrReq = fac_q.NrReq

                    WHERE
                        fac_q.Agencia = os.Agencia
                        AND fac_q.NrOS = os.NrOS
                        AND fac_q.NrAtendim = os.NrAtendimento

                        AND (
                            CAST(
                                fac_q.NrReq AS varchar(50)
                            ) LIKE %s

                            OR CAST(
                                fac_q.FuncResp AS varchar(50)
                            ) LIKE %s

                            OR ref_q.CodProd LIKE %s

                            OR EXISTS (
                                SELECT
                                    1

                                FROM {TABLA_PRODUCTOS} prod_q

                                WHERE
                                    prod_q.Agencia = ref_q.Agencia
                                    AND prod_q.CodProduto = ref_q.CodProd
                                    AND prod_q.NmProduto LIKE %s
                            )
                        )
                )
            )
            """
        )

        parametros.extend(
            [patron] * 10
        )

    # --------------------------------------------------------
    # SOLO OS QUE TIENEN PARTIDAS
    # --------------------------------------------------------

    condiciones.append(
        f"""
        EXISTS (
            SELECT
                1

            FROM {TABLA_HEADER} fac_exist

            INNER JOIN {TABLA_ITEMS} ref_exist
                ON ref_exist.Agencia = fac_exist.Agencia
                AND ref_exist.NrOS = fac_exist.NrOS
                AND ref_exist.NrReq = fac_exist.NrReq

            WHERE
                fac_exist.Agencia = os.Agencia
                AND fac_exist.NrOS = os.NrOS
                AND fac_exist.NrAtendim = os.NrAtendimento
        )
        """
    )

    where_sql = (
        " AND ".join(
            condiciones
        )
        if condiciones
        else "1 = 1"
    )

    return (
        where_sql,
        parametros,
    )


# ============================================================
# SQL BASE: UNA FILA POR OS
# ============================================================


def sql_ordenes_agrupadas(
    where_sql,
    destino=None,
):
    into_sql = (
        f"INTO {destino}"
        if destino
        else ""
    )

    return f"""
        SELECT
            os.Agencia AS agencia,
            os.NrOS AS nros,
            os.NrAtendimento AS nratendimento,

            MAX(os.TpOS)
                AS tpos,

            MAX(os.SubtipoOS)
                AS subtipoos,

            MAX(os.Situacao)
                AS situacao,

            MAX(os.DtAbertura)
                AS dtabertura,

            MAX(os.DtFechamento)
                AS dtfechamento,

            MAX(os.SitGarantia)
                AS sitgarantia,

            MAX(os.CodCondPgto)
                AS codcondpgto,

            MAX(os.CodOperFiscal)
                AS codoperfiscal,

            COALESCE(
                MAX(os.VrAdicionais),
                0
            ) AS vradicionais,

            COALESCE(
                MAX(os.VrDescPeca),
                0
            ) AS vrdescpeca,

            COALESCE(
                MAX(os.VrTotalPecas),
                0
            ) AS vrtotalpecas,

            COALESCE(
                MAX(os.TtMo),
                0
            ) AS ttmo,

            COUNT(
                DISTINCT fac.NrReq
            ) AS requisiciones,

            COUNT(*)
                AS partidas,

            COALESCE(
                SUM(
                    COALESCE(
                        ref.VrProd,
                        0
                    )
                ),
                0
            ) AS valor_productos,

            COALESCE(
                SUM(
                    COALESCE(
                        ref.VrDesc,
                        0
                    )
                ),
                0
            ) AS descuentos

        {into_sql}

        FROM {TABLA_OS} os

        INNER JOIN {TABLA_HEADER} fac
            ON fac.Agencia = os.Agencia
            AND fac.NrOS = os.NrOS
            AND fac.NrAtendim = os.NrAtendimento

        INNER JOIN {TABLA_ITEMS} ref
            ON ref.Agencia = fac.Agencia
            AND ref.NrOS = fac.NrOS
            AND ref.NrReq = fac.NrReq

        WHERE
            {where_sql}

        GROUP BY
            os.Agencia,
            os.NrOS,
            os.NrAtendimento
    """

# ============================================================
# ORDERING
# ============================================================


ORDERING_MAP = {
    "agencia": "agencia",
    "nros": "nros",
    "nratendimento": "nratendimento",
    "tpos": "tpos",
    "subtipoos": "subtipoos",
    "situacao": "situacao",
    "dtabertura": "dtabertura",
    "dtfechamento": "dtfechamento",
    "sitgarantia": "sitgarantia",
    "codcondpgto": "codcondpgto",
    "codoperfiscal": "codoperfiscal",
    "vradicionais": "vradicionais",
    "vrdescpeca": "vrdescpeca",
    "vrtotalpecas": "vrtotalpecas",
    "ttmo": "ttmo",
    "requisiciones": "requisiciones",
    "partidas": "partidas",
    "valor_productos": "valor_productos",
    "descuentos": "descuentos",
}


def construir_ordering(request):
    valor = texto_parametro(
        request,
        "ordering",
    )

    if not valor:
        valor = "-dtfechamento"

    descendente = valor.startswith(
        "-"
    )

    campo = (
        valor[1:]
        if descendente
        else valor
    )

    columna = ORDERING_MAP.get(
        campo,
        "dtfechamento",
    )

    direccion = (
        "DESC"
        if descendente
        else "ASC"
    )

    return (
        f"{columna} {direccion}, "
        "agencia ASC, "
        "nros DESC, "
        "nratendimento DESC"
    )


# ============================================================
# LISTADO PAGINADO
# ============================================================

class OrdenesFacturadasListView(APIView):
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
                    "detail": str(exc)
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        page = entero_parametro(
            request,
            "page",
            1,
            minimo=1,
        )

        page_size = entero_parametro(
            request,
            "page_size",
            100,
            minimo=1,
            maximo=500,
        )

        offset = (
            page - 1
        ) * page_size

        ordering_sql = construir_ordering(
            request
        )

        sql_base = sql_ordenes_agrupadas(
            where_sql
        )

        consulta = f"""
            ;WITH Ordenes AS (
                {sql_base}
            )

            SELECT
                agencia,
                nros,
                nratendimento,
                tpos,
                subtipoos,
                situacao,
                dtabertura,
                dtfechamento,
                sitgarantia,
                codcondpgto,
                codoperfiscal,
                vradicionais,
                vrdescpeca,
                vrtotalpecas,
                ttmo,
                requisiciones,
                partidas,
                valor_productos,
                descuentos,

                COUNT(*) OVER()
                    AS total_registros

            FROM Ordenes

            ORDER BY
                {ordering_sql}

            OFFSET %s ROWS
            FETCH NEXT %s ROWS ONLY;
        """

        parametros_consulta = [
            *parametros,
            offset,
            page_size,
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

        if registros:
            total = int(
                registros[0].get(
                    "total_registros",
                    0,
                )
                or 0
            )
        else:
            total = 0

        for registro in registros:
            registro.pop(
                "total_registros",
                None,
            )

        serializer = OrdenFacturadaResumenSerializer(
            registros,
            many=True,
        )

        return Response(
            {
                "count": total,
                "page": page,
                "page_size": page_size,
                "results": serializer.data,
            }
        )
    
# ============================================================
# DETALLE DE UNA OS
# ============================================================


class OrdenFacturadaDetalleView(APIView):
    authentication_classes = [
        CRMJWTAuthentication
    ]

    permission_classes = [
        IsAuthenticated
    ]

    def get(self, request):
        agencia = texto_parametro(
            request,
            "agencia",
        )

        nros_texto = texto_parametro(
            request,
            "nros",
        )

        nratendimento_texto = texto_parametro(
            request,
            "nratendimento",
        )

        if not agencia:
            return Response(
                {
                    "detail":
                        "El parámetro 'agencia' es obligatorio."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not nros_texto:
            return Response(
                {
                    "detail":
                        "El parámetro 'nros' es obligatorio."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not nratendimento_texto:
            return Response(
                {
                    "detail":
                        "El parámetro 'nratendimento' es obligatorio."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            nros = int(
                nros_texto
            )

            nratendimento = int(
                nratendimento_texto
            )

        except (TypeError, ValueError):
            return Response(
                {
                    "detail":
                        "'nros' y 'nratendimento' deben ser numéricos."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        consulta = f"""
            SELECT
                fac.Agencia
                    AS agencia,

                fac.NrOS
                    AS nros,

                fac.NrAtendim
                    AS nratendimento,

                fac.NrReq
                    AS nrreq,

                fac.DtEmissao
                    AS dtemissao,

                fac.FuncResp
                    AS funcresp,

                fac.QtdeItens
                    AS qtdeitens,

                fac.QtdeAtend
                    AS qtdeatend,

                ref.CodProd
                    AS codprod,

                prod.NmProduto
                    AS nmproduto,

                ref.PrecoUnit
                    AS precounit,

                ref.PercDesc
                    AS percdesc,

                ref.VrDesc
                    AS vrdesc,

                ref.VrProd
                    AS vrprod

            FROM {TABLA_HEADER} fac

            INNER JOIN {TABLA_ITEMS} ref
                ON ref.Agencia = fac.Agencia
                AND ref.NrOS = fac.NrOS
                AND ref.NrReq = fac.NrReq

            OUTER APPLY (
                SELECT TOP 1
                    p.NmProduto

                FROM {TABLA_PRODUCTOS} p

                WHERE
                    p.Agencia = ref.Agencia
                    AND p.CodProduto = ref.CodProd

                ORDER BY
                    p.NmProduto
            ) prod

            WHERE
                fac.Agencia = %s
                AND fac.NrOS = %s
                AND fac.NrAtendim = %s

            ORDER BY
                fac.NrReq ASC,
                ref.CodProd ASC
        """

        with connections[
            DB_ALIAS
        ].cursor() as cursor:

            cursor.execute(
                consulta,
                [
                    agencia,
                    nros,
                    nratendimento,
                ],
            )

            registros = cursor_a_dicts(
                cursor
            )

        requisiciones = {
            registro.get(
                "nrreq"
            )
            for registro in registros
            if registro.get(
                "nrreq"
            )
            is not None
        }

        resumen = {
            "requisiciones":
                len(
                    requisiciones
                ),

            "partidas":
                len(
                    registros
                ),

            "valor_productos":
                sum(
                    float(
                        registro.get(
                            "vrprod"
                        )
                        or 0
                    )
                    for registro
                    in registros
                ),

            "descuentos":
                sum(
                    float(
                        registro.get(
                            "vrdesc"
                        )
                        or 0
                    )
                    for registro
                    in registros
                ),
        }

        serializer = (
            OrdenFacturadaDetalleSerializer(
                registros,
                many=True,
            )
        )

        return Response(
            {
                "orden": {
                    "agencia":
                        agencia,

                    "nros":
                        nros,

                    "nratendimento":
                        nratendimento,
                },

                "resumen":
                    resumen,

                "results":
                    serializer.data,
            }
        )


# ============================================================
# DASHBOARD
# ============================================================


class OrdenesFacturadasDashboardView(APIView):
    authentication_classes = [
        CRMJWTAuthentication
    ]

    permission_classes = [
        IsAuthenticated
    ]

    def get(self, request):
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
                    "detail":
                        str(exc)
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with connections[
            DB_ALIAS
        ].cursor() as cursor:

            try:
                # Por si la misma conexión del pool conserva
                # una tabla temporal de una ejecución anterior.
                cursor.execute(
                    """
                    IF OBJECT_ID(
                        'tempdb..#ordenes_dashboard'
                    ) IS NOT NULL

                    DROP TABLE
                        #ordenes_dashboard;
                    """
                )

                consulta_base = (
                    sql_ordenes_agrupadas(
                        where_sql,
                        "#ordenes_dashboard",
                    )
                )

                cursor.execute(
                    consulta_base,
                    parametros,
                )

                # ====================================================
                # TOTALES
                # ====================================================

                cursor.execute(
                    """
                    SELECT
                        COUNT(*)
                            AS ordenes,

                        COALESCE(
                            SUM(requisiciones),
                            0
                        ) AS requisiciones,

                        COALESCE(
                            SUM(partidas),
                            0
                        ) AS partidas,

                        COALESCE(
                            SUM(valor_productos),
                            0
                        ) AS valor_productos,

                        COALESCE(
                            SUM(descuentos),
                            0
                        ) AS descuentos,

                        COALESCE(
                            SUM(ttmo),
                            0
                        ) AS mano_obra,

                        COALESCE(
                            SUM(
                                valor_productos
                                + ttmo
                            ),
                            0
                        ) AS refacciones_mano_obra

                    FROM
                        #ordenes_dashboard
                    """
                )

                filas = cursor_a_dicts(
                    cursor
                )

                totales = (
                    filas[0]
                    if filas
                    else {}
                )

                # ====================================================
                # POR AGENCIA
                # ====================================================

                cursor.execute(
                    """
                    SELECT
                        agencia,

                        COUNT(*)
                            AS ordenes,

                        SUM(requisiciones)
                            AS requisiciones,

                        SUM(partidas)
                            AS partidas,

                        SUM(valor_productos)
                            AS valor_productos,

                        SUM(ttmo)
                            AS mano_obra,

                        SUM(
                            valor_productos
                            + ttmo
                        ) AS total

                    FROM
                        #ordenes_dashboard

                    GROUP BY
                        agencia

                    ORDER BY
                        total DESC
                    """
                )

                por_agencia = cursor_a_dicts(
                    cursor
                )

                # ====================================================
                # TIPO OS
                # ====================================================

                cursor.execute(
                    """
                    SELECT
                        COALESCE(
                            NULLIF(
                                LTRIM(
                                    RTRIM(tpos)
                                ),
                                ''
                            ),
                            'Sin tipo'
                        ) AS tipo,

                        COUNT(*)
                            AS ordenes,

                        SUM(valor_productos)
                            AS valor_productos,

                        SUM(ttmo)
                            AS mano_obra

                    FROM
                        #ordenes_dashboard

                    GROUP BY
                        COALESCE(
                            NULLIF(
                                LTRIM(
                                    RTRIM(tpos)
                                ),
                                ''
                            ),
                            'Sin tipo'
                        )

                    ORDER BY
                        ordenes DESC
                    """
                )

                por_tipo_os = cursor_a_dicts(
                    cursor
                )

                # ====================================================
                # SITUACIÓN
                # ====================================================

                cursor.execute(
                    """
                    SELECT
                        COALESCE(
                            NULLIF(
                                LTRIM(
                                    RTRIM(situacao)
                                ),
                                ''
                            ),
                            'Sin situación'
                        ) AS situacion,

                        COUNT(*)
                            AS ordenes,

                        SUM(valor_productos)
                            AS valor_productos,

                        SUM(ttmo)
                            AS mano_obra

                    FROM
                        #ordenes_dashboard

                    GROUP BY
                        COALESCE(
                            NULLIF(
                                LTRIM(
                                    RTRIM(situacao)
                                ),
                                ''
                            ),
                            'Sin situación'
                        )

                    ORDER BY
                        ordenes DESC
                    """
                )

                por_situacion = cursor_a_dicts(
                    cursor
                )

                # ====================================================
                # POR DÍA DE CIERRE
                # ====================================================

                cursor.execute(
                    """
                    SELECT
                        dtfechamento
                            AS fecha,

                        COUNT(*)
                            AS ordenes,

                        SUM(valor_productos)
                            AS valor_productos,

                        SUM(ttmo)
                            AS mano_obra,

                        SUM(
                            valor_productos
                            + ttmo
                        ) AS total

                    FROM
                        #ordenes_dashboard

                    WHERE
                        dtfechamento IS NOT NULL

                    GROUP BY
                        dtfechamento

                    ORDER BY
                        dtfechamento ASC
                    """
                )

                por_dia = cursor_a_dicts(
                    cursor
                )

                # ====================================================
                # GARANTÍA
                # ====================================================

                cursor.execute(
                    """
                    SELECT
                        COALESCE(
                            NULLIF(
                                LTRIM(
                                    RTRIM(sitgarantia)
                                ),
                                ''
                            ),
                            'Sin dato'
                        ) AS garantia,

                        COUNT(*)
                            AS ordenes,

                        SUM(valor_productos)
                            AS valor_productos,

                        SUM(ttmo)
                            AS mano_obra

                    FROM
                        #ordenes_dashboard

                    GROUP BY
                        COALESCE(
                            NULLIF(
                                LTRIM(
                                    RTRIM(sitgarantia)
                                ),
                                ''
                            ),
                            'Sin dato'
                        )

                    ORDER BY
                        ordenes DESC
                    """
                )

                por_garantia = cursor_a_dicts(
                    cursor
                )

                # ====================================================
                # TOP PRODUCTOS
                #
                # Se parte de las OS ya filtradas.
                # ====================================================

                cursor.execute(
                    f"""
                    SELECT TOP 15
                        ref.CodProd
                            AS codprod,

                        MAX(
                            prod.NmProduto
                        ) AS nmproduto,

                        COUNT(*)
                            AS partidas,

                        COALESCE(
                            SUM(
                                ref.VrProd
                            ),
                            0
                        ) AS importe

                    FROM
                        #ordenes_dashboard od

                    INNER JOIN {TABLA_HEADER} fac
                        ON fac.Agencia = od.agencia
                        AND fac.NrOS = od.nros
                        AND fac.NrAtendim = od.nratendimento

                    INNER JOIN {TABLA_ITEMS} ref
                        ON ref.Agencia = fac.Agencia
                        AND ref.NrOS = fac.NrOS
                        AND ref.NrReq = fac.NrReq

                    OUTER APPLY (
                        SELECT TOP 1
                            p.NmProduto

                        FROM {TABLA_PRODUCTOS} p

                        WHERE
                            p.Agencia = ref.Agencia
                            AND p.CodProduto = ref.CodProd

                        ORDER BY
                            p.NmProduto
                    ) prod

                    GROUP BY
                        ref.CodProd

                    ORDER BY
                        importe DESC
                    """
                )

                top_productos = cursor_a_dicts(
                    cursor
                )

            finally:
                try:
                    cursor.execute(
                        """
                        IF OBJECT_ID(
                            'tempdb..#ordenes_dashboard'
                        ) IS NOT NULL

                        DROP TABLE
                            #ordenes_dashboard;
                        """
                    )
                except Exception:
                    pass

        return Response(
            {
                "totales":
                    totales,

                "graficas": {
                    "por_agencia":
                        por_agencia,

                    "por_tipo_os":
                        por_tipo_os,

                    "por_situacion":
                        por_situacion,

                    "por_dia":
                        por_dia,

                    "por_garantia":
                        por_garantia,

                    "top_productos":
                        top_productos,
                },
            }
        )


# ============================================================
# OPCIONES
# ============================================================


class OrdenesFacturadasOpcionesView(APIView):
    authentication_classes = [
        CRMJWTAuthentication
    ]

    permission_classes = [
        IsAuthenticated
    ]

    def get(self, request):
        resultado_cache = cache.get(
            CACHE_OPCIONES
        )

        if resultado_cache:
            return Response(
                resultado_cache
            )

        where_con_partidas = f"""
            EXISTS (
                SELECT
                    1

                FROM {TABLA_HEADER} fac_op

                INNER JOIN {TABLA_ITEMS} ref_op
                    ON ref_op.Agencia = fac_op.Agencia
                    AND ref_op.NrOS = fac_op.NrOS
                    AND ref_op.NrReq = fac_op.NrReq

                WHERE
                    fac_op.Agencia = os.Agencia
                    AND fac_op.NrOS = os.NrOS
                    AND fac_op.NrAtendim = os.NrAtendimento
            )
        """

        with connections[
            DB_ALIAS
        ].cursor() as cursor:

            def obtener_distintos(
                columna,
            ):
                cursor.execute(
                    f"""
                    SELECT DISTINCT
                        {columna}

                    FROM {TABLA_OS} os

                    WHERE
                        {where_con_partidas}

                        AND {columna} IS NOT NULL

                        AND LTRIM(
                            RTRIM(
                                CAST(
                                    {columna}
                                    AS varchar(255)
                                )
                            )
                        ) <> ''

                    ORDER BY
                        {columna}
                    """
                )

                return [
                    fila[0]
                    for fila
                    in cursor.fetchall()
                    if fila[0]
                    is not None
                ]

            agencias = obtener_distintos(
                "os.Agencia"
            )

            tpos = obtener_distintos(
                "os.TpOS"
            )

            situaciones = obtener_distintos(
                "os.Situacao"
            )

            subtipos = obtener_distintos(
                "os.SubtipoOS"
            )

            garantias = obtener_distintos(
                "os.SitGarantia"
            )

            condiciones_pago = obtener_distintos(
                "os.CodCondPgto"
            )

            operaciones_fiscales = obtener_distintos(
                "os.CodOperFiscal"
            )

            cursor.execute(
                f"""
                SELECT DISTINCT
                    fac.FuncResp

                FROM {TABLA_HEADER} fac

                INNER JOIN {TABLA_ITEMS} ref
                    ON ref.Agencia = fac.Agencia
                    AND ref.NrOS = fac.NrOS
                    AND ref.NrReq = fac.NrReq

                INNER JOIN {TABLA_OS} os
                    ON os.Agencia = fac.Agencia
                    AND os.NrOS = fac.NrOS
                    AND os.NrAtendimento = fac.NrAtendim

                WHERE
                    fac.FuncResp IS NOT NULL

                ORDER BY
                    fac.FuncResp
                """
            )

            funcionarios = [
                fila[0]
                for fila
                in cursor.fetchall()
                if fila[0]
                is not None
            ]

            cursor.execute(
                f"""
                SELECT
                    MIN(os.DtFechamento)
                        AS minima,

                    MAX(os.DtFechamento)
                        AS maxima

                FROM {TABLA_OS} os

                WHERE
                    {where_con_partidas}
                """
            )

            fila_fecha = cursor.fetchone()

            minima = (
                fila_fecha[0]
                if fila_fecha
                else None
            )

            maxima = (
                fila_fecha[1]
                if fila_fecha
                else None
            )

        resultado = {
            "agencias":
                agencias,

            "tpos":
                tpos,

            "situaciones":
                situaciones,

            "subtipos":
                subtipos,

            "garantias":
                garantias,

            "condiciones_pago":
                condiciones_pago,

            "operaciones_fiscales":
                operaciones_fiscales,

            "funcionarios":
                funcionarios,

            "fechas": {
                "minima":
                    (
                        minima.isoformat()
                        if minima
                        else None
                    ),

                "maxima":
                    (
                        maxima.isoformat()
                        if maxima
                        else None
                    ),
            },
        }

        cache.set(
            CACHE_OPCIONES,
            resultado,
            1800,
        )

        return Response(
            resultado
        )