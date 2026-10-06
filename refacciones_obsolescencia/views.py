# refacciones_obsolescencia/views.py
from django.core.cache import cache
from django.db import connections
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from CrmConformidad.jwt_authentication import CRMJWTAuthentication
from .serializers import InventarioRefaccionesObsolescenciaSerializer


DB_ALIAS = "tdsql"
TABLA = "inventario_refacciones_obsolescencia"
CACHE_OPCIONES = "refacciones_obsolescencia_opciones_postgresql_v1"

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
        raise ValueError(
            f"El parámetro '{nombre}' debe tener formato YYYY-MM-DD."
        )


def cursor_a_dicts(cursor):
    columnas = [columna[0] for columna in cursor.description]
    return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]


def ejecutar_dicts(cursor, consulta, parametros=None):
    cursor.execute(consulta, parametros or [])
    return cursor_a_dicts(cursor)


def construir_filtros(request):
    busqueda = texto_parametro(request, "q")
    agencia = texto_parametro(request, "agencia")
    grupo_principal = texto_parametro(request, "grupo_principal")
    categoria = texto_parametro(request, "categoria")
    capa_obsolescencia = texto_parametro(request, "capa_obsolescencia")
    categoria_movimiento = texto_parametro(request, "categoria_movimiento")
    reservadas = texto_parametro(request, "reservadas").lower()
    pendientes = texto_parametro(request, "pendientes").lower()
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

    if (dias_min is not None and dias_max is not None and dias_min > dias_max):
        raise ValueError("'dias_min' no puede ser mayor que 'dias_max'.")

    if reservadas not in ("", "con", "sin"):
        raise ValueError("El parámetro 'reservadas' debe ser 'con' o 'sin'.")

    if pendientes not in ("", "con", "sin"):
        raise ValueError("El parámetro 'pendientes' debe ser 'con' o 'sin'.")

    condiciones = []
    parametros = []

    if busqueda:
        termino = f"%{busqueda}%"

        condiciones.append(
            """
            (
                "Agencia" ILIKE %s
                OR "CodLinhaProd" ILIKE %s
                OR "Localizacao" ILIKE %s
                OR "CodProduto" ILIKE %s
                OR "NmProduto" ILIKE %s
                OR "GrupoPrincipal" ILIKE %s
                OR "Subgrupo" ILIKE %s
                OR "NombreEstandarizado" ILIKE %s
                OR "Categoria" ILIKE %s
                OR "Observacion" ILIKE %s
                OR "Categoria_Movimiento" ILIKE %s
            )
            """
        )

        parametros.extend([termino] * 11)

    if agencia:
        condiciones.append('"Agencia" = %s')
        parametros.append(agencia)

    if grupo_principal:
        condiciones.append('"GrupoPrincipal" = %s')
        parametros.append(grupo_principal)

    if categoria:
        condiciones.append('"Categoria" = %s')
        parametros.append(categoria)

    if capa_obsolescencia:
        condiciones.append('"Capa_Obsolescencia" = %s')
        parametros.append(capa_obsolescencia)

    if categoria_movimiento:
        condiciones.append('"Categoria_Movimiento" = %s')
        parametros.append(categoria_movimiento)

    if reservadas == "con":
        condiciones.append('COALESCE("QtReservada", 0) > 0')
    elif reservadas == "sin":
        condiciones.append('COALESCE("QtReservada", 0) <= 0')

    if pendientes == "con":
        condiciones.append('COALESCE("QtPedida", 0) > 0')
    elif pendientes == "sin":
        condiciones.append('COALESCE("QtPedida", 0) <= 0')

    if fecha_desde:
        condiciones.append('"Fecha_Referencia" >= %s')
        parametros.append(fecha_desde)

    if fecha_hasta:
        condiciones.append('"Fecha_Referencia" <= %s')
        parametros.append(fecha_hasta)

    if dias_min is not None:
        condiciones.append(
            '"Dias_Desde_Ultimo_Movimiento" >= %s'
        )
        parametros.append(dias_min)

    if dias_max is not None:
        condiciones.append('"Dias_Desde_Ultimo_Movimiento" <= %s')
        parametros.append(dias_max)

    where_sql = (
        f"WHERE {' AND '.join(condiciones)}"
        if condiciones
        else ""
    )
    return where_sql, parametros


def construir_base_cte(where_sql):
    return f"""
        WITH base AS (
            SELECT
                "Agencia",
                "QtInventario",
                "CodLinhaProd",
                "Localizacao",
                "CodProduto",
                "NmProduto",
                "Unidade",
                "QtdeEstoque",
                "VrEstoque",
                "VrUnitarioMedio",
                "QtReservada",
                "QtPedida",
                "GrupoPrincipal",
                "Subgrupo",
                "NombreEstandarizado",
                "Categoria",
                "Observacion",
                "Fecha_Ultima_Venta",
                "Fecha_Ult_Comp_Prod",
                "Fecha_Ult_Ped_Prod",
                "Fecha_Ult_Actu_Prod",
                "Fecha_Regis_Refac",
                "Fecha_Inventario_Refac",
                "Fecha_Primera_Compra_Refac",
                "Fecha_Actualizacion_Refac",
                "VrUniUltCpa",
                "Fecha_Referencia",
                "Dias_Desde_Ultimo_Movimiento",
                "Capa_Obsolescencia",
                "Categoria_Movimiento",

                COALESCE("QtdeEstoque", 0)
                    - COALESCE("QtReservada", 0)
                    AS qt_disponible,

                COALESCE("QtdeEstoque", 0)
                    * COALESCE("VrUnitarioMedio", 0)
                    AS valor_stock,

                COALESCE("QtReservada", 0)
                    * COALESCE("VrUnitarioMedio", 0)
                    AS valor_reservado,

                (
                    COALESCE("QtdeEstoque", 0)
                    - COALESCE("QtReservada", 0)
                )
                    * COALESCE("VrUnitarioMedio", 0)
                    AS valor_disponible,

                COALESCE("QtPedida", 0)
                    * COALESCE("VrUnitarioMedio", 0)
                    AS valor_pendiente

            FROM {TABLA}
            {where_sql}
        )
    """


class InventarioRefaccionesObsolescenciaListView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            pagina = max(
                int(request.query_params.get("page", 1)),
                1,
            )
        except (TypeError, ValueError):
            pagina = 1

        try:
            tamano_pagina = int(
                request.query_params.get("page_size", 100)
            )
        except (TypeError, ValueError):
            tamano_pagina = 100

        tamano_pagina = max(
            1,
            min(tamano_pagina, 25000),
        )

        offset = (pagina - 1) * tamano_pagina

        try:
            where_sql, parametros = construir_filtros(request)
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        consulta_total = f"""
            SELECT COUNT(*)
            FROM {TABLA}
            {where_sql}
        """

        consulta = f"""
            SELECT
                "Agencia" AS agencia,
                "QtInventario" AS qt_inventario,
                "CodLinhaProd" AS cod_linha_prod,
                "Localizacao" AS localizacao,
                "CodProduto" AS cod_produto,
                "NmProduto" AS nm_produto,
                "Unidade" AS unidade,
                "QtdeEstoque" AS qtde_estoque,
                "VrEstoque" AS vr_estoque,
                "VrUnitarioMedio" AS vr_unitario_medio,
                "QtReservada" AS qt_reservada,
                "QtPedida" AS qt_pedida,
                "GrupoPrincipal" AS grupo_principal,
                "Subgrupo" AS subgrupo,
                "NombreEstandarizado" AS nombre_estandarizado,
                "Categoria" AS categoria,
                "Observacion" AS observacion,
                "Fecha_Ultima_Venta" AS fecha_ultima_venta,
                "Fecha_Ult_Comp_Prod" AS fecha_ult_comp_prod,
                "Fecha_Ult_Ped_Prod" AS fecha_ult_ped_prod,
                "Fecha_Ult_Actu_Prod" AS fecha_ult_actu_prod,
                "Fecha_Regis_Refac" AS fecha_regis_refac,
                "Fecha_Inventario_Refac" AS fecha_inventario_refac,
                "Fecha_Primera_Compra_Refac" AS fecha_primera_compra_refac,
                "Fecha_Actualizacion_Refac" AS fecha_actualizacion_refac,
                "VrUniUltCpa" AS vr_uni_ult_cpa,
                "Fecha_Referencia" AS fecha_referencia,
                "Dias_Desde_Ultimo_Movimiento" AS dias_desde_ultimo_movimiento,
                "Capa_Obsolescencia" AS capa_obsolescencia,
                "Categoria_Movimiento" AS categoria_movimiento,
                "Categoria_Fiscal" AS categoria_fiscal
            FROM {TABLA}
            {where_sql}
            ORDER BY
                "Dias_Desde_Ultimo_Movimiento" DESC NULLS LAST,
                "Agencia",
                "CodProduto",
                "Localizacao"
            LIMIT %s
            OFFSET %s
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
                    tamano_pagina,
                    offset,
                ],
            )

            registros = cursor_a_dicts(cursor)

        serializer = InventarioRefaccionesObsolescenciaSerializer(
            registros,
            many=True,
        )

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
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        base_cte = construir_base_cte(where_sql)

        consulta_totales = f"""
            {base_cte}

            SELECT
                COUNT(*) AS registros,

                COUNT(
                    DISTINCT NULLIF(
                        TRIM("CodProduto"),
                        ''
                    )
                ) AS productos,

                COALESCE(
                    SUM(COALESCE("QtInventario", 0)),
                    0
                ) AS qt_inventario,

                COALESCE(
                    SUM(COALESCE("QtdeEstoque", 0)),
                    0
                ) AS existencia,

                COALESCE(
                    SUM(COALESCE("QtReservada", 0)),
                    0
                ) AS reservada,

                COALESCE(
                    SUM(COALESCE("QtPedida", 0)),
                    0
                ) AS pedida,

                COALESCE(
                    SUM(qt_disponible),
                    0
                ) AS disponible,

                COALESCE(
                    SUM(COALESCE("VrEstoque", 0)),
                    0
                ) AS valor_inventario,

                COALESCE(
                    SUM(valor_stock),
                    0
                ) AS valor_stock,

                COALESCE(
                    SUM(valor_reservado),
                    0
                ) AS valor_reservado,

                COALESCE(
                    SUM(valor_disponible),
                    0
                ) AS valor_disponible,

                COALESCE(
                    SUM(valor_pendiente),
                    0
                ) AS valor_pendiente,

                COALESCE(
                    SUM(
                        CASE
                            WHEN TRIM(
                                COALESCE(
                                    "Capa_Obsolescencia",
                                    ''
                                )
                            ) = 'O'
                            THEN COALESCE("VrEstoque", 0)
                            ELSE 0
                        END
                    ),
                    0
                ) AS valor_obsoleto,

                COALESCE(
                    (
                        SUM(
                            CASE
                                WHEN TRIM(
                                    COALESCE(
                                        "Capa_Obsolescencia",
                                        ''
                                    )
                                ) = 'O'
                                THEN COALESCE(
                                    "VrEstoque",
                                    0
                                )
                                ELSE 0
                            END
                        ) * 100.0
                    )
                    /
                    NULLIF(
                        SUM(
                            COALESCE(
                                "VrEstoque",
                                0
                            )
                        ),
                        0
                    ),
                    0
                ) AS porcentaje_obsolescencia,

                COALESCE(
                    (
                        SUM(
                            COALESCE(
                                "QtReservada",
                                0
                            )
                        ) * 100.0
                    )
                    /
                    NULLIF(
                        SUM(
                            COALESCE(
                                "QtPedida",
                                0
                            )
                        ),
                        0
                    ),
                    0
                ) AS relacion_reservada_pedida,

                COALESCE(
                    AVG(
                        "Dias_Desde_Ultimo_Movimiento"::numeric
                    ),
                    0
                ) AS promedio_dias_movimiento

            FROM base
        """

        consulta_por_capa = f"""
            {base_cte}

            SELECT
                COALESCE(
                    NULLIF(
                        TRIM("Capa_Obsolescencia"),
                        ''
                    ),
                    'Sin capa'
                ) AS capa_obsolescencia,

                COUNT(
                    DISTINCT NULLIF(
                        TRIM("CodProduto"),
                        ''
                    )
                ) AS productos,

                COALESCE(
                    SUM(COALESCE("QtdeEstoque", 0)),
                    0
                ) AS existencia,

                COALESCE(
                    SUM(COALESCE("QtReservada", 0)),
                    0
                ) AS reservada,

                COALESCE(
                    SUM(COALESCE("QtPedida", 0)),
                    0
                ) AS pedida,

                COALESCE(
                    SUM(qt_disponible),
                    0
                ) AS disponible,

                COALESCE(
                    SUM(COALESCE("VrEstoque", 0)),
                    0
                ) AS valor_inventario,

                COALESCE(
                    SUM(valor_stock),
                    0
                ) AS valor_stock,

                COALESCE(
                    SUM(valor_disponible),
                    0
                ) AS valor_disponible,

                COALESCE(
                    SUM(valor_reservado),
                    0
                ) AS valor_reservado,

                COALESCE(
                    SUM(valor_pendiente),
                    0
                ) AS valor_pendiente

            FROM base

            GROUP BY
                COALESCE(
                    NULLIF(
                        TRIM("Capa_Obsolescencia"),
                        ''
                    ),
                    'Sin capa'
                )

            ORDER BY valor_inventario DESC
        """

        consulta_por_categoria_movimiento = f"""
            {base_cte}

            SELECT
                COALESCE(
                    NULLIF(
                        TRIM("Categoria_Movimiento"),
                        ''
                    ),
                    'Sin categoría'
                ) AS categoria_movimiento,

                COUNT(
                    DISTINCT NULLIF(
                        TRIM("CodProduto"),
                        ''
                    )
                ) AS productos,

                COALESCE(
                    SUM(COALESCE("QtdeEstoque", 0)),
                    0
                ) AS existencia,

                COALESCE(
                    SUM(COALESCE("VrEstoque", 0)),
                    0
                ) AS valor_inventario,

                COALESCE(
                    SUM(valor_stock),
                    0
                ) AS valor_stock

            FROM base

            GROUP BY
                COALESCE(
                    NULLIF(
                        TRIM("Categoria_Movimiento"),
                        ''
                    ),
                    'Sin categoría'
                )

            ORDER BY valor_inventario DESC
        """

        consulta_por_agencia = f"""
            {base_cte}

            SELECT
                COALESCE(
                    NULLIF(
                        TRIM("Agencia"),
                        ''
                    ),
                    'Sin agencia'
                ) AS agencia,

                COUNT(
                    DISTINCT NULLIF(
                        TRIM("CodProduto"),
                        ''
                    )
                ) AS productos,

                COALESCE(
                    SUM(COALESCE("QtdeEstoque", 0)),
                    0
                ) AS existencia,

                COALESCE(
                    SUM(COALESCE("VrEstoque", 0)),
                    0
                ) AS valor_inventario,

                COALESCE(
                    SUM(valor_stock),
                    0
                ) AS valor_stock,

                COALESCE(
                    SUM(valor_disponible),
                    0
                ) AS valor_disponible,

                COALESCE(
                    SUM(valor_reservado),
                    0
                ) AS valor_reservado

            FROM base

            GROUP BY
                COALESCE(
                    NULLIF(
                        TRIM("Agencia"),
                        ''
                    ),
                    'Sin agencia'
                )

            ORDER BY valor_inventario DESC
        """

        consulta_por_grupo = f"""
            {base_cte}

            SELECT
                COALESCE(
                    NULLIF(
                        TRIM("GrupoPrincipal"),
                        ''
                    ),
                    'Sin grupo'
                ) AS grupo_principal,

                COUNT(
                    DISTINCT NULLIF(
                        TRIM("CodProduto"),
                        ''
                    )
                ) AS productos,

                COALESCE(
                    SUM(COALESCE("QtdeEstoque", 0)),
                    0
                ) AS existencia,

                COALESCE(
                    SUM(COALESCE("VrEstoque", 0)),
                    0
                ) AS valor_inventario,

                COALESCE(
                    SUM(valor_stock),
                    0
                ) AS valor_stock,

                COALESCE(
                    SUM(valor_disponible),
                    0
                ) AS valor_disponible,

                COALESCE(
                    SUM(valor_reservado),
                    0
                ) AS valor_reservado,

                COALESCE(
                    AVG(
                        "Dias_Desde_Ultimo_Movimiento"::numeric
                    ),
                    0
                ) AS "promedioDias"

            FROM base

            GROUP BY
                COALESCE(
                    NULLIF(
                        TRIM("GrupoPrincipal"),
                        ''
                    ),
                    'Sin grupo'
                )

            ORDER BY valor_stock DESC

            LIMIT 12
        """

        consulta_por_grupo_capa = f"""
            {base_cte},

            top_grupos AS (
                SELECT
                    COALESCE(
                        NULLIF(
                            TRIM("GrupoPrincipal"),
                            ''
                        ),
                        'Sin grupo'
                    ) AS grupo_principal,

                    COALESCE(
                        SUM(valor_stock),
                        0
                    ) AS valor_stock

                FROM base

                GROUP BY
                    COALESCE(
                        NULLIF(
                            TRIM("GrupoPrincipal"),
                            ''
                        ),
                        'Sin grupo'
                    )

                ORDER BY valor_stock DESC

                LIMIT 12
            )

            SELECT
                t.grupo_principal,

                COALESCE(
                    NULLIF(
                        TRIM(b."Capa_Obsolescencia"),
                        ''
                    ),
                    'Sin capa'
                ) AS capa_obsolescencia,

                COUNT(
                    DISTINCT NULLIF(
                        TRIM(b."CodProduto"),
                        ''
                    )
                ) AS productos,

                COALESCE(
                    SUM(
                        COALESCE(
                            b."QtdeEstoque",
                            0
                        )
                    ),
                    0
                ) AS existencia,

                COALESCE(
                    SUM(
                        COALESCE(
                            b."VrEstoque",
                            0
                        )
                    ),
                    0
                ) AS valor_inventario,

                COALESCE(
                    SUM(b.valor_stock),
                    0
                ) AS valor_stock,

                COALESCE(
                    SUM(b.valor_disponible),
                    0
                ) AS valor_disponible,

                COALESCE(
                    SUM(b.valor_reservado),
                    0
                ) AS valor_reservado

            FROM base b

            INNER JOIN top_grupos t
                ON t.grupo_principal =
                    COALESCE(
                        NULLIF(
                            TRIM(b."GrupoPrincipal"),
                            ''
                        ),
                        'Sin grupo'
                    )

            GROUP BY
                t.grupo_principal,
                COALESCE(
                    NULLIF(
                        TRIM(b."Capa_Obsolescencia"),
                        ''
                    ),
                    'Sin capa'
                )

            ORDER BY
                MAX(t.valor_stock) DESC,
                capa_obsolescencia
        """

        consulta_por_categoria = f"""
            {base_cte}

            SELECT
                COALESCE(
                    NULLIF(
                        TRIM("Categoria"),
                        ''
                    ),
                    'Sin categoría'
                ) AS categoria,

                COUNT(
                    DISTINCT NULLIF(
                        TRIM("CodProduto"),
                        ''
                    )
                ) AS productos,

                COALESCE(
                    SUM(COALESCE("QtdeEstoque", 0)),
                    0
                ) AS existencia,

                COALESCE(
                    SUM(COALESCE("VrEstoque", 0)),
                    0
                ) AS valor_inventario,

                COALESCE(
                    SUM(valor_stock),
                    0
                ) AS valor_stock

            FROM base

            GROUP BY
                COALESCE(
                    NULLIF(
                        TRIM("Categoria"),
                        ''
                    ),
                    'Sin categoría'
                )

            ORDER BY valor_inventario DESC

            LIMIT 12
        """

        consulta_por_antiguedad = f"""
            {base_cte},

            datos AS (
                SELECT
                    "CodProduto",
                    "QtdeEstoque",
                    "VrEstoque",
                    valor_stock,

                    CASE
                        WHEN "Dias_Desde_Ultimo_Movimiento" IS NULL
                            THEN 'Sin dato'
                        WHEN "Dias_Desde_Ultimo_Movimiento" <= 90
                            THEN '0-90 días'
                        WHEN "Dias_Desde_Ultimo_Movimiento" <= 180
                            THEN '91-180 días'
                        WHEN "Dias_Desde_Ultimo_Movimiento" <= 365
                            THEN '181-365 días'
                        WHEN "Dias_Desde_Ultimo_Movimiento" <= 730
                            THEN '366-730 días'
                        ELSE 'Más de 730 días'
                    END AS rango,

                    CASE
                        WHEN "Dias_Desde_Ultimo_Movimiento" IS NULL
                            THEN 6
                        WHEN "Dias_Desde_Ultimo_Movimiento" <= 90
                            THEN 1
                        WHEN "Dias_Desde_Ultimo_Movimiento" <= 180
                            THEN 2
                        WHEN "Dias_Desde_Ultimo_Movimiento" <= 365
                            THEN 3
                        WHEN "Dias_Desde_Ultimo_Movimiento" <= 730
                            THEN 4
                        ELSE 5
                    END AS orden

                FROM base
            )

            SELECT
                rango,

                COUNT(
                    DISTINCT NULLIF(
                        TRIM("CodProduto"),
                        ''
                    )
                ) AS productos,

                COALESCE(
                    SUM(COALESCE("QtdeEstoque", 0)),
                    0
                ) AS existencia,

                COALESCE(
                    SUM(COALESCE("VrEstoque", 0)),
                    0
                ) AS valor_inventario,

                COALESCE(
                    SUM(valor_stock),
                    0
                ) AS valor_stock

            FROM datos

            GROUP BY
                rango,
                orden

            ORDER BY orden
        """

        with connections[DB_ALIAS].cursor() as cursor:
            resultados_totales = ejecutar_dicts(
                cursor,
                consulta_totales,
                parametros,
            )

            por_capa = ejecutar_dicts(
                cursor,
                consulta_por_capa,
                parametros,
            )

            por_categoria_movimiento = ejecutar_dicts(
                cursor,
                consulta_por_categoria_movimiento,
                parametros,
            )

            por_agencia = ejecutar_dicts(
                cursor,
                consulta_por_agencia,
                parametros,
            )

            por_grupo = ejecutar_dicts(
                cursor,
                consulta_por_grupo,
                parametros,
            )

            por_grupo_capa = ejecutar_dicts(
                cursor,
                consulta_por_grupo_capa,
                parametros,
            )

            por_categoria = ejecutar_dicts(
                cursor,
                consulta_por_categoria,
                parametros,
            )

            por_antiguedad = ejecutar_dicts(
                cursor,
                consulta_por_antiguedad,
                parametros,
            )

        totales = (
            resultados_totales[0]
            if resultados_totales
            else {
                "registros": 0,
                "productos": 0,
                "qt_inventario": 0,
                "existencia": 0,
                "reservada": 0,
                "pedida": 0,
                "disponible": 0,
                "valor_inventario": 0,
                "valor_stock": 0,
                "valor_reservado": 0,
                "valor_disponible": 0,
                "valor_pendiente": 0,
                "valor_obsoleto": 0,
                "porcentaje_obsolescencia": 0,
                "relacion_reservada_pedida": 0,
                "promedio_dias_movimiento": 0,
            }
        )

        return Response({
            "totales": totales,
            "graficas": {
                "por_capa": por_capa,
                "por_categoria_movimiento":
                    por_categoria_movimiento,
                "por_agencia": por_agencia,
                "por_grupo": por_grupo,
                "por_grupo_capa": por_grupo_capa,
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
                    TRIM("{columna}") AS valor

                FROM {TABLA}

                WHERE "{columna}" IS NOT NULL
                  AND TRIM("{columna}") <> ''

                ORDER BY valor
            """

            cursor.execute(consulta)

            return [
                fila[0]
                for fila in cursor.fetchall()
                if fila[0]
            ]

        with connections[DB_ALIAS].cursor() as cursor:
            opciones = {
                "agencias": valores_distintos(
                    cursor,
                    "Agencia",
                ),
                "grupos_principales": valores_distintos(
                    cursor,
                    "GrupoPrincipal",
                ),
                "categorias": valores_distintos(
                    cursor,
                    "Categoria",
                ),
                "capas_obsolescencia": valores_distintos(
                    cursor,
                    "Capa_Obsolescencia",
                ),
                "categorias_movimiento": valores_distintos(
                    cursor,
                    "Categoria_Movimiento",
                ),
            }

        cache.set(
            CACHE_OPCIONES,
            opciones,
            300,
        )

        return Response(opciones)