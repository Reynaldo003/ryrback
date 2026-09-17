# Autos/compra_ref_tipificada.py
from django.db import connections
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from CrmConformidad.jwt_authentication import CRMJWTAuthentication

TABLA_COMPRA_REF_TIPIFICADA = "Matriz_CompraRef_Tipificada"

CATEGORIAS_PROVEEDOR_MAIN = (
    "VOLKSWAGEN DE MEXICO",
    "AUTOMOTRIZ R&R",
    "OTROS",
)

COLUMNAS_TABLA = """
    Agencia,
    NrNota,
    Serie,
    DtEntrada,
    HrEntrada,
    TpCompra,
    NrPedCompra,
    ProdServ,
    CodProducto,
    DescrProd,
    NombreEstandarizado,
    GrupoPrincipal,
    Subgrupo,
    Categoria,
    EstadoTipificacion,
    TpProduto,
    Unidade,
    QtProdutos,
    VrUnitLiq,
    VrUnitBruto,
    VrDescontos,
    VrLiqTotal,
    VrMovEstoq,
    Cant_pzas_recib,
    Proveedor,
    CategoriaProveedor,
    rowid__
"""


def dictfetchall(cursor):
    columnas = [col[0] for col in cursor.description]

    return [
        dict(zip(columnas, fila))
        for fila in cursor.fetchall()
    ]


def _fecha_entrada(value):
    texto = String_or_vacio(value)
    if len(texto) == 8 and texto.isdigit():
        return f"{texto[:4]}-{texto[4:6]}-{texto[6:]}"
    return texto or None


def _hora_entrada(value):
    try:
        segundos = int(value or 0)
    except (TypeError, ValueError):
        return None
    if segundos <= 0:
        return None
    horas = segundos // 3600
    minutos = (segundos % 3600) // 60
    segs = segundos % 60
    return f"{horas:02d}:{minutos:02d}:{segs:02d}"


def String_or_vacio(value):
    if value is None:
        return ""
    return str(value).strip()


class CompraRefTipificadaListView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        agencia = (request.GET.get("agencia") or "").strip()
        estado = (request.GET.get("estado") or "").strip()
        serie = (request.GET.get("serie") or "").strip()
        q = (request.GET.get("q") or "").strip()
        proveedor = (request.GET.get("proveedor") or "").strip()
        proveedor_nombre = (request.GET.get("proveedor_nombre") or "").strip()

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

        condiciones = []
        params = []

        with connections["sqlserver_inv"].cursor() as cursor:
            cursor.execute(
                f"SELECT DISTINCT Agencia FROM dbo.{TABLA_COMPRA_REF_TIPIFICADA} "
                "WHERE NULLIF(Agencia, N'') IS NOT NULL ORDER BY Agencia"
            )
            lista_agencias = [fila[0] for fila in cursor.fetchall()]

        if agencia and agencia != "Todos":
            condiciones.append("Agencia = %s")
            params.append(agencia)

        if proveedor_nombre and proveedor_nombre != "Todos":
            condiciones.append("(CategoriaProveedor = %s OR Proveedor = %s)")
            params.extend([proveedor_nombre, proveedor_nombre])
        elif proveedor and proveedor != "Todos":
            condiciones.append("CategoriaProveedor = %s")
            params.append(proveedor)

        if estado and estado != "Todos":
            condiciones.append("EstadoTipificacion = %s")
            params.append(estado)

        if serie and serie != "Todos":
            condiciones.append("Serie = %s")
            params.append(serie)

        if q:
            like = f"%{q}%"
            condiciones.append(
                """
                (
                    COALESCE(NrPedCompra, N'') LIKE %s
                    OR COALESCE(ProdServ, N'') LIKE %s
                    OR COALESCE(CodProducto, N'') LIKE %s
                    OR COALESCE(DescrProd, N'') LIKE %s
                    OR COALESCE(NombreEstandarizado, N'') LIKE %s
                    OR COALESCE(GrupoPrincipal, N'') LIKE %s
                    OR COALESCE(Subgrupo, N'') LIKE %s
                    OR COALESCE(Categoria, N'') LIKE %s
                    OR COALESCE(Proveedor, N'') LIKE %s
                    OR CAST(NrNota AS varchar) LIKE %s
                    OR COALESCE(Serie, N'') LIKE %s
                    OR COALESCE(Agencia, N'') LIKE %s
                )
                """
            )
            params.extend([like] * 12)

        where_sql = (
            f"WHERE {' AND '.join(condiciones)}"
            if condiciones
            else ""
        )

        count_sql = f"""
            SELECT COUNT(*)
            FROM dbo.{TABLA_COMPRA_REF_TIPIFICADA}
            {where_sql}
        """

        data_sql = f"""
            SELECT {COLUMNAS_TABLA}
            FROM dbo.{TABLA_COMPRA_REF_TIPIFICADA}
            {where_sql}
            ORDER BY
                DtEntrada DESC,
                HrEntrada DESC,
                NrNota DESC,
                rowid__ DESC
            OFFSET %s ROWS
            FETCH NEXT %s ROWS ONLY
        """

        opciones_sql = {
            "estados": (
                "SELECT DISTINCT EstadoTipificacion FROM dbo.{tabla} "
                "ORDER BY EstadoTipificacion"
            ),
            "series": (
                "SELECT DISTINCT Serie FROM dbo.{tabla} "
                "WHERE LTRIM(RTRIM(COALESCE(Serie, N''))) <> N'' "
                "ORDER BY Serie"
            ),
            "proveedores": (
                "SELECT DISTINCT CategoriaProveedor FROM dbo.{tabla} "
                "WHERE LTRIM(RTRIM(COALESCE(CategoriaProveedor, N''))) <> N'' "
                "ORDER BY CategoriaProveedor"
            ),
        }

        with connections["sqlserver_inv"].cursor() as cursor:
            cursor.execute(count_sql, params)
            total = cursor.fetchone()[0]

            cursor.execute(data_sql, params + [offset, page_size])
            resultados = dictfetchall(cursor)
            columnas = [col[0] for col in cursor.description]

            opciones = {"agencias": lista_agencias}
            for clave, plantilla in opciones_sql.items():
                cursor.execute(plantilla.format(tabla=TABLA_COMPRA_REF_TIPIFICADA))
                opciones[clave] = [fila[0] for fila in cursor.fetchall()]

            cursor.execute(
                f"""
                SELECT CategoriaProveedor, COUNT(*) AS n
                FROM dbo.{TABLA_COMPRA_REF_TIPIFICADA}
                WHERE LTRIM(RTRIM(COALESCE(CategoriaProveedor, N''))) <> N''
                GROUP BY CategoriaProveedor
                ORDER BY n DESC
                """
            )
            estadisticas_categorias = cursor.fetchall()

            principales = set(CATEGORIAS_PROVEEDOR_MAIN)
            opciones["proveedores"] = [
                valor
                for valor, _ in estadisticas_categorias
                if valor in principales
            ]
            opciones["proveedores_nombre"] = [
                {"proveedor": valor, "categoria": "OTROS", "n": total_n}
                for valor, total_n in estadisticas_categorias
                if valor not in principales
            ]

        for fila in resultados:
            fila["DtEntrada"] = _fecha_entrada(fila.get("DtEntrada"))
            fila["HrEntrada"] = _hora_entrada(fila.get("HrEntrada"))

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
                "opciones": opciones,
            }
        )