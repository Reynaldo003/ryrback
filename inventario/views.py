# inventario/views.py
from django.db import connections
from django.http import JsonResponse


# Mapeo de código de agencia (DN_Atual) -> nombre legible.
# Si llega a abrirse una agencia nueva, solo hay que agregarla aquí.
AGENCIAS = {
    "2923": "Córdoba",
    "2924": "Orizaba",
    "1905": "Tuxtepec",
    "2927": "Poza Rica",
    "2929": "Tuxpan",
}

# Catálogo de Status del Stock (StEstoque), tal cual el desplegable del sistema origen.
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


def _filtros_desde_request(request):
    """
    Lee los filtros globales que manda el front (agencia y estatus) y regresa
    el fragmento WHERE junto con sus parámetros, listos para usarse con cursor.execute.
    Siempre excluye DN_Atual = '0' (registro basura sin agencia real).
    """
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


def get_inventario(request):
    """
    Listado crudo de vehículos (detalle fila por fila), respetando los filtros
    globales de agencia / estatus si vienen en el querystring.
    """
    where_sql, parametros = _filtros_desde_request(request)

    query = f"""
        SELECT
            DN_Atual,
            NmFamilia,
            NmMarca,
            SitVeiculo,
            StEstoque,
            TpNacImp,
            ModalVda,
            EdiModelo,
            CondUso
        FROM dbo.Listado_Vehiculos_VW
        WHERE {where_sql}
    """

    with connections["sqlserver"].cursor() as cursor:
        cursor.execute(query, parametros)
        columns = [col[0] for col in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

    for row in rows:
        row["agenciaNombre"] = _agencia_nombre(row.get("DN_Atual"))
        row["estatusNombre"] = _estatus_nombre(row.get("StEstoque"))

    return JsonResponse({"data": rows})


def get_inventario_por_agencia(request):
    """
    Gráfica principal: total de vehículos agrupados por agencia (DN_Atual).
    """
    where_sql, parametros = _filtros_desde_request(request)

    query = f"""
        SELECT DN_Atual, COUNT(*) AS total
        FROM dbo.Listado_Vehiculos_VW
        WHERE {where_sql}
        GROUP BY DN_Atual
        ORDER BY total DESC
    """

    with connections["sqlserver"].cursor() as cursor:
        cursor.execute(query, parametros)
        rows = cursor.fetchall()

    data = [
        {"agencia": codigo, "agenciaNombre": _agencia_nombre(codigo), "total": total}
        for codigo, total in rows
    ]
    return JsonResponse({"data": data})


def get_inventario_por_estatus(request):
    """
    Distribución de vehículos por Status del Stock (StEstoque).
    """
    where_sql, parametros = _filtros_desde_request(request)

    query = f"""
        SELECT StEstoque, COUNT(*) AS total
        FROM dbo.Listado_Vehiculos_VW
        WHERE {where_sql}
        GROUP BY StEstoque
        ORDER BY total DESC
    """

    with connections["sqlserver"].cursor() as cursor:
        cursor.execute(query, parametros)
        rows = cursor.fetchall()

    data = [
        {"estatus": (codigo or "").strip(), "estatusNombre": _estatus_nombre(codigo), "total": total}
        for codigo, total in rows
    ]
    return JsonResponse({"data": data})


def get_inventario_por_marca(request):
    """
    Inventario agrupado por marca / familia de vehículo.
    Se limita a las familias con más volumen para no saturar la gráfica.
    """
    where_sql, parametros = _filtros_desde_request(request)

    query = f"""
        SELECT NmMarca, NmFamilia, COUNT(*) AS total
        FROM dbo.Listado_Vehiculos_VW
        WHERE {where_sql}
        GROUP BY NmMarca, NmFamilia
        ORDER BY total DESC
    """

    with connections["sqlserver"].cursor() as cursor:
        cursor.execute(query, parametros)
        rows = cursor.fetchall()

    data = [
        {"marca": marca, "familia": familia, "total": total}
        for marca, familia, total in rows
    ]
    return JsonResponse({"data": data})


def get_inventario_nuevo_usado(request):
    """
    Nuevo (N) vs Usado (U) por agencia, según CondUso.
    """
    where_sql, parametros = _filtros_desde_request(request)

    query = f"""
        SELECT DN_Atual, CondUso, COUNT(*) AS total
        FROM dbo.Listado_Vehiculos_VW
        WHERE {where_sql}
        GROUP BY DN_Atual, CondUso
        ORDER BY DN_Atual
    """

    with connections["sqlserver"].cursor() as cursor:
        cursor.execute(query, parametros)
        rows = cursor.fetchall()

    data = [
        {
            "agencia": codigo,
            "agenciaNombre": _agencia_nombre(codigo),
            "condicion": "Nuevo" if (cond or "").strip() == "N" else "Usado" if (cond or "").strip() == "U" else (cond or "Sin dato"),
            "total": total,
        }
        for codigo, cond, total in rows
    ]
    return JsonResponse({"data": data})


def get_inventario_nacional_importado(request):
    """
    Nacional (N) vs Importado (I) según TpNacImp.
    """
    where_sql, parametros = _filtros_desde_request(request)

    query = f"""
        SELECT TpNacImp, COUNT(*) AS total
        FROM dbo.Listado_Vehiculos_VW
        WHERE {where_sql}
        GROUP BY TpNacImp
        ORDER BY total DESC
    """

    with connections["sqlserver"].cursor() as cursor:
        cursor.execute(query, parametros)
        rows = cursor.fetchall()

    etiquetas = {"N": "Nacional", "I": "Importado"}
    data = [
        {"tipo": (tipo or "").strip(), "tipoNombre": etiquetas.get((tipo or "").strip(), tipo or "Sin dato"), "total": total}
        for tipo, total in rows
    ]
    return JsonResponse({"data": data})


def get_inventario_filtros(request):
    """
    Catálogos para alimentar los selects del front (agencias y estatus de stock),
    así el dropdown no se queda hardcodeado en el componente.
    """
    agencias = [{"codigo": cod, "nombre": nombre} for cod, nombre in AGENCIAS.items()]
    estatus = [{"codigo": cod, "nombre": nombre} for cod, nombre in ESTATUS_STOCK.items()]
    return JsonResponse({"agencias": agencias, "estatus": estatus})