# inventario/views.py
from django.db import connections
from django.http import JsonResponse


AGENCIAS = {
    "2923": "Córdoba",
    "2924": "Orizaba",
    "1905": "Tuxtepec",
    "2927": "Poza Rica",
    "2929": "Tuxpan",
}

ESTATUS_STOCK = {
    "V": "Vendido",
    "E": "En Stock",
    "T": "En Tránsito",
    "P": "Programado",
    "O": "Otra Localidad",
    "X": "En Exposición",
    "D": "Devuelto",
    "C": "En Consignación",
}

ESTATUS_EXCLUIDOS = [
    "V",
    "O",
    "C",
    "D",
    "P",
    "T",
]


def _filtros_desde_request(request, solo_activos=False):
    condiciones = [
        "DN_Atual IS NOT NULL",
        "LTRIM(RTRIM(DN_Atual)) <> ''",
        "LTRIM(RTRIM(DN_Atual)) <> '0'",
    ]

    parametros = []

    agencia = request.GET.get("agencia")

    if agencia:
        condiciones.append("LTRIM(RTRIM(DN_Atual)) = %s")
        parametros.append(agencia)

    estatus = request.GET.get("estatus")

    if estatus:
        condiciones.append("LTRIM(RTRIM(StEstoque)) = %s")
        parametros.append(estatus)

    if solo_activos:
        placeholders = ", ".join(
            ["%s"] * len(ESTATUS_EXCLUIDOS)
        )

        condiciones.append(
            f"""
            LTRIM(RTRIM(COALESCE(StEstoque, '')))
            NOT IN ({placeholders})
            """
        )

        parametros.extend(ESTATUS_EXCLUIDOS)

    return " AND ".join(condiciones), parametros


def _agencia_nombre(codigo):
    codigo = str(codigo or "").strip()
    return AGENCIAS.get(codigo, codigo or "Sin agencia")


def _estatus_nombre(codigo):
    codigo = str(codigo or "").strip()
    return ESTATUS_STOCK.get(
        codigo,
        codigo or "Sin estatus",
    )


def get_inventario(request):
    """
    Regresa el inventario activo.

    La antigüedad se calcula directamente en SQL Server porque
    DtFaturamento está almacenado como nvarchar.

    Soporta:
    - YYYY-MM-DD HH:MM:SS
    - YYYY-MM-DD
    - YYYYMMDD
    """

    where_sql, parametros = _filtros_desde_request(
        request,
        solo_activos=True,
    )

    query = f"""
        SELECT
            v.DN_Atual,
            v.NrChassi,
            v.NmFamilia,
            v.NmMarca,
            v.SitVeiculo,
            v.StEstoque,
            v.TpNacImp,
            v.ModalVda,
            v.EdiModelo,
            v.CondUso,

            CASE
                WHEN f.FechaFacturacion IS NULL
                    THEN NULL
                WHEN f.FechaFacturacion < CONVERT(DATE, '19000101', 112)
                    THEN NULL
                ELSE CONVERT(
                    VARCHAR(10),
                    f.FechaFacturacion,
                    23
                )
            END AS DtFaturamento,

            CASE
                WHEN f.FechaFacturacion IS NULL
                    THEN NULL
                WHEN f.FechaFacturacion < CONVERT(DATE, '19000101', 112)
                    THEN NULL
                WHEN f.FechaFacturacion > CAST(GETDATE() AS DATE)
                    THEN NULL
                ELSE DATEDIFF(
                    DAY,
                    f.FechaFacturacion,
                    CAST(GETDATE() AS DATE)
                )
            END AS diasEnStock,

            v.VrNF_Compra

        FROM dbo.Listado_Vehiculos_VW v

        OUTER APPLY (
            SELECT
                COALESCE(
                    TRY_CONVERT(
                        DATE,
                        LEFT(
                            LTRIM(RTRIM(v.DtFaturamento)),
                            10
                        ),
                        23
                    ),
                    TRY_CONVERT(
                        DATE,
                        LEFT(
                            LTRIM(RTRIM(v.DtFaturamento)),
                            8
                        ),
                        112
                    )
                ) AS FechaFacturacion
        ) f

        WHERE {where_sql}
        AND NmMarca = 'VOLKSWAGEN'
        AND SitVeiculo = 'L'

        ORDER BY
            diasEnStock DESC,
            v.DN_Atual,
            v.NrChassi
    """

    with connections["sqlserver_inv"].cursor() as cursor:
        cursor.execute(query, parametros)

        columns = [
            column[0]
            for column in cursor.description
        ]

        rows = [
            dict(zip(columns, row))
            for row in cursor.fetchall()
        ]

    for row in rows:
        row["DN_Atual"] = str(
            row.get("DN_Atual") or ""
        ).strip()

        row["StEstoque"] = str(
            row.get("StEstoque") or ""
        ).strip()

        row["CondUso"] = str(
            row.get("CondUso") or ""
        ).strip()

        row["agenciaNombre"] = _agencia_nombre(
            row.get("DN_Atual")
        )

        row["estatusNombre"] = _estatus_nombre(
            row.get("StEstoque")
        )

        if row.get("VrNF_Compra") is not None:
            row["VrNF_Compra"] = float(
                row["VrNF_Compra"]
            )

        if row.get("diasEnStock") is not None:
            row["diasEnStock"] = int(
                row["diasEnStock"]
            )

    return JsonResponse({
        "data": rows
    })


def get_inventario_costo(request):
    where_sql, parametros = _filtros_desde_request(
        request,
        solo_activos=True,
    )

    query = f"""
        SELECT
            COALESCE(
                SUM(VrNF_Compra),
                0
            ) AS costo_total

        FROM dbo.Listado_Vehiculos_VW

        WHERE {where_sql}
        AND NmMarca = 'VOLKSWAGEN'
    """

    with connections["sqlserver_inv"].cursor() as cursor:
        cursor.execute(query, parametros)
        row = cursor.fetchone()

    costo_total = (
        float(row[0])
        if row and row[0] is not None
        else 0
    )

    return JsonResponse({
        "costo_total": costo_total
    })


def get_inventario_antiguedad(request):
    """
    Calcula directamente en SQL Server la antigüedad.

    Así evitamos volver a convertir las fechas en Python.
    """

    where_sql, parametros = _filtros_desde_request(
        request,
        solo_activos=True,
    )

    query = f"""
        SELECT
            CASE
                WHEN DATEDIFF(
                    DAY,
                    f.FechaFacturacion,
                    CAST(GETDATE() AS DATE)
                ) <= 30
                    THEN '0-30'

                WHEN DATEDIFF(
                    DAY,
                    f.FechaFacturacion,
                    CAST(GETDATE() AS DATE)
                ) <= 60
                    THEN '31-60'

                WHEN DATEDIFF(
                    DAY,
                    f.FechaFacturacion,
                    CAST(GETDATE() AS DATE)
                ) <= 90
                    THEN '61-90'

                WHEN DATEDIFF(
                    DAY,
                    f.FechaFacturacion,
                    CAST(GETDATE() AS DATE)
                ) <= 120
                    THEN '91-120'

                ELSE '+120'
            END AS rango,

            COUNT(*) AS total

        FROM dbo.Listado_Vehiculos_VW v

        OUTER APPLY (
            SELECT
                COALESCE(
                    TRY_CONVERT(
                        DATE,
                        LEFT(
                            LTRIM(RTRIM(v.DtFaturamento)),
                            10
                        ),
                        23
                    ),
                    TRY_CONVERT(
                        DATE,
                        LEFT(
                            LTRIM(RTRIM(v.DtFaturamento)),
                            8
                        ),
                        112
                    )
                ) AS FechaFacturacion
        ) f

        WHERE {where_sql}

          AND f.FechaFacturacion IS NOT NULL

          AND f.FechaFacturacion >=
              CONVERT(DATE, '19000101', 112)

          AND f.FechaFacturacion <=
              CAST(GETDATE() AS DATE)
          AND NmMarca = 'VOLKSWAGEN'

        GROUP BY
            CASE
                WHEN DATEDIFF(
                    DAY,
                    f.FechaFacturacion,
                    CAST(GETDATE() AS DATE)
                ) <= 30
                    THEN '0-30'

                WHEN DATEDIFF(
                    DAY,
                    f.FechaFacturacion,
                    CAST(GETDATE() AS DATE)
                ) <= 60
                    THEN '31-60'

                WHEN DATEDIFF(
                    DAY,
                    f.FechaFacturacion,
                    CAST(GETDATE() AS DATE)
                ) <= 90
                    THEN '61-90'

                WHEN DATEDIFF(
                    DAY,
                    f.FechaFacturacion,
                    CAST(GETDATE() AS DATE)
                ) <= 120
                    THEN '91-120'

                ELSE '+120'
            END
    """

    with connections["sqlserver_inv"].cursor() as cursor:
        cursor.execute(query, parametros)
        rows = cursor.fetchall()

    buckets = {
        "0-30": 0,
        "31-60": 0,
        "61-90": 0,
        "91-120": 0,
        "+120": 0,
    }

    for rango, total in rows:
        if rango in buckets:
            buckets[rango] = int(total)

    data = [
        {
            "rango": rango,
            "total": total,
        }
        for rango, total in buckets.items()
    ]

    return JsonResponse({
        "data": data
    })


def get_inventario_por_agencia(request):
    where_sql, parametros = _filtros_desde_request(
        request,
        solo_activos=True,
    )

    query = f"""
        SELECT
            DN_Atual,
            COUNT(*) AS total

        FROM dbo.Listado_Vehiculos_VW

        WHERE {where_sql}
        AND NmMarca = 'VOLKSWAGEN'

        GROUP BY DN_Atual

        ORDER BY total DESC
    """

    with connections["sqlserver_inv"].cursor() as cursor:
        cursor.execute(query, parametros)
        rows = cursor.fetchall()

    data = [
        {
            "agencia": str(codigo or "").strip(),
            "agenciaNombre": _agencia_nombre(codigo),
            "total": int(total),
        }
        for codigo, total in rows
    ]

    return JsonResponse({
        "data": data
    })


def get_inventario_por_estatus(request):
    where_sql, parametros = _filtros_desde_request(
        request,
        solo_activos=True,
    )

    query = f"""
        SELECT
            StEstoque,
            COUNT(*) AS total

        FROM dbo.Listado_Vehiculos_VW

        WHERE {where_sql}
        AND NmMarca = 'VOLKSWAGEN'

        GROUP BY StEstoque

        ORDER BY total DESC
    """

    with connections["sqlserver_inv"].cursor() as cursor:
        cursor.execute(query, parametros)
        rows = cursor.fetchall()

    data = [
        {
            "estatus": str(codigo or "").strip(),
            "estatusNombre": _estatus_nombre(codigo),
            "total": int(total),
        }
        for codigo, total in rows
    ]

    return JsonResponse({
        "data": data
    })


def get_inventario_por_marca(request):
    where_sql, parametros = _filtros_desde_request(
        request,
        solo_activos=True,
    )

    query = f"""
        SELECT
            NmMarca,
            NmFamilia,
            COUNT(*) AS total

        FROM dbo.Listado_Vehiculos_VW

        WHERE {where_sql}
        AND NmMarca = 'VOLKSWAGEN'

        GROUP BY
            NmMarca,
            NmFamilia

        ORDER BY total DESC
    """

    with connections["sqlserver_inv"].cursor() as cursor:
        cursor.execute(query, parametros)
        rows = cursor.fetchall()

    data = [
        {
            "marca": marca,
            "familia": familia,
            "total": int(total),
        }
        for marca, familia, total in rows
    ]

    return JsonResponse({
        "data": data
    })


def get_inventario_nuevo_usado(request):
    where_sql, parametros = _filtros_desde_request(
        request,
        solo_activos=True,
    )

    query = f"""
        SELECT
            DN_Atual,
            CondUso,
            COUNT(*) AS total

        FROM dbo.Listado_Vehiculos_VW

        WHERE {where_sql}

        GROUP BY
            DN_Atual,
            CondUso

        ORDER BY DN_Atual
    """

    with connections["sqlserver_inv"].cursor() as cursor:
        cursor.execute(query, parametros)
        rows = cursor.fetchall()

    data = []

    for codigo, condicion, total in rows:
        condicion_limpia = str(
            condicion or ""
        ).strip()

        if condicion_limpia == "N":
            condicion_nombre = "Nuevo"

        elif condicion_limpia == "U":
            condicion_nombre = "Usado"

        else:
            condicion_nombre = (
                condicion_limpia
                or "Sin dato"
            )

        data.append({
            "agencia": str(
                codigo or ""
            ).strip(),
            "agenciaNombre": _agencia_nombre(
                codigo
            ),
            "condicion": condicion_nombre,
            "total": int(total),
        })

    return JsonResponse({
        "data": data
    })


def get_inventario_nacional_importado(request):
    where_sql, parametros = _filtros_desde_request(
        request,
        solo_activos=True,
    )

    query = f"""
        SELECT
            TpNacImp,
            COUNT(*) AS total

        FROM dbo.Listado_Vehiculos_VW

        WHERE {where_sql}

        GROUP BY TpNacImp

        ORDER BY total DESC
    """

    with connections["sqlserver_inv"].cursor() as cursor:
        cursor.execute(query, parametros)
        rows = cursor.fetchall()

    etiquetas = {
        "N": "Nacional",
        "I": "Importado",
    }

    data = []

    for tipo, total in rows:
        tipo_limpio = str(
            tipo or ""
        ).strip()

        data.append({
            "tipo": tipo_limpio,
            "tipoNombre": etiquetas.get(
                tipo_limpio,
                tipo_limpio or "Sin dato",
            ),
            "total": int(total),
        })

    return JsonResponse({
        "data": data
    })


def get_inventario_filtros(request):
    agencias = [
        {
            "codigo": codigo,
            "nombre": nombre,
        }
        for codigo, nombre
        in AGENCIAS.items()
    ]

    estatus = [
        {
            "codigo": codigo,
            "nombre": nombre,
        }
        for codigo, nombre
        in ESTATUS_STOCK.items()
    ]

    return JsonResponse({
        "agencias": agencias,
        "estatus": estatus,
    })