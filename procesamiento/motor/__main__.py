"""Corre los escenarios de ejemplo, los compara y calcula la frontera de Pareto.

    python -m motor                          # semilla 982314, impacto = fallecimientos
    python -m motor --semilla 7
    python -m motor --metrica hospitalizaciones
    python -m motor --json                   # salida completa en JSON

La distribucion por edad SI es real: la del Censo 2020 de INEGI para Nuevo Leon
(data/censo/nl_estructura_edad_2020.tsv). El tamanio de la poblacion, los
parametros de la enfermedad y los costos son SUPUESTOS ilustrativos para probar
el motor: no son parametros validados de influenza ni costos reales.
"""

import argparse
import json
import sys

from . import AVISO_SIMULACION, ENGINE_VERSION, METRICAS_IMPACTO, comparar, simular

SUP = "Ejemplo del motor, no validado"

INFLUENZA_EJEMPLO = {
    "r0": {"valor": 1.6, "supuesto": True, "fuente": SUP},
    "incubacion_dias": {"valor": 2.0, "supuesto": True, "fuente": SUP},
    "infeccioso_dias": {"valor": 5.0, "supuesto": True, "fuente": SUP},
    "dias_hospitalizacion": {"valor": 5.0, "supuesto": True, "fuente": SUP},
    "tasa_hospitalizacion": {"supuesto": True, "fuente": SUP, "valor": {
        "0-19": 0.002, "20-39": 0.003, "40-59": 0.008, "60-79": 0.03, "80+": 0.08}},
    "letalidad": {"supuesto": True, "fuente": SUP, "valor": {
        "0-19": 0.00001, "20-39": 0.00005, "40-59": 0.0003, "60-79": 0.002, "80+": 0.008}},
}

# Pesos por habitante-dia a intensidad completa, y pesos por dosis.
COSTOS_EJEMPLO = {
    "CIERRE_ESCUELAS": {"valor": 15.0, "supuesto": True, "fuente": SUP},
    "VACUNACION": {"valor": 400.0, "supuesto": True, "fuente": SUP},
}

# Estructura por edad de Nuevo Leon, Censo 2020 de INEGI: los 21 grupos
# quinquenales del tabulado, agrupados en cinco tramos. Excluye "No
# especificado" (18,132 personas). Ver data/censo/nl_estructura_edad_2020.tsv.
ESTRUCTURA_NL_2020 = {
    "0-19": 1_853_344, "20-39": 1_867_264, "40-59": 1_391_652,
    "60-79": 564_795, "80+": 89_255,
}

POBLACION_EJEMPLO = 500_000


def poblacion_por_edad(total=POBLACION_EJEMPLO):
    """Reparte `total` habitantes con la estructura por edad real del estado.

    No se usa el estado completo (5,766,310) porque el esquema limita un
    escenario a 5,000,000 habitantes; lo que se conserva es la proporcion.
    """
    base = sum(ESTRUCTURA_NL_2020.values())
    reparto = {g: round(n * total / base) for g, n in ESTRUCTURA_NL_2020.items()}
    # El redondeo puede desviar unas unidades: se ajustan en el grupo mas grande.
    mayor = max(reparto, key=reparto.get)
    reparto[mayor] += total - sum(reparto.values())
    return reparto


BASE = {
    "poblacion": poblacion_por_edad(),
    "infectados_iniciales": 100,
    "dias": 120,
    "enfermedad": INFLUENZA_EJEMPLO,
}

CIERRE = {"tipo": "CIERRE_ESCUELAS", "dia_inicio": 7, "dia_fin": 45, "params": {"reduccion": 1.0}}
VACUNA = {"tipo": "VACUNACION", "dia_inicio": 30, "cobertura": 0.70,
          "params": {"eficacia": 0.6, "dosis_diarias": 3000,
                     "prioridad": "edad_desc", "edad_minima": 60}}

ESCENARIOS = {
    "A - Sin intervencion": [],
    "B - Cierre escolar": [CIERRE],
    "C - Vacunacion 60+": [VACUNA],
    "D - Cierre + vacuna": [CIERRE, VACUNA],
}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m motor", description=__doc__.splitlines()[0])
    ap.add_argument("--semilla", type=int, default=982314)
    ap.add_argument("--metrica", choices=METRICAS_IMPACTO, default="fallecimientos")
    ap.add_argument("--json", action="store_true", help="imprime la salida completa en JSON")
    args = ap.parse_args(argv)

    entradas = []
    for nombre, ivs in ESCENARIOS.items():
        esc = {**BASE, "intervenciones": ivs}
        entradas.append({"id": nombre[0], "nombre": nombre, "escenario": esc,
                         "resultado": simular(esc, args.semilla)})
    comparacion = comparar(entradas, COSTOS_EJEMPLO, metrica=args.metrica, base="A")

    if args.json:
        json.dump({"corridas": {e["nombre"]: e["resultado"] for e in entradas},
                   "comparacion": comparacion}, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return

    print(f"Motor {ENGINE_VERSION} | semilla {args.semilla} | "
          f"poblacion {sum(BASE['poblacion'].values()):,} con estructura por edad "
          f"del Censo 2020 | {BASE['dias']} dias\n")
    enc = f"{'Escenario':<22}{'Casos acum.':>13}{'Pico activos':>14}{'Dia pico':>10}" \
          f"{'Hospitaliz.':>13}{'Fallecim.':>11}{'Ataque':>9}"
    print(enc)
    print("-" * len(enc))
    for e in entradas:
        s = e["resultado"]["resumen"]
        print(f"{e['nombre']:<22}{s['casos_acumulados']:>13,}{s['pico_casos_activos']:>14,}"
              f"{s['dia_pico']:>10}{s['hospitalizaciones']:>13,}{s['fallecimientos']:>11,}"
              f"{s['tasa_ataque']:>9.1%}")

    print(f"\nTrade-off: costo de intervencion vs {args.metrica} (base: A)\n")
    enc = f"{'Escenario':<22}{'Costo (MXN)':>16}{'Impacto':>10}{'Evitado':>10}" \
          f"{'Costo x evitado':>18}  Frontera"
    print(enc)
    print("-" * len(enc))
    for f in comparacion["filas"]:
        evitado = "" if f["impacto_evitado"] is None else f"{f['impacto_evitado']:,}"
        unidad = "" if f["costo_por_unidad_evitada"] is None else f"{f['costo_por_unidad_evitada']:,.0f}"
        marca = f"dominado por {', '.join(f['dominado_por'])}" if f["dominado"] else "SI"
        print(f"{f['nombre']:<22}{f['costo']:>16,.0f}{f['impacto']:>10,}{evitado:>10}"
              f"{unidad:>18}  {marca}")
    print(f"\nFrontera de Pareto (por costo): {' -> '.join(comparacion['frontera'])}")
    for aviso in comparacion["avisos"]:
        print(f"Aviso: {aviso}")
    print(f"\nTodos los parametros y costos de este ejemplo son SUPUESTOS.\n{AVISO_SIMULACION}")


if __name__ == "__main__":
    main()
