"""Indicadores resumen de una corrida, calculados a partir de la serie diaria.

Definiciones (para que la pantalla de resultados y el reporte digan lo mismo):

- casos_acumulados: infecciones totales, incluidos los infectados iniciales.
- casos_activos:    infecciones en curso = expuestos + infecciosos + hospitalizados.
- pico_casos_activos / dia_pico: maximo de casos activos y el PRIMER dia en que ocurre.
- tasa_ataque:      casos_acumulados / poblacion.
"""


def _pico(serie, campo):
    fila = max(serie, key=lambda f: f[campo])  # max() conserva el primer maximo
    return fila[campo], fila["dia"]


def resumir(serie, poblacion, infectados_iniciales, desglose):
    ultima = serie[-1]
    acumulados = infectados_iniciales + sum(f["nuevos_casos"] for f in serie)
    pico_activos, dia_pico = _pico(serie, "casos_activos")
    pico_nuevos, dia_pico_nuevos = _pico(serie, "nuevos_casos")
    pico_hosp, dia_pico_hosp = _pico(serie, "H")

    return {
        "casos_acumulados": acumulados,
        "casos_activos_final": ultima["casos_activos"],
        "pico_casos_activos": pico_activos,
        "dia_pico": dia_pico,
        "pico_nuevos_casos": pico_nuevos,
        "dia_pico_nuevos_casos": dia_pico_nuevos,
        "hospitalizaciones": sum(f["nuevas_hospitalizaciones"] for f in serie),
        "pico_hospitalizados": pico_hosp,
        "dia_pico_hospitalizados": dia_pico_hosp,
        "fallecimientos": ultima["D"],
        "tasa_ataque": round(acumulados / poblacion, 6),
        "vacunados_protegidos": ultima["V"],
        "dosis_aplicadas": sum(f["dosis_aplicadas"] for f in serie),
        "desglose_por_grupo": desglose,
    }
