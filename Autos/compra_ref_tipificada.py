# Autos/compra_ref_tipificada.py
import time

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
    """Devuelve las columnas de la tabla ordenadas, excluyendo las que no
    tienen ningun valor real (nulas, vacias, o todo ceros). El resultado se
    cachea en memoria por corto tiempo para no escanear la tabla completa en
    cada peticion."""
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


def dictfetchall(cursor):
    columnas = [col[0] for col in cursor.description]

    return [
        dict(zip(columnas, fila))
        for fila in cursor.fetchall()
    ]


def _fecha_entrada(value):
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    texto = String_or_vacio(value)
    if len(texto) == 8 and texto.isdigit():
        if texto == "00000000":
            return None
        return f"{texto[:4]}-{texto[4:6]}-{texto[6:]}"
    if len(texto) >= 10 and texto[4] == "-" and texto[7] == "-":
        return texto[:10]
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
        anio = (request.GET.get("anio") or "").strip()
        mes = (request.GET.get("mes") or "").strip()

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
            lista_columnas = columnas_con_datos(cursor)

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

        if len(anio) == 4 and anio.isdigit():
            if len(mes) == 2 and mes.isdigit() and 1 <= int(mes) <= 12:
                condiciones.append(
                    "SUBSTRING(REPLACE(CAST(DtEmissao AS varchar), '-', ''), 1, 6) = %s"
                )
                params.append(f"{anio}{mes}")
            else:
                condiciones.append(
                    "SUBSTRING(REPLACE(CAST(DtEmissao AS varchar), '-', ''), 1, 4) = %s"
                )
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
            SELECT {", ".join("t." + c for c in lista_columnas)}
            FROM dbo.{TABLA_COMPRA_REF_TIPIFICADA} AS t
            INNER JOIN (
                SELECT NrNota, Serie, DtEntrada, HrEntrada, rowid__
                FROM dbo.{TABLA_COMPRA_REF_TIPIFICADA}
                {where_sql}
                ORDER BY
                    DtEmissao DESC,
                    HrEntrada DESC,
                    NrNota DESC,
                    rowid__ DESC
                OFFSET %s ROWS
                FETCH NEXT %s ROWS ONLY
            ) AS p
                ON t.NrNota = p.NrNota
                AND t.Serie = p.Serie
                AND t.rowid__ = p.rowid__
            ORDER BY
                t.DtEmissao DESC,
                t.HrEntrada DESC,
                t.NrNota DESC,
                t.rowid__ DESC
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
            for clave in lista_columnas:
                if clave.startswith(("Dt", "DT_")):
                    fila[clave] = _fecha_entrada(fila.get(clave))
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
                "columns": lista_columnas,
                "results": resultados,
                "opciones": opciones,
            }
        )