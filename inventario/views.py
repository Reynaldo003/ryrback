# inventario/views.py
from collections import Counter, defaultdict
from datetime import date
from hashlib import sha256

from django.core.cache import cache
from django.db import connections
from django.http import JsonResponse
from django.utils import timezone

AGENCIAS = {
    "2923": "Córdoba", "2924": "Orizaba", "1905": "Tuxtepec",
    "2927": "Poza Rica", "2929": "Tuxpan",
}

ESTATUS_STOCK = {
    "V": "Vendido", "E": "Entregadas", "T": "En Tránsito",
    "P": "Programado", "O": "Otro", "X": "Canceladas",
    "D": "Devuelto", "C": "",
}

ESTATUS_EXCLUIDOS = ("V", "O", "C", "D", "P", "T")
MODELOS_COMERCIALES = ("E-CRAFTER", "CRAFTER", "AMAROK", "TRANSPORTER", "CADDY")
RANGOS_ANTIGUEDAD = ("0-30", "31-60", "61-90", "91-120", "+120")
CACHE_SEGUNDOS = 60


def _texto(valor):
    return str(valor or "").strip()


def _agencia_nombre(codigo):
    codigo = _texto(codigo)
    return AGENCIAS.get(codigo, codigo or "Sin agencia")


def _estatus_nombre(codigo):
    codigo = _texto(codigo)
    return ESTATUS_STOCK.get(codigo, codigo or "Sin estatus")


def _modelos_solicitados(request):
    # No permitir listas enormes de modelos que degraden la consulta.
    modelos = request.GET.get("modelos", "")
    return tuple(dict.fromkeys(
        modelo.strip().upper()[:80]
        for modelo in modelos.split(",")[:30]
        if modelo.strip()
    ))


def _parametros_filtros(request, condicion_forzada=None):
    agencia = _texto(request.GET.get("agencia"))
    estatus = _texto(request.GET.get("estatus"))
    condicion = _texto(condicion_forzada or request.GET.get("condicion", "N")).upper()
    if condicion not in ("N", "U"):
        condicion = "N"
    return agencia, estatus, condicion, _modelos_solicitados(request)


def _consultar_base(agencia, estatus, modelos):
    """Lee una sola vez el stock, incluyendo N y U para el gráfico de condición."""
    condiciones = [
        '"DN_Atual" IS NOT NULL',
        '"DN_Atual" <> 0',
        '"NmMarca" = %s',
        '"SitVeiculo" = %s',
        "COALESCE(BTRIM(\"StEstoque\"), '') NOT IN (%s, %s, %s, %s, %s, %s)",
    ]
    parametros = ["VOLKSWAGEN", "L", *ESTATUS_EXCLUIDOS]

    if agencia:
        # DN_Atual es BIGINT en PostgreSQL; comparar como entero facilita usar índices.
        condiciones.append('"DN_Atual" = %s')
        parametros.append(int(agencia) if agencia.isdecimal() else -1)
        if agencia == "2923":
            condiciones.append(
                "NOT (" + " OR ".join(
                    'UPPER(COALESCE("NmFamilia", \'\')) LIKE %s'
                    for _ in MODELOS_COMERCIALES
                ) + ")"
            )
            parametros.extend(f"%{modelo}%" for modelo in MODELOS_COMERCIALES)

    if estatus:
        condiciones.append('BTRIM("StEstoque") = %s')
        parametros.append(estatus)

    if modelos:
        condiciones.append("(" + " OR ".join(
            'UPPER(COALESCE("NmFamilia", \'\')) LIKE %s' for _ in modelos
        ) + ")")
        # LIKE parametrizado: no se concatena SQL proporcionado por el usuario.
        parametros.extend(f"%{modelo.replace('%', r'\%').replace('_', r'\_')}%" for modelo in modelos)

    query = f"""
        SELECT "DN_Atual", "NrChassi", "NmFamilia", "NmMarca",
               "SitVeiculo", "StEstoque", "TpNacImp", "ModalVda",
               "EdiModelo", "CondUso", "DtFaturamento", "VrNF_Compra"
        FROM public.matriz_veiculosestoque
        WHERE {' AND '.join(condiciones)}
    """
    with connections["tdsql"].cursor() as cursor:
        cursor.execute(query, parametros)
        columnas = [columna[0] for columna in cursor.description]
        return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]


def _normalizar_vehiculo(fila, hoy):
    fecha = fila["DtFaturamento"]
    if fecha is not None:
        fecha = fecha.date() if hasattr(fecha, "date") else fecha

    fecha_valida = isinstance(fecha, date) and fecha >= date(1900, 1, 1)
    dias_stock = (hoy - fecha).days if fecha_valida and fecha <= hoy else None
    codigo_agencia = _texto(fila["DN_Atual"])
    codigo_estatus = _texto(fila["StEstoque"])

    return {
        "DN_Atual": codigo_agencia,
        "NrChassi": fila["NrChassi"],
        "NmFamilia": fila["NmFamilia"],
        "NmMarca": fila["NmMarca"],
        "SitVeiculo": fila["SitVeiculo"],
        "StEstoque": codigo_estatus,
        "TpNacImp": _texto(fila["TpNacImp"]),
        "ModalVda": fila["ModalVda"],
        "EdiModelo": fila["EdiModelo"],
        "CondUso": _texto(fila["CondUso"]).upper(),
        "DtFaturamento": fecha.isoformat() if fecha_valida else None,
        "diasEnStock": dias_stock,
        "VrNF_Compra": float(fila["VrNF_Compra"]) if fila["VrNF_Compra"] is not None else None,
        "agenciaNombre": _agencia_nombre(codigo_agencia),
        "estatusNombre": _estatus_nombre(codigo_estatus),
    }


def _rango_antiguedad(dias):
    if dias <= 30:
        return "0-30"
    if dias <= 60:
        return "31-60"
    if dias <= 90:
        return "61-90"
    if dias <= 120:
        return "91-120"
    return "+120"


def _obtener_resumen(request, condicion_forzada=None):
    agencia, estatus, condicion, modelos = _parametros_filtros(request, condicion_forzada)
    clave_filtros = repr((agencia, estatus, condicion, modelos))
    clave_cache = "inventario:pg:v1:" + sha256(clave_filtros.encode()).hexdigest()
    forzar_actualizacion = request.GET.get("actualizar") == "1"
    resultado = None if forzar_actualizacion else cache.get(clave_cache)
    if resultado is not None:
        return resultado

    hoy = timezone.localdate()
    registros = [_normalizar_vehiculo(fila, hoy) for fila in _consultar_base(agencia, estatus, modelos)]
    vehiculos = [fila for fila in registros if fila["CondUso"] == condicion]
    vehiculos.sort(key=lambda v: (v["diasEnStock"] is None, -(v["diasEnStock"] or 0), v["DN_Atual"], v["NrChassi"] or ""))

    agencias = Counter()
    estatuses = Counter()
    marcas = Counter()
    condiciones = Counter()
    origenes = Counter()
    rangos = Counter()
    costo_total = 0.0

    # El gráfico Nuevo/Usado no se restringe por condición (comportamiento original).
    for fila in registros:
        nombre_condicion = {"N": "Nuevo", "U": "Usado"}.get(fila["CondUso"], fila["CondUso"] or "Sin dato")
        condiciones[(fila["DN_Atual"], nombre_condicion)] += 1

    for fila in vehiculos:
        agencias[fila["DN_Atual"]] += 1
        estatuses[fila["StEstoque"]] += 1
        marcas[(fila["NmMarca"] or "", fila["NmFamilia"] or "Sin familia")] += 1
        origenes[fila["TpNacImp"]] += 1
        costo_total += fila["VrNF_Compra"] or 0
        if fila["diasEnStock"] is not None:
            rangos[_rango_antiguedad(fila["diasEnStock"])] += 1

    resultado = {
        "data": vehiculos,
        "porAgencia": [
            {"agencia": codigo, "agenciaNombre": _agencia_nombre(codigo), "total": total}
            for codigo, total in agencias.most_common()
        ],
        "porEstatus": [
            {"estatus": codigo, "estatusNombre": _estatus_nombre(codigo), "total": total}
            for codigo, total in estatuses.most_common()
        ],
        "porMarca": [
            {"marca": marca, "familia": familia, "total": total}
            for (marca, familia), total in marcas.most_common()
        ],
        "nuevoUsado": [
            {"agencia": codigo, "agenciaNombre": _agencia_nombre(codigo), "condicion": nombre, "total": total}
            for (codigo, nombre), total in sorted(condiciones.items())
        ],
        "nacionalImportado": [
            {"tipo": tipo, "tipoNombre": {"N": "Nacional", "I": "Importado"}.get(tipo, tipo or "Sin dato"), "total": total}
            for tipo, total in origenes.most_common()
        ],
        "costoTotal": costo_total,
        "antiguedad": [{"rango": rango, "total": rangos[rango]} for rango in RANGOS_ANTIGUEDAD],
    }
    cache.set(clave_cache, resultado, CACHE_SEGUNDOS)
    return resultado


def get_inventario_dashboard(request):
    return JsonResponse(_obtener_resumen(request))


def get_inventario(request):
    return JsonResponse({"data": _obtener_resumen(request)["data"]})


def get_inventario_usados(request):
    return JsonResponse({"data": _obtener_resumen(request, condicion_forzada="U")["data"]})


def get_inventario_por_agencia(request):
    return JsonResponse({"data": _obtener_resumen(request)["porAgencia"]})


def get_inventario_por_estatus(request):
    return JsonResponse({"data": _obtener_resumen(request)["porEstatus"]})


def get_inventario_por_marca(request):
    return JsonResponse({"data": _obtener_resumen(request)["porMarca"]})


def get_inventario_nuevo_usado(request):
    # Esta ruta histórica no filtra por condición.
    return JsonResponse({"data": _obtener_resumen(request)["nuevoUsado"]})


def get_inventario_nacional_importado(request):
    return JsonResponse({"data": _obtener_resumen(request)["nacionalImportado"]})


def get_inventario_costo(request):
    return JsonResponse({"costo_total": _obtener_resumen(request)["costoTotal"]})


def get_inventario_antiguedad(request):
    return JsonResponse({"data": _obtener_resumen(request)["antiguedad"]})


def get_inventario_filtros(request):
    return JsonResponse({
        "agencias": [{"codigo": codigo, "nombre": nombre} for codigo, nombre in AGENCIAS.items()],
        "estatus": [{"codigo": codigo, "nombre": nombre} for codigo, nombre in ESTATUS_STOCK.items()],
    })
