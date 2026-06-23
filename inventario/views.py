# inventario/views.py
from django.db import connections
from django.http import JsonResponse
from datetime import date

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

ESTATUS_EXCLUIDOS = ["V", "O", "C", "D", "P"]


def _filtros_desde_request(request):
    condiciones = ["DN_Atual IS NOT NULL", "DN_Atual <> '0'"]
    parametros = []

    agencia = request.GET.get("agencia")
    if agencia:
        condiciones.append("DN_Atual = %s")
        parametros.append(agencia)

    estatus = request.GET.get("estatus")
    if estatus:
        condiciones.append("StEstoque = %s")
        parametros.append(estatus)

    where_sql = " AND ".join(condiciones)
    return where_sql, parametros


def _agencia_nombre(codigo):
    return AGENCIAS.get(codigo, codigo)


def _estatus_nombre(codigo):
    if codigo is None:
        return "Sin estatus"
    codigo = codigo.strip()
    return ESTATUS_STOCK.get(codigo, codigo or "Sin estatus")


def _calcular_dias(dt_recebim):
    """Calcula días en stock desde DtRecebim (formato 'YYYYMMDD' o 'YYYY-MM-DD')."""
    if not dt_recebim:
        return None
    try:
        s = str(dt_recebim).strip().replace("-", "")
        if len(s) < 8:
            return None
        fecha = date(int(s[0:4]), int(s[4:6]), int(s[6:8]))
        return (date.today() - fecha).days
    except Exception:
        return None


def _antiguedad_bucket(dias):
    if dias is None:
        return None
    if dias <= 30:
        return "0-30"
    elif dias <= 60:
        return "31-60"
    elif dias <= 90:
        return "61-90"
    elif dias <= 120:
        return "91-120"
    else:
        return "+120"


def get_inventario(request):
    """
    Listado crudo — ahora incluye NrChassi, DtRecebim, VrNF_Compra y días calculados.
    """
    where_sql, parametros = _filtros_desde_request(request)

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
            DtRecebim,
            VrNF_Compra
        FROM dbo.Listado_Vehiculos_VW
        WHERE {where_sql}
    """

    with connections["sqlserver_inv"].cursor() as cursor:
        cursor.execute(query, parametros)
        columns = [col[0] for col in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

    for row in rows:
        row["agenciaNombre"] = _agencia_nombre(row.get("DN_Atual"))
        row["estatusNombre"] = _estatus_nombre(row.get("StEstoque"))
        dias = _calcular_dias(row.get("DtRecebim"))
        row["diasEnStock"] = dias
        row["VrNF_Compra"] = float(row["VrNF_Compra"]) if row.get("VrNF_Compra") is not None else None

    return JsonResponse({"data": rows})


# Costo total del inventario ─────────────────────────────────────────

def get_inventario_costo(request):
    """
    Suma de VrNF_Compra para los vehículos activos (excluye V, O, C, D, P).
    """
    where_sql, parametros = _filtros_desde_request(request)
    excluidos = ",".join(f"'{e}'" for e in ESTATUS_EXCLUIDOS)

    query = f"""
        SELECT COALESCE(SUM(VrNF_Compra), 0) AS costo_total
        FROM dbo.Listado_Vehiculos_VW
        WHERE {where_sql}
          AND StEstoque NOT IN ({excluidos})
    """

    with connections["sqlserver_inv"].cursor() as cursor:
        cursor.execute(query, parametros)
        row = cursor.fetchone()

    return JsonResponse({"costo_total": float(row[0]) if row else 0})


# ── NUEVO: Antigüedad en stock ─────────────────────────────────────────────────

def get_inventario_antiguedad(request):
    """
    Distribución de vehículos activos por rango de días en stock.
    """
    where_sql, parametros = _filtros_desde_request(request)
    excluidos = ",".join(f"'{e}'" for e in ESTATUS_EXCLUIDOS)

    query = f"""
        SELECT DtRecebim
        FROM dbo.Listado_Vehiculos_VW
        WHERE {where_sql}
          AND StEstoque NOT IN ({excluidos})
    """

    with connections["sqlserver_inv"].cursor() as cursor:
        cursor.execute(query, parametros)
        rows = cursor.fetchall()

    buckets = {"0-30": 0, "31-60": 0, "61-90": 0, "91-120": 0, "+120": 0}
    for (dt,) in rows:
        dias = _calcular_dias(dt)
        bucket = _antiguedad_bucket(dias)
        if bucket:
            buckets[bucket] += 1

    data = [{"rango": k, "total": v} for k, v in buckets.items()]
    return JsonResponse({"data": data})


# ── Endpoints existentes (sin cambios) ────────────────────────────────────────

def get_inventario_por_agencia(request):
    where_sql, parametros = _filtros_desde_request(request)
    query = f"""
        SELECT DN_Atual, COUNT(*) AS total
        FROM dbo.Listado_Vehiculos_VW
        WHERE {where_sql}
        GROUP BY DN_Atual
        ORDER BY total DESC
    """
    with connections["sqlserver_inv"].cursor() as cursor:
        cursor.execute(query, parametros)
        rows = cursor.fetchall()
    data = [{"agencia": c, "agenciaNombre": _agencia_nombre(c), "total": t} for c, t in rows]
    return JsonResponse({"data": data})


def get_inventario_por_estatus(request):
    where_sql, parametros = _filtros_desde_request(request)
    query = f"""
        SELECT StEstoque, COUNT(*) AS total
        FROM dbo.Listado_Vehiculos_VW
        WHERE {where_sql}
        GROUP BY StEstoque
        ORDER BY total DESC
    """
    with connections["sqlserver_inv"].cursor() as cursor:
        cursor.execute(query, parametros)
        rows = cursor.fetchall()
    data = [{"estatus": (c or "").strip(), "estatusNombre": _estatus_nombre(c), "total": t} for c, t in rows]
    return JsonResponse({"data": data})


def get_inventario_por_marca(request):
    where_sql, parametros = _filtros_desde_request(request)
    query = f"""
        SELECT NmMarca, NmFamilia, COUNT(*) AS total
        FROM dbo.Listado_Vehiculos_VW
        WHERE {where_sql}
        GROUP BY NmMarca, NmFamilia
        ORDER BY total DESC
    """
    with connections["sqlserver_inv"].cursor() as cursor:
        cursor.execute(query, parametros)
        rows = cursor.fetchall()
    data = [{"marca": m, "familia": f, "total": t} for m, f, t in rows]
    return JsonResponse({"data": data})


def get_inventario_nuevo_usado(request):
    where_sql, parametros = _filtros_desde_request(request)
    query = f"""
        SELECT DN_Atual, CondUso, COUNT(*) AS total
        FROM dbo.Listado_Vehiculos_VW
        WHERE {where_sql}
        GROUP BY DN_Atual, CondUso
        ORDER BY DN_Atual
    """
    with connections["sqlserver_inv"].cursor() as cursor:
        cursor.execute(query, parametros)
        rows = cursor.fetchall()
    data = [
        {
            "agencia": c,
            "agenciaNombre": _agencia_nombre(c),
            "condicion": "Nuevo" if (cond or "").strip() == "N" else "Usado" if (cond or "").strip() == "U" else (cond or "Sin dato"),
            "total": t,
        }
        for c, cond, t in rows
    ]
    return JsonResponse({"data": data})


def get_inventario_nacional_importado(request):
    where_sql, parametros = _filtros_desde_request(request)
    query = f"""
        SELECT TpNacImp, COUNT(*) AS total
        FROM dbo.Listado_Vehiculos_VW
        WHERE {where_sql}
        GROUP BY TpNacImp
        ORDER BY total DESC
    """
    with connections["sqlserver_inv"].cursor() as cursor:
        cursor.execute(query, parametros)
        rows = cursor.fetchall()
    etiquetas = {"N": "Nacional", "I": "Importado"}
    data = [{"tipo": (t or "").strip(), "tipoNombre": etiquetas.get((t or "").strip(), t or "Sin dato"), "total": tot} for t, tot in rows]
    return JsonResponse({"data": data})


def get_inventario_filtros(request):
    agencias = [{"codigo": c, "nombre": n} for c, n in AGENCIAS.items()]
    estatus  = [{"codigo": c, "nombre": n} for c, n in ESTATUS_STOCK.items()]
    return JsonResponse({"agencias": agencias, "estatus": estatus})