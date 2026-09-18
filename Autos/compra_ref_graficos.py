# Autos/compra_ref_graficos.py
import time

from django.db import connections
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from CrmConformidad.jwt_authentication import CRMJWTAuthentication

TABLA_COMPRA_REF_TIPIFICADA = "Matriz_CompraRef_Tipificada"

CATEGORIA_PLANTA = "VOLKSWAGEN DE MEXICO"

_TIPOS_NUMERICOS = {"float", "bigint", "decimal", "int", "smallint", "tinyint", "bit", "money", "smallmoney", "numeric", "real"}

_CACHE_COLUMNAS = {"ts": 0.0, "cols": None}


def columnas_tabla(cursor):
    cursor.execute(
        """
        SELECT COLUMN_NAME, DATA_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = %s
        ORDER BY ORDINAL_POSITION
        """,
        [TABLA_COMPRA_REF_TIPIFICADA],
    )
    return [(fila[0], fila[1]) for fila in cursor.fetchall()]


def columnas_con_datos(cursor):
    if _CACHE_COLUMNAS["cols"] is not None and time.time() - _CACHE_COLUMNAS["ts"] < 600:
        return _CACHE_COLUMNAS["cols"]

    columnas = columnas_tabla(cursor)
    expr = []
    for nombre, tipo in columnas:
        if tipo.lower() in _TIPOS_NUMERICOS:
            expr.append(
                f"SUM(CASE WHEN {nombre} IS NOT NULL AND {nombre} <> 0 THEN 1 ELSE 0 END)"
            )
        else:
            expr.append(
                f"SUM(CASE WHEN LTRIM(RTRIM(COALESCE(CAST({nombre} AS varchar(4000)), N''))) NOT IN (N'', N'0', N'00000000') THEN 1 ELSE 0 END)"
            )
    cursor.execute(
        f"SELECT {', '.join(expr)} FROM dbo.{TABLA_COMPRA_REF_TIPIFICADA}"
    )
    fila = cursor.fetchone()
    cols = [nombre for nombre, valor in zip((n for n, _ in columnas), fila) if (valor or 0) > 0]
    _CACHE_COLUMNAS["ts"] = time.time()
    _CACHE_COLUMNAS["cols"] = cols
    return cols


EXPR_ANIO = "SUBSTRING(REPLACE(CAST(DtEmissao AS varchar), '-', ''), 1, 4)"
EXPR_MES = "SUBSTRING(REPLACE(CAST(DtEmissao AS varchar), '-', ''), 5, 2)"


def dictfetchall(cursor):
    columnas = [col[0] for col in cursor.description]

    return [
        dict(zip(columnas, fila))
        for fila in cursor.fetchall()
    ]


class CompraRefGraficosView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        agencia = (request.GET.get("agencia") or "").strip()
        estado = (request.GET.get("estado") or "").strip()
        serie = (request.GET.get("serie") or "").strip()
        q = (request.GET.get("q") or "").strip()
        proveedor = (request.GET.get("proveedor") or "").strip()
        proveedor_nombre = (request.GET.get("proveedor_nombre") or "").strip()
        anio = (request.GET.get("anio") or "").strip()
        mes = (request.GET.get("mes") or "").strip()

        condiciones = []
        params = []

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

        if len(anio) == 4 and anio.isdigit():
            condiciones.append(f"{EXPR_ANIO} = %s")
            params.append(anio)

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

        def _where(tipo_operacion):
            base = " AND ".join(condiciones) if condiciones else None
            if base:
                return f"WHERE {tipo_operacion} AND {base}"
            return f"WHERE {tipo_operacion}"

        where_compra = _where("TpOper = N'C'")
        where_devol = _where("TpOper = N'D'")
        where_cd = _where("TpOper IN (N'C', N'D')")

        with connections["sqlserver_inv"].cursor() as cursor:
            lista_columnas = columnas_con_datos(cursor)

            cursor.execute(
                f"""
                SELECT
                    {EXPR_ANIO} AS anio,
                    CAST({EXPR_MES} AS int) AS mes,
                    ROUND(SUM(CASE WHEN CategoriaProveedor = N'{CATEGORIA_PLANTA}' THEN CAST(COALESCE(VrLiqTotal, 0) AS float) ELSE 0 END), 2) AS compras_planta,
                    ROUND(SUM(CASE WHEN CategoriaProveedor <> N'{CATEGORIA_PLANTA}' THEN CAST(COALESCE(VrLiqTotal, 0) AS float) ELSE 0 END), 2) AS compras_otros
                FROM dbo.{TABLA_COMPRA_REF_TIPIFICADA}
                {where_compra}
                GROUP BY
                    {EXPR_ANIO},
                    {EXPR_MES}
                ORDER BY anio, mes
                """,
                params,
            )
            por_mes = dictfetchall(cursor)

            cursor.execute(
                f"""
                SELECT
                    COUNT(*) AS registros,
                    ROUND(SUM(CAST(COALESCE(QtProdutos, 0) AS float)), 2) AS cantidad,
                    ROUND(SUM(CAST(COALESCE(VrLiqTotal, 0) AS float)), 2) AS valor_total,
                    SUM(CASE WHEN LTRIM(RTRIM(COALESCE(EstadoTipificacion, N''))) <> N'TIPIFICADO' THEN 1 ELSE 0 END) AS sin_tipificar,
                    COUNT(DISTINCT NULLIF(Agencia, N'')) AS agencias
                FROM dbo.{TABLA_COMPRA_REF_TIPIFICADA}
                {where_compra}
                """,
                params,
            )
            kpi_fila = cursor.fetchone()

            cursor.execute(
                f"""
                SELECT
                    NULLIF(LTRIM(RTRIM(COALESCE(GrupoPrincipal, N''))), N'') AS linea,
                    ROUND(SUM(CASE WHEN CategoriaProveedor = N'{CATEGORIA_PLANTA}' THEN CAST(COALESCE(VrLiqTotal, 0) AS float) ELSE 0 END), 2) AS planta,
                    ROUND(SUM(CASE WHEN CategoriaProveedor <> N'{CATEGORIA_PLANTA}' THEN CAST(COALESCE(VrLiqTotal, 0) AS float) ELSE 0 END), 2) AS otros,
                    ROUND(SUM(CAST(COALESCE(VrLiqTotal, 0) AS float)), 2) AS total
                FROM dbo.{TABLA_COMPRA_REF_TIPIFICADA}
                {where_compra}
                GROUP BY NULLIF(LTRIM(RTRIM(COALESCE(GrupoPrincipal, N''))), N'')
                ORDER BY total DESC
                """,
                params,
            )
            por_linea = dictfetchall(cursor)

            cursor.execute(
                f"""
                SELECT
                    CASE WHEN CategoriaProveedor = N'{CATEGORIA_PLANTA}' THEN N'planta' ELSE N'otros' END AS fuente,
                    ROUND(SUM(CAST(COALESCE(VrLiqTotal, 0) AS float)), 2) AS compras,
                    ROUND(SUM(CAST(COALESCE(QtProdutos, 0) AS float)), 2) AS cantidad
                FROM dbo.{TABLA_COMPRA_REF_TIPIFICADA}
                {where_compra}
                GROUP BY CASE WHEN CategoriaProveedor = N'{CATEGORIA_PLANTA}' THEN N'planta' ELSE N'otros' END
                """,
                params,
            )
            compras_fuente = {fila["fuente"]: fila for fila in dictfetchall(cursor)}

            cursor.execute(
                f"""
                SELECT
                    CASE WHEN CategoriaProveedor = N'{CATEGORIA_PLANTA}' THEN N'planta' ELSE N'otros' END AS fuente,
                    ROUND(SUM(CAST(COALESCE(VrLiqTotal, 0) AS float)), 2) AS devol,
                    ROUND(SUM(CAST(COALESCE(QtProdutos, 0) AS float)), 2) AS cantidad
                FROM dbo.{TABLA_COMPRA_REF_TIPIFICADA}
                {where_devol}
                GROUP BY CASE WHEN CategoriaProveedor = N'{CATEGORIA_PLANTA}' THEN N'planta' ELSE N'otros' END
                """,
                params,
            )
            devol_fuente = {fila["fuente"]: fila for fila in dictfetchall(cursor)}

            cursor.execute(
                f"""
                SELECT
                    linea,
                    tipificada,
                    ROUND(SUM(CASE WHEN TpOper = N'C' THEN CAST(COALESCE(VrLiqTotal, 0) AS float) ELSE 0 END), 2) AS compras,
                    ROUND(SUM(CASE WHEN TpOper = N'D' THEN CAST(COALESCE(VrLiqTotal, 0) AS float) ELSE 0 END), 2) AS devol,
                    ROUND(SUM(CASE WHEN TpOper = N'C' THEN CAST(COALESCE(VrLiqTotal, 0) AS float) ELSE -CAST(COALESCE(VrLiqTotal, 0) AS float) END), 2) AS neto
                FROM (
                    SELECT
                        CASE
                            WHEN NULLIF(LTRIM(RTRIM(COALESCE(GrupoPrincipal, N''))), N'') IS NULL
                                THEN CONCAT(N'SIN TIPIFICAR - ', NULLIF(LTRIM(RTRIM(COALESCE(Proveedor, N''))), N''))
                            ELSE LTRIM(RTRIM(GrupoPrincipal))
                        END AS linea,
                        CASE
                            WHEN NULLIF(LTRIM(RTRIM(COALESCE(GrupoPrincipal, N''))), N'') IS NULL THEN 0
                            ELSE 1
                        END AS tipificada,
                        TpOper,
                        VrLiqTotal
                    FROM dbo.{TABLA_COMPRA_REF_TIPIFICADA}
                    {where_cd}
                ) sub
                GROUP BY linea, tipificada
                HAVING ROUND(SUM(CASE WHEN TpOper = N'C' THEN CAST(COALESCE(VrLiqTotal, 0) AS float) ELSE -CAST(COALESCE(VrLiqTotal, 0) AS float) END), 2) > 0
                ORDER BY neto DESC
                """,
                params,
            )
            por_linea_neto = dictfetchall(cursor)

            opciones = {}
            cursor.execute(
                f"SELECT DISTINCT Agencia FROM dbo.{TABLA_COMPRA_REF_TIPIFICADA} "
                "WHERE NULLIF(Agencia, N'') IS NOT NULL ORDER BY Agencia"
            )
            opciones["agencias"] = [fila[0] for fila in cursor.fetchall()]

            cursor.execute(
                f"SELECT DISTINCT EstadoTipificacion FROM dbo.{TABLA_COMPRA_REF_TIPIFICADA} "
                "ORDER BY EstadoTipificacion"
            )
            opciones["estados"] = [fila[0] for fila in cursor.fetchall()]

            cursor.execute(
                f"SELECT DISTINCT Serie FROM dbo.{TABLA_COMPRA_REF_TIPIFICADA} "
                "WHERE LTRIM(RTRIM(COALESCE(Serie, N''))) <> N'' "
                "ORDER BY Serie"
            )
            opciones["series"] = [fila[0] for fila in cursor.fetchall()]

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

        opciones["proveedores"] = [
            valor
            for valor, _ in estadisticas_categorias
            if valor in ("VOLKSWAGEN DE MEXICO", "AUTOMOTRIZ R&R", "OTROS")
        ]
        opciones["proveedores_nombre"] = [
            {"proveedor": valor, "categoria": "OTROS", "n": total_n}
            for valor, total_n in estadisticas_categorias
            if valor not in ("VOLKSWAGEN DE MEXICO", "AUTOMOTRIZ R&R", "OTROS")
        ]

        def fila_neto(fuente):
            compras = compras_fuente.get(fuente, {}).get("compras", 0) or 0
            devol = devol_fuente.get(fuente, {}).get("devol", 0) or 0
            return {
                "compras": round(compras, 2),
                "devol": round(devol, 2),
                "neto": round(compras - devol, 2),
            }

        devoluciones = {
            "otros": fila_neto("otros"),
            "planta": fila_neto("planta"),
        }
        total_compras = round((devoluciones["otros"]["compras"] + devoluciones["planta"]["compras"]), 2)
        total_devol = round((devoluciones["otros"]["devol"] + devoluciones["planta"]["devol"]), 2)
        devoluciones["total"] = {
            "compras": total_compras,
            "devol": total_devol,
            "neto": round(total_compras - total_devol, 2),
        }

        return Response(
            {
                "por_mes": por_mes,
                "por_linea": por_linea,
                "por_linea_neto": por_linea_neto,
                "devoluciones": devoluciones,
                "kpi": {
                    "registros": kpi_fila[0],
                    "cantidad": kpi_fila[1],
                    "valor_total": kpi_fila[2],
                    "valor_neto": devoluciones["total"]["neto"],
                    "sin_tipificar": kpi_fila[3],
                    "agencias": kpi_fila[4],
                } if kpi_fila else {},
                "anio": anio or None,
                "mes": mes or None,
                "columnas": lista_columnas,
                "opciones": opciones,
            }
        )