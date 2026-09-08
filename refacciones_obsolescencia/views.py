from django.core.cache import cache
from django.db import connections
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from CrmConformidad.jwt_authentication import CRMJWTAuthentication
from .serializers import InventarioRefaccionesObsolescenciaSerializer


DB_ALIAS = "sqlserver_inv"
TABLA = "dbo.Inventario_Refacciones_Obsolescencia"
CACHE_OPCIONES = "refacciones_obsolescencia_opciones_v2"


def texto_parametro(request, nombre):
    return str(request.query_params.get(nombre, "") or "").strip()


def entero_parametro(request, nombre):
    valor = texto_parametro(request, nombre)
    if not valor:
        return None

    try:
        return int(valor)
    except (TypeError, ValueError):
        raise ValueError(f"El parámetro '{nombre}' debe ser un número entero.")


def validar_fecha(valor, nombre):
    if valor and not parse_date(valor):
        raise ValueError(f"El parámetro '{nombre}' debe tener formato YYYY-MM-DD.")


def cursor_a_dicts(cursor):
    columnas = [columna[0] for columna in cursor.description]
    return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]


def construir_filtros(request):
    busqueda = texto_parametro(request, "q")
    agencia = texto_parametro(request, "agencia")
    grupo_principal = texto_parametro(request, "grupo_principal")
    categoria = texto_parametro(request, "categoria")
    capa_obsolescencia = texto_parametro(request, "capa_obsolescencia")
    categoria_movimiento = texto_parametro(request, "categoria_movimiento")
    fecha_desde = texto_parametro(request, "fecha_desde")
    fecha_hasta = texto_parametro(request, "fecha_hasta")
    dias_min = entero_parametro(request, "dias_min")
    dias_max = entero_parametro(request, "dias_max")

    validar_fecha(fecha_desde, "fecha_desde")
    validar_fecha(fecha_hasta, "fecha_hasta")

    if dias_min is not None and dias_min < 0:
        raise ValueError("El parámetro 'dias_min' no puede ser negativo.")

    if dias_max is not None and dias_max < 0:
        raise ValueError("El parámetro 'dias_max' no puede ser negativo.")

    if dias_min is not None and dias_max is not None and dias_min > dias_max:
        raise ValueError("'dias_min' no puede ser mayor que 'dias_max'.")

    condiciones = []
    parametros = []

    if busqueda:
        termino = f"%{busqueda}%"
        condiciones.append("""
            (
                Agencia LIKE %s
                OR CodLinhaProd LIKE %s
                OR Localizacao LIKE %s
                OR CodProduto LIKE %s
                OR NmProduto LIKE %s
                OR GrupoPrincipal LIKE %s
                OR Subgrupo LIKE %s
                OR NombreEstandarizado LIKE %s
                OR Categoria LIKE %s
                OR Observacion LIKE %s
                OR Categoria_Movimiento LIKE %s
            )
        """)
        parametros.extend([termino] * 11)

    if agencia:
        condiciones.append("Agencia = %s")
        parametros.append(agencia)

    if grupo_principal:
        condiciones.append("GrupoPrincipal = %s")
        parametros.append(grupo_principal)

    if categoria:
        condiciones.append("Categoria = %s")
        parametros.append(categoria)

    if capa_obsolescencia:
        condiciones.append("Capa_Obsolescencia = %s")
        parametros.append(capa_obsolescencia)

    if categoria_movimiento:
        condiciones.append("Categoria_Movimiento = %s")
        parametros.append(categoria_movimiento)

    if fecha_desde:
        condiciones.append("Fecha_Referencia >= %s")
        parametros.append(fecha_desde)

    if fecha_hasta:
        condiciones.append("Fecha_Referencia <= %s")
        parametros.append(fecha_hasta)

    if dias_min is not None:
        condiciones.append("Dias_Desde_Ultimo_Movimiento >= %s")
        parametros.append(dias_min)

    if dias_max is not None:
        condiciones.append("Dias_Desde_Ultimo_Movimiento <= %s")
        parametros.append(dias_max)

    where_sql = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
    return where_sql, parametros


class InventarioRefaccionesObsolescenciaListView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            pagina = max(int(request.query_params.get("page", 1)), 1)
        except (TypeError, ValueError):
            pagina = 1

        try:
            tamano_pagina = int(request.query_params.get("page_size", 100))
        except (TypeError, ValueError):
            tamano_pagina = 100

        tamano_pagina = max(1, min(tamano_pagina, 500))
        offset = (pagina - 1) * tamano_pagina

        try:
            where_sql, parametros = construir_filtros(request)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        consulta_total = f"""
            SELECT COUNT(*)
            FROM {TABLA}
            {where_sql}
        """

        consulta = f"""
            SELECT
                Agencia AS agencia,
                QtInventario AS qt_inventario,
                CodLinhaProd AS cod_linha_prod,
                Localizacao AS localizacao,
                CodProduto AS cod_produto,
                NmProduto AS nm_produto,
                Unidade AS unidade,
                QtdeEstoque AS qtde_estoque,
                VrEstoque AS vr_estoque,
                VrUnitarioMedio AS vr_unitario_medio,
                QtReservada AS qt_reservada,
                QtPedida AS qt_pedida,
                GrupoPrincipal AS grupo_principal,
                Subgrupo AS subgrupo,
                NombreEstandarizado AS nombre_estandarizado,
                Categoria AS categoria,
                Observacion AS observacion,
                Fecha_Ultima_Venta AS fecha_ultima_venta,
                Fecha_Ult_Comp_Prod AS fecha_ult_comp_prod,
                Fecha_Ult_Ped_Prod AS fecha_ult_ped_prod,
                Fecha_Ult_Actu_Prod AS fecha_ult_actu_prod,
                Fecha_Regis_Refac AS fecha_regis_refac,
                Fecha_Inventario_Refac AS fecha_inventario_refac,
                Fecha_Primera_Compra_Refac AS fecha_primera_compra_refac,
                Fecha_Actualizacion_Refac AS fecha_actualizacion_refac,
                VrUniUltCpa AS vr_uni_ult_cpa,
                Fecha_Referencia AS fecha_referencia,
                Dias_Desde_Ultimo_Movimiento AS dias_desde_ultimo_movimiento,
                Capa_Obsolescencia AS capa_obsolescencia,
                Categoria_Movimiento AS categoria_movimiento
            FROM {TABLA}
            {where_sql}
            ORDER BY
                CASE WHEN Dias_Desde_Ultimo_Movimiento IS NULL THEN 1 ELSE 0 END,
                Dias_Desde_Ultimo_Movimiento DESC,
                Agencia,
                CodProduto,
                Localizacao
            OFFSET %s ROWS
            FETCH NEXT %s ROWS ONLY
        """

        with connections[DB_ALIAS].cursor() as cursor:
            cursor.execute(consulta_total, parametros)
            total = cursor.fetchone()[0]

            cursor.execute(consulta, [*parametros, offset, tamano_pagina])
            registros = cursor_a_dicts(cursor)

        serializer = InventarioRefaccionesObsolescenciaSerializer(registros, many=True)

        return Response({
            "count": total,
            "page": pagina,
            "page_size": tamano_pagina,
            "results": serializer.data,
        })


class InventarioRefaccionesObsolescenciaDashboardView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            where_sql, parametros = construir_filtros(request)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        with connections[DB_ALIAS].cursor() as cursor:
            cursor.execute("SET NOCOUNT ON;")

            cursor.execute("""
                IF OBJECT_ID('tempdb..#Base') IS NOT NULL
                    DROP TABLE #Base;
            """)

            consulta_base = f"""
                SELECT
                    Agencia,
                    QtInventario,
                    CodLinhaProd,
                    Localizacao,
                    CodProduto,
                    NmProduto,
                    QtdeEstoque,
                    VrEstoque,
                    VrUnitarioMedio,
                    QtReservada,
                    QtPedida,
                    GrupoPrincipal,
                    Subgrupo,
                    Categoria,
                    Capa_Obsolescencia,
                    Categoria_Movimiento,
                    Dias_Desde_Ultimo_Movimiento,
                    Fecha_Referencia
                INTO #Base
                FROM {TABLA}
                {where_sql};
            """

            cursor.execute(consulta_base, parametros)

            cursor.execute("""
                SELECT
                    COUNT(*) AS registros,

                    COUNT(
                        DISTINCT NULLIF(
                            LTRIM(RTRIM(CodProduto)),
                            ''
                        )
                    ) AS productos,

                    COALESCE(
                        SUM(COALESCE(QtInventario, 0)),
                        0
                    ) AS qt_inventario,

                    COALESCE(
                        SUM(COALESCE(QtdeEstoque, 0)),
                        0
                    ) AS existencia,

                    COALESCE(
                        SUM(COALESCE(VrEstoque, 0)),
                        0
                    ) AS valor_estoque,

                    COALESCE(
                        SUM(COALESCE(QtReservada, 0)),
                        0
                    ) AS reservada,

                    COALESCE(
                        SUM(COALESCE(QtPedida, 0)),
                        0
                    ) AS pedida,

                    COALESCE(
                        AVG(
                            CAST(
                                Dias_Desde_Ultimo_Movimiento
                                AS DECIMAL(18, 2)
                            )
                        ),
                        0
                    ) AS promedio_dias_movimiento

                FROM #Base;
            """)

            columnas = [columna[0] for columna in cursor.description]
            totales = dict(zip(columnas, cursor.fetchone()))

            cursor.execute("""
                SELECT
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(Capa_Obsolescencia)), ''),
                        'Sin capa'
                    ) AS capa_obsolescencia,

                    COUNT(*) AS productos,

                    COALESCE(
                        SUM(COALESCE(QtdeEstoque, 0)),
                        0
                    ) AS existencia,

                    COALESCE(
                        SUM(COALESCE(VrEstoque, 0)),
                        0
                    ) AS valor_estoque

                FROM #Base

                GROUP BY
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(Capa_Obsolescencia)), ''),
                        'Sin capa'
                    )

                ORDER BY valor_estoque DESC;
            """)
            por_capa = cursor_a_dicts(cursor)

            cursor.execute("""
                SELECT
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(Categoria_Movimiento)), ''),
                        'Sin categoría'
                    ) AS categoria_movimiento,

                    COUNT(*) AS productos,

                    COALESCE(
                        SUM(COALESCE(QtdeEstoque, 0)),
                        0
                    ) AS existencia,

                    COALESCE(
                        SUM(COALESCE(VrEstoque, 0)),
                        0
                    ) AS valor_estoque

                FROM #Base

                GROUP BY
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(Categoria_Movimiento)), ''),
                        'Sin categoría'
                    )

                ORDER BY valor_estoque DESC;
            """)
            por_categoria_movimiento = cursor_a_dicts(cursor)

            cursor.execute("""
                SELECT
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(Agencia)), ''),
                        'Sin agencia'
                    ) AS agencia,

                    COUNT(*) AS productos,

                    COALESCE(
                        SUM(COALESCE(QtdeEstoque, 0)),
                        0
                    ) AS existencia,

                    COALESCE(
                        SUM(COALESCE(VrEstoque, 0)),
                        0
                    ) AS valor_estoque

                FROM #Base

                GROUP BY
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(Agencia)), ''),
                        'Sin agencia'
                    )

                ORDER BY valor_estoque DESC;
            """)
            por_agencia = cursor_a_dicts(cursor)

            cursor.execute("""
                SELECT TOP 12
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(GrupoPrincipal)), ''),
                        'Sin grupo'
                    ) AS grupo_principal,

                    COUNT(*) AS productos,

                    COALESCE(
                        SUM(COALESCE(QtdeEstoque, 0)),
                        0
                    ) AS existencia,

                    COALESCE(
                        SUM(COALESCE(VrEstoque, 0)),
                        0
                    ) AS valor_estoque

                FROM #Base

                GROUP BY
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(GrupoPrincipal)), ''),
                        'Sin grupo'
                    )

                ORDER BY valor_estoque DESC;
            """)
            por_grupo = cursor_a_dicts(cursor)

            cursor.execute("""
                SELECT TOP 12
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(Categoria)), ''),
                        'Sin categoría'
                    ) AS categoria,

                    COUNT(*) AS productos,

                    COALESCE(
                        SUM(COALESCE(QtdeEstoque, 0)),
                        0
                    ) AS existencia,

                    COALESCE(
                        SUM(COALESCE(VrEstoque, 0)),
                        0
                    ) AS valor_estoque

                FROM #Base

                GROUP BY
                    COALESCE(
                        NULLIF(LTRIM(RTRIM(Categoria)), ''),
                        'Sin categoría'
                    )

                ORDER BY valor_estoque DESC;
            """)
            por_categoria = cursor_a_dicts(cursor)

            cursor.execute("""
                SELECT
                    rango,
                    COUNT(*) AS productos,

                    COALESCE(
                        SUM(COALESCE(QtdeEstoque, 0)),
                        0
                    ) AS existencia,

                    COALESCE(
                        SUM(COALESCE(VrEstoque, 0)),
                        0
                    ) AS valor_estoque

                FROM (
                    SELECT
                        QtdeEstoque,
                        VrEstoque,

                        CASE
                            WHEN Dias_Desde_Ultimo_Movimiento IS NULL THEN 'Sin dato'
                            WHEN Dias_Desde_Ultimo_Movimiento <= 90 THEN '0-90 días'
                            WHEN Dias_Desde_Ultimo_Movimiento <= 180 THEN '91-180 días'
                            WHEN Dias_Desde_Ultimo_Movimiento <= 365 THEN '181-365 días'
                            WHEN Dias_Desde_Ultimo_Movimiento <= 730 THEN '366-730 días'
                            ELSE 'Más de 730 días'
                        END AS rango,

                        CASE
                            WHEN Dias_Desde_Ultimo_Movimiento IS NULL THEN 6
                            WHEN Dias_Desde_Ultimo_Movimiento <= 90 THEN 1
                            WHEN Dias_Desde_Ultimo_Movimiento <= 180 THEN 2
                            WHEN Dias_Desde_Ultimo_Movimiento <= 365 THEN 3
                            WHEN Dias_Desde_Ultimo_Movimiento <= 730 THEN 4
                            ELSE 5
                        END AS orden

                    FROM #Base
                ) AS datos

                GROUP BY
                    rango,
                    orden

                ORDER BY orden;
            """)
            por_antiguedad = cursor_a_dicts(cursor)

            cursor.execute("DROP TABLE #Base;")

        return Response({
            "totales": totales,
            "graficas": {
                "por_capa": por_capa,
                "por_categoria_movimiento": por_categoria_movimiento,
                "por_agencia": por_agencia,
                "por_grupo": por_grupo,
                "por_categoria": por_categoria,
                "por_antiguedad": por_antiguedad,
            },
        })


class InventarioRefaccionesObsolescenciaOpcionesView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        opciones_cache = cache.get(CACHE_OPCIONES)

        if opciones_cache:
            return Response(opciones_cache)

        def valores_distintos(cursor, columna):
            consulta = f"""
                SELECT DISTINCT
                    LTRIM(RTRIM({columna})) AS valor
                FROM {TABLA}
                WHERE {columna} IS NOT NULL
                  AND LTRIM(RTRIM({columna})) <> ''
                ORDER BY valor
            """

            cursor.execute(consulta)
            return [fila[0] for fila in cursor.fetchall() if fila[0]]

        with connections[DB_ALIAS].cursor() as cursor:
            opciones = {
                "agencias": valores_distintos(cursor, "Agencia"),
                "grupos_principales": valores_distintos(cursor, "GrupoPrincipal"),
                "categorias": valores_distintos(cursor, "Categoria"),
                "capas_obsolescencia": valores_distintos(cursor, "Capa_Obsolescencia"),
                "categorias_movimiento": valores_distintos(cursor, "Categoria_Movimiento"),
            }

        cache.set(CACHE_OPCIONES, opciones, 300)
        return Response(opciones)