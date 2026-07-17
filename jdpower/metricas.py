# jdpower/metricas.py

def normalizar_escala_5(valor):
    if not valor:
        return 0
    valor = float(valor)
    return (valor / 10 * 5) if valor > 5 else valor


def calcular_metricas(datos, campo_satisfaccion, campo_recomendacion):
    completadas = [d for d in datos if d.get(campo_satisfaccion)]
    total = len(datos)
    n_completadas = len(completadas)

    valores_sat = [
        normalizar_escala_5(d[campo_satisfaccion])
        for d in completadas
        if d.get(campo_satisfaccion)
    ]
    satisfaccion_promedio = (
        round(sum(valores_sat) / len(valores_sat), 2) if valores_sat else 0
    )

    promotores = sum(
        1 for d in completadas if (d.get(campo_recomendacion) or 0) >= 9
    )
    neutrales = sum(
        1 for d in completadas if 7 <= (d.get(campo_recomendacion) or 0) <= 8
    )
    detractores = sum(
        1 for d in completadas if 0 < (d.get(campo_recomendacion) or 0) <= 6
    )
    total_nps = promotores + neutrales + detractores
    nps = round(((promotores - detractores) / total_nps) * 100) if total_nps else 0

    return {
        "total_encuestas": total,
        "completadas": n_completadas,
        "satisfaccion_promedio": satisfaccion_promedio,
        "nps": nps,
        "promotores": promotores,
        "neutrales": neutrales,
        "detractores": detractores,
    }


def calcular_por_concesionaria(datos, campo_satisfaccion, campo_recomendacion):
    grupos = {}

    for d in datos:
        clave = d.get("codigo_concesionaria") or d.get("concesionaria") or "Sin dato"

        if clave not in grupos:
            grupos[clave] = {
                "concesionaria": d.get("concesionaria") or clave,
                "datos": [],
            }

        grupos[clave]["datos"].append(d)

    resultado = {}

    for clave, info in grupos.items():
        m = calcular_metricas(info["datos"], campo_satisfaccion, campo_recomendacion)
        resultado[clave] = {"concesionaria": info["concesionaria"], **m}

    return resultado


def calcular_alertas(
    metricas_actual_por_conc,
    metricas_anterior_por_conc,
    umbral_caida_nps=10,
    umbral_caida_satisfaccion=0.4,
    minimo_encuestas=3,
):
    """
    Marca como alerta cualquier concesionaria cuyo NPS o satisfacción
    hayan caído respecto al periodo anterior por encima del umbral.
    """
    alertas = []

    for clave, actual in metricas_actual_por_conc.items():
        anterior = metricas_anterior_por_conc.get(clave)

        if not anterior or actual["completadas"] < minimo_encuestas:
            continue

        variacion_nps = actual["nps"] - anterior["nps"]
        variacion_sat = round(
            actual["satisfaccion_promedio"] - anterior["satisfaccion_promedio"], 2
        )

        if variacion_nps <= -umbral_caida_nps or variacion_sat <= -umbral_caida_satisfaccion:
            alertas.append(
                {
                    "concesionaria": actual["concesionaria"],
                    "nps_actual": actual["nps"],
                    "nps_anterior": anterior["nps"],
                    "variacion_nps": variacion_nps,
                    "satisfaccion_actual": actual["satisfaccion_promedio"],
                    "satisfaccion_anterior": anterior["satisfaccion_promedio"],
                    "variacion_satisfaccion": variacion_sat,
                    "encuestas_actual": actual["completadas"],
                }
            )

    alertas.sort(key=lambda a: (a["variacion_nps"], a["variacion_satisfaccion"]))
    return alertas


def extraer_comentarios(datos, campos_comentario_map, campo_satisfaccion, limite=150):
    """
    campos_comentario_map: {"nombre_campo_bd": "Etiqueta legible"}
    Prioriza (ordena primero) los comentarios de calificaciones más bajas,
    para que la IA analice primero las quejas.
    """
    comentarios = []

    for d in datos:
        calif = normalizar_escala_5(d.get(campo_satisfaccion) or 0)

        for campo, etiqueta in campos_comentario_map.items():
            texto = (d.get(campo) or "").strip()

            if texto:
                comentarios.append(
                    {
                        "origen": etiqueta,
                        "calificacion": calif,
                        "texto": texto[:300],
                    }
                )

    comentarios.sort(key=lambda c: c["calificacion"])
    return comentarios[:limite]