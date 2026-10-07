from datetime import date, timedelta

from django.core.cache import cache

from django.db import connections

from django.utils.dateparse import parse_date

from rest_framework import status

from rest_framework.permissions import IsAuthenticated

from rest_framework.response import Response

from rest_framework.views import APIView

from CrmConformidad.jwt_authentication import CRMJWTAuthentication

from .serializers import (

    OrdenFacturadaDetalleSerializer,

    OrdenFacturadaResumenSerializer,

)

DB_ALIAS = "tdsql"

TABLA_HEADER = "public.matriz_os_reqheader"

TABLA_OS = "public.matriz_os"

TABLA_ITEMS = "public.matriz_os_reqitenslojas"

TABLA_PRODUCTOS = "public.matriz_produtosativos_5vw"

# Este módulo solamente trabajará con información desde 2025.

# No es el filtro seleccionado por el usuario.

# Los filtros reales siguen llegando desde React.

FECHA_MINIMA_DATOS = date(2025, 1, 1)

# Cambiamos la versión para no reutilizar el cache anterior.

CACHE_OPCIONES = "ordenes_facturadas_opciones_2025_v1"

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

    Soporta:

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

# FILTROS DE LA CONSULTA BASE

#

# Los alias coinciden directamente con:

#

# fac = Matriz_OS_ReqHeader

# os  = Matriz_OS

# ref = Matriz_OS_ReqItensLojas

# ============================================================

def construir_filtros_base(request):

    condiciones = [

        'os."DtFechamento" >= %s',

    ]

    parametros = [

        FECHA_MINIMA_DATOS,

    ]

    # ---------------------------------------------------------

    # AGENCIA

    # ---------------------------------------------------------

    agregar_filtro_in(

        condiciones,

        parametros,

        'fac."Agencia"',

        valores_parametro(

            request,

            "agencia",

        ),

    )

    # ---------------------------------------------------------

    # FECHA

    # ---------------------------------------------------------

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

            "\'fecha_desde\' no puede ser mayor que \'fecha_hasta\'."

        )

    if fecha_desde:

        condiciones.append(

            'os."DtFechamento" >= %s'

        )

        parametros.append(

            fecha_desde

        )

    if fecha_hasta:

        condiciones.append(

            'os."DtFechamento" < %s'

        )

        parametros.append(

            fecha_hasta + timedelta(days=1)

        )

    # ---------------------------------------------------------

    # TIPO OS

    # ---------------------------------------------------------

    agregar_filtro_in(

        condiciones,

        parametros,

        'os."TpOS"',

        valores_parametro(

            request,

            "tp_os",

        ),

    )

    # ---------------------------------------------------------

    # SITUACIÓN

    # ---------------------------------------------------------

    agregar_filtro_in(

        condiciones,

        parametros,

        'os."Situacao"',

        valores_parametro(

            request,

            "situacao",

        ),

    )

    # ---------------------------------------------------------

    # SUBTIPO

    # ---------------------------------------------------------

    agregar_filtro_in(

        condiciones,

        parametros,

        'os."SubtipoOS"',

        valores_parametro(

            request,

            "subtipo_os",

        ),

    )

    # ---------------------------------------------------------

    # GARANTÍA

    # ---------------------------------------------------------

    agregar_filtro_in(

        condiciones,

        parametros,

        'os."SitGarantia"',

        valores_parametro(

            request,

            "sit_garantia",

        ),

    )

    # ---------------------------------------------------------

    # CONDICIÓN DE PAGO

    # ---------------------------------------------------------

    agregar_filtro_in(

        condiciones,

        parametros,

        'os."CodCondPgto"',

        valores_enteros_parametro(

            request,

            "cod_cond_pgto",

        ),

    )

    # ---------------------------------------------------------

    # OPERACIÓN FISCAL

    # ---------------------------------------------------------

    agregar_filtro_in(

        condiciones,

        parametros,

        'os."CodOperFiscal"',

        valores_enteros_parametro(

            request,

            "cod_oper_fiscal",

        ),

    )

    # ---------------------------------------------------------

    # RESPONSABLE

    # ---------------------------------------------------------

    agregar_filtro_in(

        condiciones,

        parametros,

        'fac."FuncResp"',

        valores_enteros_parametro(

            request,

            "func_resp",

        ),

    )

    # ---------------------------------------------------------

    # BÚSQUEDA GLOBAL

    # ---------------------------------------------------------

    busqueda = texto_parametro(

        request,

        "q",

    )

    if busqueda:

        patron = f"%{busqueda}%"

        condiciones.append(

            f"""

            (

                CAST(fac."NrOS" AS varchar(50)) ILIKE %s

                OR CAST(

                    fac."NrAtendim" AS varchar(50)

                ) ILIKE %s

                OR CAST(

                    fac."NrReq" AS varchar(50)

                ) ILIKE %s

                OR CAST(

                    fac."FuncResp" AS varchar(50)

                ) ILIKE %s

                OR fac."Agencia" ILIKE %s

                OR ref."CodProd" ILIKE %s

                OR os."TpOS" ILIKE %s

                OR os."Situacao" ILIKE %s

                OR os."SubtipoOS" ILIKE %s

                OR EXISTS (

                    SELECT 1

                    FROM {TABLA_PRODUCTOS} prod_busqueda

                    WHERE

                        prod_busqueda."Agencia" = ref."Agencia"

                        AND prod_busqueda."CodProduto" = ref."CodProd"

                        AND prod_busqueda."NmProduto" ILIKE %s

                )

            )

            """

        )

        parametros.extend(

            [patron] * 10

        )

    where_sql = " AND ".join(

        condiciones

    )

    return (

        where_sql,

        parametros,

    )

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

# LISTADO + MÉTRICAS + GRÁFICAS

#

# IMPORTANTE:

#

# 1. Ejecutamos UNA VEZ la consulta base.




#

# No existe ya una segunda consulta /dashboard/ pesada.

# ============================================================

class OrdenesFacturadasListView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            where_sql, parametros = construir_filtros_base(request)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        page = entero_parametro(request, "page", 1, minimo=1)
        page_size = entero_parametro(request, "page_size", 50, minimo=1, maximo=250)
        offset = (page - 1) * page_size
        ordering_sql = construir_ordering(request)

        base_cte = f"""
            WITH base_facturada AS (
                SELECT
                    fac."Agencia" AS agencia,
                    fac."NrOS" AS nros,
                    fac."NrAtendim" AS nratendimento,
                    fac."NrReq" AS nrreq,
                    fac."DtEmissao"::date AS dtemissao,
                    fac."FuncResp" AS funcresp,
                    fac."QtdeItens" AS qtdeitens,
                    fac."QtdeAtend" AS qtdeatend,
                    ref."CodProd" AS codprod,
                    ref."PrecoUnit" AS precounit,
                    ref."PercDesc" AS percdesc,
                    ref."VrDesc" AS vrdesc,
                    ref."VrProd" AS vrprod,
                    os."VrAdicionais" AS vradicionais,
                    os."VrDescPeca" AS vrdescpeca,
                    os."VrTotalPecas" AS vrtotalpecas,
                    os."TtMo" AS ttmo,
                    os."TpOS" AS tpos,
                    os."DtFechamento"::date AS dtfechamento,
                    os."DtAbertura"::date AS dtabertura,
                    os."Situacao" AS situacao,
                    os."CodCondPgto" AS codcondpgto,
                    os."CodOperFiscal" AS codoperfiscal,
                    os."SitGarantia" AS sitgarantia,
                    os."SubtipoOS" AS subtipoos
                FROM {TABLA_HEADER} fac
                INNER JOIN {TABLA_OS} os
                    ON os."Agencia" = fac."Agencia"
                    AND os."NrOS" = fac."NrOS"
                    AND os."NrAtendimento" = fac."NrAtendim"
                INNER JOIN {TABLA_ITEMS} ref
                    ON ref."Agencia" = fac."Agencia"
                    AND ref."NrOS" = fac."NrOS"
                    AND ref."NrReq" = fac."NrReq"
                WHERE {where_sql}
            ),
            ordenes_facturadas AS (
                SELECT
                    agencia, nros, nratendimento,
                    MAX(tpos) AS tpos,
                    MAX(subtipoos) AS subtipoos,
                    MAX(situacao) AS situacao,
                    MAX(dtabertura) AS dtabertura,
                    MAX(dtfechamento) AS dtfechamento,
                    MAX(sitgarantia) AS sitgarantia,
                    MAX(codcondpgto) AS codcondpgto,
                    MAX(codoperfiscal) AS codoperfiscal,
                    COALESCE(MAX(vradicionais), 0) AS vradicionais,
                    COALESCE(MAX(vrdescpeca), 0) AS vrdescpeca,
                    COALESCE(MAX(vrtotalpecas), 0) AS vrtotalpecas,
                    COALESCE(MAX(ttmo), 0) AS ttmo,
                    COUNT(DISTINCT nrreq) AS requisiciones,
                    COUNT(*) AS partidas,
                    COALESCE(SUM(COALESCE(vrprod, 0)), 0) AS valor_productos,
                    COALESCE(SUM(COALESCE(vrdesc, 0)), 0) AS descuentos
                FROM base_facturada
                GROUP BY agencia, nros, nratendimento
            )
        """

        consultas = [
            base_cte + """ SELECT COUNT(*) AS ordenes,
                COALESCE(SUM(requisiciones),0) AS requisiciones,
                COALESCE(SUM(partidas),0) AS partidas,
                COALESCE(SUM(valor_productos),0) AS valor_productos,
                COALESCE(SUM(vrtotalpecas),0) AS total_piezas_os,
                COALESCE(SUM(ttmo),0) AS mano_obra,
                COALESCE(SUM(descuentos),0) AS descuentos,
                COALESCE(SUM(vradicionais),0) AS adicionales,
                COALESCE(SUM(valor_productos + ttmo),0) AS refacciones_mano_obra
                FROM ordenes_facturadas""",
            base_cte + """ SELECT agencia, COUNT(*) AS ordenes,
                COALESCE(SUM(valor_productos),0) AS valor_productos,
                COALESCE(SUM(ttmo),0) AS mano_obra,
                COALESCE(SUM(valor_productos + ttmo),0) AS total
                FROM ordenes_facturadas GROUP BY agencia ORDER BY total DESC""",
            base_cte + """ SELECT COALESCE(NULLIF(BTRIM(tpos),''),'Sin tipo') AS tipo,
                COUNT(*) AS ordenes, COALESCE(SUM(valor_productos),0) AS valor_productos,
                COALESCE(SUM(ttmo),0) AS mano_obra
                FROM ordenes_facturadas
                GROUP BY COALESCE(NULLIF(BTRIM(tpos),''),'Sin tipo')
                ORDER BY ordenes DESC""",
            base_cte + """ SELECT COALESCE(NULLIF(BTRIM(situacao),''),'Sin situación') AS situacion,
                COUNT(*) AS ordenes, COALESCE(SUM(valor_productos),0) AS valor_productos,
                COALESCE(SUM(ttmo),0) AS mano_obra
                FROM ordenes_facturadas
                GROUP BY COALESCE(NULLIF(BTRIM(situacao),''),'Sin situación')
                ORDER BY ordenes DESC""",
            base_cte + """ SELECT dtfechamento AS fecha, COUNT(*) AS ordenes,
                COALESCE(SUM(valor_productos),0) AS valor_productos,
                COALESCE(SUM(ttmo),0) AS mano_obra,
                COALESCE(SUM(valor_productos + ttmo),0) AS total
                FROM ordenes_facturadas WHERE dtfechamento IS NOT NULL
                GROUP BY dtfechamento ORDER BY dtfechamento""",
            base_cte + """ SELECT COALESCE(NULLIF(BTRIM(sitgarantia),''),'Sin dato') AS garantia,
                COUNT(*) AS ordenes, COALESCE(SUM(valor_productos),0) AS valor_productos,
                COALESCE(SUM(ttmo),0) AS mano_obra
                FROM ordenes_facturadas
                GROUP BY COALESCE(NULLIF(BTRIM(sitgarantia),''),'Sin dato')
                ORDER BY ordenes DESC""",
            base_cte + f""" SELECT agencia,nros,nratendimento,tpos,subtipoos,situacao,
                dtabertura,dtfechamento,sitgarantia,codcondpgto,codoperfiscal,
                vradicionais,vrdescpeca,vrtotalpecas,ttmo,requisiciones,partidas,
                valor_productos,descuentos
                FROM ordenes_facturadas ORDER BY {ordering_sql}
                LIMIT %s OFFSET %s""",
        ]

        with connections[DB_ALIAS].cursor() as cursor:
            resultados = []
            for indice, consulta in enumerate(consultas):
                params = list(parametros)
                if indice == len(consultas) - 1:
                    params.extend([page_size, offset])
                cursor.execute(consulta, params)
                resultados.append(cursor_a_dicts(cursor))

        metricas = resultados[0][0] if resultados[0] else {
            "ordenes": 0, "requisiciones": 0, "partidas": 0,
            "valor_productos": 0, "total_piezas_os": 0, "mano_obra": 0,
            "descuentos": 0, "adicionales": 0, "refacciones_mano_obra": 0,
        }
        serializer = OrdenFacturadaResumenSerializer(resultados[6], many=True)
        return Response({
            "count": int(metricas.get("ordenes", 0) or 0),
            "page": page,
            "page_size": page_size,
            "metricas": metricas,
            "graficas": {
                "por_agencia": resultados[1],
                "por_tipo_os": resultados[2],
                "por_situacion": resultados[3],
                "por_dia": resultados[4],
                "por_garantia": resultados[5],
            },
            "results": serializer.data,
        })


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

                        "\'agencia\' es obligatorio."

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

                        "\'nros\' y \'nratendimento\' deben ser numéricos."

                },

                status=status.HTTP_400_BAD_REQUEST,

            )

        consulta = f"""

            SELECT

                fac."Agencia"

                    AS agencia,

                fac."NrOS"

                    AS nros,

                fac."NrAtendim"

                    AS nratendimento,

                fac."NrReq"

                    AS nrreq,

                fac."DtEmissao"::date

                    AS dtemissao,

                fac."FuncResp"

                    AS funcresp,

                fac."QtdeItens"

                    AS qtdeitens,

                fac."QtdeAtend"

                    AS qtdeatend,

                ref."CodProd"

                    AS codprod,

                prod."NmProduto"

                    AS nmproduto,

                ref."PrecoUnit"

                    AS precounit,

                ref."PercDesc"

                    AS percdesc,

                ref."VrDesc"

                    AS vrdesc,

                ref."VrProd"

                    AS vrprod

            FROM {TABLA_HEADER} fac

            INNER JOIN {TABLA_OS} os

                ON os."Agencia" = fac."Agencia"

                AND os."NrOS" = fac."NrOS"

                AND os."NrAtendimento" = fac."NrAtendim"

            INNER JOIN {TABLA_ITEMS} ref

                ON ref."Agencia" = fac."Agencia"

                AND ref."NrOS" = fac."NrOS"

                AND ref."NrReq" = fac."NrReq"

            INNER JOIN {TABLA_PRODUCTOS} prod

                ON prod."CodProduto" = ref."CodProd"

                AND prod."Agencia" = ref."Agencia"

            WHERE

                fac."Agencia" = %s

                AND fac."NrOS" = %s

                AND fac."NrAtendim" = %s

            ORDER BY

                fac."NrReq",

                ref."CodProd";

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

        serializer = (

            OrdenFacturadaDetalleSerializer(

                registros,

                many=True,

            )

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

                "resumen": {

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

                },

                "results":

                    serializer.data,

            }

        )

# ============================================================

# OPCIONES

#

# Ya NO hacemos EXISTS contra Header + Items 7 veces.

# Es un catálogo y queda cacheado.

# ============================================================

class OrdenesFacturadasOpcionesView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        resultado_cache = cache.get(CACHE_OPCIONES)
        if resultado_cache is not None:
            return Response(resultado_cache)

        resultado = {}
        textos = {
            "agencias": "Agencia",
            "tpos": "TpOS",
            "situaciones": "Situacao",
            "subtipos": "SubtipoOS",
            "garantias": "SitGarantia",
        }
        numeros = {
            "condiciones_pago": "CodCondPgto",
            "operaciones_fiscales": "CodOperFiscal",
        }

        with connections[DB_ALIAS].cursor() as cursor:
            for clave, columna in textos.items():
                cursor.execute(
                    f"""SELECT DISTINCT "{columna}"
                        FROM {TABLA_OS}
                        WHERE "DtFechamento" >= %s
                          AND "{columna}" IS NOT NULL
                          AND NULLIF(BTRIM(CAST("{columna}" AS varchar(255))), '') IS NOT NULL
                        ORDER BY "{columna}" """,
                    [FECHA_MINIMA_DATOS],
                )
                resultado[clave] = [r[0] for r in cursor.fetchall() if r[0] is not None]

            for clave, columna in numeros.items():
                cursor.execute(
                    f"""SELECT DISTINCT "{columna}"
                        FROM {TABLA_OS}
                        WHERE "DtFechamento" >= %s
                          AND "{columna}" IS NOT NULL
                        ORDER BY "{columna}" """,
                    [FECHA_MINIMA_DATOS],
                )
                resultado[clave] = [r[0] for r in cursor.fetchall() if r[0] is not None]

            cursor.execute(
                f"""SELECT DISTINCT fac."FuncResp"
                    FROM {TABLA_HEADER} fac
                    INNER JOIN {TABLA_OS} osf
                      ON osf."Agencia" = fac."Agencia"
                     AND osf."NrOS" = fac."NrOS"
                     AND osf."NrAtendimento" = fac."NrAtendim"
                    WHERE osf."DtFechamento" >= %s
                      AND fac."FuncResp" IS NOT NULL
                    ORDER BY fac."FuncResp" """,
                [FECHA_MINIMA_DATOS],
            )
            resultado["funcionarios"] = [
                r[0] for r in cursor.fetchall() if r[0] is not None
            ]

            cursor.execute(
                f"""SELECT MIN("DtFechamento"), MAX("DtFechamento")
                    FROM {TABLA_OS}
                    WHERE "DtFechamento" >= %s""",
                [FECHA_MINIMA_DATOS],
            )
            fila = cursor.fetchone()
            minima = fila[0] if fila else None
            maxima = fila[1] if fila else None

        resultado["fechas"] = {
            "minima": minima.isoformat() if minima else None,
            "maxima": maxima.isoformat() if maxima else None,
        }
        cache.set(CACHE_OPCIONES, resultado, 60 * 60 * 6)
        return Response(resultado)
