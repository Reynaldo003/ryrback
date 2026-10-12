# VentaRefacciones/views.py
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from django.db import connections
from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
CONEXION = "tdsql"

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
    # Mismos criterios del reporte administrativo en lista, indicadores y gráficas.
    condiciones = [
        'vr."TpProduto" = %s',
        "(vr.\"CodArea\" = 'AT' OR (vr.\"CodArea\" = 'PA' AND vr.\"Serie\" <> 'IN'))",
    ]
    parametros = ["P"]
    if filtros["agencia"]:
        condiciones.append('vr."Agencia" = %s')
        parametros.append(filtros["agencia"])
    if filtros["fecha_desde"]:
        condiciones.append('vr."DtEmissao" >= %s')
        parametros.append(filtros["fecha_desde"])
    if filtros["fecha_hasta"]:
        condiciones.append('vr."DtEmissao" < %s')
        parametros.append(filtros["fecha_hasta"] + timedelta(days=1))
    if filtros["q"]:
        condiciones.append('(CAST(vr."NrNota" AS TEXT) ILIKE %s OR vr."Serie" ILIKE %s)')
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



def _ventas_por_linea(where, parametros):
    """Agrupa renglones de refacciones por línea, sin duplicar importes."""
    sql = f"""
        WITH ventas AS (
            SELECT
                COALESCE(
                    NULLIF(BTRIM(pa.codlinhaprod::text), ''),
                    NULLIF(BTRIM(vr."CodLinhaProd"::text), ''),
                    'SIN_LINEA'
                ) AS codigo_linea,
                vr."QtProdutos" AS piezas,
                vr."VrLiqItem" AS neto,
                ROUND(COALESCE(vr."VrCustoEstoque", 0)::numeric, 2) AS costo
            FROM public.matriz_ventasref vr
            LEFT JOIN LATERAL (
                SELECT prod.codlinhaprod
                FROM public.matriz_produtosativos_5vw prod
                WHERE prod.agencia = vr."Agencia"
                  AND BTRIM(prod.codproduto) = BTRIM(vr."ProdOuServ")
                ORDER BY prod.codlinhaprod NULLS LAST
                LIMIT 1
            ) pa ON TRUE
            WHERE {where}
        ),
        agrupado AS (
            SELECT
                codigo_linea,
                COUNT(*) AS items,
                COALESCE(SUM(piezas), 0) AS piezas,
                ROUND(COALESCE(SUM(neto), 0)::numeric, 2) AS ventas,
                COALESCE(SUM(costo), 0) AS costo
            FROM ventas
            GROUP BY codigo_linea
        )
        SELECT
            a.codigo_linea,
            COALESCE(NULLIF(BTRIM(lin.nmlinhaprod), ''),
                CASE WHEN a.codigo_linea = 'SIN_LINEA' THEN 'Sin línea'
                     ELSE 'Línea ' || a.codigo_linea END
            ) AS linea,
            a.items,
            a.piezas,
            a.ventas,
            a.costo,
            a.ventas - a.costo AS utilidad_bruta,
            COALESCE(ROUND((a.ventas - a.costo) * 100 / NULLIF(a.ventas, 0), 2), 0)
                AS margen_bruto,
            COALESCE(ROUND(a.ventas * 100 / NULLIF(SUM(a.ventas) OVER (), 0), 2), 0)
                AS porcentaje_total
        FROM agrupado a
        LEFT JOIN LATERAL (
            SELECT l.nmlinhaprod
            FROM public.matriz_linea l
            WHERE BTRIM(l.codlinhaprod::text) = a.codigo_linea
            ORDER BY l.nmlinhaprod NULLS LAST
            LIMIT 1
        ) lin ON TRUE
        ORDER BY a.ventas DESC, linea
    """
    return _consultar(sql, parametros)


def _ventas_por_cliente(where, parametros):
    """Agrupa primero por agencia y código de entidad; después busca el nombre."""
    sql = f"""
        WITH agrupado AS (
            SELECT
                vr."Agencia" AS agencia,
                vr."CodEntidade" AS codigo_cliente,
                COUNT(*) AS items,
                COALESCE(SUM(vr."QtProdutos"), 0) AS piezas,
                ROUND(COALESCE(SUM(vr."VrLiqItem"), 0)::numeric, 2) AS ventas,
                SUM(ROUND(COALESCE(vr."VrCustoEstoque", 0)::numeric, 2)) AS costo
            FROM public.matriz_ventasref vr
            WHERE {where}
            GROUP BY vr."Agencia", vr."CodEntidade"
        )
        SELECT
            a.agencia,
            a.codigo_cliente,
            COALESCE(
                NULLIF(BTRIM(ent.razao_social), ''),
                NULLIF(BTRIM(CONCAT_WS(' ',
                    NULLIF(BTRIM(ent.nomes), ''),
                    NULLIF(BTRIM(ent.sobrenm_pat), ''),
                    NULLIF(BTRIM(ent.sobrenm_mat), '')
                )), ''),
                CASE WHEN a.codigo_cliente IS NULL THEN 'Cliente sin código'
                     ELSE 'Cliente ' || a.codigo_cliente::text END
            ) AS cliente,
            NULLIF(CONCAT_WS('',
                NULLIF(BTRIM(ent.nr_ddd1::text), ''),
                NULLIF(BTRIM(ent.tel1::text), '')
            ), '') AS telefono,
            a.items,
            a.piezas,
            a.ventas,
            a.costo,
            a.ventas - a.costo AS utilidad_bruta,
            COALESCE(ROUND((a.ventas - a.costo) * 100 / NULLIF(a.ventas, 0), 2), 0)
                AS margen_bruto,
            COALESCE(ROUND(a.ventas * 100 / NULLIF(SUM(a.ventas) OVER (), 0), 2), 0)
                AS porcentaje_total
        FROM agrupado a
        LEFT JOIN LATERAL (
            SELECT e.razao_social, e.nomes, e.sobrenm_pat, e.sobrenm_mat,
                   e.nr_ddd1, e.tel1
            FROM public.matriz_entidades e
            WHERE e.cod_entidade = a.codigo_cliente
              AND e.dn_modifico::text = CASE a.agencia
                  WHEN 'Vw Tuxtepec' THEN '1905'
                  WHEN 'Vw Cordoba' THEN '2923'
                  WHEN 'Vw Orizaba' THEN '2924'
                  WHEN 'Vw Poza Rica' THEN '2927'
                  WHEN 'Vw Tuxpan' THEN '2929'
                  ELSE NULL
              END
            ORDER BY e.razao_social NULLS LAST, e.nomes NULLS LAST
            LIMIT 1
        ) ent ON TRUE
        ORDER BY a.ventas DESC, cliente, a.agencia
    """
    return _consultar(sql, parametros)


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
    # Cada factura se agrupa primero sobre la tabla original, sin JOIN que dupliquen importes.
    sql_facturas = f"""
        SELECT
            vr."Agencia" AS agencia,
            vr."Serie" AS serie,
            vr."NrNota" AS nrnota,
            vr."DtEmissao"::date AS fecha,
            COUNT(*) AS partidas,
            COALESCE(SUM(vr."QtProdutos"), 0) AS cantidad,
            ROUND(COALESCE(SUM(vr."VrBrutoItem"), 0)::numeric, 2) AS importe_bruto,
            ROUND(COALESCE(SUM(vr."VrDescItem"), 0)::numeric, 2) AS descuento,
            ROUND(COALESCE(SUM(vr."VrLiqItem"), 0)::numeric, 2) AS venta_neta,
            ROUND(COALESCE(SUM(vr."VrICMS"), 0)::numeric, 2) AS impuesto_icms,
            SUM(ROUND(COALESCE(vr."VrCustoEstoque", 0)::numeric, 2)) AS costo_registrado,
            ROUND(COALESCE(SUM(vr."VrLiqItem"), 0)::numeric, 2)
                + ROUND(COALESCE(SUM(vr."VrICMS"), 0)::numeric, 2) AS total_facturado,
            ROUND(COALESCE(SUM(vr."VrLiqItem"), 0)::numeric, 2)
                - SUM(ROUND(COALESCE(vr."VrCustoEstoque", 0)::numeric, 2)) AS utilidad_bruta
        FROM public.matriz_ventasref vr
        WHERE {where}
        GROUP BY vr."Agencia", vr."Serie", vr."NrNota", vr."DtEmissao"::date
        ORDER BY fecha DESC, nrnota DESC NULLS LAST, agencia, serie
        LIMIT %s OFFSET %s
    """
    facturas = _consultar(sql_facturas, [*parametros, tamanio, desplazamiento])
    if request.GET.get("solo_detalle") == "1":
        return JsonResponse({
            "results": facturas,
            "page": filtros["page"],
            "page_size": tamanio,
        })
    # Agregar primero por factura permite contar documentos y redondear correctamente.
    # El costo se redondea por renglón ANTES de sumarse, igual que en el reporte.
    sql_metricas = f"""
        WITH facturas AS (
            SELECT
                vr."Agencia", vr."Serie", vr."NrNota", vr."DtEmissao"::date AS fecha,
                COUNT(*) AS partidas,
                COALESCE(SUM(vr."QtProdutos"), 0) AS cantidad,
                ROUND(COALESCE(SUM(vr."VrBrutoItem"), 0)::numeric, 2) AS bruto,
                ROUND(COALESCE(SUM(vr."VrDescItem"), 0)::numeric, 2) AS descuento,
                ROUND(COALESCE(SUM(vr."VrLiqItem"), 0)::numeric, 2) AS neto,
                ROUND(COALESCE(SUM(vr."VrICMS"), 0)::numeric, 2) AS iva,
                SUM(ROUND(COALESCE(vr."VrCustoEstoque", 0)::numeric, 2)) AS costo
            FROM public.matriz_ventasref vr
            WHERE {where}
            GROUP BY vr."Agencia", vr."Serie", vr."NrNota", vr."DtEmissao"::date
        )
        SELECT
            COUNT(*) AS facturas,
            COALESCE(SUM(partidas), 0) AS partidas,
            COALESCE(SUM(cantidad), 0) AS cantidad_total,
            COALESCE(SUM(bruto), 0) AS importe_bruto,
            COALESCE(SUM(descuento), 0) AS descuento,
            COALESCE(SUM(neto), 0) AS venta_neta,
            COALESCE(SUM(iva), 0) AS impuesto_icms,
            COALESCE(SUM(neto + iva), 0) AS total_facturado,
            COALESCE(SUM(costo), 0) AS costo_registrado,
            COALESCE(SUM(neto - costo), 0) AS utilidad_bruta,
            COALESCE(ROUND(SUM(neto - costo) * 100 / NULLIF(SUM(neto), 0), 2), 0)
                AS margen_utilidad
        FROM facturas
    """
    metricas = _consultar(sql_metricas, parametros, unico=True)
    sql_agencias = f"""
        SELECT COALESCE(NULLIF(BTRIM(vr."Agencia"), ''), 'Sin agencia') AS agencia,
               COUNT(*) AS partidas,
               ROUND(COALESCE(SUM(vr."VrLiqItem"), 0)::numeric, 2) AS total
        FROM public.matriz_ventasref vr
        WHERE {where}
        GROUP BY 1
        ORDER BY total DESC
    """
    agencias = _consultar(sql_agencias, parametros)
    sql_areas = f"""
        SELECT COALESCE(NULLIF(BTRIM(vr."CodArea"), ''), 'Sin área') AS area,
               COUNT(*) AS partidas,
               ROUND(COALESCE(SUM(vr."VrLiqItem"), 0)::numeric, 2) AS total
        FROM public.matriz_ventasref vr
        WHERE {where}
        GROUP BY 1
        ORDER BY total DESC
    """
    areas = _consultar(sql_areas, parametros)
    lineas = _ventas_por_linea(where, parametros)
    clientes = _ventas_por_cliente(where, parametros)
    return JsonResponse({
        "count": metricas.get("facturas", 0),
        "page": filtros["page"],
        "page_size": tamanio,
        "results": facturas,
        "metricas": metricas,
        "analisis": {"agencias": agencias, "areas": areas, "lineas": lineas, "clientes": clientes},
    })

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def venta_refacciones_opciones(request):
    registros = _consultar("""
        SELECT DISTINCT "Agencia" AS agencia
        FROM public.matriz_ventasref
        WHERE "TpProduto" = %s
          AND ("CodArea" = 'AT' OR ("CodArea" = 'PA' AND "Serie" <> 'IN'))
          AND NULLIF(BTRIM("Agencia"), '') IS NOT NULL
        ORDER BY agencia
    """, ["P"])
    return JsonResponse({"agencias": [fila["agencia"] for fila in registros]})

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def venta_refacciones_piezas(request):
    agencia = request.GET.get("agencia", "")
    serie = request.GET.get("serie")
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
            COALESCE(pa.codlinhaprod::text, vr."CodLinhaProd"::text) AS codigo_linea,
            lin.nombre_linea,
            ent.nombre_cliente,
            ent.telefono_cliente,
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
            ROUND(COALESCE(vr."VrCustoEstoque", 0)::numeric, 2) AS costo_registrado,
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
            SELECT prod.nmproduto AS nombre_producto, prod.codlinhaprod
            FROM public.matriz_produtosativos_5vw prod
            WHERE prod.agencia = vr."Agencia"
              AND BTRIM(prod.codproduto) = BTRIM(vr."ProdOuServ")
            ORDER BY prod.nmproduto NULLS LAST
            LIMIT 1
        ) pa ON TRUE
        LEFT JOIN LATERAL (
            SELECT l.nmlinhaprod AS nombre_linea
            FROM public.matriz_linea l
            WHERE BTRIM(l.codlinhaprod::text) = COALESCE(
                NULLIF(BTRIM(pa.codlinhaprod::text), ''),
                NULLIF(BTRIM(vr."CodLinhaProd"::text), '')
            )
            ORDER BY l.nmlinhaprod NULLS LAST
            LIMIT 1
        ) lin ON TRUE
        LEFT JOIN LATERAL (
            SELECT
                COALESCE(
                    NULLIF(BTRIM(e.razao_social), ''),
                    NULLIF(BTRIM(CONCAT_WS(' ',
                        NULLIF(BTRIM(e.nomes), ''),
                        NULLIF(BTRIM(e.sobrenm_pat), ''),
                        NULLIF(BTRIM(e.sobrenm_mat), '')
                    )), ''),
                    'Cliente ' || vr."CodEntidade"::text
                ) AS nombre_cliente,
                NULLIF(CONCAT_WS('',
                    NULLIF(BTRIM(e.nr_ddd1::text), ''),
                    NULLIF(BTRIM(e.tel1::text), '')
                ), '') AS telefono_cliente
            FROM public.matriz_entidades e
            WHERE e.cod_entidade = vr."CodEntidade"
              AND e.dn_modifico::text = CASE vr."Agencia"
                  WHEN 'Vw Tuxtepec' THEN '1905'
                  WHEN 'Vw Cordoba' THEN '2923'
                  WHEN 'Vw Orizaba' THEN '2924'
                  WHEN 'Vw Poza Rica' THEN '2927'
                  WHEN 'Vw Tuxpan' THEN '2929'
                  ELSE NULL
              END
            ORDER BY e.razao_social NULLS LAST, e.nomes NULLS LAST
            LIMIT 1
        ) ent ON TRUE
        WHERE vr."Agencia" = %s
          AND vr."Serie" IS NOT DISTINCT FROM %s
          AND vr."NrNota" = %s
          AND vr."DtEmissao" >= %s
          AND vr."DtEmissao" < %s
          AND vr."TpProduto" = 'P'
          AND (vr."CodArea" = 'AT' OR (vr."CodArea" = 'PA' AND vr."Serie" <> 'IN'))
        ORDER BY
            vr."SeqItensNota" NULLS LAST,
            vr.rowid__ NULLS LAST
    """
    parametros = [
        agencia,
        serie,
        nrnota,
        fecha,
        fecha + timedelta(days=1)
    ]
    piezas = _consultar(sql, parametros)
    centavos = Decimal("0.01")
    def decimal_campo(fila, campo):
        return Decimal(str(fila.get(campo) or 0))
    bruto = sum((decimal_campo(f, "importe_bruto") for f in piezas), Decimal(0)).quantize(centavos, rounding=ROUND_HALF_UP)
    descuento = sum((decimal_campo(f, "descuento") for f in piezas), Decimal(0)).quantize(centavos, rounding=ROUND_HALF_UP)
    neto = sum((decimal_campo(f, "venta_neta") for f in piezas), Decimal(0)).quantize(centavos, rounding=ROUND_HALF_UP)
    iva = sum((decimal_campo(f, "impuesto_icms") for f in piezas), Decimal(0)).quantize(centavos, rounding=ROUND_HALF_UP)
    costo = sum((decimal_campo(f, "costo_registrado") for f in piezas), Decimal(0))
    utilidad = neto - costo
    margen = (utilidad * 100 / neto).quantize(centavos, rounding=ROUND_HALF_UP) if neto else Decimal(0)
    return JsonResponse({
        "results": piezas,
        "resumen": {
            "partidas": len(piezas),
            "cantidad_total": sum((decimal_campo(f, "cantidad") for f in piezas), Decimal(0)),
            "importe_bruto": bruto,
            "descuento": descuento,
            "venta_neta": neto,
            "impuesto_icms": iva,
            "total_facturado": neto + iva,
            "costo_registrado": costo,
            "utilidad_bruta": utilidad,
            "margen_utilidad": margen,
        },
    })
