"""Corre los escenarios de ejemplo, los compara y calcula la frontera de Pareto.

    python -m motor                          # semilla 982314, impacto = fallecimientos
    python -m motor --semilla 7
    python -m motor --metrica hospitalizaciones
    python -m motor --json                   # salida completa en JSON

TODOS los numeros de este ejemplo (poblacion, parametros y costos) son SUPUESTOS
ilustrativos para probar el motor. No son datos de Monterrey, ni parametros
validados de influenza, ni costos reales.
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

BASE = {
    "poblacion": {"0-19": 160_000, "20-39": 155_000, "40-59": 120_000,
                  "60-79": 55_000, "80+": 10_000},
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

    print(f"Motor {ENGINE_VERSION} | semilla {args.semilla} | poblacion 500,000 | 120 dias\n")
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
