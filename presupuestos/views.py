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
    return f'{alias}."{nombre}"' if alias else f'"{nombre}"'


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
                mp."Agencia" AS agencia,
                mp."NrOrcamento" AS nr_orcamento,
                mp."CodEntidade" AS cod_entidade,
                mp."Nome" AS nome,
                mp."Endereco" AS endereco,
                mp."Bairro" AS bairro,
                mp."CodMunic" AS cod_munic,
                mp."Cep" AS cep,
                mp."TelFax1" AS tel_fax1,
                mp."TelFax2" AS tel_fax2,
                mp."TpPessoa" AS tp_pessoa,
                mp."CGC" AS cgc,
                mp."Rg" AS rg,
                mp."CodSegurad" AS cod_segurad,
                mp."PlacaVeic" AS placa_veic,
                mp."Chassi" AS chassi,
                mp."Km" AS km,
                mp."CorVeic" AS cor_veic,
                mp."CodModelo" AS cod_modelo,
                mp."AnoFabr" AS ano_fabr,
                mp."AnoMod" AS ano_mod,
                mp."VrProdutos" AS vr_produtos,
                mp."VrMDO_Pub" AS vr_mdo_pub,
                mp."DtEmissao"::date AS dt_emissao,
                mp."HrEmissao" AS hr_emissao,
                mp."DtValidade"::date AS dt_validade,
                mp."DtAprov"::date AS dt_aprov,
                mp."Sit" AS sit,
                mp."NrPrisma" AS nr_prisma,
                mp."CorPrisma" AS cor_prisma,
                mp."CodFunc" AS cod_func,
                mf.nm_funcionario AS nm_funcionario,
                mp."Comentario" AS comentario,
                mp."NrApolice" AS nr_apolice,
                mp."DescPcs" AS desc_pcs,
                mp."VrDescPcs" AS vr_desc_pcs,
                mp."DescServ" AS desc_serv,
                mp."VrDescServ" AS vr_desc_serv,
                mp."NrAtPed" AS nr_at_ped,
                mp."TpEntrega" AS tp_entrega,
                mp."DestPed" AS dest_ped,
                mp."TpPreco" AS tp_preco,
                mp."ImprCodPcs" AS impr_cod_pcs,
                mp."AreaOrcam" AS area_orcam,
                mp."CodContacto" AS cod_contacto,
                mp."CodPacote" AS cod_pacote,
                mp."Sinistro" AS sinistro,
                mp."Ajustador" AS ajustador,
                mp."OrcamDyP" AS orcam_dyp,
                mp."PresElsaPro" AS pres_elsa_pro,
                mp."PresElsaAut" AS pres_elsa_aut,
                mp."NrAtend" AS nr_atend,
                mp."VrAdicionais" AS vr_adicionais,
                mp."NrRemision" AS nr_remision,
                mp."NrConvenio" AS nr_convenio,
                mp."Asegurado" AS asegurado,
                mp."Taller" AS taller,
                mp."NrVale" AS nr_vale,
                mp."NrOrdenCpa" AS nr_orden_cpa,
                mp."Cod_Empresa" AS cod_empresa,
                mp."Cod_Filial" AS cod_filial,
                mp."rowid__" AS rowid
            FROM {TABLA_PRESUPUESTOS} AS mp
            LEFT JOIN (
                SELECT
                    "Agencia" AS agencia,
                    "Cod_Funcionario" AS cod_funcionario,
                    MAX("Nm_Funcionario") AS nm_funcionario
                FROM {TABLA_FUNCIONARIOS}
                GROUP BY "Agencia", "Cod_Funcionario"
            ) AS mf
                ON mf.cod_funcionario = mp."CodFunc"
                AND mf.agencia = mp."Agencia"
            {where_sql}
            ORDER BY
                CASE WHEN mp."NrOrcamento" IS NULL THEN 1 ELSE 0 END,
                mp."NrOrcamento" DESC,
                mp."Agencia"
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
                r."Agencia" AS agencia,
                r."NrOrcamento" AS nr_orcamento,
                r."NmProd" AS nm_prod,
                r."CodProd" AS cod_prod,
                r."QtProd" AS qt_prod,
                r."PrecoPc" AS preco_pc,
                r."DescPc" AS desc_pc,
                r."VrDescPc" AS vr_desc_pc,
                r."VrLiqPc" AS vr_liq_pc,
                r."VrCasco" AS vr_casco,
                r."HrCreacion" AS hr_creacion,
                r."DNStock" AS dn_stock,
                r."DNMediaVta" AS dn_media_vta,
                r."DNCtSolicitada" AS dn_ct_solicitada,
                r."Filler05" AS filler05,
                r."Filler06" AS filler06,
                r."Filler07" AS filler07,
                r."Filler08" AS filler08,
                r."Filler09" AS filler09,
                r."Filler10" AS filler10,
                r."Selec" AS selec,
                r."IdCasco" AS id_casco,
                r."ImprDesc" AS impr_desc,
                r."Filler12" AS filler12,
                r."Filler13" AS filler13,
                r."Filler14" AS filler14,
                r."Filler15" AS filler15,
                r."Filler16" AS filler16,
                r."CodPacote" AS cod_pacote,
                r."Filler17" AS filler17,
                r."ComentRef" AS coment_ref,
                r."DtCreacion"::date AS dt_creacion,
                r."Filler20" AS filler20,
                r."rowid__" AS rowid
            FROM {TABLA_REFACCIONES} AS r
            {where_sql}
            ORDER BY
                CASE WHEN r."NrOrcamento" IS NULL THEN 1 ELSE 0 END,
                r."NrOrcamento" DESC,
                r."Agencia",
                r."CodProd"
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
                COUNT(DISTINCT "NrOrcamento") AS presupuestos,
                COALESCE(SUM(COALESCE("VrProdutos", 0)), 0) AS monto_productos,
                COALESCE(SUM(COALESCE("VrMDO_Pub", 0)), 0) AS monto_mano_obra,
                COALESCE(SUM(COALESCE("VrAdicionais", 0)), 0) AS monto_adicionales,
                COALESCE(SUM(COALESCE("VrDescPcs", 0)), 0) AS descuento_refacciones,
                COALESCE(SUM(COALESCE("VrDescServ", 0)), 0) AS descuento_servicios,
                COALESCE(SUM(
                    COALESCE("VrProdutos", 0)
                    + COALESCE("VrMDO_Pub", 0)
                    + COALESCE("VrAdicionais", 0)
                ), 0) AS monto_total
            FROM base_presupuestos
        """

        consulta_estatus = base + """
            SELECT
                COALESCE(NULLIF(BTRIM("Sit"), ''), 'Sin estatus') AS estatus,
                COUNT(*) AS total,
                COUNT(DISTINCT "NrOrcamento") AS presupuestos,
                COALESCE(SUM(
                    COALESCE("VrProdutos", 0)
                    + COALESCE("VrMDO_Pub", 0)
                    + COALESCE("VrAdicionais", 0)
                ), 0) AS monto_total
            FROM base_presupuestos
            GROUP BY COALESCE(NULLIF(BTRIM("Sit"), ''), 'Sin estatus')
            ORDER BY total DESC
        """

        consulta_agencias = base + """
            SELECT
                COALESCE(NULLIF(BTRIM("Agencia"), ''), 'Sin agencia') AS agencia,
                COUNT(DISTINCT "NrOrcamento") AS presupuestos,
                COALESCE(SUM(COALESCE("VrProdutos", 0)), 0) AS monto_productos,
                COALESCE(SUM(COALESCE("VrMDO_Pub", 0)), 0) AS monto_mano_obra,
                COALESCE(SUM(
                    COALESCE("VrProdutos", 0)
                    + COALESCE("VrMDO_Pub", 0)
                    + COALESCE("VrAdicionais", 0)
                ), 0) AS monto_total
            FROM base_presupuestos
            GROUP BY COALESCE(NULLIF(BTRIM("Agencia"), ''), 'Sin agencia')
            ORDER BY presupuestos DESC
        """

        consulta_asesores = base + f"""
            , funcionarios AS (
                SELECT
                    "Agencia" AS agencia,
                    "Cod_Funcionario" AS cod_funcionario,
                    MAX("Nm_Funcionario") AS nm_funcionario
                FROM {TABLA_FUNCIONARIOS}
                GROUP BY "Agencia", "Cod_Funcionario"
            )
            SELECT
                bp."CodFunc" AS cod_func,
                COALESCE(
                    NULLIF(BTRIM(mf.nm_funcionario), ''),
                    CASE
                        WHEN bp."CodFunc" IS NULL THEN 'Sin asignar'
                        ELSE CONCAT('Asesor ', CAST(bp."CodFunc" AS TEXT))
                    END
                ) AS nm_funcionario,
                COUNT(DISTINCT bp."NrOrcamento") AS presupuestos,
                COALESCE(SUM(
                    COALESCE(bp."VrProdutos", 0)
                    + COALESCE(bp."VrMDO_Pub", 0)
                    + COALESCE(bp."VrAdicionais", 0)
                ), 0) AS monto_total
            FROM base_presupuestos AS bp
            LEFT JOIN funcionarios AS mf
                ON mf.cod_funcionario = bp."CodFunc"
                AND mf.agencia = bp."Agencia"
            GROUP BY bp."CodFunc", mf.nm_funcionario
            ORDER BY presupuestos DESC
        """

        base_refacciones = base + f"""
            , claves_presupuestos AS (
                SELECT DISTINCT "Agencia", "NrOrcamento"
                FROM base_presupuestos
                WHERE "NrOrcamento" IS NOT NULL
            ),
            base_refacciones AS (
                SELECT r.*
                FROM {TABLA_REFACCIONES} AS r
                INNER JOIN claves_presupuestos AS p
                    ON p."NrOrcamento" = r."NrOrcamento"
                    AND p."Agencia" IS NOT DISTINCT FROM r."Agencia"
            )
        """

        consulta_refacciones = base_refacciones + """
            SELECT
                COUNT(*) AS lineas_refaccion,
                COUNT(DISTINCT "NrOrcamento") AS presupuestos_con_refacciones,
                COALESCE(SUM(COALESCE("QtProd", 0)), 0) AS cantidad_refacciones,
                COALESCE(SUM(COALESCE("VrLiqPc", 0)), 0) AS suma_vr_liq_pc,
                COALESCE(SUM(COALESCE("QtProd", 0) * COALESCE("VrLiqPc", 0)), 0)
                    AS valor_refacciones_estimado
            FROM base_refacciones
        """

        consulta_top_refacciones = base_refacciones + """
            SELECT
                COALESCE(NULLIF(BTRIM("CodProd"), ''), 'Sin código') AS cod_prod,
                COALESCE(NULLIF(BTRIM("NmProd"), ''), 'Sin descripción') AS nm_prod,
                COUNT(*) AS lineas,
                COUNT(DISTINCT "NrOrcamento") AS presupuestos,
                COALESCE(SUM(COALESCE("QtProd", 0)), 0) AS cantidad,
                COALESCE(SUM(COALESCE("QtProd", 0) * COALESCE("VrLiqPc", 0)), 0)
                    AS valor_estimado
            FROM base_refacciones
            GROUP BY
                COALESCE(NULLIF(BTRIM("CodProd"), ''), 'Sin código'),
                COALESCE(NULLIF(BTRIM("NmProd"), ''), 'Sin descripción')
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
                SELECT BTRIM("Agencia") AS valor FROM {TABLA_PRESUPUESTOS}
                UNION
                SELECT BTRIM("Agencia") AS valor FROM {TABLA_REFACCIONES}
            ) AS datos
            WHERE valor IS NOT NULL AND valor <> ''
            ORDER BY valor
        """
        consulta_estatus = f"""
            SELECT DISTINCT BTRIM("Sit") AS valor
            FROM {TABLA_PRESUPUESTOS}
            WHERE "Sit" IS NOT NULL AND BTRIM("Sit") <> ''
            ORDER BY valor
        """
        consulta_modelos = f"""
            SELECT DISTINCT BTRIM("CodModelo") AS valor
            FROM {TABLA_PRESUPUESTOS}
            WHERE "CodModelo" IS NOT NULL AND BTRIM("CodModelo") <> ''
            ORDER BY valor
        """
        consulta_asesores = f"""
            SELECT DISTINCT "CodFunc"
            FROM {TABLA_PRESUPUESTOS}
            WHERE "CodFunc" IS NOT NULL
            ORDER BY "CodFunc"
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
