#VentaRefacciones/views.py

from datetime import date, timedelta

from django.core.cache import cache
from django.db import connections
from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

CONEXION = "tdsql"
CACHE_OPCIONES = 600


def _obtener_filtros(request):
    agencia = request.GET.get("agencia", "").strip()[:100]
    busqueda = request.GET.get("q", "").strip()[:80]
    desde_texto = request.GET.get("fecha_desde", "").strip()
    hasta_texto = request.GET.get("fecha_hasta", "").strip()

    try:
        fecha_desde = date.fromisoformat(desde_texto) if desde_texto else None
        fecha_hasta = date.fromisoformat(hasta_texto) if hasta_texto else None
    except ValueError as error:
        raise ValueError("Las fechas deben tener el formato AAAA-MM-DD.") from error

    if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
        raise ValueError("fecha_desde no puede ser mayor que fecha_hasta.")

    try:
        pagina = int(request.GET.get("page", "1"))
        tamanio = int(request.GET.get("page_size", "50"))
    except ValueError as error:
        raise ValueError("page y page_size deben ser números enteros.") from error

    if pagina < 1 or tamanio < 1:
        raise ValueError("page y page_size deben ser mayores a cero.")

    return {
        "agencia": agencia,
        "q": busqueda,
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "page": pagina,
        "page_size": min(tamanio, 200),
    }


def _construir_where(filtros):
    condiciones = ['vr."TpProduto" = %s']
    parametros = ["P"]

    if filtros["agencia"]:
        condiciones.append('vr."Agencia" = %s')
        parametros.append(filtros["agencia"])

    if filtros["fecha_desde"]:
        condiciones.append('vr."DtEmissao" >= %s')
        parametros.append(filtros["fecha_desde"])

    if filtros["fecha_hasta"]:
        # Se incluye todo el último día, incluso si la hora no es 00:00.
        condiciones.append('vr."DtEmissao" < %s')
        parametros.append(filtros["fecha_hasta"] + timedelta(days=1))

    if filtros["q"]:
        condiciones.append('(' + ' OR '.join([
            'CAST(vr."NrNota" AS TEXT) ILIKE %s',
            'vr."Serie" ILIKE %s',
        ]) + ')')
        patron = f'%{filtros["q"]}%'
        parametros.extend([patron, patron])

    return " AND ".join(condiciones), parametros


def _consultar(sql, parametros=None, unico=False):
    with connections[CONEXION].cursor() as cursor:
        cursor.execute(sql, parametros or [])
        columnas = [columna[0] for columna in cursor.description]
        if unico:
            fila = cursor.fetchone()
            return dict(zip(columnas, fila)) if fila else {}
        return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def venta_refacciones_lista(request):
    try:
        filtros = _obtener_filtros(request)
    except ValueError as error:
        return JsonResponse({"detail": str(error)}, status=400)

    where, parametros = _construir_where(filtros)
    tamanio = filtros["page_size"]
    desplazamiento = (filtros["page"] - 1) * tamanio

    # Se agrupa ANTES de unir las tablas auxiliares: así no se duplican importes.
    sql_facturas = f"""
        SELECT vr."Agencia" AS agencia,
               vr."Serie" AS serie,
               vr."NrNota" AS nrnota,
               vr."DtEmissao"::date AS fecha,
               COUNT(*) AS partidas,
               COALESCE(SUM(vr."QtProdutos"), 0) AS cantidad,
               COALESCE(SUM(vr."VrBrutoItem"), 0) AS importe_bruto,
               COALESCE(SUM(vr."VrDescItem"), 0) AS descuento,
               COALESCE(SUM(vr."VrLiqItem"), 0) AS venta_neta,
               COALESCE(SUM(vr."VrICMS"), 0) AS impuesto_icms,
               COALESCE(SUM(vr."VrCustoEstoque"), 0) AS costo_registrado
        FROM public.matriz_ventasref vr
        WHERE {where}
        GROUP BY vr."Agencia", vr."Serie", vr."NrNota", vr."DtEmissao"::date
        ORDER BY fecha DESC, nrnota DESC NULLS LAST, agencia, serie
        LIMIT %s OFFSET %s
    """
    facturas = _consultar(sql_facturas, [*parametros, tamanio, desplazamiento])

    # La exportación pide sólo las facturas; evita recalcular indicadores por cada lote.
    if request.GET.get("solo_detalle") == "1":
        return JsonResponse({"results": facturas, "page": filtros["page"], "page_size": tamanio})

    sql_metricas = f"""
        SELECT COUNT(*) AS partidas,
               COUNT(DISTINCT (vr."Agencia", vr."Serie", vr."NrNota", vr."DtEmissao"::date)) AS facturas,
               COALESCE(SUM(vr."QtProdutos"), 0) AS cantidad_total,
               COALESCE(SUM(vr."VrBrutoItem"), 0) AS importe_bruto,
               COALESCE(SUM(vr."VrDescItem"), 0) AS descuento,
               COALESCE(SUM(vr."VrLiqItem"), 0) AS venta_neta,
               COALESCE(SUM(vr."VrICMS"), 0) AS impuesto_icms,
               COALESCE(SUM(vr."VrCustoEstoque"), 0) AS costo_registrado
        FROM public.matriz_ventasref vr
        WHERE {where}
    """
    metricas = _consultar(sql_metricas, parametros, unico=True)

    sql_agencias = f"""
        SELECT COALESCE(NULLIF(BTRIM(vr."Agencia"), ''), 'Sin agencia') AS agencia,
               COUNT(*) AS partidas,
               COALESCE(SUM(vr."VrLiqItem"), 0) AS total
        FROM public.matriz_ventasref vr
        WHERE {where}
        GROUP BY 1
        ORDER BY total DESC
    """
    agencias = _consultar(sql_agencias, parametros)

    sql_areas = f"""
        SELECT COALESCE(NULLIF(BTRIM(vr."CodArea"), ''), 'Sin área') AS area,
               COUNT(*) AS partidas,
               COALESCE(SUM(vr."VrLiqItem"), 0) AS total
        FROM public.matriz_ventasref vr
        WHERE {where}
        GROUP BY 1
        ORDER BY total DESC
    """
    areas = _consultar(sql_areas, parametros)

    return JsonResponse({
        "count": metricas.get("facturas", 0),
        "page": filtros["page"],
        "page_size": tamanio,
        "results": facturas,
        "metricas": metricas,
        "analisis": {"agencias": agencias, "areas": areas},
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def venta_refacciones_opciones(request):
    registros = _consultar("""
        SELECT DISTINCT "Agencia" AS agencia
        FROM public.matriz_ventasref
        WHERE "TpProduto" = %s
          AND NULLIF(BTRIM("Agencia"), '') IS NOT NULL
        ORDER BY agencia
    """, ["P"])

    agencias = [fila["agencia"] for fila in registros]

    return JsonResponse({"agencias": agencias})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def venta_refacciones_piezas(request):
    agencia = request.GET.get("agencia", "")
    serie = request.GET.get("serie", "")
    numero = request.GET.get("nrnota", "")
    fecha_texto = request.GET.get("fecha", "")

    if not agencia or not numero or not fecha_texto:
        return JsonResponse({
            "detail": "Se requieren agencia, nrnota y fecha."
        }, status=400)

    try:
        nrnota = int(numero)
        fecha = date.fromisoformat(fecha_texto)
    except ValueError:
        return JsonResponse({
            "detail": "nrnota o fecha no son válidos."
        }, status=400)

    sql = """
        SELECT
            vr.rowid__ AS rowid__,
            vr."Agencia" AS agencia,
            vr."Serie" AS serie,
            vr."NrNota" AS nrnota,
            vr."DtEmissao" AS fecha_emision,
            vr."TpProduto" AS tipo_producto,
            vr."ProdOuServ" AS codigo_producto,
            pa.nombre_producto,
            vr."QtProdutos" AS cantidad,
            vr."PrcUnitario" AS precio_unitario,
            vr."VrBrutoItem" AS importe_bruto,
            vr."InfluiEstat" AS influye_estadistica,
            vr."AliqICMS" AS tasa_icms,
            vr."PercDescItem" AS porcentaje_descuento,
            vr."VrDescItem" AS descuento,
            vr."VrLiqItem" AS venta_neta,
            vr."CodArea" AS codigo_area,
            a.descripcion_area,
            vr."CodSetor" AS codigo_sector,
            st.descripcion_sector,
            vr."CodFunc" AS codigo_funcionario,
            fc.nombre_funcionario,
            vr."VrBaseICMS" AS base_icms,
            vr."VrICMS" AS impuesto_icms,
            vr."SeqItensNota" AS secuencia,
            vr."VrCustoEstoque" AS costo_registrado,
            vr."CodEntidade" AS codigo_entidad,
            vr."Situacao" AS situacion,
            vr."TpNF" AS tipo_nota,
            vr."TpDocMov" AS tipo_documento,
            vr."TpPed" AS tipo_pedido,
            vr."SubTpOS" AS subtipo_os,
            vr."NrMov" AS numero_movimiento,
            vr."AliqISS" AS tasa_iss,
            vr."VrBaseISS" AS base_iss,
            vr."VrISS" AS impuesto_iss,
            vr."VrPis" AS impuesto_pis,
            vr."VrCofins" AS impuesto_cofins,
            vr."DrUltVenda" AS ultima_venta,
            vr."DiasEstVenda" AS dias_estancia,
            vr."PercRedICMS" AS reduccion_icms,
            vr."VrIPI" AS impuesto_ipi,
            vr."VrBaseSubs" AS base_sustitucion,
            vr."VrSubs" AS impuesto_sustitucion,
            vr."AfetaEstoque" AS afecta_inventario,
            vr."GrpMO" AS grupo_mo,
            vr."GrpDesconto" AS grupo_descuento,
            vr."CodLinhaProd" AS codigo_linea,
            vr."SugGrpTpOfic" AS grupo_taller,
            vr."VrReposProd" AS valor_reposicion
        FROM public.matriz_ventasref vr

        LEFT JOIN LATERAL (
            SELECT
                COALESCE(
                    NULLIF(BTRIM(f.nombre), ''),
                    NULLIF(BTRIM(f.nm_funcionario), '')
                ) AS nombre_funcionario
            FROM public.matriz_funcionarios f
            WHERE f.agencia = vr."Agencia"
              AND f.cod_funcionario = vr."CodFunc"
            ORDER BY f.rowid__ DESC NULLS LAST
            LIMIT 1
        ) fc ON TRUE

        LEFT JOIN LATERAL (
            SELECT ar.descrarea AS descripcion_area
            FROM public.matriz_areas ar
            WHERE ar.codarea = vr."CodArea"
            ORDER BY ar.descrarea NULLS LAST
            LIMIT 1
        ) a ON TRUE

        LEFT JOIN LATERAL (
            SELECT sec.descrsetor AS descripcion_sector
            FROM public.matriz_sectores sec
            WHERE sec.codarea = vr."CodArea"
              AND sec.codsetor = vr."CodSetor"
            ORDER BY sec.descrsetor NULLS LAST
            LIMIT 1
        ) st ON TRUE

        LEFT JOIN LATERAL (
            SELECT prod.nmproduto AS nombre_producto
            FROM public.matriz_produtosativos_5vw prod
            WHERE prod.agencia = vr."Agencia"
              AND BTRIM(prod.codproduto) = BTRIM(vr."ProdOuServ")
            ORDER BY prod.nmproduto NULLS LAST
            LIMIT 1
        ) pa ON TRUE

        WHERE vr."TpProduto" = %s
          AND vr."Agencia" = %s
          AND vr."Serie" IS NOT DISTINCT FROM %s
          AND vr."NrNota" = %s
          AND vr."DtEmissao" >= %s
          AND vr."DtEmissao" < %s

        ORDER BY
            vr."SeqItensNota" NULLS LAST,
            vr.rowid__ NULLS LAST
    """

    parametros = [
        "P",
        agencia,
        serie,
        nrnota,
        fecha,
        fecha + timedelta(days=1)
    ]

    piezas = _consultar(sql, parametros)

    return JsonResponse({
        "results": piezas,
        "resumen": {
            "partidas": len(piezas),
            "cantidad_total": sum(fila["cantidad"] or 0 for fila in piezas),
            "venta_neta": sum(fila["venta_neta"] or 0 for fila in piezas),
            "impuesto_icms": sum(fila["impuesto_icms"] or 0 for fila in piezas)
        }
    })