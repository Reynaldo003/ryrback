from datetime import date

from django.db import connections
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from CrmConformidad.jwt_authentication import CRMJWTAuthentication

from .inventario_refacciones import (
    InventarioRefaccionesListView,
    TABLAS_INVENTARIO_REFACCIONES,
)
from .productos_estoque import TABLAS_PRODUCTOS_ESTOQUE

VISTA_PIEZAS_TIPIFICADAS = "vw_Cordoba_PiezasTipificadas"
AGENCIA_CORDOBA = "VW Córdoba"
FECHA_NULA = "CAST('0001-01-01' AS date)"

NIVELES_JERARQUIA = ("dealer", "grupo_principal", "subgrupo", "producto")

# La vista puede repetir CodigoProductoNormalizado (variantes con espacios),
# por lo que se usa una versión deduplicada como catálogo maestro de la pieza.
VISTA_MAESTRO = f"""
    SELECT
        CodigoProductoNormalizado,
        MAX(GrupoPrincipal) AS GrupoPrincipal,
        MAX(Subgrupo) AS Subgrupo,
        MAX(
            COALESCE(
                NULLIF(NombreEstandarizado, N''),
                NULLIF(NombreInventario, N''),
                N''
            )
        ) AS NombreEstandarizado
    FROM dbo.{VISTA_PIEZAS_TIPIFICADAS}
    GROUP BY CodigoProductoNormalizado
"""

COLUMNAS_VISTA = """
    CodProduto,
    CodigoProductoNormalizado,
    NombreInventario,
    DescripcionInventario,
    ItemOriginal,
    GrupoPrincipal,
    Subgrupo,
    NombreEstandarizado,
    Categoria,
    Observacion,
    MarcaPeca,
    QtdeEstoque,
    QtReservada,
    QtPedida,
    VrEstoque,
    VrUnitarioMedio,
    FechaActualizacionEstoque,
    NombreFabrica,
    NmExpandido,
    PrecoPublico,
    PrecoRevenda,
    PrecoGarantia,
    PrecoVenda,
    FechaActualizacionFabrica
"""


def dictfetchall(cursor):
    columnas = [col[0] for col in cursor.description]

    return [
        dict(zip(columnas, fila))
        for fila in cursor.fetchall()
    ]


def _fuente_jerarquia(agencia):
    tablas = (
        {agencia: TABLAS_PRODUCTOS_ESTOQUE[agencia]}
        if agencia
        else TABLAS_PRODUCTOS_ESTOQUE
    )

    partes = []

    for nombre_agencia, tabla in tablas.items():
        nombre_literal = nombre_agencia.replace("'", "''")
        partes.append(
            f"""
            SELECT
                N'{nombre_literal}' AS agencia,
                REPLACE(E.CodProduto, N' ', N'') AS codigo,
                CAST(E.QtdeEstoque AS float) AS QtdeEstoque,
                CAST(E.VrEstoque AS float) AS VrEstoque,
                CAST(E.DtUltimaVenda AS date) AS DtUltimaVenda,
                CAST(E.DtUltimaCompra AS date) AS DtUltimaCompra,
                V.GrupoPrincipal,
                V.Subgrupo,
                COALESCE(V.NombreEstandarizado, N'') AS producto
            FROM dbo.{tabla} E
            LEFT JOIN (
                {VISTA_MAESTRO}
            ) V
                ON REPLACE(E.CodProduto, N' ', N'') = V.CodigoProductoNormalizado
            """
        )

    return "\nUNION ALL\n".join(partes)


def _literal_texto(value):
    return "N'" + value.replace("'", "''") + "'"


def _condicion_padre(columna, valor, sentinel):
    if not valor:
        return None
    if valor == sentinel:
        return f"({columna} IS NULL OR {columna} = N'')"
    return f"{columna} = {_literal_texto(valor)}"


def _clave_y_grupo_nivel(nivel):
    if nivel == "dealer":
        return "F.agencia", "F.agencia"
    if nivel == "grupo_principal":
        expr = "COALESCE(NULLIF(F.GrupoPrincipal, N''), N'Sin grupo')"
        return expr, expr
    if nivel == "subgrupo":
        expr = "COALESCE(NULLIF(F.Subgrupo, N''), N'Sin subgrupo')"
        return expr, expr
    # producto
    return "F.codigo", "F.codigo"


class PiezasObsolescenciaListView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        sql = f"""
            WITH Estoque AS (
                SELECT
                    REPLACE(CodProduto, N' ', N'') AS CodigoJoin,
                    SUM(QtdeEstoque) AS QtdeEstoque,
                    SUM(VrEstoque) AS VrEstoque,
                    MAX(DtUltimaVenda) AS DtUltimaVenda,
                    MAX(DtUltimaCompra) AS DtUltimaCompra
                FROM dbo.Cordoba_ProductosEstoque
                WHERE NULLIF(REPLACE(CodProduto, N' ', N''), N'') IS NOT NULL
                  AND QtdeEstoque > 0
                GROUP BY REPLACE(CodProduto, N' ', N'')
            ),
            Dias AS (
                SELECT
                    VrEstoque,
                    QtdeEstoque,
                    DATEDIFF(
                        day,
                        COALESCE(
                            NULLIF(DtUltimaVenda, {FECHA_NULA}),
                            NULLIF(DtUltimaCompra, {FECHA_NULA})
                        ),
                        CAST(GETDATE() AS date)
                    ) AS dias
                FROM Estoque
            )
            SELECT 'capa' AS tipo,
                CASE
                    WHEN dias IS NULL THEN 'O'
                    WHEN dias < 180 THEN 'A'
                    WHEN dias <= 365 THEN 'B'
                    ELSE 'O'
                END AS grupo,
                COUNT(*) AS cantidad,
                SUM(VrEstoque) AS valor,
                SUM(QtdeEstoque) AS unidades
            FROM Dias
            GROUP BY CASE
                WHEN dias IS NULL THEN 'O'
                WHEN dias < 180 THEN 'A'
                WHEN dias <= 365 THEN 'B'
                ELSE 'O'
            END

            UNION ALL

            SELECT 'movimiento' AS tipo,
                CASE
                    WHEN dias <= 180 THEN 'rapido'
                    WHEN dias <= 365 THEN 'lento'
                    ELSE 'obsoleto'
                END AS grupo,
                COUNT(*),
                SUM(VrEstoque),
                SUM(QtdeEstoque)
            FROM Dias
            GROUP BY CASE
                WHEN dias <= 180 THEN 'rapido'
                WHEN dias <= 365 THEN 'lento'
                ELSE 'obsoleto'
            END

            UNION ALL

            SELECT 'dias' AS tipo,
                CASE
                    WHEN dias IS NULL THEN 'sin_referencia'
                    WHEN dias <= 30 THEN '0_30'
                    WHEN dias <= 90 THEN '31_90'
                    WHEN dias <= 180 THEN '91_180'
                    WHEN dias <= 365 THEN '181_365'
                    ELSE 'mas_365'
                END AS grupo,
                COUNT(*),
                SUM(VrEstoque),
                SUM(QtdeEstoque)
            FROM Dias
            GROUP BY CASE
                WHEN dias IS NULL THEN 'sin_referencia'
                WHEN dias <= 30 THEN '0_30'
                WHEN dias <= 90 THEN '31_90'
                WHEN dias <= 180 THEN '91_180'
                WHEN dias <= 365 THEN '181_365'
                ELSE 'mas_365'
            END
        """

        sql_top = f"""
            WITH Estoque AS (
                SELECT
                    REPLACE(CodProduto, N' ', N'') AS CodigoJoin,
                    SUM(QtdeEstoque) AS QtdeEstoque,
                    SUM(VrEstoque) AS VrEstoque,
                    MAX(DtUltimaVenda) AS DtUltimaVenda,
                    MAX(DtUltimaCompra) AS DtUltimaCompra
                FROM dbo.Cordoba_ProductosEstoque
                WHERE NULLIF(REPLACE(CodProduto, N' ', N''), N'') IS NOT NULL
                  AND QtdeEstoque > 0
                GROUP BY REPLACE(CodProduto, N' ', N'')
            )
            SELECT TOP 15
                E.CodigoJoin AS codigo,
                COALESCE(V.NombreEstandarizado, N'') AS producto,
                E.VrEstoque AS valor,
                E.QtdeEstoque AS unidades,
                DATEDIFF(
                    day,
                    COALESCE(
                        NULLIF(E.DtUltimaVenda, {FECHA_NULA}),
                        NULLIF(E.DtUltimaCompra, {FECHA_NULA})
                    ),
                    CAST(GETDATE() AS date)
                ) AS dias_sin_venta
            FROM Estoque E
            LEFT JOIN (
                {VISTA_MAESTRO}
            ) V
                ON E.CodigoJoin = V.CodigoProductoNormalizado
            WHERE (
                    DATEDIFF(
                        day,
                        COALESCE(
                            NULLIF(E.DtUltimaVenda, {FECHA_NULA}),
                            NULLIF(E.DtUltimaCompra, {FECHA_NULA})
                        ),
                        CAST(GETDATE() AS date)
                    ) > 365
                    OR DATEDIFF(
                        day,
                        COALESCE(
                            NULLIF(E.DtUltimaVenda, {FECHA_NULA}),
                            NULLIF(E.DtUltimaCompra, {FECHA_NULA})
                        ),
                        CAST(GETDATE() AS date)
                    ) IS NULL
                )
            ORDER BY E.VrEstoque DESC
        """

        with connections["sqlserver_inv"].cursor() as cursor:
            cursor.execute(sql)
            filas = dictfetchall(cursor)

            cursor.execute(sql_top)
            top_obsoletos = dictfetchall(cursor)

        capas = [f for f in filas if f["tipo"] == "capa"]
        movimiento = [f for f in filas if f["tipo"] == "movimiento"]
        distribucion_dias = [f for f in filas if f["tipo"] == "dias"]

        for f in capas:
            f["capa"] = f.pop("grupo")
            f.pop("tipo", None)
        for f in movimiento:
            f["categoria"] = f.pop("grupo")
            f.pop("tipo", None)
        for f in distribucion_dias:
            f["rango"] = f.pop("grupo")
            f.pop("tipo", None)

        orden_capas = {"A": 0, "B": 1, "O": 2}
        capas.sort(key=lambda c: orden_capas.get(c["capa"], 9))

        orden_movimiento = {
            "rapido": 0,
            "lento": 1,
            "obsoleto": 2,
        }
        movimiento.sort(key=lambda m: orden_movimiento.get(m["categoria"], 9))

        orden_dias = {
            "0_30": 0,
            "31_90": 1,
            "91_180": 2,
            "181_365": 3,
            "mas_365": 4,
            "sin_referencia": 5,
        }
        distribucion_dias.sort(key=lambda r: orden_dias.get(r["rango"], 9))

        totales = {
            "cantidad": sum(c["cantidad"] or 0 for c in capas),
            "valor": sum(c["valor"] or 0 for c in capas),
            "unidades": sum(c["unidades"] or 0 for c in capas),
        }

        capa_obsoleta = next(
            (c for c in capas if c["capa"] == "O"),
            {"cantidad": 0, "valor": 0, "unidades": 0},
        )

        valor_total_inventario = totales["valor"] or 0

        inventario_obsoleto = {
            "valor_total_inventario": valor_total_inventario,
            "valor_obsoleto": capa_obsoleta["valor"] or 0,
            "pct_obsoleto": (
                round((capa_obsoleta["valor"] / valor_total_inventario) * 100, 1)
                if valor_total_inventario
                else 0
            ),
            "cantidad_sku": capa_obsoleta["cantidad"] or 0,
            "unidades": capa_obsoleta["unidades"] or 0,
            "dias_limite": 365,
            "top_skus": [
                {
                    "codigo": f.get("codigo") or "",
                    "producto": f.get("producto") or "",
                    "valor": f.get("valor") or 0,
                    "unidades": f.get("unidades") or 0,
                    "dias_sin_venta": (
                        f.get("dias_sin_venta")
                        if f.get("dias_sin_venta") is not None
                        else None
                    ),
                }
                for f in top_obsoletos
            ],
        }

        return Response(
            {
                "fecha_calculo": date.today().isoformat(),
                "fuente": "Inventario Córdoba · SKU únicos con existencia",
                "capas": capas,
                "movimiento": movimiento,
                "distribucion_dias": distribucion_dias,
                "inventario_obsoleto": inventario_obsoleto,
                "totales": totales,
            }
        )


class PiezasJerarquiaListView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        nivel = (request.GET.get("nivel") or "dealer").strip().lower()
        if nivel not in NIVELES_JERARQUIA:
            nivel = "dealer"

        agencia = (request.GET.get("agencia") or "").strip()
        grupo = (request.GET.get("grupo_principal") or "").strip()
        subgrupo = (request.GET.get("subgrupo") or "").strip()

        if agencia and agencia not in TABLAS_PRODUCTOS_ESTOQUE:
            return Response(
                {"detail": "Agencia no válida."},
                status=400,
            )

        if nivel == "subgrupo" and not grupo:
            return Response(
                {"detail": "Se requiere grupo_principal para el nivel subgrupo."},
                status=400,
            )
        if nivel == "producto" and not (grupo and subgrupo):
            return Response(
                {
                    "detail":
                    "Se requiere grupo_principal y subgrupo para el nivel producto."
                },
                status=400,
            )

        condiciones = []

        if agencia:
            condiciones.append(
                f"F.agencia = {_literal_texto(agencia)}"
            )

        if nivel in ("subgrupo", "producto"):
            condicion = _condicion_padre(
                "F.GrupoPrincipal", grupo, "Sin grupo"
            )
            if condicion:
                condiciones.append(condicion)

        if nivel == "producto":
            condicion = _condicion_padre(
                "F.Subgrupo", subgrupo, "Sin subgrupo"
            )
            if condicion:
                condiciones.append(condicion)

        clave_expr, grupo_expr = _clave_y_grupo_nivel(nivel)

        where_sql = (
            f"WHERE {' AND '.join(condiciones)}"
            if condiciones
            else ""
        )

        sql = f"""
            WITH Base AS (
                {_fuente_jerarquia(agencia)}
            ),
            Filtrada AS (
                SELECT *,
                    DATEDIFF(
                        day,
                        COALESCE(
                            NULLIF(DtUltimaVenda, {FECHA_NULA}),
                            NULLIF(DtUltimaCompra, {FECHA_NULA})
                        ),
                        CAST(GETDATE() AS date)
                    ) AS dias
                FROM Base
                WHERE NULLIF(codigo, N'') IS NOT NULL
                  AND QtdeEstoque > 0
            )
            SELECT
                {clave_expr} AS clave,
                {grupo_expr} AS nombre,
                SUM(F.VrEstoque) AS valor_inventario,
                SUM(
                    CASE
                        WHEN F.dias > 365 OR F.dias IS NULL
                        THEN F.VrEstoque ELSE 0 END
                ) AS valor_obsoleto,
                COUNT(DISTINCT F.codigo) AS cantidad_sku,
                SUM(F.QtdeEstoque) AS unidades,
                SUM(
                    F.VrEstoque * CASE
                        WHEN F.dias IS NULL THEN NULL ELSE F.dias END
                ) / NULLIF(
                    SUM(
                        CASE
                            WHEN F.dias IS NOT NULL
                            THEN F.VrEstoque ELSE 0 END
                    ),
                    0
                ) AS dias_sin_venta,
                MAX(
                    COALESCE(
                        NULLIF(F.DtUltimaVenda, {FECHA_NULA}),
                        NULLIF(F.DtUltimaCompra, {FECHA_NULA})
                    )
                ) AS ultima_venta
            FROM Filtrada F
            {where_sql}
            GROUP BY {grupo_expr}
            ORDER BY SUM(F.VrEstoque) DESC
        """

        with connections["sqlserver_inv"].cursor() as cursor:
            cursor.execute(sql)
            filas = dictfetchall(cursor)

        resultados = []
        for fila in filas:
            resultados.append(
                {
                    "clave": fila["clave"],
                    "nombre": fila["nombre"],
                    "valor_inventario": fila["valor_inventario"] or 0,
                    "valor_obsoleto": fila["valor_obsoleto"] or 0,
                    "cantidad_sku": fila["cantidad_sku"] or 0,
                    "unidades": fila["unidades"] or 0,
                    "dias_sin_venta": (
                        round(float(fila["dias_sin_venta"]), 1)
                        if fila["dias_sin_venta"] is not None
                        else None
                    ),
                    "ultima_venta": (
                        fila["ultima_venta"].isoformat()
                        if fila["ultima_venta"]
                        else None
                    ),
                }
            )

        totales = {
            "valor_inventario": sum(
                r["valor_inventario"] for r in resultados
            ),
            "valor_obsoleto": sum(
                r["valor_obsoleto"] for r in resultados
            ),
            "cantidad_sku": sum(r["cantidad_sku"] for r in resultados),
            "unidades": sum(r["unidades"] for r in resultados),
            "pct_obsoleto": (
                round(
                    (
                        sum(r["valor_obsoleto"] for r in resultados)
                        / sum(r["valor_inventario"] for r in resultados)
                    )
                    * 100,
                    1,
                )
                if sum(r["valor_inventario"] for r in resultados)
                else 0
            ),
        }

        return Response(
            {
                "nivel": nivel,
                "agencia": agencia or None,
                "grupo_principal": grupo or None,
                "subgrupo": subgrupo or None,
                "niveles": list(NIVELES_JERARQUIA),
                "totales": totales,
                "results": resultados,
            }
        )


class PiezasTipificadasListView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        agencia = (request.GET.get("agencia") or "").strip()

        if not agencia or agencia == AGENCIA_CORDOBA:
            return self._consulta_vista(request)

        return InventarioRefaccionesListView().get(request)

    def _consulta_vista(self, request):
        try:
            page = max(int(request.GET.get("page", 1)), 1)
        except (TypeError, ValueError):
            page = 1

        try:
            page_size = int(request.GET.get("page_size", 50))
        except (TypeError, ValueError):
            page_size = 50

        page_size = min(max(page_size, 1), 200)
        offset = (page - 1) * page_size

        count_sql = f"""
            SELECT COUNT(*)
            FROM dbo.{VISTA_PIEZAS_TIPIFICADAS}
            WHERE QtdeEstoque > 0
        """

        data_sql = f"""
            SELECT {COLUMNAS_VISTA}
            FROM dbo.{VISTA_PIEZAS_TIPIFICADAS}
            WHERE QtdeEstoque > 0
            ORDER BY
                CodigoProductoNormalizado,
                CodProduto,
                NombreInventario
            OFFSET %s ROWS
            FETCH NEXT %s ROWS ONLY
        """

        with connections["sqlserver_inv"].cursor() as cursor:
            cursor.execute(count_sql)
            total = cursor.fetchone()[0]

            cursor.execute(data_sql, [offset, page_size])
            resultados = dictfetchall(cursor)
            columnas = [col[0] for col in cursor.description]

        return Response(
            {
                "count": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (
                    (total + page_size - 1) // page_size
                    if total
                    else 0
                ),
                "columns": columnas,
                "results": resultados,
                "opciones": {
                    "agencias": list(TABLAS_INVENTARIO_REFACCIONES.keys()),
                },
            }
        )
        
#OLA OLA PROBANDO 123