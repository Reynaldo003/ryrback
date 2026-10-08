#presupuestos/views.py
from django.core.cache import cache
from django.db import connections
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from CrmConformidad.jwt_authentication import CRMJWTAuthentication
from .serializers import (
    MatrizPresupuestosSerializer,
    MatrizPresupuestosRefSerializer,
)
DB_ALIAS = "tdsql"
TABLA_PRESUPUESTOS = "public.matriz_presupuestos"
TABLA_REFACCIONES = "public.matriz_presupuestosref"
TABLA_FUNCIONARIOS = "public.matriz_funcionarios"
CACHE_OPCIONES = "presupuestos_opciones_v1"
# ============================================================
# HELPERS
# ============================================================
def texto_parametro(request, nombre):
    return str(request.query_params.get(nombre, "") or "").strip()
def entero_parametro(request, nombre):
    valor = texto_parametro(request, nombre)
    if not valor:
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        raise ValueError(f"El parámetro '{nombre}' debe ser un número entero.")
def validar_fecha(valor, nombre):
    if valor and not parse_date(valor):
        raise ValueError(f"El parámetro '{nombre}' debe tener formato YYYY-MM-DD.")
def cursor_a_dicts(cursor):
    columnas = [columna[0] for columna in cursor.description]
    return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]
def obtener_paginacion(request):
    try:
        pagina = int(request.query_params.get("page", 1))
    except (TypeError, ValueError):
        pagina = 1
    pagina = max(pagina, 1)
    try:
        tamano_pagina = int(request.query_params.get("page_size", 100))
    except (TypeError, ValueError):
        tamano_pagina = 100
    tamano_pagina = max(1, min(tamano_pagina, 500))
    offset = (pagina - 1) * tamano_pagina
    return pagina, tamano_pagina, offset
def _col(alias, nombre):
    columna = nombre.lower()
    return f"{alias}.{columna}" if alias else columna
def construir_filtros_presupuestos(request, alias=""):
    busqueda = texto_parametro(request, "q")
    agencia = texto_parametro(request, "agencia")
    nr_orcamento = entero_parametro(request, "nr_orcamento")
    sit = texto_parametro(request, "sit")
    cod_func = entero_parametro(request, "cod_func")
    cod_modelo = texto_parametro(request, "cod_modelo")
    placa = texto_parametro(request, "placa")
    chassi = texto_parametro(request, "chassi")
    fecha_desde = texto_parametro(request, "fecha_desde")
    fecha_hasta = texto_parametro(request, "fecha_hasta")
    validar_fecha(fecha_desde, "fecha_desde")
    validar_fecha(fecha_hasta, "fecha_hasta")
    condiciones = []
    parametros = []
    if busqueda:
        termino = f"%{busqueda}%"
        campos = [
            _col(alias, "Agencia"),
            f'CAST({_col(alias, "NrOrcamento")} AS TEXT)',
            _col(alias, "Nome"),
            _col(alias, "PlacaVeic"),
            _col(alias, "Chassi"),
            _col(alias, "CodModelo"),
            _col(alias, "Sit"),
            _col(alias, "Comentario"),
            _col(alias, "NrApolice"),
            _col(alias, "Sinistro"),
            _col(alias, "Asegurado"),
            _col(alias, "Taller"),
        ]
        condiciones.append("(" + " OR ".join(f"{campo} ILIKE %s" for campo in campos) + ")")
        parametros.extend([termino] * len(campos))
    filtros = (
        ("Agencia", agencia),
        ("NrOrcamento", nr_orcamento),
        ("Sit", sit),
        ("CodFunc", cod_func),
        ("CodModelo", cod_modelo),
    )
    for campo, valor in filtros:
        if valor is not None and valor != "":
            condiciones.append(f"{_col(alias, campo)} = %s")
            parametros.append(valor)
    if placa:
        condiciones.append(f'{_col(alias, "PlacaVeic")} ILIKE %s')
        parametros.append(f"%{placa}%")
    if chassi:
        condiciones.append(f'{_col(alias, "Chassi")} ILIKE %s')
        parametros.append(f"%{chassi}%")
    if fecha_desde:
        condiciones.append(f'{_col(alias, "DtEmissao")}::date >= %s')
        parametros.append(fecha_desde)
    if fecha_hasta:
        condiciones.append(f'{_col(alias, "DtEmissao")}::date <= %s')
        parametros.append(fecha_hasta)
    return ("WHERE " + " AND ".join(condiciones) if condiciones else ""), parametros
def construir_filtros_refacciones(request, alias=""):
    busqueda = texto_parametro(request, "q")
    agencia = texto_parametro(request, "agencia")
    nr_orcamento = entero_parametro(request, "nr_orcamento")
    cod_prod = texto_parametro(request, "cod_prod")
    fecha_desde = texto_parametro(request, "fecha_desde")
    fecha_hasta = texto_parametro(request, "fecha_hasta")
    validar_fecha(fecha_desde, "fecha_desde")
    validar_fecha(fecha_hasta, "fecha_hasta")
    condiciones = []
    parametros = []
    if busqueda:
        termino = f"%{busqueda}%"
        campos = [
            _col(alias, "Agencia"),
            f'CAST({_col(alias, "NrOrcamento")} AS TEXT)',
            _col(alias, "NmProd"),
            _col(alias, "CodProd"),
            _col(alias, "ComentRef"),
            _col(alias, "CodPacote"),
            _col(alias, "IdCasco"),
        ]
        condiciones.append("(" + " OR ".join(f"{campo} ILIKE %s" for campo in campos) + ")")
        parametros.extend([termino] * len(campos))
    if agencia:
        condiciones.append(f'{_col(alias, "Agencia")} = %s')
        parametros.append(agencia)
    if nr_orcamento is not None:
        condiciones.append(f'{_col(alias, "NrOrcamento")} = %s')
        parametros.append(nr_orcamento)
    if cod_prod:
        condiciones.append(f'{_col(alias, "CodProd")} = %s')
        parametros.append(cod_prod)
    if fecha_desde:
        condiciones.append(f'{_col(alias, "DtCreacion")}::date >= %s')
        parametros.append(fecha_desde)
    if fecha_hasta:
        condiciones.append(f'{_col(alias, "DtCreacion")}::date <= %s')
        parametros.append(fecha_hasta)
    return ("WHERE " + " AND ".join(condiciones) if condiciones else ""), parametros
# ============================================================
# LISTADO DE PRESUPUESTOS
# ============================================================
class MatrizPresupuestosListView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]
    def get(self, request):
        pagina, tamano_pagina, offset = obtener_paginacion(request)
        try:
            where_sql, parametros = construir_filtros_presupuestos(request, "mp")
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        consulta_total = f"""
            SELECT COUNT(*)
            FROM {TABLA_PRESUPUESTOS} AS mp
            {where_sql}
        """
        consulta = f"""
            SELECT
                mp.agencia AS agencia,
                mp.nrorcamento AS nr_orcamento,
                mp.codentidade AS cod_entidade,
                mp.nome AS nome,
                mp.endereco AS endereco,
                mp.bairro AS bairro,
                mp.codmunic AS cod_munic,
                mp.cep AS cep,
                mp.telfax1 AS tel_fax1,
                mp.telfax2 AS tel_fax2,
                mp.tppessoa AS tp_pessoa,
                mp.cgc AS cgc,
                mp.rg AS rg,
                mp.codsegurad AS cod_segurad,
                mp.placaveic AS placa_veic,
                mp.chassi AS chassi,
                mp.km AS km,
                mp.corveic AS cor_veic,
                mp.codmodelo AS cod_modelo,
                mp.anofabr AS ano_fabr,
                mp.anomod AS ano_mod,
                mp.vrprodutos AS vr_produtos,
                mp.vrmdo_pub AS vr_mdo_pub,
                mp.dtemissao::date AS dt_emissao,
                mp.hremissao AS hr_emissao,
                mp.dtvalidade::date AS dt_validade,
                mp.dtaprov::date AS dt_aprov,
                mp.sit AS sit,
                mp.nrprisma AS nr_prisma,
                mp.corprisma AS cor_prisma,
                mp.codfunc AS cod_func,
                mf.nm_funcionario AS nm_funcionario,
                mp.comentario AS comentario,
                mp.nrapolice AS nr_apolice,
                mp.descpcs AS desc_pcs,
                mp.vrdescpcs AS vr_desc_pcs,
                mp.descserv AS desc_serv,
                mp.vrdescserv AS vr_desc_serv,
                mp.nratped AS nr_at_ped,
                mp.tpentrega AS tp_entrega,
                mp.destped AS dest_ped,
                mp.tppreco AS tp_preco,
                mp.imprcodpcs AS impr_cod_pcs,
                mp.areaorcam AS area_orcam,
                mp.codcontacto AS cod_contacto,
                mp.codpacote AS cod_pacote,
                mp.sinistro AS sinistro,
                mp.ajustador AS ajustador,
                mp.orcamdyp AS orcam_dyp,
                mp.preselsapro AS pres_elsa_pro,
                mp.preselsaaut AS pres_elsa_aut,
                mp.nratend AS nr_atend,
                mp.vradicionais AS vr_adicionais,
                mp.nrremision AS nr_remision,
                mp.nrconvenio AS nr_convenio,
                mp.asegurado AS asegurado,
                mp.taller AS taller,
                mp.nrvale AS nr_vale,
                mp.nrordencpa AS nr_orden_cpa,
                mp.cod_empresa AS cod_empresa,
                mp.cod_filial AS cod_filial,
                mp.rowid__ AS rowid
            FROM {TABLA_PRESUPUESTOS} AS mp
            LEFT JOIN (
                SELECT
                    agencia AS agencia,
                    cod_funcionario AS cod_funcionario,
                    MAX(nm_funcionario) AS nm_funcionario
                FROM {TABLA_FUNCIONARIOS}
                GROUP BY agencia, cod_funcionario
            ) AS mf
                ON mf.cod_funcionario = mp.codfunc
                AND mf.agencia = mp.agencia
            {where_sql}
            ORDER BY
                CASE WHEN mp.nrorcamento IS NULL THEN 1 ELSE 0 END,
                mp.nrorcamento DESC,
                mp.agencia
            LIMIT %s OFFSET %s
        """
        with connections[DB_ALIAS].cursor() as cursor:
            cursor.execute(consulta_total, parametros)
            total = cursor.fetchone()[0]
            cursor.execute(consulta, [*parametros, tamano_pagina, offset])
            registros = cursor_a_dicts(cursor)
        serializer = MatrizPresupuestosSerializer(registros, many=True)
        return Response({
            "count": total,
            "page": pagina,
            "page_size": tamano_pagina,
            "results": serializer.data,
        })
# ============================================================
# LISTADO DE REFACCIONES DE LOS PRESUPUESTOS
# ============================================================
class MatrizPresupuestosRefListView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]
    def get(self, request):
        pagina, tamano_pagina, offset = obtener_paginacion(request)
        try:
            where_sql, parametros = construir_filtros_refacciones(request, "r")
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        consulta_total = f"""
            SELECT COUNT(*)
            FROM {TABLA_REFACCIONES} AS r
            {where_sql}
        """
        consulta = f"""
            SELECT
                r.agencia AS agencia,
                r.nrorcamento AS nr_orcamento,
                r.nmprod AS nm_prod,
                r.codprod AS cod_prod,
                r.qtprod AS qt_prod,
                r.precopc AS preco_pc,
                r.descpc AS desc_pc,
                r.vrdescpc AS vr_desc_pc,
                r.vrliqpc AS vr_liq_pc,
                r.vrcasco AS vr_casco,
                r.hrcreacion AS hr_creacion,
                r.dnstock AS dn_stock,
                r.dnmediavta AS dn_media_vta,
                r.dnctsolicitada AS dn_ct_solicitada,
                r.filler05 AS filler05,
                r.filler06 AS filler06,
                r.filler07 AS filler07,
                r.filler08 AS filler08,
                r.filler09 AS filler09,
                r.filler10 AS filler10,
                r.selec AS selec,
                r.idcasco AS id_casco,
                r.imprdesc AS impr_desc,
                r.filler12 AS filler12,
                r.filler13 AS filler13,
                r.filler14 AS filler14,
                r.filler15 AS filler15,
                r.filler16 AS filler16,
                r.codpacote AS cod_pacote,
                r.filler17 AS filler17,
                r.comentref AS coment_ref,
                r.dtcreacion::date AS dt_creacion,
                r.filler20 AS filler20,
                r."rowid__" AS rowid
            FROM {TABLA_REFACCIONES} AS r
            {where_sql}
            ORDER BY
                CASE WHEN r.nrorcamento IS NULL THEN 1 ELSE 0 END,
                r.nrorcamento DESC,
                r.agencia,
                r.codprod
            LIMIT %s OFFSET %s
        """
        with connections[DB_ALIAS].cursor() as cursor:
            cursor.execute(consulta_total, parametros)
            total = cursor.fetchone()[0]
            cursor.execute(consulta, [*parametros, tamano_pagina, offset])
            registros = cursor_a_dicts(cursor)
        serializer = MatrizPresupuestosRefSerializer(registros, many=True)
        return Response({
            "count": total,
            "page": pagina,
            "page_size": tamano_pagina,
            "results": serializer.data,
        })
# ============================================================
# DASHBOARD
# ============================================================
class PresupuestosDashboardView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]
    def get(self, request):
        try:
            where_sql, parametros = construir_filtros_presupuestos(request, "p")
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        base = f"""
            WITH base_presupuestos AS (
                SELECT p.*
                FROM {TABLA_PRESUPUESTOS} AS p
                {where_sql}
            )
        """
        consulta_totales = base + """
            SELECT
                COUNT(*) AS registros,
                COUNT(DISTINCT nrorcamento) AS presupuestos,
                COALESCE(SUM(COALESCE(vrprodutos, 0)), 0) AS monto_productos,
                COALESCE(SUM(COALESCE(vrmdo_pub, 0)), 0) AS monto_mano_obra,
                COALESCE(SUM(COALESCE(vradicionais, 0)), 0) AS monto_adicionales,
                COALESCE(SUM(COALESCE(vrdescpcs, 0)), 0) AS descuento_refacciones,
                COALESCE(SUM(COALESCE(vrdescserv, 0)), 0) AS descuento_servicios,
                COALESCE(SUM(
                    COALESCE(vrprodutos, 0)
                    + COALESCE(vrmdo_pub, 0)
                    + COALESCE(vradicionais, 0)
                ), 0) AS monto_total
            FROM base_presupuestos
        """
        consulta_estatus = base + """
            SELECT
                COALESCE(NULLIF(BTRIM(sit), ''), 'Sin estatus') AS estatus,
                COUNT(*) AS total,
                COUNT(DISTINCT nrorcamento) AS presupuestos,
                COALESCE(SUM(
                    COALESCE(vrprodutos, 0)
                    + COALESCE(vrmdo_pub, 0)
                    + COALESCE(vradicionais, 0)
                ), 0) AS monto_total
            FROM base_presupuestos
            GROUP BY COALESCE(NULLIF(BTRIM(sit), ''), 'Sin estatus')
            ORDER BY total DESC
        """
        consulta_agencias = base + """
            SELECT
                COALESCE(NULLIF(BTRIM(agencia), ''), 'Sin agencia') AS agencia,
                COUNT(DISTINCT nrorcamento) AS presupuestos,
                COALESCE(SUM(COALESCE(vrprodutos, 0)), 0) AS monto_productos,
                COALESCE(SUM(COALESCE(vrmdo_pub, 0)), 0) AS monto_mano_obra,
                COALESCE(SUM(
                    COALESCE(vrprodutos, 0)
                    + COALESCE(vrmdo_pub, 0)
                    + COALESCE(vradicionais, 0)
                ), 0) AS monto_total
            FROM base_presupuestos
            GROUP BY COALESCE(NULLIF(BTRIM(agencia), ''), 'Sin agencia')
            ORDER BY presupuestos DESC
        """
        consulta_asesores = base + f"""
            , funcionarios AS (
                SELECT
                    agencia AS agencia,
                    cod_funcionario AS cod_funcionario,
                    MAX(nm_funcionario) AS nm_funcionario
                FROM {TABLA_FUNCIONARIOS}
                GROUP BY agencia, cod_funcionario
            )
            SELECT
                bp.codfunc AS cod_func,
                COALESCE(
                    NULLIF(BTRIM(mf.nm_funcionario), ''),
                    CASE
                        WHEN bp.codfunc IS NULL THEN 'Sin asignar'
                        ELSE CONCAT('Asesor ', CAST(bp.codfunc AS TEXT))
                    END
                ) AS nm_funcionario,
                COUNT(DISTINCT bp.nrorcamento) AS presupuestos,
                COALESCE(SUM(
                    COALESCE(bp.vrprodutos, 0)
                    + COALESCE(bp.vrmdo_pub, 0)
                    + COALESCE(bp.vradicionais, 0)
                ), 0) AS monto_total
            FROM base_presupuestos AS bp
            LEFT JOIN funcionarios AS mf
                ON mf.cod_funcionario = bp.codfunc
                AND mf.agencia = bp.agencia
            GROUP BY bp.codfunc, mf.nm_funcionario
            ORDER BY presupuestos DESC
        """
        base_refacciones = base + f"""
            , claves_presupuestos AS (
                SELECT DISTINCT agencia, nrorcamento
                FROM base_presupuestos
                WHERE nrorcamento IS NOT NULL
            ),
            base_refacciones AS (
                SELECT r.*
                FROM {TABLA_REFACCIONES} AS r
                INNER JOIN claves_presupuestos AS p
                    ON p.nrorcamento = r.nrorcamento
                    AND p.agencia IS NOT DISTINCT FROM r.agencia
            )
        """
        consulta_refacciones = base_refacciones + """
            SELECT
                COUNT(*) AS lineas_refaccion,
                COUNT(DISTINCT nrorcamento) AS presupuestos_con_refacciones,
                COALESCE(SUM(COALESCE(qtprod, 0)), 0) AS cantidad_refacciones,
                COALESCE(SUM(COALESCE(vrliqpc, 0)), 0) AS suma_vr_liq_pc,
                COALESCE(SUM(COALESCE(qtprod, 0) * COALESCE(vrliqpc, 0)), 0)
                    AS valor_refacciones_estimado
            FROM base_refacciones
        """
        consulta_top_refacciones = base_refacciones + """
            SELECT
                COALESCE(NULLIF(BTRIM(codprod), ''), 'Sin código') AS cod_prod,
                COALESCE(NULLIF(BTRIM(nmprod), ''), 'Sin descripción') AS nm_prod,
                COUNT(*) AS lineas,
                COUNT(DISTINCT nrorcamento) AS presupuestos,
                COALESCE(SUM(COALESCE(qtprod, 0)), 0) AS cantidad,
                COALESCE(SUM(COALESCE(qtprod, 0) * COALESCE(vrliqpc, 0)), 0)
                    AS valor_estimado
            FROM base_refacciones
            GROUP BY
                COALESCE(NULLIF(BTRIM(codprod), ''), 'Sin código'),
                COALESCE(NULLIF(BTRIM(nmprod), ''), 'Sin descripción')
            ORDER BY cantidad DESC
            LIMIT 15
        """
        with connections[DB_ALIAS].cursor() as cursor:
            cursor.execute(consulta_totales, parametros)
            resultados_totales = cursor_a_dicts(cursor)
            cursor.execute(consulta_estatus, parametros)
            por_estatus = cursor_a_dicts(cursor)
            cursor.execute(consulta_agencias, parametros)
            por_agencia = cursor_a_dicts(cursor)
            cursor.execute(consulta_asesores, parametros)
            por_asesor = cursor_a_dicts(cursor)
            cursor.execute(consulta_refacciones, parametros)
            resultados_refacciones = cursor_a_dicts(cursor)
            cursor.execute(consulta_top_refacciones, parametros)
            top_refacciones = cursor_a_dicts(cursor)
        totales = resultados_totales[0] if resultados_totales else {
            "registros": 0,
            "presupuestos": 0,
            "monto_productos": 0,
            "monto_mano_obra": 0,
            "monto_adicionales": 0,
            "descuento_refacciones": 0,
            "descuento_servicios": 0,
            "monto_total": 0,
        }
        refacciones = resultados_refacciones[0] if resultados_refacciones else {
            "lineas_refaccion": 0,
            "presupuestos_con_refacciones": 0,
            "cantidad_refacciones": 0,
            "suma_vr_liq_pc": 0,
            "valor_refacciones_estimado": 0,
        }
        return Response({
            "totales": totales,
            "refacciones": refacciones,
            "graficas": {
                "por_estatus": por_estatus,
                "por_agencia": por_agencia,
                "por_asesor": por_asesor,
                "top_refacciones": top_refacciones,
            },
        })
# ============================================================
# OPCIONES PARA FILTROS
# ============================================================
class PresupuestosOpcionesView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]
    def get(self, request):
        opciones_cache = cache.get(CACHE_OPCIONES)
        if opciones_cache:
            return Response(opciones_cache)
        consulta_agencias = f"""
            SELECT DISTINCT valor
            FROM (
                SELECT BTRIM(agencia) AS valor FROM {TABLA_PRESUPUESTOS}
                UNION
                SELECT BTRIM(agencia) AS valor FROM {TABLA_REFACCIONES}
            ) AS datos
            WHERE valor IS NOT NULL AND valor <> ''
            ORDER BY valor
        """
        consulta_estatus = f"""
            SELECT DISTINCT BTRIM(sit) AS valor
            FROM {TABLA_PRESUPUESTOS}
            WHERE sit IS NOT NULL AND BTRIM(sit) <> ''
            ORDER BY valor
        """
        consulta_modelos = f"""
            SELECT DISTINCT BTRIM(codmodelo) AS valor
            FROM {TABLA_PRESUPUESTOS}
            WHERE codmodelo IS NOT NULL AND BTRIM(codmodelo) <> ''
            ORDER BY valor
        """
        consulta_asesores = f"""
            SELECT DISTINCT codfunc
            FROM {TABLA_PRESUPUESTOS}
            WHERE codfunc IS NOT NULL
            ORDER BY codfunc
        """
        with connections[DB_ALIAS].cursor() as cursor:
            cursor.execute(consulta_agencias)
            agencias = [fila[0] for fila in cursor.fetchall() if fila[0]]
            cursor.execute(consulta_estatus)
            estatus = [fila[0] for fila in cursor.fetchall() if fila[0]]
            cursor.execute(consulta_modelos)
            modelos = [fila[0] for fila in cursor.fetchall() if fila[0]]
            cursor.execute(consulta_asesores)
            asesores = [fila[0] for fila in cursor.fetchall() if fila[0] is not None]
        opciones = {
            "agencias": agencias,
            "estatus": estatus,
            "modelos": modelos,
            "codigos_asesor": asesores,
        }
        cache.set(CACHE_OPCIONES, opciones, 300)
        return Response(opciones)
