# Autos/costo_venta.py
from django.db import connections
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from CrmConformidad.jwt_authentication import CRMJWTAuthentication

TABLA_KARDEX_REF = "Matriz_KardexRef"

TIPO_MOVIMIENTOS_VENTA = ("VO", "VB")


def _depurar(value):
    if value is None:
        return ""
    return str(value).strip()


class CostoVentaView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        agencia = _depurar(request.GET.get("agencia"))
        anio = _depurar(request.GET.get("anio"))
        mes = _depurar(request.GET.get("mes"))

        condiciones = ["TpFormaMov = 'S'", "TpMovimento IN ('VO', 'VB')"]
        params = []

        if agencia and agencia != "Todos":
            condiciones.append("Agencia = %s")
            params.append(agencia)

        if len(anio) == 4 and anio.isdigit():
            if len(mes) == 2 and mes.isdigit() and 1 <= int(mes) <= 12:
                condiciones.append("DtMovimento LIKE %s")
                params.append(f"{anio}{mes}%")
            else:
                condiciones.append("DtMovimento LIKE %s")
                params.append(f"{anio}%")

        where_sql = " AND ".join(condiciones)

        with connections["sqlserver_inv"].cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    COUNT(*) AS operaciones,
                    ROUND(SUM(CAST(VrMovEstoque AS float)), 2) AS costo_venta,
                    ROUND(SUM(CAST(QtMovEstoque AS float)), 2) AS cantidad
                FROM dbo.{TABLA_KARDEX_REF}
                WHERE {where_sql}
                """
                if not params
                else f"""
                SELECT
                    COUNT(*) AS operaciones,
                    ROUND(SUM(CAST(VrMovEstoque AS float)), 2) AS costo_venta,
                    ROUND(SUM(CAST(QtMovEstoque AS float)), 2) AS cantidad
                FROM dbo.{TABLA_KARDEX_REF}
                WHERE {where_sql}
                """,
                params or None,
            )
            fila = cursor.fetchone()

        return Response(
            {
                "costo_venta": fila[1] if fila else 0,
                "operaciones": fila[0] if fila else 0,
                "cantidad": fila[2] if fila else 0,
                "filtros": {
                    "agencia": agencia or None,
                    "anio": anio or None,
                    "mes": mes or None,
                },
            }
        )