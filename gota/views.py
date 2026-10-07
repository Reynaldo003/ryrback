from django.core.cache import cache
from django.db import connections
from django.utils.dateparse import parse_date

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from CrmConformidad.jwt_authentication import CRMJWTAuthentication

from .serializers import MatrizOSActivasSerializer


DB_ALIAS = "tdsql"

TABLA_OS_ACTIVAS = "public.matriz_osactivas"

CACHE_OPCIONES = "gota_opciones_v1"


# Columnas permitidas para ordenar, mapeadas a su nombre real en SQL.
# Se usa una lista blanca para que el parámetro `ordering` nunca
# llegue directo desde el cliente a la cláusula ORDER BY.
ORDENAMIENTO_PERMITIDO = {
    "agencia": '"Agencia"',
    "nr_os": '"NrOS"',
    "nr_atendimento": '"NrAtendimento"',
    "tp_os": '"TpOS"',
    "situacao": '"Situacao"',
    "subtipo_os": '"SubtipoOS"',
    "dt_abertura": '"DtAbertura"',
    "hr_abertura": '"HrAbertura"',
    "dt_fechamento": '"DtFechamento"',
    "vr_total_pecas": '"VrTotalPecas"',
    "vr_pecas": '"VrPecas"',
    "vr_om": '"VrOM"',
    "vr_adicionais": '"VrAdicionais"',
    "vr_adiantam": '"VrAdiantam"',
    "rowid": '"rowid__"',
}

ORDENAMIENTO_POR_DEFECTO = "rowid"

ORDENAMIENTO_POR_DEFECTO_SQL = ORDENAMIENTO_PERMITIDO[
    ORDENAMIENTO_POR_DEFECTO
]

SELECT_BASE = f"""
    SELECT
        \"Agencia\" AS agencia,
        \"NrAtendimento\" AS nr_atendimento,
        \"NrOS\" AS nr_os,
        \"TpOS\" AS tp_os,
        \"DtFechamento\" AS dt_fechamento,
        \"HrFechamento\" AS hr_fechamento,
        \"Situacao\" AS situacao,
        \"CodPagador\" AS cod_pagador,
        \"VrAdicionais\" AS vr_adicionais,
        \"VrAdiantam\" AS vr_adiantam,
        \"VrTotalPecas\" AS vr_total_pecas,
        \"VrPecas\" AS vr_pecas,
        \"VrAcessor\" AS vr_acessor,
        \"VrOM\" AS vr_om,
        \"VrLubrif\" AS vr_lubrif,
        \"VrCascos\" AS vr_cascos,
        \"VrDescPeca\" AS vr_desc_peca,
        \"MotivoCancel\" AS motivo_cancel,
        \"PercDescPcs\" AS perc_desc_pcs,
        \"CodCondPgto\" AS cod_cond_pgto,
        \"CodOperFiscal\" AS cod_oper_fiscal,
        \"SitGarantia\" AS sit_garantia,
        \"SitFISS\" AS sit_fiss,
        \"SubtipoOS\" AS subtipo_os,
        \"DtAbertura\" AS dt_abertura,
        \"HrAbertura\" AS hr_abertura,
        \"TipoGolpe\" AS tipo_golpe,
        \"TemFunPin\" AS tem_fun_pin,
        \"NrGarHda\" AS nr_gar_hda,
        \"Filler01\" AS filler01,
        \"Func_Cancel\" AS func_cancel,
        \"Filler03\" AS filler03,
        \"TpServMarca\" AS tp_serv_marca,
        \"CheckGM\" AS check_gm,
        \"Flag_Pago\" AS flag_pago,
        \"Uso_CFDI\" AS uso_cfdi,
        \"AutoriCrhysler\" AS autori_crhysler,
        \"FormaPago\" AS forma_pago,
        \"DtDebloq\" AS dt_debloq,
        \"Dt_Emi_Prefact\" AS dt_emi_prefact,
        \"Hr_Emi_Prefact\" AS hr_emi_prefact,
        \"HoraLLegada\" AS hora_llegada,
        \"Id_Job\" AS id_job,
        \"rowid__\" AS rowid
    FROM {TABLA_OS_ACTIVAS}
"""


# ============================================================
# HELPERS
# ============================================================

def texto_parametro(request, nombre):
    return str(
        request.query_params.get(
            nombre,
            "",
        ) or ""
    ).strip()


def entero_parametro(request, nombre):
    valor = texto_parametro(
        request,
        nombre,
    )

    if not valor:
        return None

    try:
        return int(valor)
    except (TypeError, ValueError):
        raise ValueError(
            f"El parámetro '{nombre}' debe ser un número entero."
        )


def lista_parametro(request, nombre):
    """
    Lee un parámetro de tipo "clave__in=A,B,C" para los filtros de columna
    del encabezado, que permiten seleccionar varios valores a la vez.

    Devuelve [] si el parámetro no viene, y filtra los valores vacíos.
    """

    crudo = texto_parametro(
        request,
        f"{nombre}__in",
    )

    if not crudo:
        return []

    vistos = set()
    valores = []

    for parte in crudo.split(","):
        valor = parte.strip()

        if not valor or valor in vistos:
            continue

        vistos.add(valor)
        valores.append(valor)

    return valores


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


def construir_ordenamiento(request):
    """
    Traduce el parámetro `ordering` (p.ej. `-dt_abertura`)
    a SQL usando la lista blanca ORDENAMIENTO_PERMITIDO.

    Devuelve la cláusula ORDER BY completa. `rowid__` se usa como
    desempate porque es único, y SQL Server no admite repetir una
    columna en la misma lista ORDER BY.
    """

    ordenamiento = texto_parametro(
        request,
        "ordering",
    )

    columna = ORDENAMIENTO_PERMITIDO[
        ORDENAMIENTO_POR_DEFECTO
    ]
    direccion = "DESC"

    if ordenamiento:
        descendente = ordenamiento.startswith("-")

        clave = (
            ordenamiento[1:]
            if descendente
            else ordenamiento
        )

        columna_ignorada = ORDENAMIENTO_PERMITIDO.get(
            clave
        )

        if columna_ignorada:
            columna = columna_ignorada
            direccion = (
                "DESC"
                if descendente
                else "ASC"
            )

    if columna == ORDENAMIENTO_POR_DEFECTO_SQL:
        return f"{columna} {direccion}"

    return (
        f"{columna} {direccion}, "
        f"{ORDENAMIENTO_POR_DEFECTO_SQL} DESC"
    )


# ============================================================
# FILTROS
# ============================================================

def construir_filtros(request):
    busqueda = texto_parametro(
        request,
        "q",
    )

    agencia = texto_parametro(
        request,
        "agencia",
    )

    nr_os = entero_parametro(
        request,
        "nr_os",
    )

    nr_atendimento = entero_parametro(
        request,
        "nr_atendimento",
    )

    tp_os = texto_parametro(
        request,
        "tp_os",
    )

    situacao = texto_parametro(
        request,
        "situacao",
    )

    subtipo_os = texto_parametro(
        request,
        "subtipo_os",
    )

    uso_cfdi = texto_parametro(
        request,
        "uso_cfdi",
    )

    forma_pago = texto_parametro(
        request,
        "forma_pago",
    )

    sit_garantia = texto_parametro(
        request,
        "sit_garantia",
    )

    cod_oper_fiscal = entero_parametro(
        request,
        "cod_oper_fiscal",
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

    # Filtros de columna con selección múltiple (clave__in=A,B,C). Cuando viene
    # la lista gana sobre el valor simple de la misma columna, para no aplicar
    # ambos a la vez.
    agencias_in = lista_parametro(
        request,
        "agencia",
    )

    tipos_os_in = lista_parametro(
        request,
        "tp_os",
    )

    situaciones_in = lista_parametro(
        request,
        "situacao",
    )

    subtipos_os_in = lista_parametro(
        request,
        "subtipo_os",
    )

    condiciones = []
    parametros = []

    if busqueda:
        termino = f"%{busqueda}%"

        condiciones.append(
            """
            (
                \"Agencia\" ILIKE %s
                OR CAST(\"NrOS\" AS VARCHAR(50)) ILIKE %s
                OR CAST(\"NrAtendimento\" AS VARCHAR(50)) ILIKE %s
                OR CAST(\"Id_Job\" AS VARCHAR(50)) ILIKE %s
            )
            """
        )

        parametros.extend(
            [termino] * 4
        )

    if agencias_in:
        marcadores = ", ".join(
            ["%s"] * len(agencias_in)
        )

        condiciones.append(
            f'"Agencia" IN ({marcadores})'
        )
        parametros.extend(agencias_in)
    elif agencia:
        condiciones.append(
            '"Agencia" = %s'
        )
        parametros.append(
            agencia
        )

    if nr_os is not None:
        condiciones.append(
            '"NrOS" = %s'
        )
        parametros.append(
            nr_os
        )

    if nr_atendimento is not None:
        condiciones.append(
            '"NrAtendimento" = %s'
        )
        parametros.append(
            nr_atendimento
        )

    if tipos_os_in:
        marcadores = ", ".join(
            ["%s"] * len(tipos_os_in)
        )

        condiciones.append(
            f'"TpOS" IN ({marcadores})'
        )
        parametros.extend(tipos_os_in)
    elif tp_os:
        condiciones.append(
            '"TpOS" = %s'
        )
        parametros.append(
            tp_os
        )

    if situaciones_in:
        marcadores = ", ".join(
            ["%s"] * len(situaciones_in)
        )

        condiciones.append(
            f'"Situacao" IN ({marcadores})'
        )
        parametros.extend(situaciones_in)
    elif situacao:
        condiciones.append(
            '"Situacao" = %s'
        )
        parametros.append(
            situacao
        )

    if subtipos_os_in:
        marcadores = ", ".join(
            ["%s"] * len(subtipos_os_in)
        )

        condiciones.append(
            f'"SubtipoOS" IN ({marcadores})'
        )
        parametros.extend(subtipos_os_in)
    elif subtipo_os:
        condiciones.append(
            '"SubtipoOS" = %s'
        )
        parametros.append(
            subtipo_os
        )

    if uso_cfdi:
        condiciones.append(
            '"Uso_CFDI" = %s'
        )
        parametros.append(
            uso_cfdi
        )

    if forma_pago:
        condiciones.append(
            '"FormaPago" = %s'
        )
        parametros.append(
            forma_pago
        )

    if sit_garantia:
        condiciones.append(
            '"SitGarantia" = %s'
        )
        parametros.append(
            sit_garantia
        )

    if cod_oper_fiscal is not None:
        condiciones.append(
            '"CodOperFiscal" = %s'
        )
        parametros.append(
            cod_oper_fiscal
        )

    # DtAbertura es DATETIME: comparar contra 'YYYY-MM-DD' la interpretaría
    # como medianoche y descartaría todo lo abierto después de las 00:00 del
    # último día (p. ej. el filtro por mes perdería su último día). Se
    # compara por la parte de fecha para que el rango sea inclusivo completo.
    if fecha_desde:
        condiciones.append(
            "CAST(\"DtAbertura\" AS DATE) >= %s"
        )
        parametros.append(
            fecha_desde
        )

    if fecha_hasta:
        condiciones.append(
            "CAST(\"DtAbertura\" AS DATE) <= %s"
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
# LISTADO DE ÓRDENES DE TALLER
# ============================================================

class GotaOrdenesListView(APIView):
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
            ) = construir_filtros(request)
        except ValueError as exc:
            return Response(
                {
                    "detail": str(exc)
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        ordenamiento = construir_ordenamiento(
            request
        )

        consulta_total = f"""
            SELECT COUNT(*)
            FROM {TABLA_OS_ACTIVAS}
            {where_sql}
        """

        consulta = f"""
            {SELECT_BASE}
            {where_sql}
            ORDER BY
                {ordenamiento}
            LIMIT %s OFFSET %s
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
                    tamano_pagina,
                    offset,
                ],
            )

            registros = cursor_a_dicts(
                cursor
            )

        serializer = MatrizOSActivasSerializer(
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

class GotaDashboardView(APIView):
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
            ) = construir_filtros(request)
        except ValueError as exc:
            return Response(
                {
                    "detail": str(exc)
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        base = f"""
            WITH base_os AS (
                SELECT *
                FROM {TABLA_OS_ACTIVAS}
                {where_sql}
            )
        """

        dias = '(CURRENT_DATE - "DtAbertura"::date)'

        rango = f"""
            CASE
                WHEN {dias} <= 1 THEN '0-1 días'
                WHEN {dias} <= 3 THEN '2-3 días'
                WHEN {dias} <= 7 THEN '4-7 días'
                WHEN {dias} <= 15 THEN '8-15 días'
                ELSE 'Más de 15 días'
            END
        """

        consultas = {
            "totales": base + f"""
                SELECT
                    COUNT(*) AS ordenes,
                    COUNT(DISTINCT "Agencia") AS agencias,
                    COUNT(DISTINCT "NrOS") AS ordenes_unicas,
                    COALESCE(SUM(COALESCE("VrPecas", 0)), 0) AS monto_pecas,
                    COALESCE(SUM(COALESCE("VrOM", 0)), 0) AS monto_mano_obra,
                    COALESCE(SUM(COALESCE("VrLubrif", 0)), 0) AS monto_lubricantes,
                    COALESCE(SUM(COALESCE("VrAcessor", 0)), 0) AS monto_accesorios,
                    COALESCE(SUM(COALESCE("VrCascos", 0)), 0) AS monto_cascos,
                    COALESCE(SUM(COALESCE("VrAdicionais", 0)), 0) AS monto_adicionales,
                    COALESCE(SUM(COALESCE("VrAdiantam", 0)), 0) AS monto_adiantamientos,
                    COALESCE(SUM(COALESCE("VrDescPeca", 0)), 0) AS descuento_pecas,
                    COALESCE(
                        SUM(
                            COALESCE("VrPecas", 0)
                            + COALESCE("VrOM", 0)
                            + COALESCE("VrLubrif", 0)
                            + COALESCE("VrAcessor", 0)
                            + COALESCE("VrCascos", 0)
                            + COALESCE("VrAdicionais", 0)
                        ),
                        0
                    ) AS monto_total,
                    CAST(
                        AVG(CAST({dias} AS DOUBLE PRECISION))
                        AS NUMERIC(18, 2)
                    ) AS dias_promedio,
                    MAX({dias}) AS dias_maximo
                FROM base_os
            """,
            "agencia": base + """
                SELECT
                    COALESCE(NULLIF(BTRIM("Agencia"), ''), 'Sin agencia') AS agencia,
                    COUNT(*) AS ordenes,
                    COALESCE(
                        SUM(
                            COALESCE("VrPecas", 0)
                            + COALESCE("VrOM", 0)
                            + COALESCE("VrAdicionais", 0)
                        ),
                        0
                    ) AS monto_total
                FROM base_os
                GROUP BY COALESCE(NULLIF(BTRIM("Agencia"), ''), 'Sin agencia')
                ORDER BY ordenes DESC
            """,
            "tipo": base + """
                SELECT
                    COALESCE(NULLIF(BTRIM("TpOS"), ''), 'Sin tipo') AS tp_os,
                    COUNT(*) AS ordenes
                FROM base_os
                GROUP BY COALESCE(NULLIF(BTRIM("TpOS"), ''), 'Sin tipo')
                ORDER BY ordenes DESC
            """,
            "subtipo": base + """
                SELECT
                    COALESCE(NULLIF(BTRIM("SubtipoOS"), ''), 'Sin subtipo') AS subtipo_os,
                    COUNT(*) AS ordenes
                FROM base_os
                GROUP BY COALESCE(NULLIF(BTRIM("SubtipoOS"), ''), 'Sin subtipo')
                ORDER BY ordenes DESC
                LIMIT 15
            """,
            "antiguedad": base + f"""
                SELECT
                    {rango} AS rango,
                    {dias} AS orden_dias,
                    COUNT(*) AS ordenes
                FROM base_os
                WHERE "DtAbertura" IS NOT NULL
                GROUP BY {rango}, {dias}
                ORDER BY orden_dias
            """,
            "dia": base + """
                SELECT
                    "DtAbertura" AS dia,
                    COUNT(*) AS ordenes
                FROM base_os
                WHERE "DtAbertura" IS NOT NULL
                GROUP BY "DtAbertura"
                ORDER BY "DtAbertura" DESC
                LIMIT 30
            """,
            "permanencia": base + f"""
                SELECT
                    COALESCE(NULLIF(BTRIM("Agencia"), ''), 'Sin agencia') AS agencia,
                    {rango} AS rango,
                    COALESCE(NULLIF(BTRIM("TpOS"), ''), 'Sin tipo') AS tp_os,
                    COUNT(*) AS ordenes
                FROM base_os
                WHERE "DtAbertura" IS NOT NULL
                GROUP BY
                    COALESCE(NULLIF(BTRIM("Agencia"), ''), 'Sin agencia'),
                    {rango},
                    COALESCE(NULLIF(BTRIM("TpOS"), ''), 'Sin tipo')
                ORDER BY ordenes DESC
                LIMIT 3000
            """,
        }

        with connections[
            DB_ALIAS
        ].cursor() as cursor:

            def ejecutar(consulta):
                cursor.execute(
                    consulta,
                    parametros,
                )
                return cursor_a_dicts(cursor)

            resultados_totales = ejecutar(
                consultas["totales"]
            )

            por_agencia = ejecutar(
                consultas["agencia"]
            )

            por_tipo = ejecutar(
                consultas["tipo"]
            )

            por_subtipo = ejecutar(
                consultas["subtipo"]
            )

            por_antiguedad = ejecutar(
                consultas["antiguedad"]
            )

            por_dia = ejecutar(
                consultas["dia"]
            )

            por_agencia_permanencia_tipo = ejecutar(
                consultas["permanencia"]
            )

        totales = (
            resultados_totales[0]
            if resultados_totales
            else {
                "ordenes": 0,
                "agencias": 0,
                "ordenes_unicas": 0,
                "monto_pecas": 0,
                "monto_mano_obra": 0,
                "monto_lubricantes": 0,
                "monto_accesorios": 0,
                "monto_cascos": 0,
                "monto_adicionales": 0,
                "monto_adiantamientos": 0,
                "descuento_pecas": 0,
                "monto_total": 0,
                "dias_promedio": 0,
                "dias_maximo": 0,
            }
        )

        return Response(
            {
                "totales": totales,
                "graficas": {
                    "por_agencia": por_agencia,
                    "por_tipo": por_tipo,
                    "por_subtipo": por_subtipo,
                    "por_antiguedad": por_antiguedad,
                    "por_dia": por_dia,
                    "por_agencia_permanencia_tipo": por_agencia_permanencia_tipo,
                },
            }
        )


# ============================================================
# OPCIONES PARA FILTROS
# ============================================================

class GotaOpcionesView(APIView):
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

        columnas_distintas = [
            "Agencia",
            "TpOS",
            "SubtipoOS",
            "Uso_CFDI",
            "FormaPago",
        ]

        with connections[
            DB_ALIAS
        ].cursor() as cursor:

            opciones = {}

            for columna in columnas_distintas:
                cursor.execute(
                    f"""
                    SELECT DISTINCT
                        LTRIM(
                            RTRIM(\"{columna}\")
                        ) AS valor
                    FROM {TABLA_OS_ACTIVAS}

                    WHERE
                        \"{columna}\" IS NOT NULL
                        AND LTRIM(
                                RTRIM(\"{columna}\")
                            ) <> ''

                    ORDER BY
                        valor
                    """
                )

                opciones[columna.lower()] = [
                    fila[0]
                    for fila in cursor.fetchall()
                    if fila[0]
                ]

            cursor.execute(
                f"""
                SELECT DISTINCT
                    \"Situacao\",
                    \"SitGarantia\"
                FROM {TABLA_OS_ACTIVAS}
                """
            )

            situaciones = set()
            garantias = set()

            for fila in cursor.fetchall():
                if fila[0]:
                    situaciones.add(str(fila[0]).strip())
                if fila[1]:
                    garantias.add(str(fila[1]).strip())

            cursor.execute(
                f"""
                SELECT
                    MIN(\"DtAbertura\") AS fecha_minima,
                    MAX(\"DtAbertura\") AS fecha_maxima
                FROM {TABLA_OS_ACTIVAS}
                WHERE
                    \"DtAbertura\" IS NOT NULL
                """
            )

            fila_rango = cursor.fetchone()

        opciones["situacao"] = sorted(
            situaciones
        )
        opciones["sit_garantia"] = sorted(
            garantias
        )
        opciones["fechas"] = {
            "minima": (
                fila_rango[0].isoformat()
                if fila_rango and fila_rango[0]
                else None
            ),
            "maxima": (
                fila_rango[1].isoformat()
                if fila_rango and fila_rango[1]
                else None
            ),
        }

        cache.set(
            CACHE_OPCIONES,
            opciones,
            300,
        )

        return Response(
            opciones
        )
