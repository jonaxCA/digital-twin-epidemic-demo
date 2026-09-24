"""Modelo SEIR-HDV estocastico por cadena binomial, en pasos de un dia.

Compartimentos por grupo de edad:
    S susceptibles, E expuestos, I infecciosos, R recuperados,
    H hospitalizados, D fallecidos, V vacunados protegidos.

Transiciones de cada dia t = 1..dias (el dia 0 es el estado inicial):

    S -> E   con probabilidad 1 - exp(-lambda),
             lambda = beta * contactos(t) * aislamiento(t) * I / vivos,
             beta = R0 / infeccioso_dias
    E -> I   con probabilidad 1 - exp(-1 / incubacion_dias)
    I -> sale con probabilidad 1 - exp(-1 / infeccioso_dias), y se reparte en
             H con tasa_hospitalizacion,
             D directo con max(0, letalidad - tasa_hospitalizacion),
             R el resto
    H -> sale con probabilidad 1 - exp(-1 / dias_hospitalizacion), y muere con
             min(letalidad, tasa_hospitalizacion) / tasa_hospitalizacion
    S -> V   por vacunacion, con eficacia parcial

Asi la letalidad acumulada de un grupo tiende a su 'letalidad' (IFR) y la
fraccion hospitalizada a su 'tasa_hospitalizacion' (IHR).

Simplificaciones declaradas (van en la salida como 'simplificaciones'):
- Mezcla homogenea entre grupos de edad: todos comparten la misma fuerza de
  infeccion. La edad solo cambia hospitalizacion, letalidad y vacunacion.
- Duraciones con distribucion geometrica (tiempo discreto); de la distribucion
  capturada solo se usa la media.
- Los hospitalizados no transmiten.
- La vacuna se aplica sin conocer el estado inmunologico: las dosis caen sobre
  vivos no hospitalizados, y solo las que llegan a susceptibles protegen.
- Las intervenciones sobre capas multiplican los contactos de esa capa por
  (1 - reduccion * cobertura * cumplimiento).
"""

import hashlib
import json
import math

import numpy as np

from .indicadores import resumir
from .parametros import resolver

ENGINE_VERSION = "python-ref-0.1"

AVISO_SIMULACION = (
    "Los resultados representan escenarios simulados basados en parametros y "
    "supuestos. No constituyen una prediccion epidemiologica ni una "
    "recomendacion sanitaria."
)

SIMPLIFICACIONES = [
    "Mezcla homogenea entre grupos de edad; la edad solo modifica hospitalizacion, "
    "letalidad y vacunacion.",
    "Duraciones geometricas en pasos de un dia; solo se usa la media de cada distribucion.",
    "Los hospitalizados no transmiten.",
    "La vacuna se aplica sin conocer el estado inmunologico de la persona.",
    "Las intervenciones sobre una capa reducen sus contactos en "
    "reduccion x cobertura x cumplimiento.",
]


class ErrorMotor(RuntimeError):
    """Fallo interno durante la corrida (no un escenario invalido)."""


def huella_escenario(escenario):
    """SHA-256 de la entrada canonica: identifica exactamente que se simulo."""
    canonico = json.dumps(escenario, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":"), default=str)
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def _activa(iv, dia):
    return iv["dia_inicio"] <= dia and (iv["dia_fin"] is None or dia <= iv["dia_fin"])


def _multiplicador_contactos(capas, activas):
    total = 0.0
    for capa, peso in capas.items():
        factor = 1.0
        for iv in activas:
            if iv["clase"] == "capa" and iv["capa"] in (capa, "todas"):
                factor *= 1.0 - iv["efecto"]
        total += peso * factor
    return total


def _factor_aislamiento(activas):
    factor = 1.0
    for iv in activas:
        if iv["clase"] == "aislamiento":
            factor *= 1.0 - iv["efecto"]
    return factor


def simular(escenario, semilla):
    """Corre el escenario y regresa serie diaria, resumen y trazabilidad.

    Levanta EscenarioInvalido si la entrada no es simulable y ErrorMotor si algo
    falla durante la corrida. La salida es serializable a JSON.
    """
    if isinstance(semilla, bool) or not isinstance(semilla, int) or semilla < 0:
        raise ValueError("La semilla debe ser un entero >= 0.")

    p = resolver(escenario)
    rng = np.random.default_rng(semilla)

    pob = np.array(p["poblacion"], dtype=np.int64)
    N = int(p["N"])
    ihr = np.array(p["tasa_hospitalizacion"])
    ifr = np.array(p["letalidad"])

    beta = p["r0"] / p["infeccioso_dias"]
    p_ei = -math.expm1(-1.0 / p["incubacion_dias"])
    p_sale_i = -math.expm1(-1.0 / p["infeccioso_dias"])
    p_sale_h = -math.expm1(-1.0 / p["dias_hospitalizacion"])

    # Reparto de quien sale de I: [a H, muerte directa, recupera].
    muerte_directa = np.maximum(0.0, ifr - ihr)
    reparto_i = np.column_stack([ihr, muerte_directa, 1.0 - ihr - muerte_directa])
    reparto_i = np.clip(reparto_i, 0.0, 1.0)
    reparto_i /= reparto_i.sum(axis=1, keepdims=True)
    muerte_en_h = np.divide(np.minimum(ifr, ihr), ihr, out=np.zeros_like(ihr), where=ihr > 0)

    S = pob.copy()
    E = np.zeros_like(pob)
    I = np.zeros_like(pob)
    R = np.zeros_like(pob)
    H = np.zeros_like(pob)
    D = np.zeros_like(pob)
    V = np.zeros_like(pob)
    vacunados = np.zeros_like(pob)  # dosis aplicadas por grupo, protejan o no
    casos_grupo = np.zeros_like(pob)

    # Los infectados iniciales se reparten sin reemplazo segun el peso de cada grupo.
    I0 = rng.multivariate_hypergeometric(pob, p["infectados_iniciales"])
    S -= I0
    I += I0
    casos_grupo += I0

    def fila(dia, nuevos_casos=0, nuevas_hosp=0, nuevas_def=0, dosis=0):
        return {
            "dia": dia,
            "S": int(S.sum()), "E": int(E.sum()), "I": int(I.sum()), "R": int(R.sum()),
            "H": int(H.sum()), "D": int(D.sum()), "V": int(V.sum()),
            "casos_activos": int(E.sum() + I.sum() + H.sum()),
            "nuevos_casos": int(nuevos_casos),
            "nuevas_hospitalizaciones": int(nuevas_hosp),
            "nuevas_defunciones": int(nuevas_def),
            "dosis_aplicadas": int(dosis),
        }

    serie = [fila(0)]
    vacunaciones = [iv for iv in p["intervenciones"] if iv["clase"] == "vacunacion"]

    for dia in range(1, p["dias"] + 1):
        activas = [iv for iv in p["intervenciones"] if _activa(iv, dia)]

        vivos = N - int(D.sum())
        contactos = _multiplicador_contactos(p["capas_contacto"], activas)
        lam = beta * contactos * _factor_aislamiento(activas) * I.sum() / vivos
        p_infeccion = -math.expm1(-lam)

        # El orden de los sorteos es parte del contrato de reproducibilidad:
        # cambiarlo obliga a subir ENGINE_VERSION.
        nuevos_e = rng.binomial(S, p_infeccion)
        nuevos_i = rng.binomial(E, p_ei)
        salen_i = rng.binomial(I, p_sale_i)
        destino_i = rng.multinomial(salen_i, reparto_i)  # columnas: H, D, R
        salen_h = rng.binomial(H, p_sale_h)
        mueren_h = rng.binomial(salen_h, muerte_en_h)

        S -= nuevos_e
        E += nuevos_e - nuevos_i
        I += nuevos_i - salen_i
        H += destino_i[:, 0] - salen_h
        D += destino_i[:, 1] + mueren_h
        R += destino_i[:, 2] + (salen_h - mueren_h)
        casos_grupo += nuevos_e

        dosis_dia = 0
        for iv in vacunaciones:
            if not _activa(iv, dia):
                continue
            objetivo = np.zeros(len(pob), dtype=bool)
            objetivo[iv["grupos_objetivo"]] = True
            tope = np.floor(iv["tope"] * pob).astype(np.int64) - vacunados
            disponibles = pob - D - H - vacunados
            cupo = np.where(objetivo, np.clip(np.minimum(tope, disponibles), 0, None), 0)
            a_repartir = min(iv["dosis_diarias"], int(cupo.sum()))
            if a_repartir == 0:
                continue

            if iv["prioridad"] == "edad_desc":
                dosis = np.zeros_like(pob)
                restante = a_repartir
                for g in sorted(range(len(pob)), key=lambda g: -p["edad_minima_grupo"][g]):
                    dosis[g] = min(restante, cupo[g])
                    restante -= dosis[g]
            else:
                dosis = rng.multivariate_hypergeometric(cupo, a_repartir)

            vivos_no_h = pob - D - H
            en_s = np.array([
                rng.hypergeometric(int(S[g]), int(vivos_no_h[g] - S[g]), int(dosis[g]))
                if dosis[g] > 0 else 0
                for g in range(len(pob))
            ], dtype=np.int64)
            protegidos = rng.binomial(en_s, iv["eficacia"])
            S -= protegidos
            V += protegidos
            vacunados += dosis
            dosis_dia += int(dosis.sum())

        if not np.array_equal(S + E + I + R + H + D + V, pob) or (S < 0).any():
            raise ErrorMotor(f"Se rompio la conservacion de la poblacion en el dia {dia}.")

        serie.append(fila(dia, nuevos_e.sum(), destino_i[:, 0].sum(),
                          destino_i[:, 1].sum() + mueren_h.sum(), dosis_dia))

    desglose = [
        {"grupo": g, "poblacion": int(pob[i]), "casos": int(casos_grupo[i]),
         "fallecimientos": int(D[i]), "vacunados_protegidos": int(V[i]),
         "dosis_aplicadas": int(vacunados[i])}
        for i, g in enumerate(p["grupos"])
    ]

    return {
        "engine_version": ENGINE_VERSION,
        "semilla": semilla,
        "numpy_version": np.__version__,
        "huella_escenario": huella_escenario(escenario),
        "dias": p["dias"],
        "poblacion": N,
        "serie": serie,
        "resumen": resumir(serie, N, p["infectados_iniciales"], desglose),
        "trazabilidad_parametros": p["trazabilidad"],
        "simplificaciones": SIMPLIFICACIONES,
        "avisos": p["avisos"],
    }
