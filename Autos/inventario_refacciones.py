from django.db import connections
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from CrmConformidad.jwt_authentication import CRMJWTAuthentication


TABLAS_INVENTARIO_REFACCIONES = {
    "VW Córdoba": "Cordoba_InventarioRefacciones",
    "VW Orizaba": "Orizaba_InventarioRefacciones",
    "VW Poza Rica": "PozaRica_InventarioRefacciones",
    "VW Tuxpan": "Tuxpan_InventarioRefacciones",
    "VW Tuxtepec": "Tuxtepec_InventarioRefacciones",
}


def dictfetchall(cursor):
    columnas = [col[0] for col in cursor.description]

    return [
        dict(zip(columnas, fila))
        for fila in cursor.fetchall()
    ]


class InventarioRefaccionesListView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        agencia = (request.GET.get("agencia") or "").strip()

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

        if agencia and agencia not in TABLAS_INVENTARIO_REFACCIONES:
            return Response(
                {"detail": "Agencia no válida."},
                status=400,
            )

        tablas = (
            {
                agencia:
                TABLAS_INVENTARIO_REFACCIONES[agencia]
            }
            if agencia
            else TABLAS_INVENTARIO_REFACCIONES
        )

        consultas = []

        for nombre_agencia, tabla in tablas.items():
            consultas.append(
                f"""
                SELECT
                    '{nombre_agencia}' AS agencia,
                    *
                FROM dbo.{tabla}
                """
            )

        union_sql = "\nUNION ALL\n".join(consultas)

        count_sql = f"""
            SELECT COUNT(*)
            FROM (
                {union_sql}
            ) AS piezas
        """

        data_sql = f"""
            SELECT *
            FROM (
                {union_sql}
            ) AS piezas
            ORDER BY
                agencia,
                CodProduto,
                rowid__
            OFFSET %s ROWS
            FETCH NEXT %s ROWS ONLY
        """

        with connections["sqlserver_inv"].cursor() as cursor:
            cursor.execute(count_sql)
            total = cursor.fetchone()[0]

            cursor.execute(
                data_sql,
                [offset, page_size],
            )

            resultados = dictfetchall(cursor)

            columnas = [
                col[0]
                for col in cursor.description
            ]

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
                    "agencias": list(
                        TABLAS_INVENTARIO_REFACCIONES.keys()
                    ),
                },
            }
        )