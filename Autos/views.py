from django.shortcuts import render

# Create your views here.

from django.db import connection

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

        condiciones = []
        parametros = []

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


        # Si no hay filtros, no agregamos WHERE.
        where_sql = ""

        if condiciones:
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

        with connection.cursor() as cursor:
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

        with connection.cursor() as cursor:
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