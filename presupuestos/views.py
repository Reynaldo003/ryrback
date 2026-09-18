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


DB_ALIAS = "sqlserver_inv"

TABLA_PRESUPUESTOS = "dbo.Matriz_Presupuestos"
TABLA_REFACCIONES = "dbo.Matriz_PresupuestosRef"

CACHE_OPCIONES = "presupuestos_opciones_v1"


# ============================================================
# HELPERS
# ============================================================

def texto_parametro(request, nombre):
    return str(
        request.query_params.get(nombre, "") or ""
    ).strip()


def entero_parametro(request, nombre):
    valor = texto_parametro(request, nombre)

    if not valor:
        return None

    try:
        return int(valor)
    except (TypeError, ValueError):
        raise ValueError(
            f"El parámetro '{nombre}' debe ser un número entero."
        )


def validar_fecha(valor, nombre):
    if valor and not parse_date(valor):
        raise ValueError(
            f"El parámetro '{nombre}' debe tener formato YYYY-MM-DD."
        )


def cursor_a_dicts(cursor):
    columnas = [
        columna[0]
        for columna in cursor.description
    ]

    return [
        dict(zip(columnas, fila))
        for fila in cursor.fetchall()
    ]


def obtener_paginacion(request):
    try:
        pagina = int(
            request.query_params.get(
                "page",
                1,
            )
        )
    except (TypeError, ValueError):
        pagina = 1

    pagina = max(pagina, 1)

    try:
        tamano_pagina = int(
            request.query_params.get(
                "page_size",
                100,
            )
        )
    except (TypeError, ValueError):
        tamano_pagina = 100

    tamano_pagina = max(
        1,
        min(
            tamano_pagina,
            500,
        ),
    )

    offset = (
        pagina - 1
    ) * tamano_pagina

    return (
        pagina,
        tamano_pagina,
        offset,
    )


def expresion_fecha(columna):
    """
    Las fechas vienen como VARCHAR.

    Intentamos interpretar los formatos más comunes:
    YYYYMMDD
    DD/MM/YYYY
    YYYY-MM-DD
    conversión automática de SQL Server
    """

    return f"""
        COALESCE(
            TRY_CONVERT(
                DATE,
                NULLIF(LTRIM(RTRIM({columna})), ''),
                112
            ),
            TRY_CONVERT(
                DATE,
                NULLIF(LTRIM(RTRIM({columna})), ''),
                103
            ),
            TRY_CONVERT(
                DATE,
                NULLIF(LTRIM(RTRIM({columna})), ''),
                23
            ),
            TRY_CONVERT(
                DATE,
                NULLIF(LTRIM(RTRIM({columna})), '')
            )
        )
    """


# ============================================================
# FILTROS DE MATRIZ_PRESUPUESTOS
# ============================================================

def construir_filtros_presupuestos(request):
    busqueda = texto_parametro(
        request,
        "q",
    )

    agencia = texto_parametro(
        request,
        "agencia",
    )

    nr_orcamento = entero_parametro(
        request,
        "nr_orcamento",
    )

    sit = texto_parametro(
        request,
        "sit",
    )

    cod_func = entero_parametro(
        request,
        "cod_func",
    )

    cod_modelo = texto_parametro(
        request,
        "cod_modelo",
    )

    placa = texto_parametro(
        request,
        "placa",
    )

    chassi = texto_parametro(
        request,
        "chassi",
    )

    fecha_desde = texto_parametro(
        request,
        "fecha_desde",
    )

    fecha_hasta = texto_parametro(
        request,
        "fecha_hasta",
    )

    validar_fecha(
        fecha_desde,
        "fecha_desde",
    )

    validar_fecha(
        fecha_hasta,
        "fecha_hasta",
    )

    condiciones = []
    parametros = []

    if busqueda:
        termino = f"%{busqueda}%"

        condiciones.append(
            """
            (
                Agencia LIKE %s
                OR CAST(NrOrcamento AS VARCHAR(50)) LIKE %s
                OR Nome LIKE %s
                OR PlacaVeic LIKE %s
                OR Chassi LIKE %s
                OR CodModelo LIKE %s
                OR Sit LIKE %s
                OR Comentario LIKE %s
                OR NrApolice LIKE %s
                OR Sinistro LIKE %s
                OR Asegurado LIKE %s
                OR Taller LIKE %s
            )
            """
        )

        parametros.extend(
            [termino] * 12
        )

    if agencia:
        condiciones.append(
            "Agencia = %s"
        )
        parametros.append(
            agencia
        )

    if nr_orcamento is not None:
        condiciones.append(
            "NrOrcamento = %s"
        )
        parametros.append(
            nr_orcamento
        )

    if sit:
        condiciones.append(
            "Sit = %s"
        )
        parametros.append(
            sit
        )

    if cod_func is not None:
        condiciones.append(
            "CodFunc = %s"
        )
        parametros.append(
            cod_func
        )

    if cod_modelo:
        condiciones.append(
            "CodModelo = %s"
        )
        parametros.append(
            cod_modelo
        )

    if placa:
        condiciones.append(
            "PlacaVeic LIKE %s"
        )
        parametros.append(
            f"%{placa}%"
        )

    if chassi:
        condiciones.append(
            "Chassi LIKE %s"
        )
        parametros.append(
            f"%{chassi}%"
        )

    fecha_emision_sql = expresion_fecha(
        "DtEmissao"
    )

    if fecha_desde:
        condiciones.append(
            f"{fecha_emision_sql} >= %s"
        )
        parametros.append(
            fecha_desde
        )

    if fecha_hasta:
        condiciones.append(
            f"{fecha_emision_sql} <= %s"
        )
        parametros.append(
            fecha_hasta
        )

    where_sql = ""

    if condiciones:
        where_sql = (
            "WHERE "
            + " AND ".join(condiciones)
        )

    return (
        where_sql,
        parametros,
    )


# ============================================================
# FILTROS DE MATRIZ_PRESUPUESTOSREF
# ============================================================

def construir_filtros_refacciones(request):
    busqueda = texto_parametro(
        request,
        "q",
    )

    agencia = texto_parametro(
        request,
        "agencia",
    )

    nr_orcamento = entero_parametro(
        request,
        "nr_orcamento",
    )

    cod_prod = texto_parametro(
        request,
        "cod_prod",
    )

    fecha_desde = texto_parametro(
        request,
        "fecha_desde",
    )

    fecha_hasta = texto_parametro(
        request,
        "fecha_hasta",
    )

    validar_fecha(
        fecha_desde,
        "fecha_desde",
    )

    validar_fecha(
        fecha_hasta,
        "fecha_hasta",
    )

    condiciones = []
    parametros = []

    if busqueda:
        termino = f"%{busqueda}%"

        condiciones.append(
            """
            (
                Agencia LIKE %s
                OR CAST(NrOrcamento AS VARCHAR(50)) LIKE %s
                OR NmProd LIKE %s
                OR CodProd LIKE %s
                OR ComentRef LIKE %s
                OR CodPacote LIKE %s
                OR IdCasco LIKE %s
            )
            """
        )

        parametros.extend(
            [termino] * 7
        )

    if agencia:
        condiciones.append(
            "Agencia = %s"
        )
        parametros.append(
            agencia
        )

    if nr_orcamento is not None:
        condiciones.append(
            "NrOrcamento = %s"
        )
        parametros.append(
            nr_orcamento
        )

    if cod_prod:
        condiciones.append(
            "CodProd = %s"
        )
        parametros.append(
            cod_prod
        )

    fecha_creacion_sql = expresion_fecha(
        "DtCreacion"
    )

    if fecha_desde:
        condiciones.append(
            f"{fecha_creacion_sql} >= %s"
        )
        parametros.append(
            fecha_desde
        )

    if fecha_hasta:
        condiciones.append(
            f"{fecha_creacion_sql} <= %s"
        )
        parametros.append(
            fecha_hasta
        )

    where_sql = ""

    if condiciones:
        where_sql = (
            "WHERE "
            + " AND ".join(condiciones)
        )

    return (
        where_sql,
        parametros,
    )


# ============================================================
# LISTADO DE PRESUPUESTOS
# ============================================================

class MatrizPresupuestosListView(APIView):
    authentication_classes = [
        CRMJWTAuthentication
    ]
    permission_classes = [
        IsAuthenticated
    ]

    def get(self, request):
        (
            pagina,
            tamano_pagina,
            offset,
        ) = obtener_paginacion(request)

        try:
            (
                where_sql,
                parametros,
            ) = construir_filtros_presupuestos(
                request
            )

        except ValueError as exc:
            return Response(
                {
                    "detail": str(exc)
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        consulta_total = f"""
            SELECT COUNT(*)
            FROM {TABLA_PRESUPUESTOS}
            {where_sql}
        """

        consulta = f"""
            SELECT
                Agencia AS agencia,
                NrOrcamento AS nr_orcamento,
                CodEntidade AS cod_entidade,
                Nome AS nome,
                Endereco AS endereco,
                Bairro AS bairro,
                CodMunic AS cod_munic,
                Cep AS cep,
                TelFax1 AS tel_fax1,
                TelFax2 AS tel_fax2,
                TpPessoa AS tp_pessoa,
                CGC AS cgc,
                Rg AS rg,
                CodSegurad AS cod_segurad,
                PlacaVeic AS placa_veic,
                Chassi AS chassi,
                Km AS km,
                CorVeic AS cor_veic,
                CodModelo AS cod_modelo,
                AnoFabr AS ano_fabr,
                AnoMod AS ano_mod,
                VrProdutos AS vr_produtos,
                VrMDO_Pub AS vr_mdo_pub,
                DtEmissao AS dt_emissao,
                HrEmissao AS hr_emissao,
                DtValidade AS dt_validade,
                DtAprov AS dt_aprov,
                Sit AS sit,
                NrPrisma AS nr_prisma,
                CorPrisma AS cor_prisma,
                CodFunc AS cod_func,
                Comentario AS comentario,
                NrApolice AS nr_apolice,
                DescPcs AS desc_pcs,
                VrDescPcs AS vr_desc_pcs,
                DescServ AS desc_serv,
                VrDescServ AS vr_desc_serv,
                NrAtPed AS nr_at_ped,
                TpEntrega AS tp_entrega,
                DestPed AS dest_ped,
                TpPreco AS tp_preco,
                ImprCodPcs AS impr_cod_pcs,
                AreaOrcam AS area_orcam,
                CodContacto AS cod_contacto,
                CodPacote AS cod_pacote,
                Sinistro AS sinistro,
                Ajustador AS ajustador,
                OrcamDyP AS orcam_dyp,
                PresElsaPro AS pres_elsa_pro,
                PresElsaAut AS pres_elsa_aut,
                NrAtend AS nr_atend,
                VrAdicionais AS vr_adicionais,
                NrRemision AS nr_remision,
                NrConvenio AS nr_convenio,
                Asegurado AS asegurado,
                Taller AS taller,
                NrVale AS nr_vale,
                NrOrdenCpa AS nr_orden_cpa,
                Cod_Empresa AS cod_empresa,
                Cod_Filial AS cod_filial,
                rowid__ AS rowid
            FROM {TABLA_PRESUPUESTOS}
            {where_sql}
            ORDER BY
                CASE
                    WHEN NrOrcamento IS NULL
                    THEN 1
                    ELSE 0
                END,
                NrOrcamento DESC,
                Agencia
            OFFSET %s ROWS
            FETCH NEXT %s ROWS ONLY
        """

        with connections[
            DB_ALIAS
        ].cursor() as cursor:

            cursor.execute(
                consulta_total,
                parametros,
            )

            total = cursor.fetchone()[0]

            cursor.execute(
                consulta,
                [
                    *parametros,
                    offset,
                    tamano_pagina,
                ],
            )

            registros = cursor_a_dicts(
                cursor
            )

        serializer = MatrizPresupuestosSerializer(
            registros,
            many=True,
        )

        return Response(
            {
                "count": total,
                "page": pagina,
                "page_size": tamano_pagina,
                "results": serializer.data,
            }
        )


# ============================================================
# LISTADO DE REFACCIONES DE LOS PRESUPUESTOS
# ============================================================

class MatrizPresupuestosRefListView(APIView):
    authentication_classes = [
        CRMJWTAuthentication
    ]
    permission_classes = [
        IsAuthenticated
    ]

    def get(self, request):
        (
            pagina,
            tamano_pagina,
            offset,
        ) = obtener_paginacion(request)

        try:
            (
                where_sql,
                parametros,
            ) = construir_filtros_refacciones(
                request
            )

        except ValueError as exc:
            return Response(
                {
                    "detail": str(exc)
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        consulta_total = f"""
            SELECT COUNT(*)
            FROM {TABLA_REFACCIONES}
            {where_sql}
        """

        consulta = f"""
            SELECT
                Agencia AS agencia,
                NrOrcamento AS nr_orcamento,
                NmProd AS nm_prod,
                CodProd AS cod_prod,
                QtProd AS qt_prod,
                PrecoPc AS preco_pc,
                DescPc AS desc_pc,
                VrDescPc AS vr_desc_pc,
                VrLiqPc AS vr_liq_pc,
                VrCasco AS vr_casco,
                HrCreacion AS hr_creacion,
                DNStock AS dn_stock,
                DNMediaVta AS dn_media_vta,
                DNCtSolicitada AS dn_ct_solicitada,
                Filler05 AS filler05,
                Filler06 AS filler06,
                Filler07 AS filler07,
                Filler08 AS filler08,
                Filler09 AS filler09,
                Filler10 AS filler10,
                Selec AS selec,
                IdCasco AS id_casco,
                ImprDesc AS impr_desc,
                Filler12 AS filler12,
                Filler13 AS filler13,
                Filler14 AS filler14,
                Filler15 AS filler15,
                Filler16 AS filler16,
                CodPacote AS cod_pacote,
                Filler17 AS filler17,
                ComentRef AS coment_ref,
                DtCreacion AS dt_creacion,
                Filler20 AS filler20,
                rowid__ AS rowid
            FROM {TABLA_REFACCIONES}
            {where_sql}
            ORDER BY
                CASE
                    WHEN NrOrcamento IS NULL
                    THEN 1
                    ELSE 0
                END,
                NrOrcamento DESC,
                Agencia,
                CodProd
            OFFSET %s ROWS
            FETCH NEXT %s ROWS ONLY
        """

        with connections[
            DB_ALIAS
        ].cursor() as cursor:

            cursor.execute(
                consulta_total,
                parametros,
            )

            total = cursor.fetchone()[0]

            cursor.execute(
                consulta,
                [
                    *parametros,
                    offset,
                    tamano_pagina,
                ],
            )

            registros = cursor_a_dicts(
                cursor
            )

        serializer = MatrizPresupuestosRefSerializer(
            registros,
            many=True,
        )

        return Response(
            {
                "count": total,
                "page": pagina,
                "page_size": tamano_pagina,
                "results": serializer.data,
            }
        )


# ============================================================
# DASHBOARD
# ============================================================

class PresupuestosDashboardView(APIView):
    authentication_classes = [
        CRMJWTAuthentication
    ]
    permission_classes = [
        IsAuthenticated
    ]

    def get(self, request):
        try:
            (
                where_sql,
                parametros,
            ) = construir_filtros_presupuestos(
                request
            )

        except ValueError as exc:
            return Response(
                {
                    "detail": str(exc)
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        consulta = f"""
            SET NOCOUNT ON;

            IF OBJECT_ID(
                'tempdb..#BasePresupuestos'
            ) IS NOT NULL
                DROP TABLE #BasePresupuestos;

            IF OBJECT_ID(
                'tempdb..#ClavesPresupuestos'
            ) IS NOT NULL
                DROP TABLE #ClavesPresupuestos;

            IF OBJECT_ID(
                'tempdb..#BaseRefacciones'
            ) IS NOT NULL
                DROP TABLE #BaseRefacciones;


            -- =====================================================
            -- BASE DE PRESUPUESTOS FILTRADA
            -- =====================================================

            SELECT
                *
            INTO #BasePresupuestos
            FROM {TABLA_PRESUPUESTOS}
            {where_sql};


            -- =====================================================
            -- CLAVES ÚNICAS PARA ENLAZAR REFACCIONES
            -- =====================================================

            SELECT DISTINCT
                Agencia,
                NrOrcamento
            INTO #ClavesPresupuestos
            FROM #BasePresupuestos
            WHERE NrOrcamento IS NOT NULL;


            -- =====================================================
            -- REFACCIONES RELACIONADAS
            -- =====================================================

            SELECT
                r.*
            INTO #BaseRefacciones
            FROM {TABLA_REFACCIONES} AS r

            INNER JOIN #ClavesPresupuestos AS p
                ON p.NrOrcamento = r.NrOrcamento

                AND (
                    p.Agencia = r.Agencia

                    OR (
                        p.Agencia IS NULL
                        AND r.Agencia IS NULL
                    )
                );


            -- =====================================================
            -- 1. KPIs GENERALES
            -- =====================================================

            SELECT
                COUNT(*) AS registros,

                COUNT(
                    DISTINCT NrOrcamento
                ) AS presupuestos,

                COALESCE(
                    SUM(
                        COALESCE(
                            VrProdutos,
                            0
                        )
                    ),
                    0
                ) AS monto_productos,

                COALESCE(
                    SUM(
                        COALESCE(
                            VrMDO_Pub,
                            0
                        )
                    ),
                    0
                ) AS monto_mano_obra,

                COALESCE(
                    SUM(
                        COALESCE(
                            VrAdicionais,
                            0
                        )
                    ),
                    0
                ) AS monto_adicionales,

                COALESCE(
                    SUM(
                        COALESCE(
                            VrDescPcs,
                            0
                        )
                    ),
                    0
                ) AS descuento_refacciones,

                COALESCE(
                    SUM(
                        COALESCE(
                            VrDescServ,
                            0
                        )
                    ),
                    0
                ) AS descuento_servicios,

                COALESCE(
                    SUM(
                        COALESCE(
                            VrProdutos,
                            0
                        )
                        +
                        COALESCE(
                            VrMDO_Pub,
                            0
                        )
                        +
                        COALESCE(
                            VrAdicionais,
                            0
                        )
                    ),
                    0
                ) AS monto_total

            FROM #BasePresupuestos;


            -- =====================================================
            -- 2. ESTATUS
            -- =====================================================

            SELECT
                COALESCE(
                    NULLIF(
                        LTRIM(
                            RTRIM(Sit)
                        ),
                        ''
                    ),
                    'Sin estatus'
                ) AS estatus,

                COUNT(*) AS total,

                COUNT(
                    DISTINCT NrOrcamento
                ) AS presupuestos,

                COALESCE(
                    SUM(
                        COALESCE(
                            VrProdutos,
                            0
                        )
                        +
                        COALESCE(
                            VrMDO_Pub,
                            0
                        )
                        +
                        COALESCE(
                            VrAdicionais,
                            0
                        )
                    ),
                    0
                ) AS monto_total

            FROM #BasePresupuestos

            GROUP BY
                COALESCE(
                    NULLIF(
                        LTRIM(
                            RTRIM(Sit)
                        ),
                        ''
                    ),
                    'Sin estatus'
                )

            ORDER BY
                total DESC;


            -- =====================================================
            -- 3. AGENCIAS
            -- =====================================================

            SELECT
                COALESCE(
                    NULLIF(
                        LTRIM(
                            RTRIM(Agencia)
                        ),
                        ''
                    ),
                    'Sin agencia'
                ) AS agencia,

                COUNT(
                    DISTINCT NrOrcamento
                ) AS presupuestos,

                COALESCE(
                    SUM(
                        COALESCE(
                            VrProdutos,
                            0
                        )
                    ),
                    0
                ) AS monto_productos,

                COALESCE(
                    SUM(
                        COALESCE(
                            VrMDO_Pub,
                            0
                        )
                    ),
                    0
                ) AS monto_mano_obra,

                COALESCE(
                    SUM(
                        COALESCE(
                            VrProdutos,
                            0
                        )
                        +
                        COALESCE(
                            VrMDO_Pub,
                            0
                        )
                        +
                        COALESCE(
                            VrAdicionais,
                            0
                        )
                    ),
                    0
                ) AS monto_total

            FROM #BasePresupuestos

            GROUP BY
                COALESCE(
                    NULLIF(
                        LTRIM(
                            RTRIM(Agencia)
                        ),
                        ''
                    ),
                    'Sin agencia'
                )

            ORDER BY
                presupuestos DESC;


            -- =====================================================
            -- 4. POR CÓDIGO DE ASESOR
            -- =====================================================

            SELECT
                CodFunc AS cod_func,

                COUNT(
                    DISTINCT NrOrcamento
                ) AS presupuestos,

                COALESCE(
                    SUM(
                        COALESCE(
                            VrProdutos,
                            0
                        )
                        +
                        COALESCE(
                            VrMDO_Pub,
                            0
                        )
                        +
                        COALESCE(
                            VrAdicionais,
                            0
                        )
                    ),
                    0
                ) AS monto_total

            FROM #BasePresupuestos

            GROUP BY
                CodFunc

            ORDER BY
                presupuestos DESC;


            -- =====================================================
            -- 5. RESUMEN DE REFACCIONES
            -- =====================================================

            SELECT
                COUNT(*) AS lineas_refaccion,

                COUNT(
                    DISTINCT NrOrcamento
                ) AS presupuestos_con_refacciones,

                COALESCE(
                    SUM(
                        COALESCE(
                            QtProd,
                            0
                        )
                    ),
                    0
                ) AS cantidad_refacciones,

                COALESCE(
                    SUM(
                        COALESCE(
                            VrLiqPc,
                            0
                        )
                    ),
                    0
                ) AS suma_vr_liq_pc,

                COALESCE(
                    SUM(
                        COALESCE(
                            QtProd,
                            0
                        )
                        *
                        COALESCE(
                            VrLiqPc,
                            0
                        )
                    ),
                    0
                ) AS valor_refacciones_estimado

            FROM #BaseRefacciones;


            -- =====================================================
            -- 6. TOP REFACCIONES
            -- =====================================================

            SELECT TOP 15
                COALESCE(
                    NULLIF(
                        LTRIM(
                            RTRIM(CodProd)
                        ),
                        ''
                    ),
                    'Sin código'
                ) AS cod_prod,

                COALESCE(
                    NULLIF(
                        LTRIM(
                            RTRIM(NmProd)
                        ),
                        ''
                    ),
                    'Sin descripción'
                ) AS nm_prod,

                COUNT(*) AS lineas,

                COUNT(
                    DISTINCT NrOrcamento
                ) AS presupuestos,

                COALESCE(
                    SUM(
                        COALESCE(
                            QtProd,
                            0
                        )
                    ),
                    0
                ) AS cantidad,

                COALESCE(
                    SUM(
                        COALESCE(
                            QtProd,
                            0
                        )
                        *
                        COALESCE(
                            VrLiqPc,
                            0
                        )
                    ),
                    0
                ) AS valor_estimado

            FROM #BaseRefacciones

            GROUP BY
                COALESCE(
                    NULLIF(
                        LTRIM(
                            RTRIM(CodProd)
                        ),
                        ''
                    ),
                    'Sin código'
                ),

                COALESCE(
                    NULLIF(
                        LTRIM(
                            RTRIM(NmProd)
                        ),
                        ''
                    ),
                    'Sin descripción'
                )

            ORDER BY
                cantidad DESC;


            DROP TABLE #BaseRefacciones;
            DROP TABLE #ClavesPresupuestos;
            DROP TABLE #BasePresupuestos;
        """

        def avanzar_hasta_resultado(cursor):
            while cursor.description is None:
                if not cursor.nextset():
                    return False

            return True

        def leer_resultado(cursor):
            if not avanzar_hasta_resultado(
                cursor
            ):
                return []

            columnas = [
                columna[0]
                for columna in cursor.description
            ]

            filas = [
                dict(
                    zip(
                        columnas,
                        fila,
                    )
                )
                for fila in cursor.fetchall()
            ]

            cursor.nextset()

            return filas

        with connections[
            DB_ALIAS
        ].cursor() as cursor:

            cursor.execute(
                consulta,
                parametros,
            )

            resultados_totales = leer_resultado(
                cursor
            )

            por_estatus = leer_resultado(
                cursor
            )

            por_agencia = leer_resultado(
                cursor
            )

            por_asesor = leer_resultado(
                cursor
            )

            resultados_refacciones = leer_resultado(
                cursor
            )

            top_refacciones = leer_resultado(
                cursor
            )

        totales = (
            resultados_totales[0]
            if resultados_totales
            else {
                "registros": 0,
                "presupuestos": 0,
                "monto_productos": 0,
                "monto_mano_obra": 0,
                "monto_adicionales": 0,
                "descuento_refacciones": 0,
                "descuento_servicios": 0,
                "monto_total": 0,
            }
        )

        refacciones = (
            resultados_refacciones[0]
            if resultados_refacciones
            else {
                "lineas_refaccion": 0,
                "presupuestos_con_refacciones": 0,
                "cantidad_refacciones": 0,
                "suma_vr_liq_pc": 0,
                "valor_refacciones_estimado": 0,
            }
        )

        return Response(
            {
                "totales": totales,
                "refacciones": refacciones,
                "graficas": {
                    "por_estatus": por_estatus,
                    "por_agencia": por_agencia,
                    "por_asesor": por_asesor,
                    "top_refacciones": top_refacciones,
                },
            }
        )


# ============================================================
# OPCIONES PARA FILTROS
# ============================================================

class PresupuestosOpcionesView(APIView):
    authentication_classes = [
        CRMJWTAuthentication
    ]
    permission_classes = [
        IsAuthenticated
    ]

    def get(self, request):
        opciones_cache = cache.get(
            CACHE_OPCIONES
        )

        if opciones_cache:
            return Response(
                opciones_cache
            )

        consulta_agencias = f"""
            SELECT DISTINCT valor
            FROM (
                SELECT
                    LTRIM(
                        RTRIM(Agencia)
                    ) AS valor
                FROM {TABLA_PRESUPUESTOS}

                UNION

                SELECT
                    LTRIM(
                        RTRIM(Agencia)
                    ) AS valor
                FROM {TABLA_REFACCIONES}
            ) AS datos

            WHERE valor IS NOT NULL
              AND valor <> ''

            ORDER BY valor
        """

        consulta_estatus = f"""
            SELECT DISTINCT
                LTRIM(
                    RTRIM(Sit)
                ) AS valor
            FROM {TABLA_PRESUPUESTOS}

            WHERE Sit IS NOT NULL
              AND LTRIM(
                    RTRIM(Sit)
                  ) <> ''

            ORDER BY valor
        """

        consulta_modelos = f"""
            SELECT DISTINCT
                LTRIM(
                    RTRIM(CodModelo)
                ) AS valor
            FROM {TABLA_PRESUPUESTOS}

            WHERE CodModelo IS NOT NULL
              AND LTRIM(
                    RTRIM(CodModelo)
                  ) <> ''

            ORDER BY valor
        """

        consulta_asesores = f"""
            SELECT DISTINCT
                CodFunc
            FROM {TABLA_PRESUPUESTOS}

            WHERE CodFunc IS NOT NULL

            ORDER BY CodFunc
        """

        with connections[
            DB_ALIAS
        ].cursor() as cursor:

            cursor.execute(
                consulta_agencias
            )

            agencias = [
                fila[0]
                for fila in cursor.fetchall()
                if fila[0]
            ]

            cursor.execute(
                consulta_estatus
            )

            estatus = [
                fila[0]
                for fila in cursor.fetchall()
                if fila[0]
            ]

            cursor.execute(
                consulta_modelos
            )

            modelos = [
                fila[0]
                for fila in cursor.fetchall()
                if fila[0]
            ]

            cursor.execute(
                consulta_asesores
            )

            asesores = [
                fila[0]
                for fila in cursor.fetchall()
                if fila[0] is not None
            ]

        opciones = {
            "agencias": agencias,
            "estatus": estatus,
            "modelos": modelos,
            "codigos_asesor": asesores,
        }

        cache.set(
            CACHE_OPCIONES,
            opciones,
            300,
        )

        return Response(
            opciones
        )