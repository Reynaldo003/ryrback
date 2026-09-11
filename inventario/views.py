# inventario/views.py
from datetime import date

from django.db import connections
from django.http import JsonResponse
from django.utils import timezone


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
        "DN_Atual <> '0'",
    ]

    parametros = []

    agencia = request.GET.get("agencia")

    if agencia:
        condiciones.append("DN_Atual = %s")
        parametros.append(agencia)

    estatus = request.GET.get("estatus")

    if estatus:
        condiciones.append(
            "LTRIM(RTRIM(StEstoque)) = %s"
        )
        parametros.append(estatus)

    if solo_activos:
        placeholders = ", ".join(
            ["%s"] * len(ESTATUS_EXCLUIDOS)
        )

        condiciones.append(
            f"""
            LTRIM(
                RTRIM(
                    COALESCE(StEstoque, '')
                )
            ) NOT IN ({placeholders})
            """
        )

        parametros.extend(ESTATUS_EXCLUIDOS)

    where_sql = " AND ".join(condiciones)

    return where_sql, parametros


def _agencia_nombre(codigo):
    return AGENCIAS.get(codigo, codigo)


def _estatus_nombre(codigo):
    if codigo is None:
        return "Sin estatus"

    codigo = codigo.strip()

    return ESTATUS_STOCK.get(
        codigo,
        codigo or "Sin estatus",
    )


def _calcular_dias(dt_valor):
    """
    Calcula los días transcurridos desde
    la fecha de facturación hasta hoy.

    Acepta:
    - datetime
    - date
    - YYYY-MM-DD
    - YYYYMMDD
    """

    if not dt_valor:
        return None

    try:
        texto = (
            str(dt_valor)
            .strip()[:10]
            .replace("-", "")
        )

        if len(texto) < 8:
            return None

        fecha = date(
            int(texto[0:4]),
            int(texto[4:6]),
            int(texto[6:8]),
        )

        # Evita fechas dummy como 0001-01-01.
        if fecha.year <= 1900:
            return None

        hoy = timezone.localdate()

        return (hoy - fecha).days

    except Exception:
        return None


def _antiguedad_bucket(dias):
    if dias is None:
        return None

    if dias <= 30:
        return "0-30"

    if dias <= 60:
        return "31-60"

    if dias <= 90:
        return "61-90"

    if dias <= 120:
        return "91-120"

    return "+120"


def get_inventario(request):
    where_sql, parametros = (
        _filtros_desde_request(
            request,
            solo_activos=True,
        )
    )

    query = f"""
        SELECT
            DN_Atual,
            NrChassi,
            NmFamilia,
            NmMarca,
            SitVeiculo,
            StEstoque,
            TpNacImp,
            ModalVda,
            EdiModelo,
            CondUso,
            DtFaturamento,
            VrNF_Compra
        FROM dbo.Listado_Vehiculos_VW
        WHERE {where_sql}
    """

    with connections[
        "sqlserver_inv"
    ].cursor() as cursor:
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
        row["agenciaNombre"] = (
            _agencia_nombre(
                row.get("DN_Atual")
            )
        )

        row["estatusNombre"] = (
            _estatus_nombre(
                row.get("StEstoque")
            )
        )

        row["diasEnStock"] = (
            _calcular_dias(
                row.get("DtFaturamento")
            )
        )

        row["DtFaturamento"] = str(
            row.get("DtFaturamento") or ""
        )[:10]

        row["VrNF_Compra"] = (
            float(row["VrNF_Compra"])
            if row.get("VrNF_Compra")
            is not None
            else None
        )

    return JsonResponse({
        "data": rows
    })


def get_inventario_costo(request):
    where_sql, parametros = (
        _filtros_desde_request(
            request,
            solo_activos=True,
        )
    )

    query = f"""
        SELECT
            COALESCE(
                SUM(VrNF_Compra),
                0
            ) AS costo_total
        FROM dbo.Listado_Vehiculos_VW
        WHERE {where_sql}
    """

    with connections[
        "sqlserver_inv"
    ].cursor() as cursor:
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
    where_sql, parametros = (
        _filtros_desde_request(
            request,
            solo_activos=True,
        )
    )

    query = f"""
        SELECT
            DtFaturamento
        FROM dbo.Listado_Vehiculos_VW
        WHERE {where_sql}
    """

    with connections[
        "sqlserver_inv"
    ].cursor() as cursor:
        cursor.execute(query, parametros)
        rows = cursor.fetchall()

    buckets = {
        "0-30": 0,
        "31-60": 0,
        "61-90": 0,
        "91-120": 0,
        "+120": 0,
    }

    for (dt_faturamento,) in rows:
        dias = _calcular_dias(
            dt_faturamento
        )

        bucket = _antiguedad_bucket(
            dias
        )

        if bucket:
            buckets[bucket] += 1

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
    where_sql, parametros = (
        _filtros_desde_request(
            request,
            solo_activos=True,
        )
    )

    query = f"""
        SELECT
            DN_Atual,
            COUNT(*) AS total
        FROM dbo.Listado_Vehiculos_VW
        WHERE {where_sql}
        GROUP BY DN_Atual
        ORDER BY total DESC
    """

    with connections[
        "sqlserver_inv"
    ].cursor() as cursor:
        cursor.execute(query, parametros)
        rows = cursor.fetchall()

    data = [
        {
            "agencia": codigo,
            "agenciaNombre": (
                _agencia_nombre(codigo)
            ),
            "total": total,
        }
        for codigo, total in rows
    ]

    return JsonResponse({
        "data": data
    })


def get_inventario_por_estatus(request):
    where_sql, parametros = (
        _filtros_desde_request(
            request,
            solo_activos=True,
        )
    )

    query = f"""
        SELECT
            StEstoque,
            COUNT(*) AS total
        FROM dbo.Listado_Vehiculos_VW
        WHERE {where_sql}
        GROUP BY StEstoque
        ORDER BY total DESC
    """

    with connections[
        "sqlserver_inv"
    ].cursor() as cursor:
        cursor.execute(query, parametros)
        rows = cursor.fetchall()

    data = [
        {
            "estatus": (
                codigo or ""
            ).strip(),
            "estatusNombre": (
                _estatus_nombre(codigo)
            ),
            "total": total,
        }
        for codigo, total in rows
    ]

    return JsonResponse({
        "data": data
    })


def get_inventario_por_marca(request):
    where_sql, parametros = (
        _filtros_desde_request(
            request,
            solo_activos=True,
        )
    )

    query = f"""
        SELECT
            NmMarca,
            NmFamilia,
            COUNT(*) AS total
        FROM dbo.Listado_Vehiculos_VW
        WHERE {where_sql}
        GROUP BY
            NmMarca,
            NmFamilia
        ORDER BY total DESC
    """

    with connections[
        "sqlserver_inv"
    ].cursor() as cursor:
        cursor.execute(query, parametros)
        rows = cursor.fetchall()

    data = [
        {
            "marca": marca,
            "familia": familia,
            "total": total,
        }
        for marca, familia, total in rows
    ]

    return JsonResponse({
        "data": data
    })


def get_inventario_nuevo_usado(request):
    where_sql, parametros = (
        _filtros_desde_request(
            request,
            solo_activos=True,
        )
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

    with connections[
        "sqlserver_inv"
    ].cursor() as cursor:
        cursor.execute(query, parametros)
        rows = cursor.fetchall()

    data = []

    for codigo, condicion, total in rows:
        condicion_limpia = (
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
            "agencia": codigo,
            "agenciaNombre": (
                _agencia_nombre(codigo)
            ),
            "condicion": condicion_nombre,
            "total": total,
        })

    return JsonResponse({
        "data": data
    })


def get_inventario_nacional_importado(
    request
):
    where_sql, parametros = (
        _filtros_desde_request(
            request,
            solo_activos=True,
        )
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

    with connections[
        "sqlserver_inv"
    ].cursor() as cursor:
        cursor.execute(query, parametros)
        rows = cursor.fetchall()

    etiquetas = {
        "N": "Nacional",
        "I": "Importado",
    }

    data = []

    for tipo, total in rows:
        tipo_limpio = (
            tipo or ""
        ).strip()

        data.append({
            "tipo": tipo_limpio,
            "tipoNombre": etiquetas.get(
                tipo_limpio,
                tipo_limpio or "Sin dato",
            ),
            "total": total,
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