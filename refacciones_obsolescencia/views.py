from django.db import connections
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from CrmConformidad.jwt_authentication import CRMJWTAuthentication
from .serializers import InventarioRefaccionesObsolescenciaSerializer


DB_ALIAS = "sqlserver_inv"
TABLA = "dbo.Inventario_Refacciones_Obsolescencia"


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


def construir_filtros(request):
    busqueda = texto_parametro(request, "q")
    agencia = texto_parametro(request, "agencia")
    grupo_principal = texto_parametro(request, "grupo_principal")
    categoria = texto_parametro(request, "categoria")
    capa_obsolescencia = texto_parametro(request, "capa_obsolescencia")
    categoria_movimiento = texto_parametro(request, "categoria_movimiento")
    fecha_desde = texto_parametro(request, "fecha_desde")
    fecha_hasta = texto_parametro(request, "fecha_hasta")
    dias_min = entero_parametro(request, "dias_min")
    dias_max = entero_parametro(request, "dias_max")

    validar_fecha(fecha_desde, "fecha_desde")
    validar_fecha(fecha_hasta, "fecha_hasta")

    condiciones = []
    parametros = []

    if busqueda:
        termino = f"%{busqueda}%"
        condiciones.append("""
            (
                Agencia LIKE %s
                OR CodProd LIKE %s
                OR NmProduto LIKE %s
                OR NombreEstandarizado LIKE %s
                OR GrupoPrincipal LIKE %s
                OR Subgrupo LIKE %s
                OR Categoria LIKE %s
                OR Localizacao LIKE %s
                OR NmPed LIKE %s
                OR Observacion LIKE %s
                OR CAST(NrPedCpa AS NVARCHAR(50)) LIKE %s
            )
        """)
        parametros.extend([termino] * 11)

    if agencia:
        condiciones.append("Agencia = %s")
        parametros.append(agencia)

    if grupo_principal:
        condiciones.append("GrupoPrincipal = %s")
        parametros.append(grupo_principal)

    if categoria:
        condiciones.append("Categoria = %s")
        parametros.append(categoria)

    if capa_obsolescencia:
        condiciones.append("Capa_Obsolescencia = %s")
        parametros.append(capa_obsolescencia)

    if categoria_movimiento:
        condiciones.append("Categoria_Movimiento = %s")
        parametros.append(categoria_movimiento)

    if fecha_desde:
        condiciones.append("Fecha_Referencia >= %s")
        parametros.append(fecha_desde)

    if fecha_hasta:
        condiciones.append("Fecha_Referencia <= %s")
        parametros.append(fecha_hasta)

    if dias_min is not None:
        condiciones.append("Dias_Desde_Ultimo_Movimiento >= %s")
        parametros.append(dias_min)

    if dias_max is not None:
        condiciones.append("Dias_Desde_Ultimo_Movimiento <= %s")
        parametros.append(dias_max)

    where_sql = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
    return where_sql, parametros


class InventarioRefaccionesObsolescenciaListView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            pagina = max(int(request.query_params.get("page", 1)), 1)
        except (TypeError, ValueError):
            pagina = 1

        try:
            tamano_pagina = int(request.query_params.get("page_size", 100))
        except (TypeError, ValueError):
            tamano_pagina = 100

        tamano_pagina = max(1, min(tamano_pagina, 500))
        offset = (pagina - 1) * tamano_pagina

        try:
            where_sql, parametros = construir_filtros(request)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        consulta_totales = f"""
            SELECT
                COUNT(*) AS registros,
                COALESCE(SUM(COALESCE(QtdeEstoque, 0)), 0) AS existencia,
                COALESCE(SUM(COALESCE(VrEstoque, 0)), 0) AS valor_estoque,
                COALESCE(SUM(COALESCE(VrPedido, 0)), 0) AS valor_pedido
            FROM {TABLA}
            {where_sql}
        """

        consulta = f"""
            SELECT
                Agencia AS agencia,
                NrPedCpa AS nr_ped_cpa,
                TpPedCpa AS tp_ped_cpa,
                NmPed AS nm_ped,
                QtdePed AS qtde_ped,
                VrPedido AS vr_pedido,
                Situacao_Header AS situacao_header,
                Situacao_Item AS situacao_item,
                Fecha_Emision AS fecha_emision,
                Fecha_Creacion AS fecha_creacion,
                Fecha_Modificacion AS fecha_modificacion,
                CodLinhaProd AS cod_linha_prod,
                Localizacao AS localizacao,
                CodProd AS cod_prod,
                NmProduto AS nm_produto,
                Unidade AS unidade,
                QtdeEstoque AS qtde_estoque,
                VrEstoque AS vr_estoque,
                VrUnitarioMedio AS vr_unitario_medio,
                QtReservada AS qt_reservada,
                QtPedida AS qt_pedida,
                GrupoPrincipal AS grupo_principal,
                Subgrupo AS subgrupo,
                NombreEstandarizado AS nombre_estandarizado,
                Categoria AS categoria,
                Observacion AS observacion,
                Fecha_Ultima_Venta AS fecha_ultima_venta,
                Fecha_Ult_Comp_Prod AS fecha_ult_comp_prod,
                Fecha_Ult_Ped_Prod AS fecha_ult_ped_prod,
                Fecha_Ult_Actu_Prod AS fecha_ult_actu_prod,
                Fecha_Regis_Refac AS fecha_regis_refac,
                Fecha_Inventario_Refac AS fecha_inventario_refac,
                Fecha_Primera_Compra_Refac AS fecha_primera_compra_refac,
                Fecha_Actualizacion_Refac AS fecha_actualizacion_refac,
                VrUniUltCpa AS vr_uni_ult_cpa,
                PrcUnitIt AS prc_unit_it,
                VrProd AS vr_prod,
                Fecha_Referencia AS fecha_referencia,
                Dias_Desde_Ultimo_Movimiento AS dias_desde_ultimo_movimiento,
                Capa_Obsolescencia AS capa_obsolescencia,
                Categoria_Movimiento AS categoria_movimiento
            FROM {TABLA}
            {where_sql}
            ORDER BY
                CASE WHEN Fecha_Referencia IS NULL THEN 1 ELSE 0 END,
                Fecha_Referencia DESC,
                Dias_Desde_Ultimo_Movimiento DESC,
                Agencia,
                CodProd
            OFFSET %s ROWS
            FETCH NEXT %s ROWS ONLY
        """

        with connections[DB_ALIAS].cursor() as cursor:
            cursor.execute(consulta_totales, parametros)
            columnas_totales = [columna[0] for columna in cursor.description]
            totales = dict(zip(columnas_totales, cursor.fetchone()))

            cursor.execute(consulta, [*parametros, offset, tamano_pagina])
            registros = cursor_a_dicts(cursor)

        serializer = InventarioRefaccionesObsolescenciaSerializer(registros, many=True)

        return Response({
            "count": totales["registros"],
            "page": pagina,
            "page_size": tamano_pagina,
            "totales": {
                "registros": totales["registros"],
                "existencia": totales["existencia"],
                "valor_estoque": totales["valor_estoque"],
                "valor_pedido": totales["valor_pedido"],
            },
            "results": serializer.data,
        }, status=status.HTTP_200_OK)


class InventarioRefaccionesObsolescenciaOpcionesView(APIView):
    authentication_classes = [CRMJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        def valores_distintos(cursor, columna):
            consulta = f"""
                SELECT DISTINCT LTRIM(RTRIM({columna})) AS valor
                FROM {TABLA}
                WHERE {columna} IS NOT NULL
                  AND LTRIM(RTRIM({columna})) <> ''
                ORDER BY valor
            """
            cursor.execute(consulta)
            return [fila[0] for fila in cursor.fetchall() if fila[0]]

        with connections[DB_ALIAS].cursor() as cursor:
            agencias = valores_distintos(cursor, "Agencia")
            grupos_principales = valores_distintos(cursor, "GrupoPrincipal")
            categorias = valores_distintos(cursor, "Categoria")
            capas_obsolescencia = valores_distintos(cursor, "Capa_Obsolescencia")
            categorias_movimiento = valores_distintos(cursor, "Categoria_Movimiento")

        return Response({
            "agencias": agencias,
            "grupos_principales": grupos_principales,
            "categorias": categorias,
            "capas_obsolescencia": capas_obsolescencia,
            "categorias_movimiento": categorias_movimiento,
        })