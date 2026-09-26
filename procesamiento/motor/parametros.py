"""Validacion y resolucion de la entrada del motor.

Regla del proyecto: el motor NO trae valores epidemiologicos por defecto. Si
falta R0, una duracion o una tasa, el escenario es invalido. La unica excepcion
declarada es el reparto de contactos por capa (CAPAS_CONTACTO_SUPUESTO), y la
salida lo reporta siempre como supuesto para que nunca pase por dato oficial.

Formato de entrada (nombres alineados con scenario_versions,
scenario_interventions, diseases e intervention_types):

    {
      "poblacion": 500000                          # o por grupo de edad:
                   | {"0-19": 150000, "20-59": 280000, "60+": 70000},
      "infectados_iniciales": 100,
      "dias": 120,                                 # scenario_versions.horizon_days
      "enfermedad": {                              # diseases.default_params
        "r0": 1.3,
        "incubacion_dias": 2.0,
        "infeccioso_dias": 5.0,
        "dias_hospitalizacion": 5.0,
        "tasa_hospitalizacion": 0.01 | {"0-19": ..., "60+": ...},
        "letalidad": 0.001          | {"0-19": ..., "60+": ...}
      },
      "intervenciones": [                          # scenario_interventions
        {"tipo": "CIERRE_ESCUELAS",                # intervention_types.code
         "dia_inicio": 7, "dia_fin": 45,           # start_day, end_day
         "cobertura": 1.0, "cumplimiento": 0.9,    # coverage, compliance
         "params": {"reduccion": 1.0}}             # params
      ],
      "capas_contacto": {...}                      # opcional
    }

Cada parametro de la enfermedad puede ir como numero o con trazabilidad:
{"valor": 1.3, "fuente": "Biggerstaff et al., 2014", "supuesto": false}.
"""

import math
import re

# Que hacer con la gente que el censo cuenta pero sin edad declarada. No hay
# valor por defecto a proposito: repartirla calladamente convertiria un dato
# observado en una imputacion, y excluirla calladamente cambiaria la poblacion
# simulada sin que nadie se entere. El escenario tiene que elegir.
POLITICAS_EDAD_DESCONOCIDA = {
    "excluir": "No se simula; la corrida cubre solo a la poblacion con edad conocida.",
    "prorratear": "Se reparte entre los grupos en proporcion a su tamanio. Es una "
                  "imputacion: queda registrada como supuesto en la trazabilidad.",
}

# Fraccion de los contactos que ocurre en cada capa. Orden de magnitud inspirado
# en estudios de matrices de contacto tipo POLYMOD; NO esta calibrado para
# Nuevo Leon. Solo importa cuando hay intervenciones que actuan sobre una capa.
CAPAS_CONTACTO_SUPUESTO = {
    "hogar": 0.35,
    "escuela": 0.15,
    "trabajo": 0.20,
    "comunidad": 0.30,
}

# Limites alineados con los CHECK de scenario_versions.
POBLACION_MIN, POBLACION_MAX = 1000, 5_000_000
DIAS_MIN, DIAS_MAX = 1, 1095

# Tipo de intervencion -> capa sobre la que actua y parametro que da su fuerza.
INTERVENCIONES_CAPA = {
    "CIERRE_ESCUELAS": ("escuela", "reduccion", 1.0),
    "REDUCCION_AFORO": ("comunidad", "reduccion", None),
    "CUBREBOCAS": ("todas", "eficacia", None),
    "CIERRE_TRABAJO": ("trabajo", "reduccion", 1.0),
}
TIPOS_VALIDOS = set(INTERVENCIONES_CAPA) | {"VACUNACION", "TESTEO_AISLAMIENTO"}
PRIORIDADES_SOPORTADAS = {"edad_desc", "aleatorio"}

RE_GRUPO_EDAD = re.compile(r"^(\d{1,3})(?:-(\d{1,3})|\+)$")


class EscenarioInvalido(ValueError):
    """El escenario no se puede simular. `errores` trae un mensaje por problema."""

    def __init__(self, errores):
        self.errores = list(errores)
        super().__init__("; ".join(self.errores))


def _es_numero(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _desempaca(crudo):
    """Separa valor, fuente y marca de supuesto.

    Acepta el numero directo, el formato con trazabilidad y el formato de
    distribucion de 010_datos_iniciales ({"dist": ..., "media": ...}), del que
    este motor determinista en duraciones solo usa la media.
    """
    if isinstance(crudo, dict) and "valor" in crudo:
        return crudo["valor"], crudo.get("fuente"), bool(crudo.get("supuesto", False))
    if isinstance(crudo, dict) and "media" in crudo:
        return crudo["media"], None, False
    return crudo, None, False


def _estado_traza(fuente, supuesto):
    if supuesto:
        return "supuesto"
    return "con_fuente" if fuente else "sin_fuente"


def _limite_inferior_edad(grupo):
    m = RE_GRUPO_EDAD.match(grupo)
    return int(m.group(1)) if m else None


def validar_escenario(escenario):
    """Regresa la lista de errores (vacia si el escenario es simulable)."""
    try:
        resolver(escenario)
    except EscenarioInvalido as e:
        return e.errores
    return []


def resolver(escenario):
    """Valida el escenario y lo convierte a la forma interna del modelo.

    Levanta EscenarioInvalido con TODOS los errores encontrados, no solo el
    primero, para que la pantalla de validacion los muestre juntos.
    """
    errores, avisos, traza = [], [], []

    if not isinstance(escenario, dict):
        raise EscenarioInvalido(["El escenario debe ser un objeto."])

    # --- Poblacion y grupos -------------------------------------------------
    crudo_pob = escenario.get("poblacion")
    grupos, pob = [], []
    if _es_numero(crudo_pob) and float(crudo_pob).is_integer():
        grupos, pob = ["total"], [int(crudo_pob)]
    elif isinstance(crudo_pob, dict) and crudo_pob:
        for nombre, n in crudo_pob.items():
            if not (_es_numero(n) and float(n).is_integer() and n >= 0):
                errores.append(f"Poblacion del grupo '{nombre}' debe ser un entero >= 0.")
            elif _limite_inferior_edad(nombre) is None:
                errores.append(f"Grupo de edad '{nombre}' no tiene formato 'min-max' o 'min+'.")
            else:
                grupos.append(nombre)
                pob.append(int(n))
        orden = sorted(range(len(grupos)), key=lambda i: _limite_inferior_edad(grupos[i]))
        grupos = [grupos[i] for i in orden]
        pob = [pob[i] for i in orden]
    else:
        errores.append("Falta 'poblacion' (entero o diccionario por grupo de edad).")

    por_edad = grupos != ["total"]

    # --- Poblacion sin edad declarada ----------------------------------------
    # El censo cuenta a quien no declaro su edad, pero no lo pone en ninguna
    # banda (18,132 personas en Nuevo Leon). Si el escenario la trae, hay que
    # decir que se hace con ella; el motor no elige por su cuenta.
    sin_edad = escenario.get("poblacion_edad_desconocida", 0)
    politica = escenario.get("politica_edad_desconocida")
    if not (_es_numero(sin_edad) and float(sin_edad).is_integer() and sin_edad >= 0):
        errores.append("'poblacion_edad_desconocida' debe ser un entero >= 0.")
        sin_edad = 0
    sin_edad = int(sin_edad)

    if sin_edad and not por_edad:
        errores.append("'poblacion_edad_desconocida' solo tiene sentido con la poblacion "
                       "abierta por grupos de edad; sin grupos, sumala a 'poblacion'.")
    elif sin_edad:
        if politica not in POLITICAS_EDAD_DESCONOCIDA:
            errores.append(
                f"{sin_edad:,} personas sin edad declarada: elige "
                f"'politica_edad_desconocida' entre "
                + " o ".join(f"'{k}'" for k in POLITICAS_EDAD_DESCONOCIDA) + ".")
        elif politica == "prorratear":
            total_con_edad = sum(pob)
            if total_con_edad <= 0:
                errores.append("No se puede prorratear la edad desconocida sin poblacion "
                               "en los grupos.")
            else:
                # Reparto proporcional; el sobrante por redondeo va al grupo mayor,
                # para que el total cuadre exacto.
                reparto = [sin_edad * n // total_con_edad for n in pob]
                reparto[pob.index(max(pob))] += sin_edad - sum(reparto)
                pob = [n + extra for n, extra in zip(pob, reparto)]
                traza.append({
                    "parametro": "poblacion_edad_desconocida",
                    "valor": {"personas": sin_edad, "politica": politica,
                              "reparto": dict(zip(grupos, reparto))},
                    "fuente": None, "estado": "supuesto"})
                avisos.append(
                    f"{sin_edad:,} personas sin edad declarada se repartieron entre los "
                    f"grupos en proporcion a su tamanio: es una imputacion, no dato censal.")
        else:
            traza.append({
                "parametro": "poblacion_edad_desconocida",
                "valor": {"personas": sin_edad, "politica": politica},
                "fuente": None, "estado": "supuesto"})
            avisos.append(
                f"{sin_edad:,} personas sin edad declarada quedan fuera de la simulacion; "
                f"los resultados cubren a la poblacion con edad conocida.")

    N = sum(pob)
    if pob and not (POBLACION_MIN <= N <= POBLACION_MAX):
        errores.append(f"La poblacion total debe estar entre {POBLACION_MIN:,} y {POBLACION_MAX:,}.")

    dias = escenario.get("dias")
    if not (_es_numero(dias) and float(dias).is_integer() and DIAS_MIN <= dias <= DIAS_MAX):
        errores.append(f"'dias' debe ser un entero entre {DIAS_MIN} y {DIAS_MAX}.")
        dias = None
    else:
        dias = int(dias)

    iniciales = escenario.get("infectados_iniciales")
    if not (_es_numero(iniciales) and float(iniciales).is_integer() and iniciales >= 1):
        errores.append("'infectados_iniciales' debe ser un entero >= 1.")
        iniciales = None
    else:
        iniciales = int(iniciales)
        if pob and iniciales > N:
            errores.append("Los infectados iniciales no pueden superar la poblacion.")

    # --- Enfermedad -----------------------------------------------------------
    enf = escenario.get("enfermedad")
    if not isinstance(enf, dict):
        errores.append("Falta 'enfermedad' con sus parametros.")
        enf = {}

    def escalar_positivo(clave):
        if clave not in enf:
            errores.append(f"Falta el parametro de enfermedad '{clave}'.")
            return None
        valor, fuente, supuesto = _desempaca(enf[clave])
        if not (_es_numero(valor) and valor > 0):
            errores.append(f"'{clave}' debe ser un numero > 0.")
            return None
        traza.append({"parametro": clave, "valor": valor, "fuente": fuente,
                      "estado": _estado_traza(fuente, supuesto)})
        return float(valor)

    def tasa_por_grupo(clave, alias=()):
        """Resuelve una tasa que puede venir global o desglosada por grupo de edad.

        Cuando la poblacion viene estratificada se prefiere la tabla por edad si
        existe; si no, la tasa global. Antes ganaba siempre la clave principal,
        asi que una enfermedad con `letalidad` y `letalidad_por_edad` ignoraba la
        segunda: el dato mas fino quedaba sin efecto, que es justo lo contrario
        de para que se captura. Sin estratificar pasa al reves, porque una tabla
        por edad no se puede aplicar a una poblacion sin grupos.
        """
        candidatos = [(k, _desempaca(enf[k])) for k in (clave, *alias) if k in enf]
        if not candidatos:
            errores.append(f"Falta el parametro de enfermedad '{clave}'.")
            return None
        if por_edad:
            prefiere = lambda v: isinstance(v, dict)
        else:
            prefiere = _es_numero
        presente, (valor, fuente, supuesto) = next(
            (c for c in candidatos if prefiere(c[1][0])), candidatos[0])
        if _es_numero(valor):
            if not 0 <= valor <= 1:
                errores.append(f"'{clave}' debe estar entre 0 y 1.")
                return None
            tasas = [float(valor)] * len(grupos)
        elif isinstance(valor, dict):
            if not por_edad:
                errores.append(f"'{clave}' viene por grupo de edad pero la poblacion no.")
                return None
            faltan = [g for g in grupos if g not in valor]
            if faltan:
                errores.append(f"'{clave}' no define los grupos: {', '.join(faltan)}.")
                return None
            if not all(_es_numero(valor[g]) and 0 <= valor[g] <= 1 for g in grupos):
                errores.append(f"Cada valor de '{clave}' debe estar entre 0 y 1.")
                return None
            tasas = [float(valor[g]) for g in grupos]
        else:
            errores.append(f"'{clave}' debe ser un numero o un diccionario por grupo.")
            return None
        traza.append({"parametro": presente, "valor": valor, "fuente": fuente,
                      "estado": _estado_traza(fuente, supuesto)})
        return tasas

    r0 = escalar_positivo("r0")
    if "r0" not in enf and "transmisibilidad_base" in enf:
        errores.append("'transmisibilidad_base' es una probabilidad por contacto del modelo "
                       "de agentes y no se convierte a R0; captura 'r0' con su fuente.")
    incubacion = escalar_positivo("incubacion_dias")
    infeccioso = escalar_positivo("infeccioso_dias")
    dias_hosp = escalar_positivo("dias_hospitalizacion")
    ihr = tasa_por_grupo("tasa_hospitalizacion")
    ifr = tasa_por_grupo("letalidad", alias=("letalidad_por_edad",))

    # --- Capas de contacto ----------------------------------------------------
    capas = escenario.get("capas_contacto")
    if capas is None:
        capas = dict(CAPAS_CONTACTO_SUPUESTO)
        traza.append({"parametro": "capas_contacto", "valor": capas, "fuente": None,
                      "estado": "supuesto"})
    elif not (isinstance(capas, dict) and capas
              and all(_es_numero(v) and v >= 0 for v in capas.values())
              and abs(sum(capas.values()) - 1.0) < 1e-6):
        errores.append("'capas_contacto' debe asignar pesos >= 0 que sumen 1.")
        capas = {}
    else:
        capas = {k: float(v) for k, v in capas.items()}
        traza.append({"parametro": "capas_contacto", "valor": capas, "fuente": None,
                      "estado": "definido_en_escenario"})

    # --- Intervenciones -------------------------------------------------------
    intervenciones = []
    for i, iv in enumerate(escenario.get("intervenciones") or [], start=1):
        pref = f"Intervencion {i}"
        if not isinstance(iv, dict):
            errores.append(f"{pref}: debe ser un objeto.")
            continue
        tipo = iv.get("tipo")
        if tipo not in TIPOS_VALIDOS:
            errores.append(f"{pref}: tipo '{tipo}' no soportado por el motor.")
            continue
        pref = f"{pref} ({tipo})"

        inicio, fin = iv.get("dia_inicio"), iv.get("dia_fin")
        if not (_es_numero(inicio) and float(inicio).is_integer() and inicio >= 0):
            errores.append(f"{pref}: 'dia_inicio' debe ser un entero >= 0.")
            continue
        if fin is not None and not (_es_numero(fin) and float(fin).is_integer() and fin >= inicio):
            errores.append(f"{pref}: 'dia_fin' debe ser un entero >= dia_inicio.")
            continue
        if dias is not None and inicio > dias:
            avisos.append(f"{pref}: empieza el dia {inicio}, despues del horizonte; no tiene efecto.")

        factores = {}
        for clave in ("cobertura", "cumplimiento"):
            v = iv.get(clave)
            if v is None:
                factores[clave] = 1.0
            elif _es_numero(v) and 0 <= v <= 1:
                factores[clave] = float(v)
            else:
                errores.append(f"{pref}: '{clave}' debe estar entre 0 y 1.")
                factores[clave] = None
        if None in factores.values():
            continue

        params = iv.get("params") or {}
        base = {"tipo": tipo, "dia_inicio": int(inicio),
                "dia_fin": None if fin is None else int(fin)}

        if tipo in INTERVENCIONES_CAPA:
            capa, clave, defecto = INTERVENCIONES_CAPA[tipo]
            fuerza = params.get(clave, defecto)
            if not (_es_numero(fuerza) and 0 <= fuerza <= 1):
                errores.append(f"{pref}: '{clave}' es obligatorio y debe estar entre 0 y 1.")
                continue
            if capa != "todas" and capa not in capas:
                errores.append(f"{pref}: la capa '{capa}' no existe en 'capas_contacto'.")
                continue
            if tipo == "CIERRE_TRABAJO" and params.get("sectores"):
                avisos.append(f"{pref}: 'sectores' se ignora; el modelo compartimental no "
                              "distingue sectores y aplica el cierre a toda la capa trabajo.")
            base.update(clase="capa", capa=capa,
                        efecto=fuerza * factores["cobertura"] * factores["cumplimiento"])

        elif tipo == "TESTEO_AISLAMIENTO":
            det, retraso = params.get("deteccion"), params.get("retraso_dias")
            aisl = params.get("dias_aislamiento", 10)
            if not (_es_numero(det) and 0 <= det <= 1):
                errores.append(f"{pref}: 'deteccion' es obligatoria y debe estar entre 0 y 1.")
                continue
            if not (_es_numero(retraso) and retraso >= 0):
                errores.append(f"{pref}: 'retraso_dias' es obligatorio y debe ser >= 0.")
                continue
            if not (_es_numero(aisl) and aisl >= 1):
                errores.append(f"{pref}: 'dias_aislamiento' debe ser >= 1.")
                continue
            if infeccioso is None:
                continue
            # Fraccion del periodo infeccioso que el detectado pasa aislado. El
            # aislamiento corta contactos fuera del hogar, no dentro.
            ventana = max(0.0, infeccioso - retraso)
            tiempo = min(ventana, aisl) / infeccioso
            fuera_hogar = 1.0 - capas.get("hogar", 0.0)
            base.update(clase="aislamiento",
                        efecto=det * factores["cobertura"] * factores["cumplimiento"]
                        * tiempo * fuera_hogar)

        else:  # VACUNACION
            eficacia, diarias = params.get("eficacia"), params.get("dosis_diarias")
            prioridad = params.get("prioridad", "aleatorio")
            edad_min = params.get("edad_minima")
            if not (_es_numero(eficacia) and 0 <= eficacia <= 1):
                errores.append(f"{pref}: 'eficacia' es obligatoria y debe estar entre 0 y 1.")
                continue
            if not (_es_numero(diarias) and float(diarias).is_integer() and diarias >= 1):
                errores.append(f"{pref}: 'dosis_diarias' es obligatorio y debe ser un entero >= 1.")
                continue
            if prioridad not in PRIORIDADES_SOPORTADAS:
                avisos.append(f"{pref}: prioridad '{prioridad}' no la modela un motor "
                              "compartimental; se aplica como 'aleatorio'.")
                prioridad = "aleatorio"
            if prioridad == "edad_desc" and not por_edad:
                errores.append(f"{pref}: prioridad 'edad_desc' requiere poblacion por grupo de edad.")
                continue
            objetivo = list(range(len(grupos)))
            if edad_min is not None:
                if not (_es_numero(edad_min) and 0 <= edad_min <= 120):
                    errores.append(f"{pref}: 'edad_minima' debe estar entre 0 y 120.")
                    continue
                if not por_edad:
                    errores.append(f"{pref}: 'edad_minima' requiere poblacion por grupo de edad.")
                    continue
                objetivo = [i for i, g in enumerate(grupos) if _limite_inferior_edad(g) >= edad_min]
                if not objetivo:
                    errores.append(f"{pref}: ningun grupo de edad empieza en {edad_min} o mas.")
                    continue
                if not any(_limite_inferior_edad(g) == edad_min for g in grupos):
                    avisos.append(f"{pref}: {edad_min} no coincide con el inicio de un grupo; "
                                  "se vacunan solo los grupos que empiezan en esa edad o despues.")
            base.update(clase="vacunacion", eficacia=float(eficacia), dosis_diarias=int(diarias),
                        prioridad=prioridad, grupos_objetivo=objetivo,
                        tope=factores["cobertura"] * factores["cumplimiento"])

        intervenciones.append(base)

    if errores:
        raise EscenarioInvalido(errores)

    sin_fuente = [t["parametro"] for t in traza if t["estado"] == "sin_fuente"]
    if sin_fuente:
        avisos.append("Parametros sin fuente ni marca de supuesto: " + ", ".join(sin_fuente) + ".")

    return {
        "grupos": grupos,
        "edad_minima_grupo": [_limite_inferior_edad(g) for g in grupos],
        "poblacion": pob,
        "N": N,
        "dias": dias,
        "infectados_iniciales": iniciales,
        "r0": r0,
        "incubacion_dias": incubacion,
        "infeccioso_dias": infeccioso,
        "dias_hospitalizacion": dias_hosp,
        "tasa_hospitalizacion": ihr,
        "letalidad": ifr,
        "capas_contacto": capas,
        "intervenciones": intervenciones,
        "trazabilidad": traza,
        "avisos": avisos,
    }
