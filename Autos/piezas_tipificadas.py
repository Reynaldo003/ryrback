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


class PiezasTipificadasListView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        agencia = (request.GET.get("agencia") or "").strip()

        if agencia and agencia == AGENCIA_CORDOBA:
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