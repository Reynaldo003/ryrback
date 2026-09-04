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

VISTA_PIEZAS_TIPIFICADAS = "vw_Cordoba_PiezasTipificadas"
AGENCIA_CORDOBA = "VW Córdoba"

COLUMNAS_VISTA = """
    CodProduto,
    CodigoProductoNormalizado,
    NombreInventario,
    DescripcionInventario,
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
    FechaActualizacionFabrica,
    ItemOriginal,
    GrupoPrincipal,
    Subgrupo,
    NombreEstandarizado,
    Categoria,
    Observacion
"""


def dictfetchall(cursor):
    columnas = [col[0] for col in cursor.description]

    return [
        dict(zip(columnas, fila))
        for fila in cursor.fetchall()
    ]


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
                GROUP BY REPLACE(CodProduto, N' ', N'')
            ),
            Dias AS (
                SELECT
                    VrEstoque,
                    QtdeEstoque,
                    DATEDIFF(
                        day,
                        COALESCE(
                            NULLIF(DtUltimaVenda, CAST('0001-01-01' AS date)),
                            NULLIF(DtUltimaCompra, CAST('0001-01-01' AS date))
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

        with connections["sqlserver_inv"].cursor() as cursor:
            cursor.execute(sql)
            filas = dictfetchall(cursor)

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

        return Response(
            {
                "fecha_calculo": date.today().isoformat(),
                "fuente": "Inventario Córdoba · SKU únicos",
                "capas": capas,
                "movimiento": movimiento,
                "distribucion_dias": distribucion_dias,
                "totales": totales,
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
        """

        data_sql = f"""
            SELECT {COLUMNAS_VISTA}
            FROM dbo.{VISTA_PIEZAS_TIPIFICADAS}
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