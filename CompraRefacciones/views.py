# CompraRefacciones/views.py
from datetime import timedelta
from hashlib import sha256
import json

from django.core.cache import cache
from django.db import connections
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from CrmConformidad.jwt_authentication import CRMJWTAuthentication
from .serializers import CompraRefaccionesSerializer, CompraRefaccionPiezaSerializer

DB_ALIAS = "tdsql"
TABLA = "matriz_facturasref"
TABLA_PIEZAS = "matriz_compraref"
CACHE_OPCIONES = "compra_refacciones_opciones_v2"
CACHE_SEGUNDOS = 60

# Mismas reglas que se aplicaban en React.
# Actualmente Autopart se identifica por "Serie": los campos codigo, linea y marca
# no forman parte de la respuesta original del endpoint de facturas.
CONDICION_VW = """(
    "Proveedor" ILIKE '%%VOLKSWAGEN%%'
    OR "Proveedor" ILIKE '%%VW DE MEXICO%%'
    OR "Proveedor" ILIKE '%%VW MEXICO%%'
)"""
CONDICION_AP = """("Serie" ILIKE '%%AP%%')"""


def texto_parametro(request, nombre):
    return str(request.query_params.get(nombre, "") or "").strip()


def entero_parametro(request, nombre, default, minimo=None, maximo=None):
    try:
        valor = int(request.query_params.get(nombre, default))
    except (TypeError, ValueError):
        valor = default
    if minimo is not None:
        valor = max(minimo, valor)
    if maximo is not None:
        valor = min(maximo, valor)
    return valor


def validar_fecha(valor, nombre):
    if not valor:
        return None
    fecha = parse_date(valor)
    if fecha is None:
        raise ValueError(f"El parámetro '{nombre}' debe tener formato YYYY-MM-DD.")
    return fecha


def cursor_a_dicts(cursor):
    columnas = [columna[0] for columna in cursor.description]
    return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]


def construir_filtros(request):
    agencia = texto_parametro(request, "agencia")
    desde = validar_fecha(texto_parametro(request, "fecha_desde"), "fecha_desde")
    hasta = validar_fecha(texto_parametro(request, "fecha_hasta"), "fecha_hasta")
    busqueda = texto_parametro(request, "q")
    if desde and hasta and desde > hasta:
        raise ValueError("'fecha_desde' no puede ser mayor que 'fecha_hasta'.")

    # Valores constantes: facilitan que PostgreSQL use los índices parciales.
    condiciones = ["\"TpItensNFE\" = '1'", "\"SitNF\" = 'V'"]
    parametros = []
    if agencia:
        condiciones.append('"Agencia" = %s')
        parametros.append(agencia)
    if desde:
        condiciones.append('"DtEntrada" >= %s')
        parametros.append(desde)
    if hasta:
        condiciones.append('"DtEntrada" < %s')
        parametros.append(hasta + timedelta(days=1))
    if busqueda:
        condiciones.append("""(
            "Agencia" ILIKE %s OR
            "NrNota"::text ILIKE %s OR
            "Serie" ILIKE %s OR
            "NrPedUnPar" ILIKE %s OR
            "Proveedor" ILIKE %s
        )""")
        parametros.extend([f"%{busqueda}%"] * 5)
    return "WHERE " + " AND ".join(condiciones), parametros


def obtener_resumen(where_sql, parametros):
    """Agrupa en PostgreSQL y almacena solamente resultados pequeños durante 60 s."""
    firma = json.dumps([where_sql, parametros], default=str, ensure_ascii=False)
    clave = "compra_ref_resumen_v2_" + sha256(firma.encode("utf-8")).hexdigest()
    resumen = cache.get(clave)
    if resumen is not None:
        return resumen

    sql_metricas = f"""
        SELECT
            COUNT(*) AS registros,
            COALESCE(SUM("QtProdutos"), 0) AS cantidad_total,
            COALESCE(SUM("Subtotal"), 0) AS subtotal,
            COALESCE(SUM("Total"), 0) AS total,
            COUNT(*) FILTER (WHERE {CONDICION_VW}) AS vw_facturas,
            COALESCE(SUM("Total") FILTER (WHERE {CONDICION_VW}), 0) AS vw_total,
            COALESCE(SUM("QtProdutos") FILTER (WHERE {CONDICION_VW}), 0) AS vw_cantidad,
            COUNT(*) FILTER (WHERE {CONDICION_AP}) AS ap_facturas,
            COALESCE(SUM("Total") FILTER (WHERE {CONDICION_AP}), 0) AS ap_total,
            COALESCE(SUM("QtProdutos") FILTER (WHERE {CONDICION_AP}), 0) AS ap_cantidad
        FROM {TABLA}
        {where_sql}
    """
    sql_agencias = f"""
        SELECT COALESCE(NULLIF(TRIM("Agencia"), ''), 'Sin agencia') AS type,
               COALESCE(SUM("Total"), 0) AS total,
               COUNT(*) AS facturas
        FROM {TABLA}
        {where_sql}
        GROUP BY 1
        ORDER BY total DESC
    """
    sql_proveedores = f"""
        SELECT COALESCE(NULLIF(TRIM("Proveedor"), ''), 'Sin proveedor') AS nombre,
               COALESCE(SUM("Total"), 0) AS total,
               COUNT(*) AS facturas
        FROM {TABLA}
        {where_sql}
        GROUP BY 1
        ORDER BY total DESC
    """
    with connections[DB_ALIAS].cursor() as cursor:
        cursor.execute(sql_metricas, parametros)
        fila = cursor_a_dicts(cursor)[0]
        cursor.execute(sql_agencias, parametros)
        agencias = cursor_a_dicts(cursor)
        cursor.execute(sql_proveedores, parametros)
        proveedores = cursor_a_dicts(cursor)

    resumen = {
        "metricas": {
            "registros": fila["registros"],
            "cantidad_total": fila["cantidad_total"],
            "subtotal": fila["subtotal"],
            "total": fila["total"],
        },
        "analisis": {
            "agencias": agencias,
            "proveedores": proveedores,
            "vw_mexico": {
                "facturas": fila["vw_facturas"],
                "total": fila["vw_total"],
                "cantidad": fila["vw_cantidad"],
            },
            "autopart": {
                "facturas": fila["ap_facturas"],
                "total": fila["ap_total"],
                "cantidad": fila["ap_cantidad"],
            },
        },
    }
    cache.set(clave, resumen, CACHE_SEGUNDOS)
    return resumen


class CompraRefaccionesListView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        pagina = entero_parametro(request, "page", 1, minimo=1)
        tamano_pagina = entero_parametro(request, "page_size", 50, minimo=1, maximo=2000)
        offset = (pagina - 1) * tamano_pagina
        try:
            where_sql, parametros = construir_filtros(request)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # Esta consulta ya NO calcula COUNT OVER ni SUM OVER por cada factura.
        consulta = f"""
            SELECT "rowid__" AS rowid__, "Agencia" AS agencia,
                   "NrNota" AS nrnota, "Serie" AS serie,
                   "NrPedUnPar" AS nrpedunpar, "QtProdutos" AS qtprodutos,
                   "Proveedor" AS proveedor,
                   "DtEmissao"::date AS dtemissao,
                   "DtEntrada"::date AS dtentrada,
                   "Subtotal" AS subtotal, "Total" AS total
            FROM {TABLA}
            {where_sql}
            ORDER BY "DtEntrada" DESC NULLS LAST,
                     "NrNota" DESC NULLS LAST,
                     "rowid__" DESC NULLS LAST
            LIMIT %s OFFSET %s
        """
        with connections[DB_ALIAS].cursor() as cursor:
            cursor.execute(consulta, [*parametros, tamano_pagina, offset])
            registros = cursor_a_dicts(cursor)

        if texto_parametro(request, "solo_detalle") == "1":
            return Response({
                "page": pagina,
                "page_size": tamano_pagina,
                "results": CompraRefaccionesSerializer(registros, many=True).data,
            })

        resumen = obtener_resumen(where_sql, parametros)
        return Response({
            "count": resumen["metricas"]["registros"],
            "page": pagina,
            "page_size": tamano_pagina,
            "metricas": resumen["metricas"],
            "analisis": resumen["analisis"],
            "results": CompraRefaccionesSerializer(registros, many=True).data,
        })


class CompraRefaccionesOpcionesView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        resultado = cache.get(CACHE_OPCIONES)
        if resultado is not None:
            return Response(resultado)
        consulta = f"""
            SELECT DISTINCT TRIM("Agencia") AS agencia
            FROM {TABLA}
            WHERE "TpItensNFE" = '1'
              AND "SitNF" = 'V'
              AND "Agencia" IS NOT NULL
              AND TRIM("Agencia") <> ''
            ORDER BY agencia
        """
        with connections[DB_ALIAS].cursor() as cursor:
            cursor.execute(consulta)
            agencias = [fila[0] for fila in cursor.fetchall() if fila[0]]
        resultado = {"agencias": agencias}
        cache.set(CACHE_OPCIONES, resultado, 3600)
        return Response(resultado)


class CompraRefaccionesPiezasView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        agencia = texto_parametro(request, "agencia")
        nota_texto = texto_parametro(request, "nrnota")
        serie = texto_parametro(request, "serie")
        if not agencia:
            return Response({"detail": "El parámetro 'agencia' es obligatorio."}, status=status.HTTP_400_BAD_REQUEST)
        if not nota_texto:
            return Response({"detail": "El parámetro 'nrnota' es obligatorio."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            nrnota = int(nota_texto)
        except (TypeError, ValueError):
            return Response({"detail": "El parámetro 'nrnota' debe ser numérico."}, status=status.HTTP_400_BAD_REQUEST)

        # Las columnas de matriz_compraref son minúsculas y sin comillas.
        # Cuando la factura tiene serie, el detalle también se restringe por ella.
        filtro_serie = "AND cr.serie = %s" if serie else ""
        validar_serie = 'AND fr."Serie" = cr.serie' if serie else ""
        parametros = [agencia, nrnota] + ([serie] if serie else [])
        consulta = f"""
            SELECT cr.rowid__ AS rowid__, cr.agencia, cr.nrnota, cr.serie,
                   cr.seqitem, cr.prodserv, cr.descrprod, cr.unidade,
                   cr.qtprodutos, cr.vrunitliq, cr.vrunitbruto,
                   cr.vrliqtotal, cr.dtentrada, cr.nrpedcompra
            FROM {TABLA_PIEZAS} cr
            WHERE cr.agencia = %s
              AND cr.nrnota = %s
              {filtro_serie}
              AND (cr.unidade <> 'UN' OR cr.qtprodutos <> 1)
              AND EXISTS (
                  SELECT 1
                  FROM {TABLA} fr
                  WHERE fr."Agencia" = cr.agencia
                    AND fr."NrNota" = cr.nrnota
                    {validar_serie}
                    AND fr."TpItensNFE" = '1'
                    AND fr."SitNF" = 'V'
              )
            ORDER BY cr.seqitem ASC NULLS LAST, cr.rowid__ ASC NULLS LAST
        """
        with connections[DB_ALIAS].cursor() as cursor:
            cursor.execute(consulta, parametros)
            registros = cursor_a_dicts(cursor)

        resumen = {
            "partidas": len(registros),
            "cantidad_total": sum(float(fila["qtprodutos"] or 0) for fila in registros),
            "importe_total": sum(float(fila["vrliqtotal"] or 0) for fila in registros),
        }
        return Response({
            "factura": {"agencia": agencia, "nrnota": nrnota, "serie": serie},
            "resumen": resumen,
            "results": CompraRefaccionPiezaSerializer(registros, many=True).data,
        })
