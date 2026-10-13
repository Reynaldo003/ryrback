# VentaRefacciones/views.py
import hashlib
import logging
from datetime import date, timedelta

from django.core.cache import cache
from django.db import DatabaseError, connections, transaction
from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

CONEXION = "tdsql"  # Cambiar solo si tu alias de settings.py es otro.
REGISTROS_POR_PAGINA = 25
logger = logging.getLogger(__name__)


def _obtener_filtros(request):
    agencia = request.GET.get("agencia", "").strip()[:100]
    busqueda = request.GET.get("q", "").strip()[:80]
    try:
        desde = date.fromisoformat(request.GET["fecha_desde"]) if request.GET.get("fecha_desde") else None
        hasta = date.fromisoformat(request.GET["fecha_hasta"]) if request.GET.get("fecha_hasta") else None
        pagina = int(request.GET.get("page", 1))
        tamanio = int(request.GET.get("page_size", REGISTROS_POR_PAGINA))
    except (ValueError, TypeError) as error:
        raise ValueError("Fecha o paginación no válida.") from error

    if not desde or not hasta:
        raise ValueError("Selecciona una fecha inicial y final.")
    if desde > hasta or (hasta - desde).days > 366:
        raise ValueError("El intervalo de fechas debe estar entre 1 y 367 días.")
    if pagina < 1 or tamanio < 1:
        raise ValueError("La página y su tamaño deben ser mayores a cero.")
    return {
        "agencia": agencia,
        "q": busqueda,
        "fecha_desde": desde,
        "fecha_hasta": hasta,
        "page": pagina,
        "page_size": min(tamanio, 100),
    }


def _construir_where(filtros):
    condiciones = [
        'vr."TpProduto" = %s',
        '(vr."CodArea" = \'AT\' OR (vr."CodArea" = \'PA\' AND vr."Serie" <> \'IN\'))',
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
        condiciones.append('(vr."Serie" ILIKE %s OR vr."NrNota"::text ILIKE %s)')
        patron = f'%{filtros["q"]}%'
        parametros.extend([patron, patron])
    return " AND ".join(condiciones), parametros


def _consultar(sql, parametros=None, unico=False, limite_ms=12000):
    # Limitar una consulta evita que una petición lenta sature indefinidamente PostgreSQL.
    # SET LOCAL afecta únicamente esta transacción, nunca las siguientes peticiones.
    with transaction.atomic(using=CONEXION):
        with connections[CONEXION].cursor() as cursor:
            cursor.execute("SELECT set_config('statement_timeout', %s, true)", [str(limite_ms)])
            cursor.execute(sql, parametros or [])
            columnas = [columna[0] for columna in cursor.description]
            if unico:
                fila = cursor.fetchone()
                return dict(zip(columnas, fila)) if fila else {}
            return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]


def _error_base_datos(error):
    logger.exception("Error consultando ventas de refacciones: %s", error)
    return JsonResponse({"detail": "La consulta excedió el tiempo permitido o la base de datos no respondió. Revisa los índices y los logs."}, status=503)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def venta_refacciones_lista(request):
    try:
        filtros = _obtener_filtros(request)
    except ValueError as error:
        return JsonResponse({"detail": str(error)}, status=400)

    where, parametros = _construir_where(filtros)
    desplazamiento = (filtros["page"] - 1) * filtros["page_size"]

    # UNA agregación sobre matriz_ventasref. Primero paginar; solo después buscar
    # la descripción del cliente de las facturas visibles (máximo 100).
    sql = f"""
        WITH facturas AS (
            SELECT
                vr."Agencia" AS agencia,
                vr."Serie" AS serie,
                vr."NrNota" AS nrnota,
                vr."DtEmissao"::date AS fecha,
                MIN(vr."CodEntidade") AS codigo_cliente,
                COUNT(*) AS partidas,
                COALESCE(SUM(vr."QtProdutos"), 0) AS cantidad,
                ROUND(COALESCE(SUM(vr."VrBrutoItem"::numeric), 0), 2) AS importe_bruto,
                ROUND(COALESCE(SUM(vr."VrDescItem"::numeric), 0), 2) AS descuento,
                ROUND(COALESCE(SUM(vr."VrLiqItem"::numeric), 0), 2) AS venta_neta,
                SUM(ROUND(COALESCE(vr."VrCustoEstoque", 0)::numeric, 2)) AS costo_registrado
            FROM public.matriz_ventasref vr
            WHERE {where}
            GROUP BY vr."Agencia", vr."Serie", vr."NrNota", vr."DtEmissao"::date
        ),
        totales AS (
            SELECT
                f.*,
                f.venta_neta - f.costo_registrado AS utilidad_bruta,
                COUNT(*) OVER () AS facturas_total,
                SUM(f.partidas) OVER () AS partidas_total,
                SUM(f.cantidad) OVER () AS piezas_total,
                SUM(f.importe_bruto) OVER () AS bruto_total,
                SUM(f.descuento) OVER () AS descuento_total,
                SUM(f.venta_neta) OVER () AS ventas_total,
                SUM(f.costo_registrado) OVER () AS costo_total
            FROM facturas f
        ),
        pagina AS MATERIALIZED (
            SELECT * FROM totales
            ORDER BY fecha DESC, nrnota DESC NULLS LAST, agencia, serie
            LIMIT %s OFFSET %s
        )
        SELECT p.*,
            COALESCE(
                NULLIF(BTRIM(ent.razao_social), ''),
                NULLIF(BTRIM(CONCAT_WS(' ', ent.nomes, ent.sobrenm_pat, ent.sobrenm_mat)), ''),
                CASE WHEN p.codigo_cliente IS NULL THEN 'Sin cliente'
                     ELSE 'Cliente ' || p.codigo_cliente::text END
            ) AS cliente
        FROM pagina p
        LEFT JOIN LATERAL (
            SELECT e.razao_social, e.nomes, e.sobrenm_pat, e.sobrenm_mat
            FROM public.matriz_entidades e
            WHERE e.cod_entidade = p.codigo_cliente
              AND e.dn_modifico = CASE p.agencia
                  WHEN 'Vw Tuxtepec' THEN 1905
                  WHEN 'Vw Cordoba' THEN 2923
                  WHEN 'Vw Orizaba' THEN 2924
                  WHEN 'Vw Poza Rica' THEN 2927
                  WHEN 'Vw Tuxpan' THEN 2929
                  ELSE NULL END
            ORDER BY e.razao_social NULLS LAST
            LIMIT 1
        ) ent ON TRUE
        ORDER BY p.fecha DESC, p.nrnota DESC NULLS LAST, p.agencia, p.serie
    """
    try:
        filas = _consultar(sql, [*parametros, filtros["page_size"], desplazamiento])
    except DatabaseError as error:
        return _error_base_datos(error)

    facturas = [{clave: valor for clave, valor in fila.items() if not clave.endswith("_total")}
                for fila in filas]
    if request.GET.get("solo_detalle") == "1":
        return JsonResponse({"results": facturas, "page": filtros["page"], "page_size": filtros["page_size"]})

    primero = filas[0] if filas else {}
    ventas = primero.get("ventas_total") or 0
    costo = primero.get("costo_total") or 0
    utilidad = ventas - costo
    metricas = {
        "facturas": primero.get("facturas_total", 0),
        "partidas": primero.get("partidas_total", 0),
        "cantidad_total": primero.get("piezas_total", 0),
        "importe_bruto": primero.get("bruto_total", 0),
        "descuento": primero.get("descuento_total", 0),
        "venta_neta": ventas,
        "costo_registrado": costo,
        "utilidad_bruta": utilidad,
        "margen_utilidad": round(utilidad * 100 / ventas, 2) if ventas else 0,
    }
    return JsonResponse({
        "count": metricas["facturas"],
        "page": filtros["page"],
        "page_size": filtros["page_size"],
        "results": facturas,
        "metricas": metricas,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def venta_refacciones_analisis(request):
    """Ventas por línea y cliente, con agencia opcional y sin IVA."""

    try:
        filtros = _obtener_filtros(request)
    except ValueError as error:
        return JsonResponse({"detail": str(error)}, status=400)

    desde = filtros["fecha_desde"]
    hasta = filtros["fecha_hasta"]
    agencia = filtros["agencia"]

    if not desde or not hasta:
        return JsonResponse({
            "detail": "Selecciona un periodo válido."
        }, status=400)

    if (hasta - desde).days > 31:
        return JsonResponse({
            "detail": "Las gráficas permiten periodos de hasta 32 días."
        }, status=400)

    # Si agencia está vacía, no se aplica filtro de agencia.
    where, parametros = _construir_where(filtros)

    sql = f"""
        WITH grupos AS (
            SELECT
                GROUPING(vr."CodLinhaProd") AS tipo,
                vr."CodLinhaProd" AS codigo_linea,
                vr."Agencia" AS agencia,
                vr."CodEntidade" AS codigo_cliente,

                COUNT(*) AS items,

                COALESCE(
                    SUM(vr."QtProdutos"), 0
                ) AS piezas,

                ROUND(
                    COALESCE(
                        SUM(vr."VrLiqItem"::numeric), 0
                    ), 2
                ) AS ventas,

                COALESCE(
                    SUM(
                        ROUND(
                            COALESCE(vr."VrCustoEstoque", 0)::numeric,
                            2
                        )
                    ), 0
                ) AS costo

            FROM public.matriz_ventasref vr
            WHERE {where}

            GROUP BY GROUPING SETS (
                (vr."CodLinhaProd"),
                (vr."Agencia", vr."CodEntidade")
            )
        ),

        ordenados AS (
            SELECT
                g.*,

                ROW_NUMBER() OVER (
                    PARTITION BY g.tipo
                    ORDER BY g.ventas DESC
                ) AS posicion,

                SUM(g.ventas) OVER (
                    PARTITION BY g.tipo
                ) AS total_grupo

            FROM grupos g
        ),

        top_grupos AS MATERIALIZED (
            SELECT *
            FROM ordenados
            WHERE posicion <= 8
        )

        SELECT
            t.*,

            COALESCE(
                NULLIF(BTRIM(lin.nmlinhaprod), ''),
                NULLIF(BTRIM(t.codigo_linea), ''),
                'Sin línea'
            ) AS linea,

            COALESCE(
                NULLIF(BTRIM(ent.razao_social), ''),
                NULLIF(
                    BTRIM(
                        CONCAT_WS(
                            ' ',
                            ent.nomes,
                            ent.sobrenm_pat,
                            ent.sobrenm_mat
                        )
                    ), ''
                ),
                CASE
                    WHEN t.codigo_cliente IS NULL
                    THEN 'Sin cliente'
                    ELSE 'Cliente ' || t.codigo_cliente::text
                END
            ) AS cliente

        FROM top_grupos t

        LEFT JOIN LATERAL (
            SELECT l.nmlinhaprod
            FROM public.matriz_linea l
            WHERE l.codlinhaprod::text = t.codigo_linea
            ORDER BY l.nmlinhaprod NULLS LAST
            LIMIT 1
        ) lin ON t.tipo = 0

        LEFT JOIN LATERAL (
            SELECT
                e.razao_social,
                e.nomes,
                e.sobrenm_pat,
                e.sobrenm_mat

            FROM public.matriz_entidades e

            WHERE e.cod_entidade = t.codigo_cliente
              AND e.dn_modifico = CASE t.agencia
                  WHEN 'Vw Tuxtepec' THEN 1905
                  WHEN 'Vw Cordoba' THEN 2923
                  WHEN 'Vw Orizaba' THEN 2924
                  WHEN 'Vw Poza Rica' THEN 2927
                  WHEN 'Vw Tuxpan' THEN 2929
                  ELSE NULL
              END

            ORDER BY e.razao_social NULLS LAST
            LIMIT 1
        ) ent ON t.tipo = 1

        ORDER BY t.tipo, t.posicion
    """

    try:
        registros = _consultar(
            sql,
            parametros,
            limite_ms=12000
        )
    except DatabaseError as error:
        return _error_base_datos(error)

    lineas = []
    clientes = []

    for fila in registros:
        ventas = fila["ventas"] or 0
        costo = fila["costo"] or 0
        utilidad = ventas - costo
        total = fila["total_grupo"] or 0

        es_linea = fila["tipo"] == 0

        if es_linea:
            nombre = fila["linea"]
            codigo = fila["codigo_linea"]
        else:
            nombre = fila["cliente"]
            codigo = fila["codigo_cliente"]

            # Identificar la agencia al consultar todas.
            if not agencia:
                nombre = f'{fila["agencia"]} - {nombre}'

        detalle = {
            "nombre": nombre,
            "codigo": codigo,
            "items": fila["items"],
            "piezas": fila["piezas"],
            "ventas": ventas,
            "costo": costo,
            "utilidad_bruta": utilidad,
            "margen_bruto": (
                round(utilidad * 100 / ventas, 2)
                if ventas else 0
            ),
            "porcentaje_total": (
                round(ventas * 100 / total, 2)
                if total else 0
            ),
            "total_grupo": total
        }

        if es_linea:
            lineas.append(detalle)
        else:
            clientes.append(detalle)

    return JsonResponse({
        "lineas": lineas,
        "clientes": clientes
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
    agencia = request.GET.get("agencia", "").strip()
    serie = request.GET.get("serie") or None
    numero = request.GET.get("nrnota", "")
    fecha_texto = request.GET.get("fecha", "")
    try:
        if not agencia:
            raise ValueError("Falta agencia.")
        nrnota = int(numero)
        fecha = date.fromisoformat(fecha_texto)
    except (ValueError, TypeError):
        return JsonResponse({"detail": "Se requieren agencia, nota y fecha válidas."}, status=400)

    sql = """
        SELECT
            vr.rowid__ AS rowid__,
            vr."SeqItensNota" AS secuencia,
            vr."ProdOuServ" AS codigo_producto,
            pa.nombre_producto,
            vr."CodArea" AS codigo_area,
            vr."CodSetor" AS codigo_sector,
            vr."CodFunc" AS codigo_funcionario,
            fc.nombre_funcionario,
            vr."QtProdutos" AS cantidad,
            vr."PrcUnitario" AS precio_unitario,
            vr."VrBrutoItem" AS importe_bruto,
            vr."VrDescItem" AS descuento,
            vr."VrLiqItem" AS venta_neta,
            ROUND(COALESCE(vr."VrCustoEstoque", 0)::numeric, 2) AS costo_registrado
        FROM public.matriz_ventasref vr
        LEFT JOIN LATERAL (
            SELECT p.nmproduto AS nombre_producto
            FROM public.matriz_produtosativos_5vw p
            WHERE p.agencia = vr."Agencia" AND p.codproduto = vr."ProdOuServ"
            ORDER BY p.nmproduto NULLS LAST LIMIT 1
        ) pa ON TRUE
        LEFT JOIN LATERAL (
            SELECT COALESCE(NULLIF(BTRIM(f.nombre), ''), NULLIF(BTRIM(f.nm_funcionario), '')) AS nombre_funcionario
            FROM public.matriz_funcionarios f
            WHERE f.agencia = vr."Agencia" AND f.cod_funcionario = vr."CodFunc"
            ORDER BY f.rowid__ DESC NULLS LAST LIMIT 1
        ) fc ON TRUE
        WHERE vr."Agencia" = %s
          AND vr."Serie" IS NOT DISTINCT FROM %s
          AND vr."NrNota" = %s
          AND vr."DtEmissao" >= %s
          AND vr."DtEmissao" < %s
          AND vr."TpProduto" = 'P'
          AND (vr."CodArea" = 'AT' OR (vr."CodArea" = 'PA' AND vr."Serie" <> 'IN'))
        ORDER BY vr."SeqItensNota" NULLS LAST, vr.rowid__ NULLS LAST
    """
    try:
        piezas = _consultar(sql, [agencia, serie, nrnota, fecha, fecha + timedelta(days=1)])
    except DatabaseError as error:
        return _error_base_datos(error)

    from decimal import Decimal
    venta = round(sum(Decimal(str(p["venta_neta"] or 0)) for p in piezas), 2)
    costo = sum(Decimal(str(p["costo_registrado"] or 0)) for p in piezas)
    return JsonResponse({
        "results": piezas,
        "resumen": {
            "partidas": len(piezas),
            "cantidad_total": sum(Decimal(str(p["cantidad"] or 0)) for p in piezas),
            "venta_neta": venta,
            "costo_registrado": costo,
            "utilidad_bruta": venta - costo,
        },
    })
