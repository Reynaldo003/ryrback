# jdpower/views.py
from django.core.cache import cache
from django.db import connections
from django.db.models import Q
from datetime import date, datetime
from django.db.models.functions import Trim, Upper
import re
import unicodedata

from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .models import EncuestaJDPower, EncuestaJDPowerServicio
from citas.models import Entregas
from .serializers import EncuestaJDPowerSerializer, EncuestaJDPowerServicioSerializer

from .metricas import (
    calcular_metricas,
    calcular_por_concesionaria,
    calcular_alertas,
    extraer_comentarios,
)
from .ia_resumen import generar_resumen_ia


DB_ALIAS = "tdsql"


def _vin_valido(vin):
    """VIN exacto de 17 caracteres; no inferir coincidencias parciales."""
    valor = str(vin or "").strip().upper()
    return valor if re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", valor) else ""


def _nombre_key(nombre):
    texto = unicodedata.normalize("NFKD", str(nombre or ""))
    return " ".join("".join(c for c in texto if not unicodedata.combining(c)).casefold().split())


def _asesores_desde_entregas_por_vin(items):
    """Cruza en Python dos bases distintas sin JOIN SQL. Ambiguos no se atribuyen."""
    vins = {_vin_valido(fila.get("chasis")) for fila in items}
    vins.discard("")
    if not vins:
        return {}

    nombres = {}
    claves = sorted(vins)
    for inicio in range(0, len(claves), 400):
        lote = claves[inicio:inicio + 400]
        entregas = (
            Entregas.objects.using("default")
            .annotate(vin_limpio=Upper(Trim("vin")))
            .filter(vin_limpio__in=lote)
            .exclude(asesor_ventas="")
            .values_list("vin", "asesor_ventas")
        )
        for vin_crm, nombre in entregas.iterator(chunk_size=500):
            vin = _vin_valido(vin_crm)
            texto = str(nombre or "").strip()
            if vin and texto:
                nombres.setdefault(vin, {})[_nombre_key(texto)] = texto

    resultados = {}
    for vin in vins:
        valores = list(nombres.get(vin, {}).values())
        if len(valores) == 1:
            resultados[vin] = (valores[0], "coincidencia")
        elif len(valores) > 1:
            resultados[vin] = ("", "ambiguo")
        else:
            resultados[vin] = ("", "sin_coincidencia")
    return resultados



def _id_asesor_normalizado(valor):
    """Normaliza la terminación .0 que aparece en IDs importados de Excel."""
    texto = str(valor or "").strip()
    if not texto or texto.casefold() in ("sin asesor", "sin dato", "null", "none"):
        return ""
    coincidencia = re.fullmatch(r"(\d+)(?:\.0+)?", texto)
    return coincidencia.group(1) if coincidencia else texto.upper()


def _asesores_por_id_historico(filas, nombres_vin):
    """Respaldo del cruce por VIN: IDs iguales + misma concesionaria + nombre único.

    Solo realiza SELECT. No edita encuestas, entregas ni catálogos.
    Las coincidencias ambiguas nunca se atribuyen automáticamente.
    """
    pendientes = set()
    for fila in filas:
        vin = _vin_valido(fila.get("chasis"))
        if vin and nombres_vin.get(vin, ("", ""))[0]:
            continue
        clave = (_id_asesor_normalizado(fila.get("id_asesor")),
                 str(fila.get("codigo_concesionaria") or "").strip())
        if all(clave):
            pendientes.add(clave)

    if not pendientes:
        return {}

    # Buscar el histórico completo, incluso si el panel está filtrado a octubre.
    # Cubrimos las representaciones habituales del identificador en Excel.
    variantes = set()
    for identificador, _ in pendientes:
        variantes.update((identificador, identificador + ".0", identificador + ".00"))

    concesionarias = {codigo for _, codigo in pendientes}
    referencias = set()
    variantes = sorted(variantes)
    for inicio in range(0, len(variantes), 150):
        registros = (
            EncuestaJDPower.objects.using(DB_ALIAS)
            .filter(
                id_asesor__in=variantes[inicio:inicio + 150],
                codigo_concesionaria__in=concesionarias,
            )
            .values_list("id_asesor", "codigo_concesionaria", "chasis")
        )
        for id_jd, codigo, chasis in registros.iterator(chunk_size=500):
            clave = (_id_asesor_normalizado(id_jd), str(codigo or "").strip())
            vin = _vin_valido(chasis)
            if clave in pendientes and vin:
                referencias.add((clave, vin))

    if not referencias:
        return {}

    por_vin = _asesores_desde_entregas_por_vin(
        [{"chasis": vin} for _, vin in referencias]
    )
    posibles = {}
    ambiguos = set()
    for clave, vin in referencias:
        nombre, estado = por_vin.get(vin, ("", "sin_coincidencia"))
        if estado == "ambiguo":
            ambiguos.add(clave)
        elif estado == "coincidencia" and nombre:
            posibles.setdefault(clave, {})[_nombre_key(nombre)] = nombre

    resultados = {}
    for clave in pendientes:
        encontrados = list(posibles.get(clave, {}).values())
        if len(encontrados) == 1 and clave not in ambiguos:
            resultados[clave] = (encontrados[0], "id_historico_misma_agencia")
        elif len(encontrados) > 1 or clave in ambiguos:
            resultados[clave] = ("", "id_historico_ambiguo")
    return resultados



def _fecha_servicio_cruce(valor):
    """Fecha real de atención, nunca el campo periodo (mes de encuesta)."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if valor:
        try:
            return date.fromisoformat(str(valor)[:10])
        except (TypeError, ValueError):
            pass
    return None


def _asesores_servicio_desde_hoja_ingresos(filas):
    """Cruce conservador de Servicio: VIN exacto + fecha de ingreso ±15 días.

    Fuente: default.public.hoja_ingresos(vin, asesor, fecha_ingreso).
    No se cruza por id_asesor (está vacío en las encuestas de Servicio).
    Los asesores distintos dentro de la ventana quedan sin identificar.
    No se escribe en ninguna base ni se inventan nombres.
    """
    vins = sorted({vin for fila in filas if (vin := _vin_valido(fila.get("chasis")))})
    if not vins:
        return {}

    ingresos_por_vin = {}
    with connections["default"].cursor() as cursor:
        for inicio in range(0, len(vins), 400):
            lote = vins[inicio:inicio + 400]
            marcadores = ",".join(["%s"] * len(lote))
            cursor.execute(
                "SELECT UPPER(TRIM(vin)), TRIM(asesor), fecha_ingreso "
                "FROM public.hoja_ingresos "
                "WHERE UPPER(TRIM(vin)) IN (" + marcadores + ") "
                "AND NULLIF(TRIM(asesor), '') IS NOT NULL",
                lote,
            )
            for vin, nombre, fecha_ingreso in cursor.fetchall():
                fecha = _fecha_servicio_cruce(fecha_ingreso)
                nombre = str(nombre or "").strip()
                if fecha and nombre:
                    ingresos_por_vin.setdefault(_vin_valido(vin), []).append((fecha, nombre))

    resultados = {}
    for fila in filas:
        pk = fila["id"]
        vin = _vin_valido(fila.get("chasis"))
        fecha_servicio = _fecha_servicio_cruce(fila.get("fecha_servicio"))
        if not vin:
            resultados[pk] = ("", "sin_vin")
            continue
        if not fecha_servicio:
            resultados[pk] = ("", "sin_fecha_servicio")
            continue

        candidatos = {}
        for fecha_ingreso, nombre in ingresos_por_vin.get(vin, ()):
            dias = abs((fecha_servicio - fecha_ingreso).days)
            if dias <= 15:
                clave = _nombre_key(nombre)
                if clave not in candidatos or dias < candidatos[clave][0]:
                    candidatos[clave] = (dias, nombre)

        if len(candidatos) == 1:
            nombre = next(iter(candidatos.values()))[1]
            resultados[pk] = (nombre, "vin_fecha_15d")
        elif len(candidatos) > 1:
            resultados[pk] = ("", "vin_fecha_ambiguo")
        else:
            resultados[pk] = ("", "sin_ingreso_fecha_cercana")

    return resultados


def _codigo_funcionario(valor):
    """Sólo códigos numéricos del DMS, sin el sufijo .0."""
    texto = str(valor or "").strip()
    return str(int(texto.split(".")[0])) if re.fullmatch(r"\d+(?:\.0+)?", texto) else ""


def _mismo_nombre_abreviado(abreviado, completo):
    """Acepta apellidos/nombres abreviados, sin confundir personas distintas."""
    corto = _nombre_key(abreviado).split()
    largo = _nombre_key(completo).split()
    if len(corto) < 2 or len(largo) < 2:
        return False
    # Cada palabra debe existir en el nombre oficial, respetando repeticiones.
    restantes = largo.copy()
    for palabra in corto:
        if palabra not in restantes:
            return False
        restantes.remove(palabra)
    return True


def _asesores_servicio_fallback_matriz(filas, cruce_hoja):
    """Prioridad: hoja_ingresos (VIN + fecha ±15 días). Para casos pendientes,
    exige VIN válido, fecha ±15 días, agencia JD/DMS verificada y un único
    empleado AST/AT/REC por agencia + código en matriz_funcionarios.
    Una segunda opción SEC/MEC puede descartarse; ASH/otras/desconocidas
    mantienen el caso ambiguo. No escribe en ninguna base de datos.
    """
    pendientes = [fila for fila in filas if not cruce_hoja.get(fila["id"], ("", ""))[0]]
    if not pendientes:
        return cruce_hoja

    vins = sorted({v for fila in filas if (v := _vin_valido(fila.get("chasis")))})
    if not vins:
        return cruce_hoja

    # Correspondencias verificadas entre códigos J.D. Power y agencias DMS.
    # No se atribuye automáticamente ninguna concesionaria desconocida.
    agencias_jd_dms = {
        "1905": _nombre_key("Vw Tuxtepec"),
        "2923": _nombre_key("Vw Cordoba"),
        "2924": _nombre_key("Vw Orizaba"),
        "2927": _nombre_key("Vw Poza Rica"),
        "2929": _nombre_key("Vw Tuxpan"),
    }

    # VIN + fecha real de atención: siempre consultar la matriz en PostgreSQL.
    matriz = {}
    try:
        with connections[DB_ALIAS].cursor() as cursor:
            for inicio in range(0, len(vins), 300):
                lote = vins[inicio:inicio + 300]
                marcas = ",".join(["%s"] * len(lote))
                cursor.execute(
                    "SELECT UPPER(TRIM(chassi::text)), dtfechamento, "
                    "funcionarioct, agencia "
                    "FROM public.matriz_atendimento "
                    "WHERE UPPER(TRIM(chassi::text)) IN (" + marcas + ")",
                    lote,
                )
                for vin, cierre, funcionario, agencia in cursor.fetchall():
                    fecha = _fecha_servicio_cruce(cierre)
                    codigo = _codigo_funcionario(funcionario)
                    agencia_dms = _nombre_key(agencia)
                    vin = _vin_valido(vin)
                    if vin and fecha and codigo and agencia_dms:
                        matriz.setdefault(vin, []).append(
                            (fecha, codigo, agencia_dms)
                        )
    except Exception:
        # Una falla en DMS no debe eliminar coincidencias de hoja_ingresos.
        return cruce_hoja

    por_encuesta = {}
    codigos = set()
    for fila in filas:
        pk = fila["id"]
        vin = _vin_valido(fila.get("chasis"))
        fecha = _fecha_servicio_cruce(fila.get("fecha_servicio"))
        agencia_jd = str(fila.get("codigo_concesionaria") or "").strip()
        agencia_esperada = agencias_jd_dms.get(agencia_jd)
        if not vin or not fecha or not agencia_esperada:
            continue

        opciones = {
            (agencia_dms, codigo)
            for cierre, codigo, agencia_dms in matriz.get(vin, ())
            if abs((fecha - cierre).days) <= 15
        }
        # Si el VIN se atendió en otra agencia en el mismo intervalo, no
        # adivinar a cuál de las atenciones pertenece la encuesta.
        if not opciones or any(a != agencia_esperada for a, _ in opciones):
            continue
        por_encuesta[pk] = opciones
        codigos.update(codigo for _, codigo in opciones)

    if not codigos:
        return cruce_hoja

    # Catálogo completo de empleados por agencia + código. Los códigos se
    # repiten entre concesionarias; consultar sólo por código sería inseguro.
    funcionarios = {}
    try:
        with connections[DB_ALIAS].cursor() as cursor:
            claves = sorted(codigos)
            for inicio in range(0, len(claves), 200):
                lote = claves[inicio:inicio + 200]
                marcas = ",".join(["%s"] * len(lote))
                cursor.execute(
                    "SELECT agencia, cod_funcionario, nm_funcionario, "
                    "cod_cargo, cod_area, cod_setor "
                    "FROM public.matriz_funcionarios "
                    "WHERE REGEXP_REPLACE(BTRIM(cod_funcionario::text), "
                    "'[.]0+$', '') IN (" + marcas + ")",
                    lote,
                )
                for agencia, codigo, nombre, cargo, area, sector in cursor.fetchall():
                    clave = (_nombre_key(agencia), _codigo_funcionario(codigo))
                    if clave[1] not in codigos or clave[0] not in agencias_jd_dms.values():
                        continue
                    texto = str(nombre or "").strip()
                    registro = (
                        _nombre_key(texto), texto,
                        str(cargo or "").strip().upper(),
                        str(area or "").strip().upper(),
                        str(sector or "").strip().upper(),
                    )
                    funcionarios.setdefault(clave, set()).add(registro)
    except Exception:
        return cruce_hoja

    # Únicamente un registro de catálogo distinto por (agencia, código).
    # SEC/MEC son cargos inequívocamente ajenos a asesoría. ASH no se
    # descarta: debe quedar en revisión si compite con un código AST.
    def asesor_validado(opciones):
        asesores = []
        for clave in opciones:
            registros = funcionarios.get(clave, set())
            if len(registros) != 1:
                return None
            nombre_key, nombre, cargo, area, sector = next(iter(registros))
            if nombre_key and (cargo, area, sector) == ("AST", "AT", "REC"):
                asesores.append((clave, nombre))
            elif len(opciones) > 1 and cargo in ("SEC", "MEC"):
                continue
            else:
                return None
        return asesores[0] if len(asesores) == 1 else None

    # Los nombres ya identificados por hoja_ingresos conservan prioridad.
    # Sólo se homologa una abreviatura si hay evidencia suficiente y no
    # existe contradicción; así evitamos barras duplicadas en la gráfica.
    evidencia = {}
    for fila in filas:
        pk = fila["id"]
        nombre_hoja = cruce_hoja.get(pk, ("", ""))[0]
        opciones = por_encuesta.get(pk)
        if not nombre_hoja or not opciones or len(opciones) != 1:
            continue
        validado = asesor_validado(opciones)
        if not validado:
            continue
        clave, nombre_dms = validado
        cuenta = evidencia.setdefault(clave, {"iguales": 0, "distintos": 0})
        if _mismo_nombre_abreviado(nombre_hoja, nombre_dms):
            cuenta["iguales"] += 1
        else:
            cuenta["distintos"] += 1

    confiables = {
        clave for clave, cuenta in evidencia.items()
        if cuenta["iguales"] >= 2
        and cuenta["iguales"] / (cuenta["iguales"] + cuenta["distintos"]) >= 0.80
    }

    resultado = cruce_hoja.copy()
    for fila in filas:
        pk = fila["id"]
        opciones = por_encuesta.get(pk)
        if not opciones:
            continue
        validado = asesor_validado(opciones)
        if not validado:
            continue
        clave, nombre_oficial = validado
        nombre_anterior, estado = resultado.get(pk, ("", "sin_coincidencia"))
        if nombre_anterior:
            if clave in confiables and _mismo_nombre_abreviado(nombre_anterior, nombre_oficial):
                resultado[pk] = (nombre_oficial, estado)
        else:
            resultado[pk] = (
                nombre_oficial, "matriz_funcionario_ast_vin_fecha_15d"
            )
    return resultado


def _asesores_servicio_fallback_recepcion(filas, cruces_existentes):
    """Respaldo adicional, solo para encuestas SIN asesor identificado.

    Criterio conservador: VIN exacto, agencia JD/DMS conocida, apertura o
    llegada +/-3 dias de fecha_servicio; UNA orden y UN empleado AST/AT/REC
    en ese intervalo, sin otra atencion ni otra agencia concurrentes.
    Nunca cambia nombres existentes, no usa SQL Server ni escribe datos.
    """
    pendientes = [
        fila for fila in filas
        if not cruces_existentes.get(fila["id"], ("", ""))[0]
        # No atribuir automaticamente si hoja_ingresos ofrecio nombres distintos.
        and cruces_existentes.get(fila["id"], ("", ""))[1] != "vin_fecha_ambiguo"
    ]
    if not pendientes:
        return cruces_existentes

    agencias_jd_dms = {
        "1905": _nombre_key("Vw Tuxtepec"),
        "2923": _nombre_key("Vw Cordoba"),
        "2924": _nombre_key("Vw Orizaba"),
        "2927": _nombre_key("Vw Poza Rica"),
        "2929": _nombre_key("Vw Tuxpan"),
    }
    vins = sorted({v for fila in pendientes if (v := _vin_valido(fila.get("chasis")))})
    if not vins:
        return cruces_existentes

    # La fecha de cierre NO se usa en este respaldo: una orden puede durar
    # semanas. El numero de orden permite detectar varias visitas del VIN.
    por_vin = {}
    try:
        with connections[DB_ALIAS].cursor() as cursor:
            for inicio in range(0, len(vins), 250):
                lote = vins[inicio:inicio + 250]
                marcas = ",".join(["%s"] * len(lote))
                cursor.execute(
                    "SELECT UPPER(TRIM(chassi::text)), agencia, nratendimento, "
                    "funcionarioct, dtabertura, dtchegada, dt_llegada_real "
                    "FROM public.matriz_atendimento "
                    "WHERE UPPER(TRIM(chassi::text)) IN (" + marcas + ")",
                    lote,
                )
                for vin, agencia, orden, empleado, apertura, llegada, llegada_real in cursor.fetchall():
                    vin_normalizado = _vin_valido(vin)
                    if not vin_normalizado:
                        continue
                    fechas = {
                        f for dato in (apertura, llegada, llegada_real)
                        if (f := _fecha_servicio_cruce(dato)) is not None
                    }
                    if not fechas:
                        continue
                    por_vin.setdefault(vin_normalizado, []).append((
                        _nombre_key(agencia), str(orden or "").strip(),
                        _codigo_funcionario(empleado), fechas,
                    ))
    except Exception:
        # Conservar el resultado anterior ante un fallo de la tabla DMS.
        return cruces_existentes

    por_encuesta = {}
    codigos = set()
    for fila in pendientes:
        pk = fila["id"]
        vin = _vin_valido(fila.get("chasis"))
        fecha = _fecha_servicio_cruce(fila.get("fecha_servicio"))
        agencia = agencias_jd_dms.get(str(fila.get("codigo_concesionaria") or "").strip())
        if not vin or not fecha or not agencia:
            continue
        # Filtrar por ventana PRIMERO, considerando todas las agencias.
        # Otra agencia u otra orden cercana impide atribuir la encuesta.
        cercanas = {
            (ag, orden, codigo)
            for ag, orden, codigo, fechas in por_vin.get(vin, ())
            if any(abs((fecha - f).days) <= 3 for f in fechas)
        }
        if len(cercanas) != 1:
            continue
        ag, orden, codigo = next(iter(cercanas))
        if ag != agencia or not orden or not codigo:
            continue
        por_encuesta[pk] = (ag, orden, codigo)
        codigos.add(codigo)

    if not codigos:
        return cruces_existentes

    funcionarios = {}
    try:
        with connections[DB_ALIAS].cursor() as cursor:
            codigos_ordenados = sorted(codigos)
            for inicio in range(0, len(codigos_ordenados), 200):
                lote = codigos_ordenados[inicio:inicio + 200]
                marcas = ",".join(["%s"] * len(lote))
                cursor.execute(
                    "SELECT agencia, cod_funcionario, nm_funcionario, "
                    "cod_cargo, cod_area, cod_setor "
                    "FROM public.matriz_funcionarios "
                    "WHERE REGEXP_REPLACE(BTRIM(cod_funcionario::text), "
                    "'[.]0+$', '') IN (" + marcas + ")",
                    lote,
                )
                for agencia, codigo, nombre, cargo, area, sector in cursor.fetchall():
                    clave = (_nombre_key(agencia), _codigo_funcionario(codigo))
                    registro = (
                        str(nombre or "").strip(),
                        str(cargo or "").strip().upper(),
                        str(area or "").strip().upper(),
                        str(sector or "").strip().upper(),
                    )
                    funcionarios.setdefault(clave, set()).add(registro)
    except Exception:
        return cruces_existentes

    resultado = cruces_existentes.copy()
    for fila in pendientes:
        pk = fila["id"]
        opcion = por_encuesta.get(pk)
        if not opcion:
            continue
        agencia, _orden, codigo = opcion
        registros = funcionarios.get((agencia, codigo), set())
        if len(registros) != 1:
            continue
        nombre, cargo, area, sector = next(iter(registros))
        if nombre and (cargo, area, sector) == ("AST", "AT", "REC"):
            # La etiqueta permite auditar este respaldo en el frontend/API.
            resultado[pk] = (nombre, "matriz_recepcion_ast_3d_orden_unica")
    return resultado

def _asesores_servicio_normalizar_nombres(filas, cruces):
    """Homologa SOLO la etiqueta del asesor ya identificado; nunca atribuye encuestas.

    Busca nombres AST/AT/REC inequívocos en tdsql.public.matriz_funcionarios
    y exige coincidencia única por agencia y palabras del nombre abreviado.
    Conserva el origen del cruce y los casos sin identificar. Solo SELECT.
    """
    agencias_jd_dms = {
        "1905": _nombre_key("Vw Tuxtepec"),
        "2923": _nombre_key("Vw Cordoba"),
        "2924": _nombre_key("Vw Orizaba"),
        "2927": _nombre_key("Vw Poza Rica"),
        "2929": _nombre_key("Vw Tuxpan"),
    }
    agencias_necesarias = {
        agencias_jd_dms[codigo]
        for fila in filas
        if cruces.get(fila["id"], ("", ""))[0]
        if (codigo := str(fila.get("codigo_concesionaria") or "").strip()) in agencias_jd_dms
    }
    if not agencias_necesarias:
        return cruces

    catalogo_por_codigo = {}
    try:
        with connections[DB_ALIAS].cursor() as cursor:
            cursor.execute(
                "SELECT agencia, cod_funcionario, nm_funcionario, "
                "cod_cargo, cod_area, cod_setor "
                "FROM public.matriz_funcionarios"
            )
            for agencia, codigo, nombre, cargo, area, sector in cursor.fetchall():
                agencia_dms = _nombre_key(agencia)
                codigo_dms = _codigo_funcionario(codigo)
                if agencia_dms not in agencias_necesarias or not codigo_dms:
                    continue
                registro = (
                    str(nombre or "").strip(),
                    str(cargo or "").strip().upper(),
                    str(area or "").strip().upper(),
                    str(sector or "").strip().upper(),
                )
                catalogo_por_codigo.setdefault((agencia_dms, codigo_dms), set()).add(registro)
    except Exception:
        # La presentación nunca debe provocar un error 500 si falla el catálogo.
        return cruces

    nombres_por_agencia = {}
    for (agencia_dms, _codigo), registros in catalogo_por_codigo.items():
        # Un código repetido con información contradictoria no se normaliza.
        if len(registros) != 1:
            continue
        nombre, cargo, area, sector = next(iter(registros))
        nombre_normalizado = _nombre_key(nombre)
        if nombre_normalizado and (cargo, area, sector) == ("AST", "AT", "REC"):
            nombres_por_agencia.setdefault(agencia_dms, {}).setdefault(
                nombre_normalizado, set()
            ).add(nombre)

    resultado = cruces.copy()
    for fila in filas:
        pk = fila["id"]
        nombre_actual, estado = resultado.get(pk, ("", "sin_coincidencia"))
        if not nombre_actual:
            continue
        agencia_jd = str(fila.get("codigo_concesionaria") or "").strip()
        agencia_dms = agencias_jd_dms.get(agencia_jd)
        if not agencia_dms:
            continue
        candidatos = set()
        for nombre_key, representaciones in nombres_por_agencia.get(agencia_dms, {}).items():
            if (_nombre_key(nombre_actual) == nombre_key or
                    _mismo_nombre_abreviado(nombre_actual, next(iter(representaciones)))):
                # Una misma persona puede tener variantes de escritura en el catálogo.
                if len(representaciones) == 1:
                    candidatos.update(representaciones)
        if len(candidatos) == 1:
            # Cambia la etiqueta, NUNCA el estado, el asesor inferido o los datos Q1.
            resultado[pk] = (next(iter(candidatos)), estado)
    return resultado


def _asesores_servicio_cruce_estable():
    """Cruce con evidencia global, independiente de filtros y paginación del panel."""
    clave_cache = "jdpower:servicio:asesores_globales:v4_pg_recepcion_nombres"
    resultado = cache.get(clave_cache)
    if resultado is not None:
        return resultado

    # Sólo las columnas necesarias, sin límites ni filtros del panel.
    referencia = list(
        EncuestaJDPowerServicio.objects.using(DB_ALIAS).values(
            "id", "chasis", "fecha_servicio", "codigo_concesionaria"
        )
    )
    directo = _asesores_servicio_desde_hoja_ingresos(referencia)
    resultado = _asesores_servicio_fallback_matriz(referencia, directo)
    resultado = _asesores_servicio_fallback_recepcion(referencia, resultado)
    resultado = _asesores_servicio_normalizar_nombres(referencia, resultado)
    # Evita repetir cruces entre tres bases en cada cambio de filtro.
    cache.set(clave_cache, resultado, timeout=120)
    return resultado


def es_filtro_vacio(valor):
    return valor in (None, "", "Todos", "Todas", "all", "null", "undefined")


def fecha_iso(valor):
    if not valor:
        return None
    return valor.isoformat()


def numero_seguro(valor):
    try:
        if valor is None:
            return 0
        return int(valor)
    except (TypeError, ValueError):
        return 0


MESES_ES = [
    "", "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def _label_periodo(anio, mes):
    if es_filtro_vacio(anio):
        return "Todos los periodos"
    if es_filtro_vacio(mes):
        return f"Año {anio}"
    try:
        return f"{MESES_ES[int(mes)]} {anio}"
    except (ValueError, IndexError):
        return str(anio)


def _calcular_periodo_anterior(anio, mes):
    """
    Si hay mes específico -> regresa el mes previo (diciembre del año
    anterior si es enero). Si solo hay año -> regresa el año anterior
    completo. Si no hay filtro de periodo -> no hay comparación posible.
    """
    if es_filtro_vacio(anio):
        return None, None

    try:
        anio_int = int(anio)
    except ValueError:
        return None, None

    if es_filtro_vacio(mes):
        return str(anio_int - 1), "Todos"

    try:
        mes_int = int(mes)
    except ValueError:
        return None, None

    if mes_int == 1:
        return str(anio_int - 1), "12"

    return str(anio_int), str(mes_int - 1)


def _queryset_periodo(model_cls, db_alias, anio, mes):
    qs = model_cls.objects.using(db_alias).all()

    if not es_filtro_vacio(anio):
        try:
            qs = qs.filter(periodo__year=int(anio))
        except ValueError:
            pass

    if not es_filtro_vacio(mes):
        try:
            qs = qs.filter(periodo__month=int(mes))
        except ValueError:
            pass

    return qs

class EncuestaJDPowerPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 1000


class EncuestaJDPowerViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EncuestaJDPowerSerializer
    pagination_class = EncuestaJDPowerPagination

    permission_classes = [permissions.AllowAny]

    ordering_permitido = {
        "periodo": "periodo",
        "-periodo": "-periodo",
        "fecha_encuesta": "fecha_encuesta",
        "-fecha_encuesta": "-fecha_encuesta",
        "fecha_entrega": "fecha_entrega",
        "-fecha_entrega": "-fecha_entrega",
        "fecha_registro": "fecha_registro",
        "-fecha_registro": "-fecha_registro",
        "id_ventas": "id_ventas",
        "-id_ventas": "-id_ventas",
        "concesionaria": "concesionaria",
        "-concesionaria": "-concesionaria",
        "modelo": "modelo",
        "-modelo": "-modelo",
        "satisfaccion": "q1_satisfaccion_general",
        "-satisfaccion": "-q1_satisfaccion_general",
        "recomendacion": "p3_recomendacion_distribuidor",
        "-recomendacion": "-p3_recomendacion_distribuidor",
    }

    def get_queryset(self):
        qs = EncuestaJDPower.objects.using(DB_ALIAS).all()
        qs = self.aplicar_filtros(qs)
        qs = self.aplicar_ordenamiento(qs)
        return qs

    def aplicar_filtros(self, qs):
        params = self.request.query_params

        anio = params.get("anio")
        mes = params.get("mes")
        tipo = params.get("tipo")
        canal_envio = params.get("canal_envio")
        estatus = params.get("estatus")
        concesionaria = params.get("concesionaria")
        codigo_concesionaria = params.get("codigo_concesionaria")
        asesor = params.get("asesor")
        modelo = params.get("modelo")
        anio_vehiculo = params.get("anio_vehiculo")
        region = params.get("region")
        zona = params.get("zona")
        estado = params.get("estado")
        ciudad = params.get("ciudad")
        search = params.get("search")

        if not es_filtro_vacio(anio):
            try:
                qs = qs.filter(periodo__year=int(anio))
            except ValueError:
                pass

        if not es_filtro_vacio(mes):
            try:
                qs = qs.filter(periodo__month=int(mes))
            except ValueError:
                pass

        if not es_filtro_vacio(tipo):
            qs = qs.filter(tipo__iexact=tipo)

        if not es_filtro_vacio(canal_envio):
            qs = qs.filter(canal_envio__iexact=canal_envio)

        if not es_filtro_vacio(estatus):
            qs = qs.filter(estatus__iexact=estatus)

        if not es_filtro_vacio(concesionaria):
            qs = qs.filter(concesionaria__iexact=concesionaria)

        if not es_filtro_vacio(codigo_concesionaria):
            qs = qs.filter(codigo_concesionaria__iexact=codigo_concesionaria)

        if not es_filtro_vacio(asesor):
            qs = qs.filter(id_asesor__iexact=asesor)

        if not es_filtro_vacio(modelo):
            qs = qs.filter(modelo__iexact=modelo)

        if not es_filtro_vacio(anio_vehiculo):
            try:
                qs = qs.filter(anio_vehiculo=int(anio_vehiculo))
            except ValueError:
                pass

        if not es_filtro_vacio(region):
            qs = qs.filter(region__iexact=region)

        if not es_filtro_vacio(zona):
            qs = qs.filter(zona__iexact=zona)

        if not es_filtro_vacio(estado):
            qs = qs.filter(estado__iexact=estado)

        if not es_filtro_vacio(ciudad):
            qs = qs.filter(ciudad__iexact=ciudad)

        if not es_filtro_vacio(search):
            texto = search.strip()
            qs = qs.filter(
                Q(id_muestra__icontains=texto)
                | Q(id_encuesta__icontains=texto)
                | Q(chasis__icontains=texto)
                | Q(modelo__icontains=texto)
                | Q(concesionaria__icontains=texto)
                | Q(codigo_concesionaria__icontains=texto)
                | Q(id_asesor__icontains=texto)
                | Q(ciudad__icontains=texto)
                | Q(estado__icontains=texto)
                | Q(q1_1_razones_calificacion__icontains=texto)
                | Q(q3_comentarios_adicionales__icontains=texto)
                | Q(p1_1_comentarios_auto__icontains=texto)
            )

        return qs

    def aplicar_ordenamiento(self, qs):
        ordering = self.request.query_params.get("ordering", "-periodo")
        campo = self.ordering_permitido.get(ordering, "-periodo")
        return qs.order_by(campo)

    @action(detail=False, methods=["get"], url_path="ligero")
    def ligero(self, request):
        limite = request.query_params.get("limit", "10000")

        try:
            limite = int(limite)
        except ValueError:
            limite = 10000

        limite = max(100, min(limite, 30000))

        campos = (
            "id_ventas",
            "id_muestra",
            "id_encuesta",
            "tipo",
            "canal_envio",
            "estatus",
            "chasis",
            "modelo",
            "anio_vehiculo",
            "region",
            "zona",
            "estado",
            "ciudad",
            "codigo_concesionaria",
            "concesionaria",
            "id_asesor",
            "vwsf",
            "s1_entrega_vehiculo",
            "pn1_forma_compra",
            "pn2_empresa_financiamiento",
            "q1_satisfaccion_general",
            "q1_1_razones_calificacion",
            "qr_2_1_proceso_entrega",
            "qr_2_1_1_efectividad_explicacion",
            "qr_2_1_2_puntualidad_entrega",
            "qr_2_1_3_condiciones_vehiculo",
            "qr_2_1_4_conexion_bluetooth",
            "qr_2_2_atencion_personal",
            "qr_2_2_1_conocimiento_vehiculo",
            "qr_2_2_2_amabilidad",
            "qr_2_2_3_respuesta",
            "qr_2_2_4_comunicacion_fuera",
            "qr_2_2_5_uso_tecnologia",
            "qr_2_2_6_info_tiempo_entrega",
            "qr_2_3_instalaciones",
            "qr_2_3_1_apariencia",
            "qr_2_3_2_facilidad_inventario",
            "qr_2_3_3_variedad_modelos",
            "qr_2_3_4_calidad_amenidades",
            "qr_2_3_5_opciones_estacionamiento",
            "qr_2_4_documentacion",
            "qr_2_4_1_claridad_documentos",
            "qr_2_4_2_transparencia_papeleo",
            "qr_2_4_3_prontitud_papeleo",
            "qr_2_5_negociacion",
            "qr_2_5_1_acuerdo_precio",
            "qr_2_5_2_precio_justo",
            "qr_2_5_3_comodidad_negociacion",
            "q3_comentarios_adicionales",
            "p1_satisfaccion_producto",
            "p1_1_comentarios_auto",
            "p3_recomendacion_distribuidor",
            "q8_transferencia_datos",
            "q10_autoriza_publicacion",
            "fecha_registro",
            "fecha_entrega",
            "fecha_encuesta",
            "periodo",
        )

        qs = self.get_queryset().values(*campos)[:limite]
        filas = list(qs)
        # No publicar nombres de empleados en respuestas anonimas.
        autenticado = bool(request.user.is_authenticated)
        nombres = _asesores_desde_entregas_por_vin(filas) if autenticado else {}
        nombres_historicos = _asesores_por_id_historico(filas, nombres) if autenticado else {}

        data = []

        for item in filas:
            vin = _vin_valido(item.get("chasis"))
            nombre_asesor, estado_cruce = nombres.get(
                vin,
                ("", "sin_autenticacion" if not autenticado else "sin_vin" if not vin else "sin_coincidencia")
            )
            if autenticado and not nombre_asesor and estado_cruce != "ambiguo":
                clave = (_id_asesor_normalizado(item.get("id_asesor")),
                         str(item.get("codigo_concesionaria") or "").strip())
                nombre_asesor, estado_cruce = nombres_historicos.get(
                    clave, (nombre_asesor, estado_cruce)
                )
            data.append(
                {
                    "asesor_nombre": nombre_asesor,
                    "asesor_cruce": estado_cruce,
                    "id_ventas": item.get("id_ventas"),
                    "id_muestra": item.get("id_muestra") or "",
                    "id_encuesta": item.get("id_encuesta") or "",
                    "tipo": item.get("tipo") or "",
                    "canal_envio": item.get("canal_envio") or "",
                    "estatus": item.get("estatus") or "",
                    "chasis": item.get("chasis") or "",
                    "modelo": item.get("modelo") or "",
                    "anio_vehiculo": numero_seguro(item.get("anio_vehiculo")),
                    "region": item.get("region") or "",
                    "zona": item.get("zona") or "",
                    "estado": item.get("estado") or "",
                    "ciudad": item.get("ciudad") or "",
                    "codigo_concesionaria": item.get("codigo_concesionaria") or "",
                    "concesionaria": item.get("concesionaria") or "",
                    "id_asesor": item.get("id_asesor") or "",
                    "vwsf": item.get("vwsf") or "",
                    "s1_entrega_vehiculo": item.get("s1_entrega_vehiculo") or "",
                    "pn1_forma_compra": item.get("pn1_forma_compra") or "",
                    "pn2_empresa_financiamiento": item.get("pn2_empresa_financiamiento") or "",
                    "q1_satisfaccion_general": numero_seguro(item.get("q1_satisfaccion_general")),
                    "q1_1_razones_calificacion": item.get("q1_1_razones_calificacion") or "",
                    "qr_2_1_proceso_entrega": numero_seguro(item.get("qr_2_1_proceso_entrega")),
                    "qr_2_1_1_efectividad_explicacion": numero_seguro(item.get("qr_2_1_1_efectividad_explicacion")),
                    "qr_2_1_2_puntualidad_entrega": numero_seguro(item.get("qr_2_1_2_puntualidad_entrega")),
                    "qr_2_1_3_condiciones_vehiculo": numero_seguro(item.get("qr_2_1_3_condiciones_vehiculo")),
                    "qr_2_1_4_conexion_bluetooth": numero_seguro(item.get("qr_2_1_4_conexion_bluetooth")),
                    "qr_2_2_atencion_personal": numero_seguro(item.get("qr_2_2_atencion_personal")),
                    "qr_2_2_1_conocimiento_vehiculo": numero_seguro(item.get("qr_2_2_1_conocimiento_vehiculo")),
                    "qr_2_2_2_amabilidad": numero_seguro(item.get("qr_2_2_2_amabilidad")),
                    "qr_2_2_3_respuesta": numero_seguro(item.get("qr_2_2_3_respuesta")),
                    "qr_2_2_4_comunicacion_fuera": numero_seguro(item.get("qr_2_2_4_comunicacion_fuera")),
                    "qr_2_2_5_uso_tecnologia": numero_seguro(item.get("qr_2_2_5_uso_tecnologia")),
                    "qr_2_2_6_info_tiempo_entrega": numero_seguro(item.get("qr_2_2_6_info_tiempo_entrega")),
                    "qr_2_3_instalaciones": numero_seguro(item.get("qr_2_3_instalaciones")),
                    "qr_2_3_1_apariencia": numero_seguro(item.get("qr_2_3_1_apariencia")),
                    "qr_2_3_2_facilidad_inventario": numero_seguro(item.get("qr_2_3_2_facilidad_inventario")),
                    "qr_2_3_3_variedad_modelos": numero_seguro(item.get("qr_2_3_3_variedad_modelos")),
                    "qr_2_3_4_calidad_amenidades": numero_seguro(item.get("qr_2_3_4_calidad_amenidades")),
                    "qr_2_3_5_opciones_estacionamiento": numero_seguro(item.get("qr_2_3_5_opciones_estacionamiento")),
                    "qr_2_4_documentacion": numero_seguro(item.get("qr_2_4_documentacion")),
                    "qr_2_4_1_claridad_documentos": numero_seguro(item.get("qr_2_4_1_claridad_documentos")),
                    "qr_2_4_2_transparencia_papeleo": numero_seguro(item.get("qr_2_4_2_transparencia_papeleo")),
                    "qr_2_4_3_prontitud_papeleo": numero_seguro(item.get("qr_2_4_3_prontitud_papeleo")),
                    "qr_2_5_negociacion": numero_seguro(item.get("qr_2_5_negociacion")),
                    "qr_2_5_1_acuerdo_precio": numero_seguro(item.get("qr_2_5_1_acuerdo_precio")),
                    "qr_2_5_2_precio_justo": numero_seguro(item.get("qr_2_5_2_precio_justo")),
                    "qr_2_5_3_comodidad_negociacion": numero_seguro(item.get("qr_2_5_3_comodidad_negociacion")),
                    "q3_comentarios_adicionales": item.get("q3_comentarios_adicionales") or "",
                    "p1_satisfaccion_producto": numero_seguro(item.get("p1_satisfaccion_producto")),
                    "p1_1_comentarios_auto": item.get("p1_1_comentarios_auto") or "",
                    "p3_recomendacion_distribuidor": numero_seguro(item.get("p3_recomendacion_distribuidor")),
                    "q8_transferencia_datos": item.get("q8_transferencia_datos") or "",
                    "q10_autoriza_publicacion": item.get("q10_autoriza_publicacion") or "",
                    "fecha_registro": fecha_iso(item.get("fecha_registro")),
                    "fecha_entrega": fecha_iso(item.get("fecha_entrega")),
                    "fecha_encuesta": fecha_iso(item.get("fecha_encuesta")),
                    "periodo": fecha_iso(item.get("periodo")),
                }
            )

        return Response(data)

    @action(detail=False, methods=["get"], url_path="opciones")
    def opciones(self, request):
        limite = 30000

        qs = (
            EncuestaJDPower.objects.using(DB_ALIAS)
            .all()
            .values(
                "periodo",
                "tipo",
                "canal_envio",
                "estatus",
                "concesionaria",
                "codigo_concesionaria",
                "id_asesor",
                "modelo",
                "anio_vehiculo",
                "region",
                "zona",
                "estado",
                "ciudad",
            )[:limite]
        )

        anios = set()
        anio_mes_set = set()
        tipos = set()
        canales = set()
        estatuses = set()
        concesionarias = set()
        codigos_concesionaria = set()
        asesores = set()
        modelos = set()
        anios_vehiculo = set()
        regiones = set()
        zonas = set()
        estados = set()
        ciudades = set()

        for item in qs:
            periodo = item.get("periodo")

            if periodo:
                anios.add(periodo.year)
                anio_mes_set.add((periodo.year, periodo.month))

            valores = {
                "tipo": tipos,
                "canal_envio": canales,
                "estatus": estatuses,
                "concesionaria": concesionarias,
                "codigo_concesionaria": codigos_concesionaria,
                "id_asesor": asesores,
                "modelo": modelos,
                "region": regiones,
                "zona": zonas,
                "estado": estados,
                "ciudad": ciudades,
            }

            for campo, destino in valores.items():
                valor = str(item.get(campo) or "").strip()
                if valor:
                    destino.add(valor)

            if item.get("anio_vehiculo"):
                anios_vehiculo.add(item["anio_vehiculo"])

        anio_mes = [
            {
                "anio": anio,
                "mes": mes,
            }
            for anio, mes in sorted(
                anio_mes_set,
                key=lambda valor: (valor[0], valor[1]),
                reverse=True,
            )
        ]

        meses_por_anio = {}

        for item in anio_mes:
            anio = str(item["anio"])

            if anio not in meses_por_anio:
                meses_por_anio[anio] = []

            meses_por_anio[anio].append(item["mes"])

        for anio in meses_por_anio:
            meses_por_anio[anio] = sorted(list(set(meses_por_anio[anio])))

        return Response(
            {
                "anios": sorted(list(anios), reverse=True),
                "anio_mes": anio_mes,
                "meses_por_anio": meses_por_anio,
                "tipos": sorted(tipos, key=lambda texto: texto.lower()),
                "canales_envio": sorted(canales, key=lambda texto: texto.lower()),
                "estatuses": sorted(estatuses, key=lambda texto: texto.lower()),
                "concesionarias": sorted(concesionarias, key=lambda texto: texto.lower()),
                "codigos_concesionaria": sorted(codigos_concesionaria, key=lambda texto: texto.lower()),
                "asesores": sorted(asesores, key=lambda texto: texto.lower()),
                "modelos": sorted(modelos, key=lambda texto: texto.lower()),
                "anios_vehiculo": sorted(list(anios_vehiculo), reverse=True),
                "regiones": sorted(regiones, key=lambda texto: texto.lower()),
                "zonas": sorted(zonas, key=lambda texto: texto.lower()),
                "estados": sorted(estados, key=lambda texto: texto.lower()),
                "ciudades": sorted(ciudades, key=lambda texto: texto.lower()),
            }
        )
        
    @action(detail=False, methods=["post"], url_path="resumen-ia")
    def resumen_ia(self, request):
        anio = request.query_params.get("anio", "Todos")
        mes = request.query_params.get("mes", "Todos")

        campos = (
            "codigo_concesionaria",
            "concesionaria",
            "q1_satisfaccion_general",
            "p3_recomendacion_distribuidor",
            "q1_1_razones_calificacion",
            "q3_comentarios_adicionales",
            "p1_1_comentarios_auto",
        )

        qs_actual = self.aplicar_filtros(
            EncuestaJDPower.objects.using(DB_ALIAS).all()
        )
        datos_actual = list(qs_actual.values(*campos)[:10000])

        anio_ant, mes_ant = _calcular_periodo_anterior(anio, mes)

        datos_anterior = []
        if anio_ant is not None:
            qs_anterior = _queryset_periodo(
                EncuestaJDPower, DB_ALIAS, anio_ant, mes_ant
            )
            datos_anterior = list(qs_anterior.values(*campos)[:10000])

        campo_sat = "q1_satisfaccion_general"
        campo_rec = "p3_recomendacion_distribuidor"

        metricas_actual = calcular_metricas(datos_actual, campo_sat, campo_rec)
        metricas_anterior = (
            calcular_metricas(datos_anterior, campo_sat, campo_rec)
            if datos_anterior
            else None
        )

        comparacion = {
            "periodo_actual": _label_periodo(anio, mes),
            "periodo_anterior": _label_periodo(anio_ant, mes_ant) if anio_ant else "N/A",
            "satisfaccion_actual": metricas_actual["satisfaccion_promedio"],
            "satisfaccion_anterior": metricas_anterior["satisfaccion_promedio"] if metricas_anterior else None,
            "nps_actual": metricas_actual["nps"],
            "nps_anterior": metricas_anterior["nps"] if metricas_anterior else None,
        }

        if metricas_anterior:
            comparacion["variacion_satisfaccion"] = round(
                metricas_actual["satisfaccion_promedio"] - metricas_anterior["satisfaccion_promedio"], 2
            )
            comparacion["variacion_nps"] = metricas_actual["nps"] - metricas_anterior["nps"]

        alertas = []
        if datos_anterior:
            por_conc_actual = calcular_por_concesionaria(datos_actual, campo_sat, campo_rec)
            por_conc_anterior = calcular_por_concesionaria(datos_anterior, campo_sat, campo_rec)
            alertas = calcular_alertas(por_conc_actual, por_conc_anterior)

        comentarios = extraer_comentarios(
            datos_actual,
            {
                "q1_1_razones_calificacion": "Razón de calificación",
                "q3_comentarios_adicionales": "Comentario adicional",
                "p1_1_comentarios_auto": "Comentario sobre el auto",
            },
            campo_sat,
        )

        resultado_ia = generar_resumen_ia(
            tipo_modulo="Ventas",
            metricas=metricas_actual,
            comparacion=comparacion,
            alertas=alertas,
            comentarios=comentarios,
        )

        return Response(
            {
                "ok": resultado_ia.get("ok", False),
                "error": resultado_ia.get("error"),
                "periodo_label": _label_periodo(anio, mes),
                "metricas": metricas_actual,
                "comparacion": comparacion,
                "alertas_concesionarias": alertas,
                "resumen_ejecutivo": resultado_ia.get("resumen_ejecutivo", ""),
                "tendencia": resultado_ia.get("tendencia", ""),
                "top_quejas": resultado_ia.get("top_quejas", []),
                "fortalezas": resultado_ia.get("fortalezas", []),
                "recomendaciones": resultado_ia.get("recomendaciones", []),
            }
        )


#  SERVICIO  
class EncuestaJDPowerServicioPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 1000


class EncuestaJDPowerServicioViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EncuestaJDPowerServicioSerializer
    pagination_class = EncuestaJDPowerServicioPagination
    permission_classes = [permissions.AllowAny]

    ordering_permitido = {
        "periodo": "periodo",
        "-periodo": "-periodo",
        "fecha_servicio": "fecha_servicio",
        "-fecha_servicio": "-fecha_servicio",
        "fecha_completo_encuesta": "fecha_completo_encuesta",
        "-fecha_completo_encuesta": "-fecha_completo_encuesta",
        "id_encuesta": "id_encuesta",
        "-id_encuesta": "-id_encuesta",
        "concesionaria": "concesionaria",
        "-concesionaria": "-concesionaria",
        "modelo": "modelo",
        "-modelo": "-modelo",
        "satisfaccion": "q1_satisfaccion_general",
        "-satisfaccion": "-q1_satisfaccion_general",
        "recomendacion": "q3_recomendacion",
        "-recomendacion": "-q3_recomendacion",
        "indice": "indice_satisfaccion_general",
        "-indice": "-indice_satisfaccion_general",
    }

    def get_queryset(self):
        qs = EncuestaJDPowerServicio.objects.using(DB_ALIAS).all()
        qs = self.aplicar_filtros(qs)
        qs = self.aplicar_ordenamiento(qs)
        return qs

    def aplicar_filtros(self, qs):
        params = self.request.query_params

        anio = params.get("anio")
        mes = params.get("mes")
        tipo = params.get("tipo")
        tipo_servicio = params.get("tipo_servicio")
        canal_envio = params.get("canal_envio")
        estatus = params.get("estatus")
        concesionaria = params.get("concesionaria")
        codigo_concesionaria = params.get("codigo_concesionaria")
        asesor = params.get("asesor")
        modelo = params.get("modelo")
        anio_vehiculo = params.get("anio_vehiculo")
        region = params.get("region")
        zona = params.get("zona")
        estado = params.get("estado")
        search = params.get("search")

        if not es_filtro_vacio(anio):
            try:
                qs = qs.filter(periodo__year=int(anio))
            except ValueError:
                pass

        if not es_filtro_vacio(mes):
            try:
                qs = qs.filter(periodo__month=int(mes))
            except ValueError:
                pass

        if not es_filtro_vacio(tipo):
            qs = qs.filter(tipo__iexact=tipo)

        if not es_filtro_vacio(tipo_servicio):
            qs = qs.filter(tipo_servicio__iexact=tipo_servicio)

        if not es_filtro_vacio(canal_envio):
            qs = qs.filter(canal_envio__iexact=canal_envio)

        if not es_filtro_vacio(estatus):
            qs = qs.filter(estatus__iexact=estatus)

        if not es_filtro_vacio(concesionaria):
            qs = qs.filter(concesionaria__iexact=concesionaria)

        if not es_filtro_vacio(codigo_concesionaria):
            qs = qs.filter(codigo_concesionaria__iexact=codigo_concesionaria)

        if not es_filtro_vacio(asesor):
            qs = qs.filter(id_asesor__iexact=asesor)

        if not es_filtro_vacio(modelo):
            qs = qs.filter(modelo__iexact=modelo)

        if not es_filtro_vacio(anio_vehiculo):
            try:
                qs = qs.filter(anio_vehiculo=int(anio_vehiculo))
            except ValueError:
                pass

        if not es_filtro_vacio(region):
            qs = qs.filter(region__iexact=region)

        if not es_filtro_vacio(zona):
            qs = qs.filter(zona__iexact=zona)

        if not es_filtro_vacio(estado):
            qs = qs.filter(estado__iexact=estado)

        if not es_filtro_vacio(search):
            texto = search.strip()
            qs = qs.filter(
                Q(id_servicio__icontains=texto)
                | Q(chasis__icontains=texto)
                | Q(modelo__icontains=texto)
                | Q(concesionaria__icontains=texto)
                | Q(codigo_concesionaria__icontains=texto)
                | Q(id_asesor__icontains=texto)
                | Q(estado__icontains=texto)
                | Q(q1_1_razones_calificacion__icontains=texto)
                | Q(q4_comentarios_servicio__icontains=texto)
                | Q(p1_1_comentarios_auto__icontains=texto)
            )

        return qs

    def aplicar_ordenamiento(self, qs):
        ordering = self.request.query_params.get("ordering", "-periodo")
        campo = self.ordering_permitido.get(ordering, "-periodo")
        return qs.order_by(campo)

    @action(detail=False, methods=["get"], url_path="ligero")
    def ligero(self, request):
        limite = request.query_params.get("limit", "10000")

        try:
            limite = int(limite)
        except ValueError:
            limite = 10000

        limite = max(100, min(limite, 30000))

        campos = (
            "id",
            "id_servicio",
            "id_muestra",
            "id_encuesta",
            "tipo",
            "periodo",
            "canal_envio",
            "estatus",
            "fecha_registro_procesado",
            "fecha_servicio",
            "fecha_completo_encuesta",
            "tipo_servicio",
            "chasis",
            "modelo",
            "anio_vehiculo",
            "region",
            "zona",
            "estado",
            "codigo_concesionaria",
            "concesionaria",
            "id_asesor",
            "s1_confirma_concesionario",
            "q1_satisfaccion_general",
            "q1_1_razones_calificacion",
            "q2_1_calidad_servicio",
            "q2_1a_problema_no_resuelto",
            "q2_1b_sin_refacciones",
            "q2_1c_condiciones_auto",
            "q2_1d_tiempo_taller",
            "q2_2_cita_servicio",
            "q2_2c_sin_cita",
            "q2_3_atendido_valorado",
            "q2_3a_amabilidad_personal",
            "q2_3b_recepcion_rapida",
            "q2_3c_informado_estatus",
            "q2_3d_transparencia",
            "q2_4_explicacion_info",
            "q2_4a_explico_trabajos_costo",
            "q2_4b_enfocado_necesidades",
            "q2_4c_conocimiento_respuesta",
            "q2_4d_reviso_trabajos_entrega",
            "q2_4e_monto_justo",
            "q2_5_entrega",
            "q2_5a_atendido_inmediato",
            "q2_5b_auto_listo_fecha",
            "q2_5c_tiempo_recoger_auto",
            "q2_6_instalaciones_amenidades",
            "q2_6a_entrada_salida",
            "q2_6b_agencia_limpia",
            "q2_6c_sala_espera",
            "q2_6d_amenidades",
            "q3_recomendacion",
            "q4_comentarios_servicio",
            "p1_satisfaccion_producto",
            "p1_1_comentarios_auto",
            "ot1_autoriza_compartir_datos",
            "q9_autoriza_seguimiento",
            "q9a_autoriza_transferencia",
            "q10_autoriza_publicacion",
            "indice_satisfaccion_general",
            "fecha_carga",
        )

        filas = list(self.get_queryset().values(*campos)[:limite])
        # Misma protección que Ventas: no publicar nombres en respuestas anónimas.
        autenticado = bool(request.user.is_authenticated)
        asesores_cruzados = _asesores_servicio_cruce_estable() if autenticado else {}

        data = []
        for item in filas:
            nombre_asesor, estado_cruce = asesores_cruzados.get(
                item["id"], ("", "sin_autenticacion" if not autenticado else "sin_coincidencia")
            )
            data.append(
                {
                    "asesor_nombre": nombre_asesor,
                    "asesor_cruce": estado_cruce,
                    "id": item.get("id"),
                    "id_servicio": item.get("id_servicio") or "",
                    "id_muestra": numero_seguro(item.get("id_muestra")),
                    "id_encuesta": numero_seguro(item.get("id_encuesta")),
                    "tipo": item.get("tipo") or "",
                    "periodo": fecha_iso(item.get("periodo")),
                    "canal_envio": item.get("canal_envio") or "",
                    "estatus": item.get("estatus") or "",
                    "fecha_registro_procesado": fecha_iso(item.get("fecha_registro_procesado")),
                    "fecha_servicio": fecha_iso(item.get("fecha_servicio")),
                    "fecha_completo_encuesta": fecha_iso(item.get("fecha_completo_encuesta")),
                    "tipo_servicio": item.get("tipo_servicio") or "",
                    "chasis": item.get("chasis") or "",
                    "modelo": item.get("modelo") or "",
                    "anio_vehiculo": numero_seguro(item.get("anio_vehiculo")),
                    "region": item.get("region") or "",
                    "zona": item.get("zona") or "",
                    "estado": item.get("estado") or "",
                    "codigo_concesionaria": item.get("codigo_concesionaria") or "",
                    "concesionaria": item.get("concesionaria") or "",
                    "id_asesor": item.get("id_asesor") or "",
                    "s1_confirma_concesionario": item.get("s1_confirma_concesionario") or "",
                    "q1_satisfaccion_general": numero_seguro(item.get("q1_satisfaccion_general")),
                    "q1_1_razones_calificacion": item.get("q1_1_razones_calificacion") or "",
                    "q2_1_calidad_servicio": numero_seguro(item.get("q2_1_calidad_servicio")),
                    "q2_1a_problema_no_resuelto": item.get("q2_1a_problema_no_resuelto") or "",
                    "q2_1b_sin_refacciones": item.get("q2_1b_sin_refacciones") or "",
                    "q2_1c_condiciones_auto": item.get("q2_1c_condiciones_auto") or "",
                    "q2_1d_tiempo_taller": item.get("q2_1d_tiempo_taller") or "",
                    "q2_2_cita_servicio": numero_seguro(item.get("q2_2_cita_servicio")),
                    "q2_2c_sin_cita": item.get("q2_2c_sin_cita") or "",
                    "q2_3_atendido_valorado": numero_seguro(item.get("q2_3_atendido_valorado")),
                    "q2_3a_amabilidad_personal": item.get("q2_3a_amabilidad_personal") or "",
                    "q2_3b_recepcion_rapida": item.get("q2_3b_recepcion_rapida") or "",
                    "q2_3c_informado_estatus": item.get("q2_3c_informado_estatus") or "",
                    "q2_3d_transparencia": item.get("q2_3d_transparencia") or "",
                    "q2_4_explicacion_info": numero_seguro(item.get("q2_4_explicacion_info")),
                    "q2_4a_explico_trabajos_costo": item.get("q2_4a_explico_trabajos_costo") or "",
                    "q2_4b_enfocado_necesidades": item.get("q2_4b_enfocado_necesidades") or "",
                    "q2_4c_conocimiento_respuesta": item.get("q2_4c_conocimiento_respuesta") or "",
                    "q2_4d_reviso_trabajos_entrega": item.get("q2_4d_reviso_trabajos_entrega") or "",
                    "q2_4e_monto_justo": item.get("q2_4e_monto_justo") or "",
                    "q2_5_entrega": numero_seguro(item.get("q2_5_entrega")),
                    "q2_5a_atendido_inmediato": item.get("q2_5a_atendido_inmediato") or "",
                    "q2_5b_auto_listo_fecha": item.get("q2_5b_auto_listo_fecha") or "",
                    "q2_5c_tiempo_recoger_auto": item.get("q2_5c_tiempo_recoger_auto") or "",
                    "q2_6_instalaciones_amenidades": numero_seguro(item.get("q2_6_instalaciones_amenidades")),
                    "q2_6a_entrada_salida": item.get("q2_6a_entrada_salida") or "",
                    "q2_6b_agencia_limpia": item.get("q2_6b_agencia_limpia") or "",
                    "q2_6c_sala_espera": item.get("q2_6c_sala_espera") or "",
                    "q2_6d_amenidades": item.get("q2_6d_amenidades") or "",
                    "q3_recomendacion": numero_seguro(item.get("q3_recomendacion")),
                    "q4_comentarios_servicio": item.get("q4_comentarios_servicio") or "",
                    "p1_satisfaccion_producto": numero_seguro(item.get("p1_satisfaccion_producto")),
                    "p1_1_comentarios_auto": item.get("p1_1_comentarios_auto") or "",
                    "ot1_autoriza_compartir_datos": item.get("ot1_autoriza_compartir_datos") or "",
                    "q9_autoriza_seguimiento": item.get("q9_autoriza_seguimiento") or "",
                    "q9a_autoriza_transferencia": item.get("q9a_autoriza_transferencia") or "",
                    "q10_autoriza_publicacion": item.get("q10_autoriza_publicacion") or "",
                    "indice_satisfaccion_general": item.get("indice_satisfaccion_general"),
                    "fecha_carga": fecha_iso(item.get("fecha_carga")),
                }
            )

        return Response(data)

    @action(detail=False, methods=["get"], url_path="opciones")
    def opciones(self, request):
        limite = 30000

        qs = (
            EncuestaJDPowerServicio.objects.using(DB_ALIAS)
            .all()
            .values(
                "periodo",
                "tipo",
                "tipo_servicio",
                "canal_envio",
                "estatus",
                "concesionaria",
                "codigo_concesionaria",
                "id_asesor",
                "modelo",
                "anio_vehiculo",
                "region",
                "zona",
                "estado",
            )[:limite]
        )

        anios = set()
        anio_mes_set = set()
        tipos = set()
        tipos_servicio = set()
        canales = set()
        estatuses = set()
        concesionarias = set()
        codigos_concesionaria = set()
        asesores = set()
        modelos = set()
        anios_vehiculo = set()
        regiones = set()
        zonas = set()
        estados = set()

        for item in qs:
            periodo = item.get("periodo")

            if periodo:
                anios.add(periodo.year)
                anio_mes_set.add((periodo.year, periodo.month))

            valores = {
                "tipo": tipos,
                "tipo_servicio": tipos_servicio,
                "canal_envio": canales,
                "estatus": estatuses,
                "concesionaria": concesionarias,
                "codigo_concesionaria": codigos_concesionaria,
                "id_asesor": asesores,
                "modelo": modelos,
                "region": regiones,
                "zona": zonas,
                "estado": estados,
            }

            for campo, destino in valores.items():
                valor = str(item.get(campo) or "").strip()
                if valor:
                    destino.add(valor)

            if item.get("anio_vehiculo"):
                anios_vehiculo.add(item["anio_vehiculo"])

        anio_mes = [
            {"anio": anio, "mes": mes}
            for anio, mes in sorted(
                anio_mes_set,
                key=lambda valor: (valor[0], valor[1]),
                reverse=True,
            )
        ]

        meses_por_anio = {}

        for item in anio_mes:
            anio = str(item["anio"])
            if anio not in meses_por_anio:
                meses_por_anio[anio] = []
            meses_por_anio[anio].append(item["mes"])

        for anio in meses_por_anio:
            meses_por_anio[anio] = sorted(list(set(meses_por_anio[anio])))

        return Response(
            {
                "anios": sorted(list(anios), reverse=True),
                "anio_mes": anio_mes,
                "meses_por_anio": meses_por_anio,
                "tipos": sorted(tipos, key=lambda texto: texto.lower()),
                "tipos_servicio": sorted(tipos_servicio, key=lambda texto: texto.lower()),
                "canales_envio": sorted(canales, key=lambda texto: texto.lower()),
                "estatuses": sorted(estatuses, key=lambda texto: texto.lower()),
                "concesionarias": sorted(concesionarias, key=lambda texto: texto.lower()),
                "codigos_concesionaria": sorted(codigos_concesionaria, key=lambda texto: texto.lower()),
                "asesores": sorted(asesores, key=lambda texto: texto.lower()),
                "modelos": sorted(modelos, key=lambda texto: texto.lower()),
                "anios_vehiculo": sorted(list(anios_vehiculo), reverse=True),
                "regiones": sorted(regiones, key=lambda texto: texto.lower()),
                "zonas": sorted(zonas, key=lambda texto: texto.lower()),
                "estados": sorted(estados, key=lambda texto: texto.lower()),
            }
        )

    @action(detail=False, methods=["post"], url_path="resumen-ia")
    def resumen_ia(self, request):
        anio = request.query_params.get("anio", "Todos")
        mes = request.query_params.get("mes", "Todos")

        campos = (
            "codigo_concesionaria",
            "concesionaria",
            "q1_satisfaccion_general",
            "q3_recomendacion",
            "q1_1_razones_calificacion",
            "q4_comentarios_servicio",
            "p1_1_comentarios_auto",
        )

        qs_actual = self.aplicar_filtros(
            EncuestaJDPowerServicio.objects.using(DB_ALIAS).all()
        )
        datos_actual = list(qs_actual.values(*campos)[:10000])

        anio_ant, mes_ant = _calcular_periodo_anterior(anio, mes)

        datos_anterior = []
        if anio_ant is not None:
            qs_anterior = _queryset_periodo(
                EncuestaJDPowerServicio, DB_ALIAS, anio_ant, mes_ant
            )
            datos_anterior = list(qs_anterior.values(*campos)[:10000])

        campo_sat = "q1_satisfaccion_general"
        campo_rec = "q3_recomendacion"

        metricas_actual = calcular_metricas(datos_actual, campo_sat, campo_rec)
        metricas_anterior = (
            calcular_metricas(datos_anterior, campo_sat, campo_rec)
            if datos_anterior
            else None
        )

        comparacion = {
            "periodo_actual": _label_periodo(anio, mes),
            "periodo_anterior": _label_periodo(anio_ant, mes_ant) if anio_ant else "N/A",
            "satisfaccion_actual": metricas_actual["satisfaccion_promedio"],
            "satisfaccion_anterior": metricas_anterior["satisfaccion_promedio"] if metricas_anterior else None,
            "nps_actual": metricas_actual["nps"],
            "nps_anterior": metricas_anterior["nps"] if metricas_anterior else None,
        }

        if metricas_anterior:
            comparacion["variacion_satisfaccion"] = round(
                metricas_actual["satisfaccion_promedio"] - metricas_anterior["satisfaccion_promedio"], 2
            )
            comparacion["variacion_nps"] = metricas_actual["nps"] - metricas_anterior["nps"]

        alertas = []
        if datos_anterior:
            por_conc_actual = calcular_por_concesionaria(datos_actual, campo_sat, campo_rec)
            por_conc_anterior = calcular_por_concesionaria(datos_anterior, campo_sat, campo_rec)
            alertas = calcular_alertas(por_conc_actual, por_conc_anterior)

        comentarios = extraer_comentarios(
            datos_actual,
            {
                "q1_1_razones_calificacion": "Razón de calificación",
                "q4_comentarios_servicio": "Comentario de servicio",
                "p1_1_comentarios_auto": "Comentario sobre el auto",
            },
            campo_sat,
        )

        resultado_ia = generar_resumen_ia(
            tipo_modulo="Servicio",
            metricas=metricas_actual,
            comparacion=comparacion,
            alertas=alertas,
            comentarios=comentarios,
        )

        return Response(
            {
                "ok": resultado_ia.get("ok", False),
                "error": resultado_ia.get("error"),
                "periodo_label": _label_periodo(anio, mes),
                "metricas": metricas_actual,
                "comparacion": comparacion,
                "alertas_concesionarias": alertas,
                "resumen_ejecutivo": resultado_ia.get("resumen_ejecutivo", ""),
                "tendencia": resultado_ia.get("tendencia", ""),
                "top_quejas": resultado_ia.get("top_quejas", []),
                "fortalezas": resultado_ia.get("fortalezas", []),
                "recomendaciones": resultado_ia.get("recomendaciones", []),
            }
        )