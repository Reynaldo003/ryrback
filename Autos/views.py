from django.shortcuts import render

# Create your views here.

from django.db import connections

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from CrmConformidad.jwt_authentication import CRMJWTAuthentication

from .serializers import VWVNSerializer


class VWVNListView(APIView):
    """
    Consulta los registros de dbo.VW_VN.

    Es un endpoint de solo lectura.
    No modifica información de la tabla original.
    """

    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # ---------------------------------------------------------
        # 1. RECIBIMOS LOS FILTROS DEL FRONTEND
        # ---------------------------------------------------------

        busqueda = str(
            request.query_params.get("q", "") or ""
        ).strip()

        agencia = str(
            request.query_params.get("agencia", "") or ""
        ).strip()

        asesor = str(
            request.query_params.get("asesor", "") or ""
        ).strip()

        fecha_desde = str(
            request.query_params.get("fecha_desde", "") or ""
        ).strip()

        fecha_hasta = str(
            request.query_params.get("fecha_hasta", "") or ""
        ).strip()

        familia = str(
            request.query_params.get("familia", "") or ""
        ).strip()

        condicion_pago = str(
            request.query_params.get("condicion_pago", "") or ""
        ).strip()

        # ---------------------------------------------------------
        # 2. PAGINACIÓN
        # ---------------------------------------------------------

        try:
            pagina = max(
                int(request.query_params.get("page", 1)),
                1,
            )
        except (TypeError, ValueError):
            pagina = 1

        try:
            tamano_pagina = int(
                request.query_params.get("page_size", 50)
            )
        except (TypeError, ValueError):
            tamano_pagina = 50

        # Evitamos que alguien solicite miles de registros
        # de golpe desde el navegador.
        tamano_pagina = max(
            1,
            min(tamano_pagina, 100),
        )

        offset = (pagina - 1) * tamano_pagina


        # ---------------------------------------------------------
        # 3. CONSTRUIMOS LOS FILTROS SQL
        # ---------------------------------------------------------

# Autos Nuevos: siempre excluir unidades usadas.
        condiciones = [
            "CondUso = %s"
        ]

        parametros = [
            "N"
        ]

        if busqueda:
            termino = f"%{busqueda}%"

            condiciones.append(
                """
                (
                    Serie LIKE %s
                    OR RazaoSocial LIKE %s
                    OR Asesor LIKE %s
                    OR AGENCIA LIKE %s
                    OR NmFamilia LIKE %s
                    OR ProdOuServ LIKE %s
                )
                """
            )

            parametros.extend([
                termino,
                termino,
                termino,
                termino,
                termino,
                termino,
            ])

        if agencia:
            condiciones.append(
                "AGENCIA = %s"
            )
            parametros.append(agencia)

        if asesor:
            condiciones.append(
                "Asesor = %s"
            )
            parametros.append(asesor)

        if fecha_desde:
            condiciones.append(
                "DtEmissao >= %s"
            )
            parametros.append(fecha_desde)

        if fecha_hasta:
            condiciones.append(
                "DtEmissao <= %s"
            )
            parametros.append(fecha_hasta)

        if familia:
            condiciones.append(
                "NmFamilia = %s"
            )
            parametros.append(familia)


        if condicion_pago:
            condiciones.append(
                "NmCondPgto = %s"
            )
            parametros.append(condicion_pago)

        # Si no hay filtros, no agregamos WHERE.
        where_sql = (
            "WHERE "
            + " AND ".join(condiciones)
        )
        # ---------------------------------------------------------
        # 4. CONTAMOS CUÁNTOS REGISTROS EXISTEN
        # ---------------------------------------------------------

        consulta_total = f"""
            SELECT COUNT(*)
            FROM dbo.VW_VN
            {where_sql}
        """

        with connections["sqlserver_inv"].cursor() as cursor:
            cursor.execute(
                consulta_total,
                parametros,
            )

            total = cursor.fetchone()[0]


        # ---------------------------------------------------------
        # 5. CONSULTAMOS LOS REGISTROS
        #
        # Los "AS" cambian los nombres originales de SQL Server
        # por nombres más cómodos para usar desde React.
        # ---------------------------------------------------------

        consulta = f"""
            SELECT
                Serie AS serie,
                NrNota AS nr_nota,
                TpProduto AS tp_producto,
                ProdOuServ AS producto_servicio,
                PrcUnitario AS precio_unitario,
                VrBrutoItem AS valor_bruto_item,
                InfluiEstat AS influye_estadistica,
                VrDescItem AS valor_descuento_item,
                CodCondPgto AS codigo_condicion_pago,
                ValorFactura AS valor_factura,
                ValorFacturaSnIva AS valor_factura_sin_iva,
                ValorCompra AS valor_compra,
                ISAN AS isan,
                IVA AS iva,
                CodEntidade AS codigo_entidad,
                DtEmissao AS fecha_emision,
                Situacao AS situacion,
                TpNF AS tipo_nf,
                NrMov AS nr_mov,
                DrUltVenda AS fecha_ultima_venta,
                RazaoSocial AS razon_social,
                TpPessoa AS tipo_persona,
                VrTotalProds AS valor_total_productos,
                CodMarca AS codigo_marca,
                NmMarca AS nombre_marca,
                NmFamilia AS nombre_familia,
                CondUso AS condicion_uso,
                NmCondPgto AS nombre_condicion_pago,
                Asesor AS asesor,
                AGENCIA AS agencia
            FROM dbo.VW_VN

            {where_sql}

            ORDER BY
                DtEmissao DESC,
                NrNota DESC

            OFFSET %s ROWS
            FETCH NEXT %s ROWS ONLY
        """


        parametros_consulta = [
            *parametros,
            offset,
            tamano_pagina,
        ]


        # ---------------------------------------------------------
        # 6. EJECUTAMOS LA CONSULTA
        # ---------------------------------------------------------

        with connections["sqlserver_inv"].cursor() as cursor:
            cursor.execute(
                consulta,
                parametros_consulta,
            )

            columnas = [
                columna[0]
                for columna in cursor.description
            ]

            registros = [
                dict(zip(columnas, fila))
                for fila in cursor.fetchall()
            ]


        # ---------------------------------------------------------
        # 7. SERIALIZAMOS LOS DATOS
        # ---------------------------------------------------------

        serializer = VWVNSerializer(
            registros,
            many=True,
        )


        # ---------------------------------------------------------
        # 8. RESPUESTA QUE RECIBIRÁ REACT
        # ---------------------------------------------------------

        return Response(
            {
                "count": total,
                "page": pagina,
                "page_size": tamano_pagina,
                "results": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

class VWVNDashboardView(APIView):
    """
    Dashboard de Autos Nuevos basado en dbo.VW_VN.

    Reglas comerciales confirmadas:

    - Solo autos nuevos:
        CondUso = 'N'

    - Unidades vendidas:
        Situacao = 'E' -> 1
        Situacao = 'X' -> 0
        Otro valor     -> NULL

    - Importe / Ingresos:
        ValorFacturaSnIva - ISAN

    - Costo:
        ValorCompra

    Filtros:
        DtEmissao
        AGENCIA
        Asesor
        NmFamilia
        NmCondPgto
    """

    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):

        # ==========================================================
        # 1. FILTROS RECIBIDOS DESDE REACT
        # ==========================================================

        fecha_desde = str(
            request.query_params.get("fecha_desde", "") or ""
        ).strip()

        fecha_hasta = str(
            request.query_params.get("fecha_hasta", "") or ""
        ).strip()

        agencia = str(
            request.query_params.get("agencia", "") or ""
        ).strip()

        asesor = str(
            request.query_params.get("asesor", "") or ""
        ).strip()

        familia = str(
            request.query_params.get("familia", "") or ""
        ).strip()

        condicion_pago = str(
            request.query_params.get("condicion_pago", "") or ""
        ).strip()


        # ==========================================================
        # 2. WHERE DINÁMICO
        #
        # CondUso = N SIEMPRE.
        # El usuario no podrá cambiar este filtro desde el frontend.
        # ==========================================================

        condiciones = [
            "CondUso = %s"
        ]

        parametros = [
            "N"
        ]


        # Fecha inicial
        if fecha_desde:
            condiciones.append(
                "DtEmissao >= %s"
            )
            parametros.append(fecha_desde)


        # Fecha final
        if fecha_hasta:
            condiciones.append(
                "DtEmissao <= %s"
            )
            parametros.append(fecha_hasta)


        # Agencia
        if agencia:
            condiciones.append(
                "AGENCIA = %s"
            )
            parametros.append(agencia)


        # Asesor
        if asesor:
            condiciones.append(
                "Asesor = %s"
            )
            parametros.append(asesor)


        # Familia / modelo
        if familia:
            condiciones.append(
                "NmFamilia = %s"
            )
            parametros.append(familia)


        # Condición de pago
        if condicion_pago:
            condiciones.append(
                "NmCondPgto = %s"
            )
            parametros.append(condicion_pago)


        where_sql = (
            "WHERE "
            + " AND ".join(condiciones)
        )


        # ==========================================================
        # FUNCIÓN INTERNA
        #
        # Convierte:
        #
        # [(dato1, dato2), ...]
        #
        # en:
        #
        # [{"columna1": dato1, "columna2": dato2}, ...]
        # ==========================================================

        def cursor_a_dicts(cursor):
            columnas = [
                columna[0]
                for columna in cursor.description
            ]

            return [
                dict(zip(columnas, fila))
                for fila in cursor.fetchall()
            ]


        # ==========================================================
        # USAMOS EL SQL SERVER REAL DE VW_VN
        # ==========================================================

        with connections["sqlserver_inv"].cursor() as cursor:

            # ======================================================
            # 3. TOTALES PRINCIPALES
            # ======================================================

            consulta_totales = f"""
                SELECT

                    -- Cantidad de registros que tienen ProdOuServ.
                    COUNT(ProdOuServ) AS productos,

                    -- Emulación exacta del DAX de Rey.
                    COALESCE(
                        SUM(
                            CASE
                                WHEN Situacao = 'E' THEN 1
                                WHEN Situacao = 'X' THEN 0
                                ELSE NULL
                            END
                        ),
                        0
                    ) AS unidades_vendidas,

                    -- IMPORTE = ValorFacturaSnIva - ISAN
                    COALESCE(
                        SUM(
                            COALESCE(ValorFacturaSnIva, 0)
                            -
                            COALESCE(ISAN, 0)
                        ),
                        0
                    ) AS ingresos,

                    -- COSTO = ValorCompra
                    COALESCE(
                        SUM(
                            COALESCE(ValorCompra, 0)
                        ),
                        0
                    ) AS costo

                FROM dbo.VW_VN

                {where_sql}
            """

            cursor.execute(
                consulta_totales,
                parametros,
            )

            columnas_totales = [
                columna[0]
                for columna in cursor.description
            ]

            fila_totales = cursor.fetchone()

            totales = dict(
                zip(
                    columnas_totales,
                    fila_totales,
                )
            )


            # ======================================================
            # 4. GRÁFICA POR MES
            # ======================================================

            consulta_meses = f"""
                SELECT

                    YEAR(DtEmissao) AS anio,

                    MONTH(DtEmissao) AS mes,

                    COUNT(ProdOuServ) AS productos,

                    COALESCE(
                        SUM(
                            CASE
                                WHEN Situacao = 'E' THEN 1
                                WHEN Situacao = 'X' THEN 0
                                ELSE NULL
                            END
                        ),
                        0
                    ) AS unidades_vendidas,

                    COALESCE(
                        SUM(
                            COALESCE(ValorFacturaSnIva, 0)
                            -
                            COALESCE(ISAN, 0)
                        ),
                        0
                    ) AS ingresos,

                    COALESCE(
                        SUM(
                            COALESCE(ValorCompra, 0)
                        ),
                        0
                    ) AS costo

                FROM dbo.VW_VN

                {where_sql}

                    AND DtEmissao IS NOT NULL

                GROUP BY
                    YEAR(DtEmissao),
                    MONTH(DtEmissao)

                ORDER BY
                    YEAR(DtEmissao),
                    MONTH(DtEmissao)
            """

            cursor.execute(
                consulta_meses,
                parametros,
            )

            por_mes = cursor_a_dicts(cursor)


            # Agregamos "periodo":
            # 2026-01
            # 2026-02
            # etc.
            for item in por_mes:

                anio = item.get("anio")
                mes = item.get("mes")

                if anio and mes:
                    item["periodo"] = (
                        f"{int(anio)}-{int(mes):02d}"
                    )
                else:
                    item["periodo"] = ""


            # ======================================================
            # 5. GRÁFICA POR ASESOR
            # ======================================================

            consulta_asesores = f"""
                SELECT

                    COALESCE(
                        NULLIF(
                            LTRIM(RTRIM(Asesor)),
                            ''
                        ),
                        'Sin asesor'
                    ) AS asesor,

                    COUNT(ProdOuServ) AS productos,

                    COALESCE(
                        SUM(
                            CASE
                                WHEN Situacao = 'E' THEN 1
                                WHEN Situacao = 'X' THEN 0
                                ELSE NULL
                            END
                        ),
                        0
                    ) AS unidades_vendidas,

                    COALESCE(
                        SUM(
                            COALESCE(ValorFacturaSnIva, 0)
                            -
                            COALESCE(ISAN, 0)
                        ),
                        0
                    ) AS ingresos,

                    COALESCE(
                        SUM(
                            COALESCE(ValorCompra, 0)
                        ),
                        0
                    ) AS costo

                FROM dbo.VW_VN

                {where_sql}

                GROUP BY
                    COALESCE(
                        NULLIF(
                            LTRIM(RTRIM(Asesor)),
                            ''
                        ),
                        'Sin asesor'
                    )

                ORDER BY
                    ingresos DESC
            """

            cursor.execute(
                consulta_asesores,
                parametros,
            )

            por_asesor = cursor_a_dicts(cursor)


            # ======================================================
            # 6. GRÁFICA POR FAMILIA / MODELO
            # ======================================================

            consulta_familias = f"""
                SELECT

                    COALESCE(
                        NULLIF(
                            LTRIM(RTRIM(NmFamilia)),
                            ''
                        ),
                        'Sin familia'
                    ) AS familia,

                    COUNT(ProdOuServ) AS productos,

                    COALESCE(
                        SUM(
                            CASE
                                WHEN Situacao = 'E' THEN 1
                                WHEN Situacao = 'X' THEN 0
                                ELSE NULL
                            END
                        ),
                        0
                    ) AS unidades_vendidas,

                    COALESCE(
                        SUM(
                            COALESCE(ValorFacturaSnIva, 0)
                            -
                            COALESCE(ISAN, 0)
                        ),
                        0
                    ) AS ingresos,

                    COALESCE(
                        SUM(
                            COALESCE(ValorCompra, 0)
                        ),
                        0
                    ) AS costo

                FROM dbo.VW_VN

                {where_sql}

                GROUP BY
                    COALESCE(
                        NULLIF(
                            LTRIM(RTRIM(NmFamilia)),
                            ''
                        ),
                        'Sin familia'
                    )

                ORDER BY
                    unidades_vendidas DESC
            """

            cursor.execute(
                consulta_familias,
                parametros,
            )

            por_familia = cursor_a_dicts(cursor)


            # ======================================================
            # 7. GRÁFICA POR CONDICIÓN DE PAGO
            # ======================================================

            consulta_condiciones_pago = f"""
                SELECT

                    COALESCE(
                        NULLIF(
                            LTRIM(RTRIM(NmCondPgto)),
                            ''
                        ),
                        'Sin condición'
                    ) AS condicion_pago,

                    COUNT(ProdOuServ) AS productos,

                    COALESCE(
                        SUM(
                            CASE
                                WHEN Situacao = 'E' THEN 1
                                WHEN Situacao = 'X' THEN 0
                                ELSE NULL
                            END
                        ),
                        0
                    ) AS unidades_vendidas,

                    COALESCE(
                        SUM(
                            COALESCE(ValorFacturaSnIva, 0)
                            -
                            COALESCE(ISAN, 0)
                        ),
                        0
                    ) AS ingresos,

                    COALESCE(
                        SUM(
                            COALESCE(ValorCompra, 0)
                        ),
                        0
                    ) AS costo

                FROM dbo.VW_VN

                {where_sql}

                GROUP BY
                    COALESCE(
                        NULLIF(
                            LTRIM(RTRIM(NmCondPgto)),
                            ''
                        ),
                        'Sin condición'
                    )

                ORDER BY
                    unidades_vendidas DESC
            """

            cursor.execute(
                consulta_condiciones_pago,
                parametros,
            )

            por_condicion_pago = cursor_a_dicts(
                cursor
            )


            # ======================================================
            # 8. OPCIONES PARA LOS FILTROS DEL FRONT
            #
            # Estas opciones se consultan con CondUso = N,
            # pero NO dependen de los filtros actuales.
            # Así los selectores siempre muestran todas las opciones.
            # ======================================================

            def opciones_distintas(columna):
                consulta = f"""
                    SELECT DISTINCT
                        {columna} AS valor

                    FROM dbo.VW_VN

                    WHERE CondUso = %s
                      AND {columna} IS NOT NULL
                      AND LTRIM(RTRIM({columna})) <> ''

                    ORDER BY {columna}
                """

                cursor.execute(
                    consulta,
                    ["N"],
                )

                return [
                    fila[0]
                    for fila in cursor.fetchall()
                    if fila[0] is not None
                ]


            agencias = opciones_distintas(
                "AGENCIA"
            )

            asesores = opciones_distintas(
                "Asesor"
            )

            familias = opciones_distintas(
                "NmFamilia"
            )

            condiciones_pago = opciones_distintas(
                "NmCondPgto"
            )


        # ==========================================================
        # 9. RESPUESTA PARA REACT
        # ==========================================================

        return Response(
            {
                "filtros_aplicados": {
                    "fecha_desde": fecha_desde,
                    "fecha_hasta": fecha_hasta,
                    "agencia": agencia,
                    "asesor": asesor,
                    "familia": familia,
                    "condicion_pago": condicion_pago,
                    "cond_uso": "N",
                },

                "totales": totales,

                "graficas": {
                    "por_mes": por_mes,
                    "por_asesor": por_asesor,
                    "por_familia": por_familia,
                    "por_condicion_pago": por_condicion_pago,
                },

                "opciones": {
                    "agencias": agencias,
                    "asesores": asesores,
                    "familias": familias,
                    "condiciones_pago": condiciones_pago,
                },
            }
        )