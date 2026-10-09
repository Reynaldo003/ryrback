from django.core.cache import cache
from django.db import connections
from django.utils.dateparse import parse_date

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from CrmConformidad.jwt_authentication import CRMJWTAuthentication

from .models import GotaOrdenComentario, GotaOrdenTallerVW
from .serializers import (
    GotaOrdenComentarioSerializer,
    MatrizOSActivasSerializer,
)


# La vista de órdenes de taller activas vive en el almacén analítico
# de SQL Server (TDSQL_VW), igual que los comentarios editables.
DB_ALIAS = "sqlserver_inv"

TABLA_OS = "dbo.GotaOrdenTallerVW"

TABLA_COMENTARIOS_HISTORICOS = "dbo.Matriz_OS_Comentarios"

CACHE_OPCIONES = "gota_opciones_v2"

# La vista no tiene índices (es un HEAP), así que las consultas con
# parámetros pueden sufrir "parameter sniffing" y tardar decenas de
# segundos. OPTION (RECOMPILE) obliga a recompilar con los valores
# reales de cada ejecución y las deja en milisegundos.
RECOMPILE = "OPTION (RECOMPILE)"


# Columnas permitidas para ordenar, mapeadas a su nombre real en la vista.
# Se usa una lista blanca para que el parámetro `ordering` nunca
# llegue directo desde el cliente a la cláusula ORDER BY.
ORDENAMIENTO_PERMITIDO = {
    "agencia": '"Agencia"',
    "nr_os": '"OS"',
    "nr_atendimento": '"Atencion"',
    "tp_os": '"TipoOS"',
    "situacao": '"Situacion"',
    "subtipo_os": '"Subtipo"',
    "dt_abertura": '"Apertura"',
    "hr_abertura": '"HoraApertura"',
    "dias_taller": '"DiasTaller"',
    "id_job": '"Job"',
    "vr_pecas": '"Partes"',
    "vr_om": '"ManoObra"',
    "vr_lubrif": '"Lubricantes"',
    "vr_acessor": '"Accesorios"',
    "vr_cascos": '"Cascos"',
    "vr_adicionais": '"Adicionales"',
    "vr_adiantam": '"AdAnticipos"',
    "vr_desc_peca": '"DescPartes"',
    "perc_desc_pcs": '"PercDescPiezas"',
    "vr_total_pecas": '"TotalPartes"',
    "cod_pagador": '"CodigoPagador"',
    "pagador": '"Pagador"',
    "cod_cond_pgto": '"CondPago"',
    "cod_oper_fiscal": '"OperFiscal"',
    "forma_pago": '"FormaPago"',
    "uso_cfdi": '"UsoCFDI"',
    "sit_garantia": '"Garantia"',
    "sit_fiss": '"FISS"',
    "motivo_cancel": '"MotivoCancel"',
    "dt_debloq": '"Desbloqueo"',
    "dt_emi_prefact": '"Prefactura"',
    "hora_llegada": '"HoraLlegada"',
    "dt_fechamento": '"Cierre"',
    "hr_fechamento": '"HoraCierre"',
    "vin": '"Vin"',
    "asesor": '"Asesor"',
    "cliente": '"Cliente"',
    "telefono": '"Telefono"',
    "ubicacion": '"Ubicacion"',
    "comentarios_n": '"ComentariosN"',
    "rowid": '"RowID"',
}

ORDENAMIENTO_POR_DEFECTO = "dt_abertura"

ORDENAMIENTO_POR_DEFECTO_SQL = ORDENAMIENTO_PERMITIDO[
    ORDENAMIENTO_POR_DEFECTO
]

SELECT_BASE = f"""
    SELECT
        "Agencia" AS agencia,
        "OS" AS nr_os,
        "Atencion" AS nr_atendimento,
        "TipoOS" AS tp_os,
        "Subtipo" AS subtipo_os,
        "Situacion" AS situacao,
        "Apertura" AS dt_abertura,
        "HoraApertura" AS hr_abertura,
        "DiasTaller" AS dias_taller,
        "Job" AS id_job,
        "Partes" AS vr_pecas,
        "ManoObra" AS vr_om,
        "Lubricantes" AS vr_lubrif,
        "Accesorios" AS vr_acessor,
        "Cascos" AS vr_cascos,
        "Adicionales" AS vr_adicionais,
        "AdAnticipos" AS vr_adiantam,
        "DescPartes" AS vr_desc_peca,
        "PercDescPiezas" AS perc_desc_pcs,
        "TotalPartes" AS vr_total_pecas,
        "CodigoPagador" AS cod_pagador,
        "Pagador" AS pagador,
        "CondPago" AS cod_cond_pgto,
        "OperFiscal" AS cod_oper_fiscal,
        "FormaPago" AS forma_pago,
        "UsoCFDI" AS uso_cfdi,
        "Garantia" AS sit_garantia,
        "FISS" AS sit_fiss,
        "MotivoCancel" AS motivo_cancel,
        "Desbloqueo" AS dt_debloq,
        "Prefactura" AS dt_emi_prefact,
        "HoraLlegada" AS hora_llegada,
        "Cierre" AS dt_fechamento,
        "HoraCierre" AS hr_fechamento,
        "RowID" AS rowid,
        "Comentarios" AS comentarios,
        "ComentariosN" AS comentarios_n,
        "Vin" AS vin,
        "Asesor" AS asesor,
        "Cliente" AS cliente,
        "Telefono" AS telefono,
        "Ubicacion" AS ubicacion
    FROM {TABLA_OS}
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

    Devuelve la cláusula ORDER BY completa. La columna RowID se usa como
    desempate porque es única, y SQL Server no admite repetir una
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
                LOWER("Agencia") LIKE LOWER(%s)
                OR CAST("OS" AS VARCHAR(50)) LIKE LOWER(%s)
                OR CAST("Atencion" AS VARCHAR(50)) LIKE LOWER(%s)
                OR CAST("Job" AS VARCHAR(50)) LIKE LOWER(%s)
                OR LOWER("Vin") LIKE LOWER(%s)
                OR LOWER("Cliente") LIKE LOWER(%s)
            )
            """
        )

        parametros.extend(
            [termino] * 6
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
            '"OS" = %s'
        )
        parametros.append(
            nr_os
        )

    if nr_atendimento is not None:
        condiciones.append(
            '"Atencion" = %s'
        )
        parametros.append(
            nr_atendimento
        )

    if tipos_os_in:
        marcadores = ", ".join(
            ["%s"] * len(tipos_os_in)
        )

        condiciones.append(
            f'"TipoOS" IN ({marcadores})'
        )
        parametros.extend(tipos_os_in)
    elif tp_os:
        condiciones.append(
            '"TipoOS" = %s'
        )
        parametros.append(
            tp_os
        )

    if situaciones_in:
        marcadores = ", ".join(
            ["%s"] * len(situaciones_in)
        )

        condiciones.append(
            f'"Situacion" IN ({marcadores})'
        )
        parametros.extend(situaciones_in)
    elif situacao:
        condiciones.append(
            '"Situacion" = %s'
        )
        parametros.append(
            situacao
        )

    if subtipos_os_in:
        marcadores = ", ".join(
            ["%s"] * len(subtipos_os_in)
        )

        condiciones.append(
            f'"Subtipo" IN ({marcadores})'
        )
        parametros.extend(subtipos_os_in)
    elif subtipo_os:
        condiciones.append(
            '"Subtipo" = %s'
        )
        parametros.append(
            subtipo_os
        )

    if uso_cfdi:
        condiciones.append(
            '"UsoCFDI" = %s'
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
            '"Garantia" = %s'
        )
        parametros.append(
            sit_garantia
        )

    if cod_oper_fiscal is not None:
        condiciones.append(
            '"OperFiscal" = %s'
        )
        parametros.append(
            cod_oper_fiscal
        )

    # Apertura es DATETIME: comparar contra 'YYYY-MM-DD' la interpretaría
    # como medianoche y descartaría todo lo abierto después de las 00:00 del
    # último día (p. ej. el filtro por mes perdería su último día). Se
    # compara por la parte de fecha para que el rango sea inclusivo completo.
    if fecha_desde:
        condiciones.append(
            "CAST(\"Apertura\" AS DATE) >= %s"
        )
        parametros.append(
            fecha_desde
        )

    if fecha_hasta:
        condiciones.append(
            "CAST(\"Apertura\" AS DATE) <= %s"
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
            FROM {TABLA_OS}
            {where_sql}
            {RECOMPILE}
        """

        consulta = f"""
            {SELECT_BASE}
            {where_sql}
            ORDER BY
                {ordenamiento}
            OFFSET %s ROWS
            FETCH NEXT %s ROWS ONLY
            {RECOMPILE}
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
            ;WITH base_os AS (
                SELECT *
                FROM {TABLA_OS}
                {where_sql}
            )
        """

        dias = (
            'DATEDIFF(DAY, CAST("Apertura" AS DATE), '
            "CAST(GETDATE() AS DATE))"
        )

        rango = f"""
            CASE
                WHEN {dias} <= 1 THEN '0-1 días'
                WHEN {dias} <= 3 THEN '2-3 días'
                WHEN {dias} <= 7 THEN '4-7 días'
                WHEN {dias} <= 15 THEN '8-15 días'
                ELSE 'Más de 15 días'
            END
        """

        agencia_limpia = (
            "COALESCE(NULLIF(LTRIM(RTRIM(\"Agencia\")), ''), 'Sin agencia')"
        )

        tipo_limpio = (
            "COALESCE(NULLIF(LTRIM(RTRIM(\"TipoOS\")), ''), 'Sin tipo')"
        )

        subtipo_limpio = (
            "COALESCE(NULLIF(LTRIM(RTRIM(\"Subtipo\")), ''), 'Sin subtipo')"
        )

        consultas = {
            "totales": base + f"""
                SELECT
                    COUNT(*) AS ordenes,
                    COUNT(DISTINCT "Agencia") AS agencias,
                    COUNT(
                        DISTINCT CONCAT(
                            "Agencia",
                            '|',
                            CAST("OS" AS VARCHAR(50))
                        )
                    ) AS ordenes_unicas,
                    COALESCE(SUM(COALESCE("Partes", 0)), 0) AS monto_pecas,
                    COALESCE(SUM(COALESCE("ManoObra", 0)), 0) AS monto_mano_obra,
                    COALESCE(SUM(COALESCE("Lubricantes", 0)), 0) AS monto_lubricantes,
                    COALESCE(SUM(COALESCE("Accesorios", 0)), 0) AS monto_accesorios,
                    COALESCE(SUM(COALESCE("Cascos", 0)), 0) AS monto_cascos,
                    COALESCE(SUM(COALESCE("Adicionales", 0)), 0) AS monto_adicionales,
                    COALESCE(SUM(COALESCE("AdAnticipos", 0)), 0) AS monto_adiantamientos,
                    COALESCE(SUM(COALESCE("DescPartes", 0)), 0) AS descuento_pecas,
                    COALESCE(SUM(
                        COALESCE("Partes", 0)
                        + COALESCE("ManoObra", 0)
                        + COALESCE("Lubricantes", 0)
                        + COALESCE("Accesorios", 0)
                        + COALESCE("Cascos", 0)
                        + COALESCE("Adicionales", 0)
                        + COALESCE("AdAnticipos", 0)
                    ), 0) AS monto_total,
                    CAST(
                        AVG(CAST({dias} AS FLOAT))
                        AS NUMERIC(18, 2)
                    ) AS dias_promedio,
                    MAX({dias}) AS dias_maximo
                FROM base_os
                {RECOMPILE}
            """,
            "agencia": base + f"""
                SELECT
                    {agencia_limpia} AS agencia,
                    COUNT(*) AS ordenes,
                    COALESCE(SUM(
                        COALESCE("Partes", 0)
                        + COALESCE("ManoObra", 0)
                        + COALESCE("Lubricantes", 0)
                        + COALESCE("Accesorios", 0)
                        + COALESCE("Cascos", 0)
                        + COALESCE("Adicionales", 0)
                        + COALESCE("AdAnticipos", 0)
                    ), 0) AS monto_total
                FROM base_os
                GROUP BY {agencia_limpia}
                ORDER BY ordenes DESC
                {RECOMPILE}
            """,
            "tipo": base + f"""
                SELECT
                    {tipo_limpio} AS tp_os,
                    COUNT(*) AS ordenes
                FROM base_os
                GROUP BY {tipo_limpio}
                ORDER BY ordenes DESC
                {RECOMPILE}
            """,
            "subtipo": base + f"""
                SELECT TOP 15
                    {subtipo_limpio} AS subtipo_os,
                    COUNT(*) AS ordenes
                FROM base_os
                GROUP BY {subtipo_limpio}
                ORDER BY ordenes DESC
                {RECOMPILE}
            """,
            "antiguedad": base + f"""
                SELECT
                    {rango} AS rango,
                    {dias} AS orden_dias,
                    COUNT(*) AS ordenes
                FROM base_os
                WHERE "Apertura" IS NOT NULL
                GROUP BY {rango}, {dias}
                ORDER BY orden_dias
                {RECOMPILE}
            """,
            "dia": base + f"""
                SELECT TOP 30
                    "Apertura" AS dia,
                    COUNT(*) AS ordenes
                FROM base_os
                WHERE "Apertura" IS NOT NULL
                GROUP BY "Apertura"
                ORDER BY "Apertura" DESC
                {RECOMPILE}
            """,
            "permanencia": base + f"""
                SELECT TOP 3000
                    {agencia_limpia} AS agencia,
                    {rango} AS rango,
                    {tipo_limpio} AS tp_os,
                    COUNT(*) AS ordenes
                FROM base_os
                WHERE "Apertura" IS NOT NULL
                GROUP BY
                    {agencia_limpia},
                    {rango},
                    {tipo_limpio}
                ORDER BY ordenes DESC
                {RECOMPILE}
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
        # Si Redis está caído, seguir con consulta directa a BD en lugar
        # de devolver 500 (el frontend se quedaría sin agencias ni tipos).
        try:
            opciones_cache = cache.get(
                CACHE_OPCIONES
            )
        except Exception:  # noqa: BLE001
            opciones_cache = None

        if opciones_cache:
            return Response(
                opciones_cache
            )

        columnas_distintas = [
            ("Agencia", "agencia"),
            ("TipoOS", "tpos"),
            ("Subtipo", "subtipoos"),
            ("UsoCFDI", "uso_cfdi"),
            ("FormaPago", "formapago"),
        ]

        with connections[
            DB_ALIAS
        ].cursor() as cursor:

            opciones = {}

            for columna, clave in columnas_distintas:
                cursor.execute(
                    f"""
                    SELECT DISTINCT
                        LTRIM(
                            RTRIM("{columna}")
                        ) AS valor
                    FROM {TABLA_OS}

                    WHERE
                        "{columna}" IS NOT NULL
                        AND LTRIM(
                                RTRIM("{columna}")
                            ) <> ''

                    ORDER BY
                        valor
                    """
                )

                opciones[clave] = [
                    fila[0]
                    for fila in cursor.fetchall()
                    if fila[0]
                ]

            cursor.execute(
                f"""
                SELECT DISTINCT
                    "Situacion",
                    "Garantia"
                FROM {TABLA_OS}
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
                    MIN("Apertura") AS fecha_minima,
                    MAX("Apertura") AS fecha_maxima
                FROM {TABLA_OS}
                WHERE
                    "Apertura" IS NOT NULL
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

        try:
            cache.set(
                CACHE_OPCIONES,
                opciones,
                300,
            )
        except Exception:  # noqa: BLE001
            pass

        return Response(
            opciones
        )


# ============================================================
# COMENTARIOS EDITABLES DE LA ORDEN
# ============================================================

def datos_usuario(request):
    usuario = getattr(
        request,
        "user",
        None,
    )

    id_usuario = getattr(
        usuario,
        "id_usuario",
        None,
    )

    return (
        str(id_usuario) if id_usuario is not None else None,
        str(usuario) if usuario is not None else "",
    )


def orden_activa(agencia, nr_os):
    """
    Devuelve la fila {agencia, nr_atendimento} de la vista para la orden
    indicada, comparando la agencia sin espacios ni mayúsculas para no
    depender del padding del origen. Devuelve None si la orden no está.
    """

    filas = (
        GotaOrdenTallerVW.objects
        .using(DB_ALIAS)
        .filter(nr_os=nr_os)
        .values("agencia", "nr_atendimento")
    )

    objetivo = agencia.strip().lower()

    for fila in filas:
        if (fila["agencia"] or "").strip().lower() == objetivo:
            return fila

    return None


class GotaComentarioListCreateView(APIView):
    authentication_classes = [
        CRMJWTAuthentication
    ]
    permission_classes = [
        IsAuthenticated
    ]

    def get(self, request):
        agencia = texto_parametro(
            request,
            "agencia",
        )

        try:
            nr_os = entero_parametro(
                request,
                "nr_os",
            )
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not agencia or nr_os is None:
            return Response(
                {
                    "detail": (
                        "Los parámetros 'agencia' y 'nr_os' son obligatorios."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        objetivo = agencia.strip().lower()

        comentarios = [
            comentario
            for comentario in (
                GotaOrdenComentario.objects
                .using(DB_ALIAS)
                .filter(nr_os=nr_os, activo=True)
            )
            if (comentario.agencia or "").strip().lower() == objetivo
        ]

        serializer = GotaOrdenComentarioSerializer(
            comentarios,
            many=True,
        )

        return Response(serializer.data)

    def post(self, request):
        agencia = str(
            request.data.get("agencia")
            or ""
        ).strip()

        texto = str(
            request.data.get("texto")
            or ""
        ).strip()

        try:
            nr_os = int(
                request.data.get("nr_os")
            )
        except (TypeError, ValueError):
            nr_os = None

        if not agencia or nr_os is None or not texto:
            return Response(
                {
                    "detail": (
                        "Agencia, NrOS y texto son obligatorios."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        fila = orden_activa(
            agencia,
            nr_os,
        )

        if fila is None:
            return Response(
                {
                    "detail": (
                        "La orden no existe o ya no está activa."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        id_usuario, nombre_usuario = datos_usuario(
            request
        )

        comentario = GotaOrdenComentario(
            agencia=(fila["agencia"] or agencia).strip(),
            nr_os=nr_os,
            nr_atendimento=fila["nr_atendimento"],
            texto=texto,
            usuario=id_usuario,
            usuario_nombre=nombre_usuario,
            activo=True,
        )

        comentario.save(
            using=DB_ALIAS
        )

        return Response(
            GotaOrdenComentarioSerializer(comentario).data,
            status=status.HTTP_201_CREATED,
        )


class GotaComentarioDetalleView(APIView):
    authentication_classes = [
        CRMJWTAuthentication
    ]
    permission_classes = [
        IsAuthenticated
    ]

    def patch(self, request, pk):
        comentario = (
            GotaOrdenComentario.objects
            .using(DB_ALIAS)
            .filter(pk=pk, activo=True)
            .first()
        )

        if comentario is None:
            return Response(
                {"detail": "El comentario no existe."},
                status=status.HTTP_404_NOT_FOUND,
            )

        texto = str(
            request.data.get("texto")
            or ""
        ).strip()

        if not texto:
            return Response(
                {"detail": "El texto es obligatorio."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        comentario.texto = texto

        comentario.save(
            using=DB_ALIAS
        )

        return Response(
            GotaOrdenComentarioSerializer(comentario).data
        )

    def delete(self, request, pk):
        comentario = (
            GotaOrdenComentario.objects
            .using(DB_ALIAS)
            .filter(pk=pk, activo=True)
            .first()
        )

        if comentario is None:
            return Response(
                {"detail": "El comentario no existe."},
                status=status.HTTP_404_NOT_FOUND,
            )

        comentario.activo = False

        comentario.save(
            using=DB_ALIAS
        )

        return Response(
            status=status.HTTP_204_NO_CONTENT
        )


# ============================================================
# OBSERVACIONES HISTÓRICAS DE SERVICIO (solo lectura)
# ============================================================

class GotaObservacionesView(APIView):
    authentication_classes = [
        CRMJWTAuthentication
    ]
    permission_classes = [
        IsAuthenticated
    ]

    def get(self, request):
        agencia = texto_parametro(
            request,
            "agencia",
        )

        try:
            nr_os = entero_parametro(
                request,
                "nr_os",
            )
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not agencia or nr_os is None:
            return Response(
                {
                    "detail": (
                        "Los parámetros 'agencia' y 'nr_os' son obligatorios."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        consulta = f"""
            SELECT
                c."Seq" AS seq,
                c."DtIncl" AS dt_incl,
                c."HrIncl" AS hr_incl,
                c."TpComentario" AS tp_comentario,
                c."RespIncl" AS resp_incl,
                f."Nm_Funcionario" AS autor,
                c."Texto" AS texto
            FROM {TABLA_COMENTARIOS_HISTORICOS} c
            LEFT JOIN dbo.Matriz_Funcionarios f
                ON f."Agencia" = c."Agencia"
                AND f."Cod_Funcionario" = c."RespIncl"
            WHERE
                LTRIM(RTRIM(c."Agencia")) = %s
                AND c."NrOS" = %s
                AND LTRIM(RTRIM(ISNULL(c."Texto", ''))) <> ''
                AND LTRIM(RTRIM(c."Texto")) <> 'Cierre de la Orden'
            ORDER BY
                c."DtIncl" DESC,
                c."Seq" DESC
            {RECOMPILE}
        """

        with connections[
            DB_ALIAS
        ].cursor() as cursor:
            cursor.execute(
                consulta,
                [
                    agencia.strip(),
                    nr_os,
                ],
            )

            observaciones = cursor_a_dicts(
                cursor
            )

        return Response(
            observaciones
        )
