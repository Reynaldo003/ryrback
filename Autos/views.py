# Autos/views.py
from django.core.cache import cache
from django.db import connections
from django.db.models import F
from django.db.models.functions import Trim, Upper
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from CrmConformidad.jwt_authentication import CRMJWTAuthentication
from Digitales.models import ExpedienteDigital
from .serializers import VWVNSerializer

BASE_DATOS = "tdsql"
TABLA = 'public."VW_VN"'
# Coincide con la clasificación visual que ya utiliza VentasVN.jsx.
FAMILIAS_COMERCIALES = ("CADDY", "CRAFTER", "TRANSPORTER", "AMAROK", "CARAVELLE")
CONDICION_COMERCIAL = "(" + " OR ".join(
    f'"NmFamilia" ILIKE \'%{modelo}%\'' for modelo in FAMILIAS_COMERCIALES
) + ")"
EXPRESION_VIN = 'UPPER(BTRIM("ProdOuServ"))'
EXPRESION_AGENCIA = f'CASE WHEN {CONDICION_COMERCIAL} THEN \'R&R VC\' ELSE "AGENCIA" END'


def cursor_a_dicts(cursor):
    columnas = [columna[0] for columna in cursor.description]
    return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]


def normalizar_vin(valor):
    return str(valor or "").strip().upper()


def obtener_vins_digitales():
    """Lee los VIN de CRM. Caché corta para evitar repetir el cruce por cada filtro."""
    clave = "vw_vn_vins_digitales"
    vins_cache = cache.get(clave)
    if vins_cache is not None:
        return vins_cache
    consulta = (
        ExpedienteDigital.objects
        .exclude(vin_facturado__isnull=True)
        .exclude(vin_facturado="")
        .values_list("vin_facturado", flat=True)
    )
    vins = sorted({
        vin for valor in consulta.iterator(chunk_size=2000)
        if (vin := normalizar_vin(valor))
    })
    cache.set(clave, vins, timeout=60)
    return vins


def leer_filtros(request, fecha_desde=None, fecha_hasta=None):
    """Normaliza los filtros comunes a detalle y dashboard."""
    parametros = request.query_params
    cond_uso = str(parametros.get("cond_uso", "N") or "N").strip().upper()
    if cond_uso not in ("N", "U"):
        cond_uso = "N"

    valores = {
        "cond_uso": cond_uso,
        "q": str(parametros.get("q", "") or "").strip(),
        "agencia": str(parametros.get("agencia", "") or "").strip(),
        "asesor": str(parametros.get("asesor", "") or "").strip(),
        "familia": str(parametros.get("familia", "") or "").strip(),
        "condicion_pago": str(parametros.get("condicion_pago", "") or "").strip(),
        "fecha_desde": fecha_desde if fecha_desde is not None else str(parametros.get("fecha_desde", "") or "").strip(),
        "fecha_hasta": fecha_hasta if fecha_hasta is not None else str(parametros.get("fecha_hasta", "") or "").strip(),
        "venta_digital": str(parametros.get("venta_digital", "") or "").strip().lower(),
    }
    for clave in ("fecha_desde", "fecha_hasta"):
        if valores[clave] and parse_date(valores[clave]) is None:
            raise ValueError(f"{clave} debe tener formato AAAA-MM-DD")
    return valores


def construir_where(filtros, vins_digitales=None):
    """SQL parametrizado; las únicas expresiones dinámicas proceden de constantes internas."""
    # N y U se validan en leer_filtros. El literal permite utilizar índices parciales.
    condiciones = [f'"CondUso" = {filtros["cond_uso"]!r}']
    parametros = []
    if filtros["fecha_desde"]:
        condiciones.append('"DtEmissao" >= %s')
        parametros.append(filtros["fecha_desde"])
    if filtros["fecha_hasta"]:
        condiciones.append('"DtEmissao" <= %s')
        parametros.append(filtros["fecha_hasta"])

    agencia = filtros["agencia"]
    if agencia == "R&R VC":
        condiciones.append(CONDICION_COMERCIAL)
    elif agencia:
        condiciones.append('"AGENCIA" = %s')
        condiciones.append(f'("NmFamilia" IS NULL OR NOT {CONDICION_COMERCIAL})')
        parametros.append(agencia)

    for clave, columna in (
        ("asesor", '"Asesor"'),
        ("familia", '"NmFamilia"'),
        ("condicion_pago", '"NmCondPgto"'),
    ):
        if filtros[clave]:
            condiciones.append(f"{columna} = %s")
            parametros.append(filtros[clave])

    if filtros["q"]:
        columnas = ('"Serie"', '"RazaoSocial"', '"Asesor"', '"AGENCIA"', '"NmFamilia"', '"ProdOuServ"')
        condiciones.append("(" + " OR ".join(f"{campo} ILIKE %s" for campo in columnas) + ")")
        parametros.extend([f'%{filtros["q"]}%'] * len(columnas))

    if filtros["venta_digital"] in ("1", "true", "si", "sí"):
        if vins_digitales:
            condiciones.append(f"{EXPRESION_VIN} = ANY(%s::text[])")
            parametros.append(vins_digitales)
        else:
            condiciones.append("FALSE")

    return "WHERE " + " AND ".join(condiciones), parametros


def obtener_opciones(cond_uso):
    """Una consulta y caché corta para no calcular 4 DISTINCT en cada carga."""
    clave = f"vw_vn_opciones_{cond_uso}"
    opciones = cache.get(clave)
    if opciones is not None:
        return opciones

    consulta = f'''
        SELECT
            ARRAY_AGG(DISTINCT "AGENCIA" ORDER BY "AGENCIA") FILTER
                (WHERE "AGENCIA" IS NOT NULL AND BTRIM("AGENCIA") <> '') AS agencias,
            ARRAY_AGG(DISTINCT "Asesor" ORDER BY "Asesor") FILTER
                (WHERE "Asesor" IS NOT NULL AND BTRIM("Asesor") <> '') AS asesores,
            ARRAY_AGG(DISTINCT "NmFamilia" ORDER BY "NmFamilia") FILTER
                (WHERE "NmFamilia" IS NOT NULL AND BTRIM("NmFamilia") <> '') AS familias,
            ARRAY_AGG(DISTINCT "NmCondPgto" ORDER BY "NmCondPgto") FILTER
                (WHERE "NmCondPgto" IS NOT NULL AND BTRIM("NmCondPgto") <> '') AS condiciones_pago
        FROM {TABLA}
        WHERE "CondUso" = %s
    '''
    with connections[BASE_DATOS].cursor() as cursor:
        cursor.execute(consulta, [cond_uso])
        fila = cursor.fetchone()
    opciones = {
        "agencias": list(fila[0] or []),
        "asesores": list(fila[1] or []),
        "familias": list(fila[2] or []),
        "condiciones_pago": list(fila[3] or []),
    }
    cache.set(clave, opciones, timeout=1800)
    return opciones


class VWVNListView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            filtros = leer_filtros(request)
        except ValueError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            pagina = max(1, int(request.query_params.get("page", 1)))
            tamano = max(1, min(100, int(request.query_params.get("page_size", 50))))
        except (ValueError, TypeError):
            pagina, tamano = 1, 50
        offset = (pagina - 1) * tamano

        aplicar_digital = filtros["venta_digital"] in ("1", "true", "si", "sí")
        vins_digitales = obtener_vins_digitales() if aplicar_digital else None
        where_sql, parametros = construir_where(filtros, vins_digitales)

        consulta = f'''
            SELECT
                "Serie" AS serie, "NrNota" AS nr_nota, "TpProduto" AS tp_producto,
                "ProdOuServ" AS producto_servicio, "PrcUnitario" AS precio_unitario,
                "VrBrutoItem" AS valor_bruto_item, "InfluiEstat" AS influye_estadistica,
                "VrDescItem" AS valor_descuento_item, "CodCondPgto" AS codigo_condicion_pago,
                "ValorFactura" AS valor_factura, "ValorFacturaSnIva" AS valor_factura_sin_iva,
                "ValorCompra" AS valor_compra, "ISAN" AS isan, "IVA" AS iva,
                "CodEntidade" AS codigo_entidad, "DtEmissao" AS fecha_emision,
                "Situacao" AS situacion, "TpNF" AS tipo_nf, "NrMov" AS nr_mov,
                "DrUltVenda" AS fecha_ultima_venta, "RazaoSocial" AS razon_social,
                "TpPessoa" AS tipo_persona, "VrTotalProds" AS valor_total_productos,
                "CodMarca" AS codigo_marca, "NmMarca" AS nombre_marca,
                "NmFamilia" AS nombre_familia, "CondUso" AS condicion_uso,
                "NmCondPgto" AS nombre_condicion_pago, "Asesor" AS asesor,
                {EXPRESION_AGENCIA} AS agencia
            FROM {TABLA}
            {where_sql}
            ORDER BY "DtEmissao" DESC NULLS LAST, "NrNota" DESC NULLS LAST,
                     "Serie" DESC NULLS LAST, "ProdOuServ" DESC NULLS LAST
            LIMIT %s OFFSET %s
        '''
        with connections[BASE_DATOS].cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) FROM {TABLA} {where_sql}", parametros)
            total = cursor.fetchone()[0]
            cursor.execute(consulta, [*parametros, tamano, offset])
            registros = cursor_a_dicts(cursor)

        vins_pagina = {
            normalizar_vin(fila["producto_servicio"])
            for fila in registros if fila["producto_servicio"]
        }
        expedientes_por_vin = {}
        if vins_pagina:
            expedientes = (
                ExpedienteDigital.objects
                .annotate(vin_normalizado=Upper(Trim(F("vin_facturado"))))
                .filter(vin_normalizado__in=vins_pagina)
                .select_related("cliente")
            )
            for expediente in expedientes:
                expedientes_por_vin[normalizar_vin(expediente.vin_facturado)] = expediente

        for registro in registros:
            expediente = expedientes_por_vin.get(normalizar_vin(registro["producto_servicio"]))
            registro["es_venta_digital"] = expediente is not None
            registro["tipo_venta"] = "Venta digital" if expediente else ""
            registro["prospecto_digital"] = None
            if expediente:
                cliente = expediente.cliente
                registro["prospecto_digital"] = {
                    "id": expediente.id,
                    "cliente_id": expediente.cliente_id,
                    "nombre": cliente.nombre if cliente else "",
                    "telefono": cliente.telefono if cliente else "",
                    "correo": cliente.correo if cliente else "",
                    "agencia": expediente.agencia,
                    "estado": expediente.estado,
                    "auto_interes": expediente.auto_interes,
                    "asesor_digital": expediente.asesor_digital,
                    "asesor_ventas": expediente.asesor_ventas,
                    "enganche_monto": expediente.enganche_monto,
                    "presupuesto_mensual": expediente.presupuesto_mensual,
                    "forma_pago": expediente.forma_pago,
                    "plazo_compra": expediente.plazo_compra,
                    "vin_facturado": expediente.vin_facturado,
                    "facturado_at": expediente.facturado_at,
                }

        return Response({
            "count": total, "page": pagina, "page_size": tamano,
            "results": VWVNSerializer(registros, many=True).data,
        })


class VWVNDashboardView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            filtros = leer_filtros(request)
            anio_tendencia = request.query_params.get("anio_tendencia", "")
            if anio_tendencia:
                anio_tendencia = int(anio_tendencia)
                if not 2000 <= anio_tendencia <= 2100:
                    raise ValueError("anio_tendencia fuera de rango")
        except (ValueError, TypeError) as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)

        # Los VIN están en crm_ryr; VW_VN está en tdsql_vw.
        vins_digitales = obtener_vins_digitales()
        where_sql, parametros = construir_where(filtros, vins_digitales)

        # GROUPING SETS calcula cinco niveles de agregación sobre el mismo filtrado.
        consulta = f'''
            WITH filtrado AS (
                SELECT
                    DATE_TRUNC('month', "DtEmissao"::timestamp) AS periodo_mes,
                    COALESCE(NULLIF(BTRIM("Asesor"), ''), 'Sin asesor') AS asesor,
                    COALESCE(NULLIF(BTRIM("NmFamilia"), ''), 'Sin familia') AS familia,
                    COALESCE(NULLIF(BTRIM("NmCondPgto"), ''), 'Sin condición') AS condicion_pago,
                    "ProdOuServ" AS producto_servicio,
                    "Situacao" AS situacion,
                    "ValorFacturaSnIva" AS factura_sin_iva,
                    "ISAN" AS isan,
                    "ValorCompra" AS costo,
                    {EXPRESION_VIN} AS vin_normalizado
                FROM {TABLA}
                {where_sql}
            )
            SELECT
                GROUPING(periodo_mes) AS g_mes,
                GROUPING(asesor) AS g_asesor,
                GROUPING(familia) AS g_familia,
                GROUPING(condicion_pago) AS g_pago,
                periodo_mes, asesor, familia, condicion_pago,
                COUNT(producto_servicio) AS productos,
                COUNT(*) FILTER (WHERE situacion = 'E') AS unidades_vendidas,
                COALESCE(SUM(COALESCE(factura_sin_iva, 0) - COALESCE(isan, 0)), 0) AS ingresos,
                COALESCE(SUM(COALESCE(costo, 0)), 0) AS costo,
                COUNT(*) FILTER (WHERE vin_normalizado = ANY(%s::text[])) AS ventas_digitales
            FROM filtrado
            GROUP BY GROUPING SETS ((), (periodo_mes), (asesor), (familia), (condicion_pago))
        '''

        totales = {"productos": 0, "unidades_vendidas": 0, "ingresos": 0, "costo": 0, "ventas_digitales": 0}
        graficas = {"por_mes": [], "por_asesor": [], "por_familia": [], "por_condicion_pago": [], "tendencia_anual": []}
        with connections[BASE_DATOS].cursor() as cursor:
            cursor.execute(consulta, [*parametros, vins_digitales])
            filas = cursor_a_dicts(cursor)

            for fila in filas:
                datos = {campo: fila[campo] for campo in totales}
                if fila["g_mes"] == 0:
                    periodo = fila["periodo_mes"]
                    if periodo is not None:
                        graficas["por_mes"].append({
                            **datos, "anio": periodo.year, "mes": periodo.month,
                            "periodo": periodo.strftime("%Y-%m"),
                        })
                elif fila["g_asesor"] == 0:
                    graficas["por_asesor"].append({**datos, "asesor": fila["asesor"]})
                elif fila["g_familia"] == 0:
                    graficas["por_familia"].append({**datos, "familia": fila["familia"]})
                elif fila["g_pago"] == 0:
                    graficas["por_condicion_pago"].append({**datos, "condicion_pago": fila["condicion_pago"]})
                else:
                    totales = datos

            # La tendencia anual evita la segunda llamada HTTP al endpoint completo.
            if anio_tendencia:
                anual = dict(filtros)
                anual["fecha_desde"] = f"{anio_tendencia}-01-01"
                anual["fecha_hasta"] = f"{anio_tendencia}-12-31"
                where_anual, parametros_anual = construir_where(anual, vins_digitales)
                consulta_anual = f'''
                    SELECT DATE_TRUNC('month', "DtEmissao"::timestamp) AS periodo_mes,
                           COUNT("ProdOuServ") AS productos,
                           COUNT(*) FILTER (WHERE "Situacao" = 'E') AS unidades_vendidas,
                           COALESCE(SUM(COALESCE("ValorFacturaSnIva", 0) - COALESCE("ISAN", 0)), 0) AS ingresos,
                           COALESCE(SUM(COALESCE("ValorCompra", 0)), 0) AS costo
                    FROM {TABLA}
                    {where_anual}
                    GROUP BY 1
                    ORDER BY 1
                '''
                cursor.execute(consulta_anual, parametros_anual)
                for fila in cursor_a_dicts(cursor):
                    periodo = fila.pop("periodo_mes")
                    graficas["tendencia_anual"].append({
                        **fila, "anio": periodo.year, "mes": periodo.month,
                        "periodo": periodo.strftime("%Y-%m"),
                    })

        graficas["por_mes"].sort(key=lambda dato: (dato["anio"], dato["mes"]))
        for nombre in ("por_asesor", "por_familia", "por_condicion_pago"):
            graficas[nombre].sort(key=lambda dato: dato["unidades_vendidas"], reverse=True)

        return Response({
            "filtros_aplicados": filtros,
            "totales": totales,
            "graficas": graficas,
            "opciones": obtener_opciones(filtros["cond_uso"]),
        })
