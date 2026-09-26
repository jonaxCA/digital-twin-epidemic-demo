"""
Todas las consultas SQL reales detras de las pantallas. Nada aqui esta
mockeado: cada numero que se ve en el dashboard o en el mapa sale de una
consulta contra PostgreSQL.

Alcance deliberado: Nuevo Leon unicamente (el estado + sus 51 municipios,
cargados por 010_datos_iniciales.sql y nl_municipios_completos.sql). Es una
decision de producto explicita de esta version, no una limitacion tecnica: el
modelo de datos (regions) soporta cualquier estado del pais.

Regla de clasificacion de tendencia (semana actual vs la previa, mismas 7+7
dias que usa el dashboard): es un umbral definido por el equipo, no viene
del documento del proyecto
    >= 50%  de aumento  -> "Critico"
    >= 15%  de aumento  -> "Alerta"
    resto (estable o a la baja) -> "Estable"
"""
import json
import math
import re
import unicodedata
from datetime import date, timedelta

import psycopg2

from .db import execute, get_conn, query

NL_ESTADO_CODE = "19"


def _pct_change(actual, previa):
    if previa == 0:
        return 100.0 if actual > 0 else 0.0
    return round((actual - previa) / previa * 100, 1)


def _clasifica_tendencia(pct):
    if pct >= 50:
        return "Critico"
    if pct >= 15:
        return "Alerta"
    return "Estable"


def get_resumen_indicadores():
    """Las 4 tarjetas del panorama: casos activos, tasa de incidencia,
    zonas en riesgo, simulaciones activas. Todo acotado a Nuevo Leon."""
    casos = query(
        """
        SELECT
            count(*) FILTER (WHERE c.report_date >= current_date - 6) AS actual,
            count(*) FILTER (WHERE c.report_date BETWEEN current_date - 13
                                                       AND current_date - 7) AS previa
        FROM cases c
        JOIN regions r ON r.id = c.region_id
        WHERE r.parent_region_id = (SELECT id FROM regions WHERE code = %s)
          AND c.status IN ('pendiente', 'validado')
        """,
        (NL_ESTADO_CODE,),
        one=True,
    )
    casos_activos = casos["actual"] or 0
    pct_casos = _pct_change(casos["actual"] or 0, casos["previa"] or 0)

    poblacion_nl = query(
        "SELECT population FROM regions WHERE code = %s", (NL_ESTADO_CODE,), one=True
    )["population"]
    # Tasa de incidencia expresada como casos por cada 100,000 habitantes
    # (convencion epidemiologica estandar -- la misma que ya usa el panel del
    # mapa). El mock de Figma la mostraba como "%", pero un state de 5.8M
    # habitantes nunca produce un porcentaje legible; "por 100k hab." si.
    tasa_actual = round((casos["actual"] or 0) / poblacion_nl * 100000, 1) if poblacion_nl else 0
    tasa_previa = round((casos["previa"] or 0) / poblacion_nl * 100000, 1) if poblacion_nl else 0
    pct_tasa = _pct_change(tasa_actual, tasa_previa)

    zonas = query(
        """
        SELECT count(*) AS n FROM (
            SELECT r.id,
                   count(c.*) FILTER (WHERE c.report_date >= current_date - 6)::numeric
                     / r.population * 100000 AS incidencia_100k
            FROM regions r
            LEFT JOIN cases c ON c.region_id = r.id AND c.status IN ('pendiente','validado')
            WHERE r.parent_region_id = (SELECT id FROM regions WHERE code = %s)
            GROUP BY r.id, r.population
        ) t
        WHERE incidencia_100k > 10
        """,
        (NL_ESTADO_CODE,),
        one=True,
    )["n"]

    simulaciones_activas = query(
        "SELECT count(*) AS n FROM simulation_runs WHERE status IN ('encolado','ejecutando')",
        one=True,
    )["n"]

    return {
        "casos_activos": casos_activos,
        "casos_pct": pct_casos,
        "tasa_incidencia": tasa_actual,
        "tasa_pct": pct_tasa,
        "zonas_en_riesgo": zonas,
        "simulaciones_activas": simulaciones_activas,
    }


def get_resumen_situacion(limit=5):
    """Tabla 'Resumen de Situacion': casos activos de la ultima semana por
    enfermedad, con su tendencia clasificada, ordenado por volumen."""
    rows = query(
        """
        SELECT d.name,
               count(*) FILTER (WHERE c.report_date >= current_date - 6) AS actual,
               count(*) FILTER (WHERE c.report_date BETWEEN current_date - 13
                                                          AND current_date - 7) AS previa
        FROM cases c
        JOIN diseases d ON d.id = c.disease_id
        JOIN regions r ON r.id = c.region_id
        WHERE r.parent_region_id = (SELECT id FROM regions WHERE code = %s)
        GROUP BY d.name
        HAVING count(*) FILTER (WHERE c.report_date >= current_date - 6) > 0
        ORDER BY actual DESC
        LIMIT %s
        """,
        (NL_ESTADO_CODE, limit),
    )
    out = []
    for r in rows:
        pct = _pct_change(r["actual"], r["previa"])
        out.append({
            "enfermedad": r["name"],
            "estado": _clasifica_tendencia(pct),
            "incidencia": r["actual"],
        })
    return out


def get_curva_epidemica(dias=30):
    """Serie diaria de casos (todas las enfermedades, todo Nuevo Leon) para
    el grafico de Highcharts 'Monitoreo en Tiempo Real'."""
    rows = query(
        """
        SELECT c.report_date::text AS fecha, count(*) AS total
        FROM cases c
        JOIN regions r ON r.id = c.region_id
        WHERE r.parent_region_id = (SELECT id FROM regions WHERE code = %s)
          AND c.report_date >= current_date - (%s || ' days')::interval
        GROUP BY c.report_date
        ORDER BY c.report_date
        """,
        (NL_ESTADO_CODE, dias - 1),
    )
    return [{"fecha": r["fecha"], "total": r["total"]} for r in rows]


def get_enfermedades_catalogo():
    return query(
        """
        SELECT d.id, d.name FROM diseases d
        JOIN cases c ON c.disease_id = d.id
        JOIN regions r ON r.id = c.region_id
        WHERE r.parent_region_id = (SELECT id FROM regions WHERE code = %s)
        GROUP BY d.id, d.name
        ORDER BY d.name
        """,
        (NL_ESTADO_CODE,),
    )


# ---------------------------------------------------------------------------
# Catalogo de enfermedades (pantalla "Enfermedades")
# ---------------------------------------------------------------------------
# Esta pantalla se queda dentro de lo que modela 004_catalogos.sql: code, name,
# description, default_params, is_active y created_at. El diseno de Figma pedia
# ademas agente, tipo de patogeno y nivel de riesgo; no existen en el esquema y
# se decidio NO agregarlos (ni como columnas ni inventados en Python), asi que
# esas tres columnas no aparecen en la tabla.
_MESES = ("Ene", "Feb", "Mar", "Abr", "May", "Jun",
          "Jul", "Ago", "Sep", "Oct", "Nov", "Dic")


def _fecha_corta(valor):
    """'12 Oct 2026'. Se arma a mano en vez de con strftime porque %b depende
    del locale del sistema y aqui la vista siempre va en espanol."""
    if valor is None:
        return None
    return f"{valor.day:02d} {_MESES[valor.month - 1]} {valor.year}"


def get_enfermedades_stats():
    """Las 4 tarjetas del encabezado. 'Detectadas recientemente' cuenta
    enfermedades con al menos un caso en Nuevo Leon en los ultimos 30 dias --
    es lo unico de esta pantalla que depende de `cases`; el resto es catalogo."""
    cat = query(
        """
        SELECT count(*)                                                     AS registradas,
               count(*) FILTER (WHERE is_active)                            AS activas,
               count(*) FILTER (WHERE NOT is_active)                        AS inactivas,
               count(*) FILTER (WHERE created_at >= now() - interval '30 days') AS altas_30d
        FROM diseases
        """,
        one=True,
    )
    detectadas = query(
        """
        SELECT count(DISTINCT c.disease_id) AS n
        FROM cases c
        JOIN regions r ON r.id = c.region_id
        WHERE r.parent_region_id = (SELECT id FROM regions WHERE code = %s)
          AND c.status IN ('pendiente', 'validado')
          AND c.report_date >= current_date - 29
        """,
        (NL_ESTADO_CODE,),
        one=True,
    )["n"]

    registradas = cat["registradas"]
    return {
        "registradas": registradas,
        "altas_30d": cat["altas_30d"],
        "activas": cat["activas"],
        "activas_pct": round(cat["activas"] / registradas * 100) if registradas else 0,
        "inactivas": cat["inactivas"],
        "detectadas_30d": detectadas,
    }


def get_enfermedades(busqueda=None, estado=None, pagina=1, por_pagina=10):
    """Listado paginado del catalogo con los filtros de la pantalla.

    Los conteos de casos van acotados a Nuevo Leon, igual que el resto de la
    app. Una enfermedad sin casos sigue apareciendo (LEFT JOIN): el catalogo
    existe aunque nadie haya reportado nada todavia.
    """
    condiciones = []
    filtro_params = []

    if busqueda:
        condiciones.append("(d.name ILIKE %s OR d.code ILIKE %s)")
        patron = f"%{busqueda}%"
        filtro_params += [patron, patron]

    if estado == "activa":
        condiciones.append("d.is_active")
    elif estado == "inactiva":
        condiciones.append("NOT d.is_active")

    where = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""
    pagina = max(1, pagina)

    # count(*) OVER () se evalua despues del GROUP BY y antes del LIMIT, asi que
    # devuelve cuantas enfermedades pasan el filtro sin repetir el WHERE en una
    # segunda consulta.
    rows = query(
        f"""
        SELECT d.id, d.code, d.name, d.description, d.is_active, d.created_at,
               d.default_params,
               count(c.id)                                                   AS casos_total,
               count(c.id) FILTER (WHERE c.report_date >= current_date - 29) AS casos_30d,
               max(c.report_date)                                            AS ultimo_caso,
               count(*) OVER ()                                              AS total_filtrado
        FROM diseases d
        LEFT JOIN cases c
               ON c.disease_id = d.id
              AND c.status IN ('pendiente', 'validado')
              AND c.region_id IN (
                    SELECT id FROM regions
                    WHERE parent_region_id = (SELECT id FROM regions WHERE code = %s))
        {where}
        GROUP BY d.id
        ORDER BY d.name
        LIMIT %s OFFSET %s
        """,
        tuple([NL_ESTADO_CODE] + filtro_params + [por_pagina, (pagina - 1) * por_pagina]),
    )

    total = rows[0]["total_filtrado"] if rows else 0
    enfermedades = [{
        "id": r["id"],
        "code": r["code"],
        "nombre": r["name"],
        "descripcion": r["description"],
        "activa": r["is_active"],
        "estado_label": "Activa" if r["is_active"] else "Inactiva",
        "actividad": _actividad(r["casos_total"], r["casos_30d"]),
        "alta_label": _fecha_corta(r["created_at"]),
        "casos_total": r["casos_total"],
        "casos_30d": r["casos_30d"],
        "ultimo_caso_label": _fecha_corta(r["ultimo_caso"]) or "Sin casos registrados",
        "parametros": estado_parametros(r["default_params"]),
    } for r in rows]

    return {
        "enfermedades": enfermedades,
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
        "paginas": max(1, -(-total // por_pagina)),
        "desde": (pagina - 1) * por_pagina + 1 if total else 0,
        "hasta": min(pagina * por_pagina, total),
    }


# ---------------------------------------------------------------------------
# Alta de enfermedades
# ---------------------------------------------------------------------------
# Dos estados distintos que conviene no confundir:
#
#   is_active   -> vigencia de la entrada en el CATALOGO. Lo decide una
#                  persona: TRUE al darla de alta, FALSE para retirarla (baja
#                  logica, igual que en el modulo de usuarios).
#   actividad   -> situacion EPIDEMIOLOGICA. No se guarda: se deriva de
#                  `cases` en cada consulta.
#
# Mezclarlos rompe el catalogo. Una enfermedad recien registrada no tiene
# casos todavia; si por eso naciera inactiva y "inactiva" significara que no
# se puede seleccionar al capturar, nunca podria recibir su primer caso. El
# esquema entregado ya resuelve esto en la direccion correcta: PATOGENO_X se
# siembra sin especificar is_active (o sea TRUE) y a proposito sin un solo
# caso, porque es el "escenario de preparacion".

RE_CODIGO_ENFERMEDAD = re.compile(r"^[A-Z][A-Z0-9_]{2,29}$")


def normaliza_codigo(valor):
    """'Dengue grave (2026)' -> 'DENGUE_GRAVE_2026'. Perdona el formato que
    escriba la gente pero deja el codigo con la convencion del catalogo."""
    limpio = unicodedata.normalize("NFKD", (valor or "").strip())
    limpio = limpio.encode("ascii", "ignore").decode("ascii")
    limpio = re.sub(r"[^A-Za-z0-9]+", "_", limpio).strip("_").upper()
    return limpio[:30]


def _actividad(casos_total, casos_30d):
    """Situacion epidemiologica derivada de `cases`, acotada a Nuevo Leon
    igual que el resto de la pantalla. Ver la nota de arriba: esto NO es
    is_active."""
    if casos_30d:
        return {"clave": "con_casos", "label": "Con casos activos"}
    if casos_total:
        return {"clave": "historico", "label": "Solo histórico"}
    return {"clave": "sin_casos", "label": "Sin casos"}


def valida_enfermedad(code, name):
    """Valida contra lo que el esquema realmente exige (004_catalogos.sql):
    code VARCHAR(30) unico, name VARCHAR(120). Devuelve lista de errores."""
    errores = []
    if not code:
        errores.append("El código es obligatorio.")
    elif not RE_CODIGO_ENFERMEDAD.match(code):
        errores.append("El código debe empezar con letra y llevar entre 3 y 30 "
                       "caracteres (solo A-Z, 0-9 y guion bajo).")
    if not name:
        errores.append("El nombre es obligatorio.")
    elif len(name) > 120:
        errores.append("El nombre no puede pasar de 120 caracteres.")
    return errores


def crear_enfermedad(code, name, description=None, params=None):
    """Alta en el catalogo. Devuelve (disease_id, error).

    Los parametros son opcionales: se puede registrar el padecimiento y
    capturarlos despues, cuando alguien tenga la fuente a la mano. Lo que no se
    permite en ningun momento es un valor sin fuente ni marca de supuesto; de
    eso se encarga parametros_desde_form().

    is_active no se manda: se deja el DEFAULT TRUE de la columna.

    El codigo duplicado se detecta por el 23505 de Postgres y no con un SELECT
    previo, que tendria carrera -- mismo criterio que crear_usuario.
    """
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO diseases (code, name, description, default_params)
                    VALUES (%s, %s, %s, %s::jsonb)
                    RETURNING id
                    """,
                    (code, name.strip(), (description or "").strip() or None,
                     json.dumps(params or {}, ensure_ascii=False)),
                )
                nuevo_id = cur.fetchone()[0]
            conn.commit()
        return nuevo_id, None
    except psycopg2.errors.UniqueViolation:
        return None, f"Ya existe una enfermedad con el código '{code}'."
    except psycopg2.errors.CheckViolation:
        return None, "Los datos no cumplen las restricciones de la base."


def get_enfermedad(disease_id):
    """Una sola enfermedad del catalogo. Se usa para la edicion y para el
    snapshot que va a audit_log."""
    return query(
        """
        SELECT id, code, name, description, is_active, created_at, default_params
        FROM diseases WHERE id = %s
        """,
        (disease_id,),
        one=True,
    )


# ---------------------------------------------------------------------------
# Parametros de simulacion de una enfermedad
# ---------------------------------------------------------------------------
# Regla del proyecto: no se inventan parametros desde la interfaz. Cada valor
# se guarda con su fuente o marcado explicitamente como supuesto del equipo.
# El formato es el que consume el motor (ver motor/parametros.py):
#
#     "r0": {"valor": 1.3, "fuente": "Biggerstaff et al. 2014", "supuesto": false}
#
# El motor tambien acepta el numero pelon y el formato de distribucion que trae
# 010_datos_iniciales.sql ({"dist": "lognormal", "media": 5.1, ...}). Aqui se
# leen los tres para no romper lo ya cargado, pero lo que se ESCRIBE siempre
# lleva fuente o marca de supuesto.
#
# Son los seis que el motor exige para poder correr. Si falta uno, la
# enfermedad no se puede simular y la pantalla lo dice.

PARAMETROS_SIMULACION = [
    {"clave": "r0", "etiqueta": "R₀ — número reproductivo básico",
     "unidad": "contagios por caso", "min": 0.01, "max": 20.0, "paso": "0.01",
     "ayuda": "Contagios que genera un caso en una población sin inmunidad."},
    {"clave": "incubacion_dias", "etiqueta": "Período de incubación",
     "unidad": "días", "min": 0.1, "max": 60.0, "paso": "0.1",
     "ayuda": "Del contagio al inicio de síntomas. El motor usa la media."},
    {"clave": "infeccioso_dias", "etiqueta": "Período infeccioso",
     "unidad": "días", "min": 0.1, "max": 60.0, "paso": "0.1",
     "ayuda": "Cuánto tiempo puede contagiar una persona."},
    {"clave": "dias_hospitalizacion", "etiqueta": "Estancia hospitalaria",
     "unidad": "días", "min": 0.1, "max": 120.0, "paso": "0.1",
     "ayuda": "Duración promedio de la hospitalización."},
    {"clave": "tasa_hospitalizacion", "etiqueta": "Tasa de hospitalización",
     "unidad": "%", "porcentaje": True, "min": 0.0, "max": 100.0, "paso": "0.001",
     "ayuda": "De cada 100 infectados, cuántos terminan hospitalizados."},
    {"clave": "letalidad", "etiqueta": "Letalidad (IFR)",
     "unidad": "%", "porcentaje": True, "min": 0.0, "max": 100.0, "paso": "0.0001",
     "ayuda": "De cada 100 infectados, cuántos fallecen."},
]

# Claves que el esquema ya trae y que este formulario no edita. Se muestran
# como informativas y se conservan intactas al guardar: son del contrato con el
# motor de agentes que viene despues, no de este formulario.
PARAMETROS_INFORMATIVOS = {
    "prob_asintomatico": "Proporción de asintomáticos",
    "transmisibilidad_base": "Transmisibilidad base (modelo de agentes)",
    "letalidad_por_edad": "Letalidad por grupo de edad",
}


def _desarma_param(bruto):
    """(valor, fuente, supuesto) a partir de cualquiera de los tres formatos."""
    if isinstance(bruto, dict):
        if "valor" in bruto:
            return bruto.get("valor"), bruto.get("fuente"), bool(bruto.get("supuesto", False))
        if "media" in bruto:                      # formato de 010_datos_iniciales
            return bruto.get("media"), None, False
        return None, None, False
    if isinstance(bruto, (int, float)) and not isinstance(bruto, bool):
        return bruto, None, False
    return None, None, False


def _inicio_de_grupo(par):
    """Ordena "0-19", "20-39", ..., "80+" por la edad con que empiezan. Lo que
    no empiece con un numero se va al final, en orden alfabetico."""
    clave = str(par[0])
    digitos = ""
    for c in clave:
        if not c.isdigit():
            break
        digitos += c
    return (0, int(digitos), clave) if digitos else (1, 0, clave)


def _numero_corto(valor):
    """3.11e-05 se lee mejor como 0.00311%. Solo para mostrar."""
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return f"{valor * 100:.4g}%"
    return str(valor)


def _formatea_valor(spec, valor):
    if valor is None:
        return None
    mostrado = valor * 100 if spec.get("porcentaje") else valor
    return f"{mostrado:g} {spec['unidad']}".strip()


def estado_parametros(default_params):
    """Todo lo que la pantalla necesita saber de los parametros de una
    enfermedad: valor, procedencia y si alcanza para simular."""
    params = default_params or {}
    por_edad = params.get("letalidad_por_edad")
    tiene_por_edad = isinstance(por_edad, dict) and bool(por_edad)

    detalle, faltan, supuestos, sin_fuente = [], [], [], []
    for spec in PARAMETROS_SIMULACION:
        valor, fuente, supuesto = _desarma_param(params.get(spec["clave"]))
        # El motor acepta letalidad_por_edad como alias de letalidad, asi que
        # una enfermedad con la tabla por edad ya cumple ese requisito.
        heredado = valor is None and spec["clave"] == "letalidad" and tiene_por_edad

        if valor is None and not heredado:
            estado = "falta"
            faltan.append(spec["clave"])
        elif heredado:
            estado = "por_grupo"
        elif supuesto:
            estado = "supuesto"
            supuestos.append(spec["clave"])
        elif fuente:
            estado = "con_fuente"
        else:
            estado = "sin_fuente"
            sin_fuente.append(spec["clave"])

        detalle.append({
            **spec,
            "valor": valor,
            # El formulario trabaja en % para las tasas; la base guarda 0–1.
            "valor_form": ("" if valor is None
                           else f"{valor * 100:g}" if spec.get("porcentaje") else f"{valor:g}"),
            "valor_label": _formatea_valor(spec, valor),
            "fuente": fuente or "",
            "supuesto": supuesto,
            "estado": estado,
        })

    # Un informativo puede venir pelado ({"0-19": 0.0001, ...}, como lo dejo
    # 010) o con trazabilidad ({"valor": {...}, "fuente": ..., "supuesto": ...},
    # como lo deja 020). Sin desenvolverlo, la pantalla imprimia el diccionario
    # entero -- fuente incluida -- en una sola linea ilegible.
    informativos = []
    for clave, etiqueta in PARAMETROS_INFORMATIVOS.items():
        bruto = params.get(clave)
        if bruto in (None, {}, ""):
            continue
        valor, fuente, supuesto = _desarma_param(bruto)
        if valor is None and isinstance(bruto, dict):
            valor = bruto                      # formato pelado: el valor es el dict
        if valor in (None, {}, ""):
            continue
        if isinstance(valor, dict):
            # Por edad, no por el orden en que JSONB devuelve las claves: sin
            # esto "80+" sale primero y la tabla se lee al reves de como se
            # piensa.
            texto = ", ".join(f"{k}: {_numero_corto(v)}"
                              for k, v in sorted(valor.items(), key=_inicio_de_grupo))
        else:
            texto = str(valor)
        informativos.append({"etiqueta": etiqueta, "texto": texto,
                             "fuente": fuente or "", "supuesto": supuesto})

    return {
        "detalle": detalle,
        "informativos": informativos,
        "faltan": faltan,
        "supuestos": supuestos,
        "sin_fuente": sin_fuente,
        "simulable": not faltan,
    }


def parametros_desde_form(form, actuales=None):
    """Arma el JSONB de parametros con lo que venga del formulario.

    Devuelve (params, errores). Conserva las claves que este formulario no
    edita (las informativas): guardar R0 no debe borrar la tabla de letalidad
    por edad que ya traia la enfermedad.

    La regla dura: un valor sin fuente y sin marca de supuesto NO se guarda.
    """
    params = dict(actuales or {})
    errores = []

    for spec in PARAMETROS_SIMULACION:
        clave = spec["clave"]
        crudo = (form.get(f"p_{clave}_valor") or "").strip()
        fuente = (form.get(f"p_{clave}_fuente") or "").strip()
        supuesto = form.get(f"p_{clave}_supuesto") == "on"

        if not crudo:
            params.pop(clave, None)      # vaciar el campo retira el parametro
            continue

        try:
            valor = float(crudo.replace(",", "."))
        except ValueError:
            errores.append(f"{spec['etiqueta']}: «{crudo}» no es un número.")
            continue
        if not math.isfinite(valor) or not (spec["min"] <= valor <= spec["max"]):
            errores.append(f"{spec['etiqueta']}: debe estar entre {spec['min']:g} "
                           f"y {spec['max']:g} {spec['unidad']}.")
            continue
        if not fuente and not supuesto:
            errores.append(f"{spec['etiqueta']}: falta la fuente. Escríbela o marca "
                           "la casilla de supuesto.")
            continue

        params[clave] = {
            "valor": round(valor / 100, 10) if spec.get("porcentaje") else valor,
            "fuente": fuente or None,
            "supuesto": supuesto,
        }

    return params, errores


def actualiza_enfermedad(disease_id, name, description, params):
    """Edicion del catalogo. El codigo NO se toca: es la llave natural con la
    que ya estan ligados los casos, los escenarios y los CSV exportados."""
    try:
        execute(
            """
            UPDATE diseases
            SET name = %s, description = %s, default_params = %s::jsonb
            WHERE id = %s
            """,
            (name.strip(), (description or "").strip() or None,
             json.dumps(params, ensure_ascii=False), disease_id),
        )
        return True, None
    except psycopg2.errors.CheckViolation:
        return False, "Los datos no cumplen las restricciones de la base."


def set_enfermedad_activa(disease_id, activa):
    """Baja y alta logica. Nunca DELETE: los casos capturados apuntan aqui con
    ON DELETE RESTRICT, y el historico no se tira."""
    execute("UPDATE diseases SET is_active = %s WHERE id = %s", (bool(activa), disease_id))


BUCKETS = [
    (0, 15, "baja", "Baja"),
    (15, 30, "moderada", "Moderada"),
    (30, 45, "alta", "Alta"),
    (45, 60, "muy_alta", "Muy alta"),
    (60, float("inf"), "critica", "Critica"),
]


def _bucket(incidencia):
    for lo, hi, key, label in BUCKETS:
        if lo <= incidencia < hi:
            return key, label
    return "critica", "Critica"


def get_mapa_municipios(disease_id=None, dias=30):
    """Un renglon por municipio de Nuevo Leon: casos totales del periodo,
    incidencia por 100k, variacion vs el periodo anterior de igual longitud,
    y el nivel del semaforo para colorear el marcador en el mapa."""
    periodo_offset = dias - 1          # p.ej. dias=30 -> ultimos 30 dias (offset 0..29)
    previo_offset = 2 * dias - 1       # los `dias` dias inmediatamente anteriores

    disease_filter = ""
    disease_params = ()
    if disease_id:
        disease_filter = "AND c.disease_id = %s"
        disease_params = (disease_id,)

    sql = f"""
        SELECT r.id, r.code, r.name, r.population, r.centroid_lat, r.centroid_lon,
               count(*) FILTER (WHERE c.report_date >= current_date - %s) AS casos_periodo,
               count(*) FILTER (WHERE c.report_date <  current_date - %s
                                   AND c.report_date >= current_date - %s) AS casos_previo
        FROM regions r
        LEFT JOIN cases c ON c.region_id = r.id
                          AND c.status IN ('pendiente','validado')
                          {disease_filter}
        WHERE r.parent_region_id = (SELECT id FROM regions WHERE code = %s)
        GROUP BY r.id, r.code, r.name, r.population, r.centroid_lat, r.centroid_lon
        ORDER BY r.name
        """
    params = (periodo_offset, periodo_offset, previo_offset) + disease_params + (NL_ESTADO_CODE,)
    rows = query(sql, params)

    out = []
    for r in rows:
        casos = r["casos_periodo"] or 0
        casos_previo = r["casos_previo"] or 0
        incidencia = round(casos / r["population"] * 100000, 1) if r["population"] else 0.0
        variacion = _pct_change(casos, casos_previo)
        bucket_key, bucket_label = _bucket(incidencia)
        out.append({
            "id": r["id"],
            "region_code": r["code"],
            "nombre": r["name"],
            "casos": casos,
            "incidencia": incidencia,
            "variacion": variacion,
            "lat": float(r["centroid_lat"]),
            "lon": float(r["centroid_lon"]),
            "nivel": bucket_key,
            "nivel_label": bucket_label,
        })
    return out


def get_tendencia_zona(region_id, disease_id=None, dias=14):
    """Serie diaria corta para el mini-grafico de 'tendencia temporal' del
    panel de detalle del mapa, para una sola zona."""
    params = [region_id, dias - 1]
    disease_filter = ""
    if disease_id:
        disease_filter = "AND disease_id = %s"
        params.append(disease_id)
    rows = query(
        f"""
        SELECT report_date::text AS fecha, count(*) AS total
        FROM cases
        WHERE region_id = %s
          AND report_date >= current_date - %s
          {disease_filter}
        GROUP BY report_date
        ORDER BY report_date
        """,
        tuple(params),
    )
    return [{"fecha": r["fecha"], "total": r["total"]} for r in rows]


def get_mapa_serie_temporal(disease_id=None, dias=30):
    """Matriz municipio x dia para la linea de tiempo del mapa.

    Un cuadro por cada dia del periodo seleccionado -- `dias` cuadros exactos,
    ni mas ni menos, para que la barra corresponda con lo que dice el filtro.
    Cada cuadro trae el ACUMULADO del periodo hasta ese dia, no una ventana
    movil: asi el recorrido se lee como el periodo llenandose dia con dia, que
    es lo que se espera al darle "reproducir".

    Dos propiedades que hay que conservar si esto se toca:

    1. El ultimo cuadro es identico al mapa estatico. Acumular los `dias` dias
       del periodo da exactamente los casos que cuenta get_mapa_municipios, y
       la variacion del ultimo cuadro compara periodo contra periodo previo
       completo, igual que alla.
    2. Ningun cuadro mira antes del inicio del periodo, asi que el acumulado
       nunca queda inflado ni deprimido por falta de historia. (La variacion si
       depende del periodo previo: si no hay datos tan atras se queda en +100%,
       que es lo que ya devolvia _pct_change contra cero.)

    La variacion de cada cuadro compara contra el mismo numero de dias
    transcurridos del periodo previo -- dia 5 del periodo contra dia 5 del
    periodo anterior -- para que sea una comparacion pareja y no acumulado
    parcial contra periodo completo.

    El conteo por dia se hace en SQL y el acumulado en Python. Son
    51 x 2 x dias numeros: no amerita un window function, y de paso el SQL se
    queda sin fragmentos armados a mano mas alla del filtro de enfermedad.
    """
    # Historia a pedir: el periodo mas el periodo previo con el que se compara.
    historia_offset = 2 * dias - 1

    disease_filter = ""
    disease_params = ()
    if disease_id:
        disease_filter = "AND c.disease_id = %s"
        disease_params = (disease_id,)

    # OJO con el orden de los %s: psycopg2 los liga por posicion en el texto
    # del SQL, no por clausula. Aqui los del JOIN (historia y enfermedad) van
    # antes que el del WHERE (codigo del estado).
    sql = f"""
        SELECT r.code, r.name, r.population,
               c.report_date::text AS dia,
               count(c.id) AS casos
        FROM regions r
        LEFT JOIN cases c ON c.region_id = r.id
                          AND c.status IN ('pendiente','validado')
                          AND c.report_date >= current_date - %s
                          {disease_filter}
        WHERE r.parent_region_id = (SELECT id FROM regions WHERE code = %s)
        GROUP BY r.code, r.name, r.population, c.report_date
        ORDER BY r.name, dia
        """
    params = (historia_offset,) + disease_params + (NL_ESTADO_CODE,)
    rows = query(sql, params)

    # La fecha de corte se pide a la base, no se asume date.today(): las dos
    # tienen que ser la misma para que el ultimo cuadro cuadre con el mapa.
    hoy = date.fromisoformat(query("SELECT current_date::text AS hoy", one=True)["hoy"])

    por_municipio = {}
    for r in rows:
        m = por_municipio.setdefault(
            r["code"], {"population": r["population"], "por_dia": {}}
        )
        if r["dia"] is not None:
            m["por_dia"][r["dia"]] = r["casos"]

    inicio = hoy - timedelta(days=dias - 1)            # primer dia del periodo
    inicio_previo = inicio - timedelta(days=dias)      # primer dia del previo
    fechas = [(inicio + timedelta(days=n)).isoformat() for n in range(dias)]

    series = {}
    for code, m in por_municipio.items():
        casos_frame, incidencia_frame, variacion_frame = [], [], []
        acumulado = acumulado_previo = 0
        for i in range(dias):
            acumulado += m["por_dia"].get(fechas[i], 0)
            acumulado_previo += m["por_dia"].get(
                (inicio_previo + timedelta(days=i)).isoformat(), 0
            )
            casos_frame.append(acumulado)
            incidencia_frame.append(
                round(acumulado / m["population"] * 100000, 1) if m["population"] else 0.0
            )
            variacion_frame.append(_pct_change(acumulado, acumulado_previo))
        series[code] = {
            "casos": casos_frame,
            "incidencia": incidencia_frame,
            "variacion": variacion_frame,
        }

    return {"fechas": fechas, "dias_periodo": dias, "series": series}


# ---------------------------------------------------------------------------
# Usuarios (pantalla adaptada del diseno de la companera)
# ---------------------------------------------------------------------------
# Nota: el schema de users NO tiene columna "departamento" (ese filtro del
# diseno original no se pudo traer -- no hay ese dato en ningun lado).
# "Pendiente" e "Inactivo" son estados que yo derive, no columnas reales:
#   activo    -> is_active = TRUE  y ya inicio sesion alguna vez
#   pendiente -> is_active = TRUE  pero nunca ha iniciado sesion (last_login_at NULL)
#   inactivo  -> is_active = FALSE (baja logica)

def get_usuarios_resumen():
    row = query(
        """
        SELECT
            count(*) AS total,
            count(*) FILTER (WHERE is_active AND last_login_at IS NOT NULL) AS activos,
            count(*) FILTER (WHERE is_active AND last_login_at IS NULL) AS pendientes,
            count(*) FILTER (WHERE NOT is_active) AS inactivos
        FROM users
        """,
        one=True,
    )
    return row


def get_roles_catalogo():
    return query("SELECT id, code, name FROM roles ORDER BY name")


def get_usuarios_lista(busqueda=None, rol_id=None, estado=None):
    condiciones = []
    params = []
    if busqueda:
        condiciones.append("(u.full_name ILIKE %s OR u.email ILIKE %s OR u.username ILIKE %s)")
        like = f"%{busqueda}%"
        params += [like, like, like]
    if rol_id:
        condiciones.append("r.id = %s")
        params.append(rol_id)
    if estado == "activo":
        condiciones.append("u.is_active AND u.last_login_at IS NOT NULL")
    elif estado == "pendiente":
        condiciones.append("u.is_active AND u.last_login_at IS NULL")
    elif estado == "inactivo":
        condiciones.append("NOT u.is_active")

    where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
    rows = query(
        f"""
        SELECT u.id, u.full_name, u.email, u.is_active, u.last_login_at,
               string_agg(DISTINCT r.name, ', ' ORDER BY r.name) AS roles
        FROM users u
        LEFT JOIN user_roles ur ON ur.user_id = u.id
        LEFT JOIN roles r ON r.id = ur.role_id
        {where}
        GROUP BY u.id, u.full_name, u.email, u.is_active, u.last_login_at
        ORDER BY u.full_name
        """,
        tuple(params),
    )
    out = []
    for r in rows:
        if not r["is_active"]:
            estado_calc = "Inactivo"
        elif r["last_login_at"] is None:
            estado_calc = "Pendiente"
        else:
            estado_calc = "Activo"
        out.append({
            "id": r["id"],
            "nombre": r["full_name"],
            "correo": r["email"],
            "roles": r["roles"] or "Sin rol asignado",
            "estado": estado_calc,
            "ultimo_acceso": r["last_login_at"].strftime("%Y-%m-%d %H:%M") if r["last_login_at"] else "Nunca",
        })
    return out


# ---------------------------------------------------------------------------
# Auditoria (pantalla adaptada del diseno de la companera)
# ---------------------------------------------------------------------------
# Nota: audit_log NO tiene columnas "descripcion" ni "estado" -- se arman
# aqui: descripcion es un texto generado a partir de accion+entidad, y estado
# se deriva de la accion (LOGIN_FAILED/PERMISSION_DENIED = Fallido, resto =
# Correcto). "Usuarios activos" del resumen es una aproximacion: usuarios con
# un LOGIN registrado en las ultimas 24 horas (no hay tabla de sesiones).

ACCIONES_FALLIDAS = ("LOGIN_FAILED", "PERMISSION_DENIED")

DESCRIPCION_POR_ACCION = {
    "LOGIN": "Inicio de sesion exitoso",
    "LOGIN_FAILED": "Intento de inicio de sesion fallido",
    "LOGOUT": "Cierre de sesion",
    "EXPORT": "Exportacion de datos",
    "CREATE": "Alta de registro",
    "UPDATE": "Modificacion de registro",
    "DELETE": "Baja de registro",
    "PUBLISH": "Publicacion",
    "RUN": "Ejecucion",
    "CANCEL": "Cancelacion",
    "SYNC": "Sincronizacion",
    "PERMISSION_DENIED": "Acceso denegado por permisos",
}


def get_auditoria_resumen():
    row = query(
        """
        SELECT
            count(*) AS eventos_totales,
            count(*) FILTER (WHERE action = 'PERMISSION_DENIED') AS criticas,
            count(*) FILTER (WHERE action = 'LOGIN_FAILED') AS fallidos,
            count(DISTINCT user_id) FILTER (
                WHERE action = 'LOGIN' AND occurred_at >= now() - interval '24 hours'
            ) AS activos_24h
        FROM audit_log
        """,
        one=True,
    )
    return row


def get_auditoria_lista(busqueda=None, usuario_id=None, modulo=None, accion=None, limit=100):
    condiciones = []
    params = []
    if busqueda:
        condiciones.append("(u.full_name ILIKE %s OR host(a.ip_address)::text ILIKE %s OR a.entity_type ILIKE %s)")
        like = f"%{busqueda}%"
        params += [like, like, like]
    if usuario_id:
        condiciones.append("a.user_id = %s")
        params.append(usuario_id)
    if modulo:
        condiciones.append("a.entity_type = %s")
        params.append(modulo)
    if accion:
        condiciones.append("a.action = %s")
        params.append(accion)

    where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
    params.append(limit)
    rows = query(
        f"""
        SELECT a.id, a.occurred_at, a.action, a.entity_type, a.entity_id,
               a.ip_address, u.full_name AS usuario
        FROM audit_log a
        LEFT JOIN users u ON u.id = a.user_id
        {where}
        ORDER BY a.occurred_at DESC
        LIMIT %s
        """,
        tuple(params),
    )
    out = []
    for r in rows:
        out.append({
            "id": r["id"],
            "fecha": r["occurred_at"].strftime("%Y-%m-%d %H:%M:%S"),
            "usuario": r["usuario"] or "Anonimo",
            "modulo": r["entity_type"],
            "accion": r["action"],
            "descripcion": DESCRIPCION_POR_ACCION.get(r["action"], r["action"]),
            "ip": str(r["ip_address"]) if r["ip_address"] else "-",
            "estado": "Fallido" if r["action"] in ACCIONES_FALLIDAS else "Correcto",
        })
    return out


def get_modulos_auditoria():
    rows = query("SELECT DISTINCT entity_type FROM audit_log ORDER BY entity_type")
    return [r["entity_type"] for r in rows]


def get_acciones_auditoria():
    rows = query("SELECT DISTINCT action FROM audit_log ORDER BY action")
    return [r["action"] for r in rows]


def get_usuarios_para_filtro():
    rows = query(
        """
        SELECT DISTINCT u.id, u.full_name
        FROM users u JOIN audit_log a ON a.user_id = u.id
        ORDER BY u.full_name
        """
    )
    return rows


# ---------------------------------------------------------------------------
# Monitoreo -- analisis epidemiologico por tiempo, zona y demografia
# ---------------------------------------------------------------------------
# Todo lo de esta pantalla sale de `cases` (edad, sexo, severidad, fecha,
# municipio). Dos notas de alcance:
#   - La columna "HOSPIT." del mock no existe en el esquema: `cases.severity`
#     no modela hospitalizacion. Se muestra "Graves" (severity = 'grave'), que
#     es el dato real mas cercano.
#   - Las "zonas" del mock (Norte/Centro/Sur...) tampoco existen: aqui son los
#     municipios reales de Nuevo Leon, que es como esta cargado `regions`.
GRUPOS_EDAD = ["0-4", "5-14", "15-24", "25-44", "45-64", "65+"]

_GRUPO_EDAD_SQL = """
    CASE WHEN c.age < 5  THEN '0-4'
         WHEN c.age < 15 THEN '5-14'
         WHEN c.age < 25 THEN '15-24'
         WHEN c.age < 45 THEN '25-44'
         WHEN c.age < 65 THEN '45-64'
         ELSE '65+' END
"""

SEXO_LABEL = {"F": "Femenino", "M": "Masculino", "O": "Otro"}


def _monitoreo_where(disease_id, region_id, dias):
    """Fragmento WHERE compartido por las consultas de la pantalla. Devuelve
    (sql, params); los valores siempre viajan como parametros ligados."""
    cond = ["c.status IN ('pendiente', 'validado')",
            "c.report_date >= current_date - %s"]
    params = [dias - 1]
    if region_id:
        cond.append("c.region_id = %s")
        params.append(region_id)
    else:
        cond.append("""c.region_id IN (SELECT id FROM regions
                       WHERE parent_region_id = (SELECT id FROM regions WHERE code = %s))""")
        params.append(NL_ESTADO_CODE)
    if disease_id:
        cond.append("c.disease_id = %s")
        params.append(disease_id)
    return " AND ".join(cond), params


def _poblacion_ambito(region_id):
    if region_id:
        row = query("SELECT population FROM regions WHERE id = %s", (region_id,), one=True)
    else:
        row = query("SELECT population FROM regions WHERE code = %s", (NL_ESTADO_CODE,), one=True)
    return (row or {}).get("population") or 0


def get_monitoreo_serie(disease_id=None, region_id=None, dias=30):
    """Serie diaria: casos por dia + incidencia acumulada por 100k, que son
    las dos series del grafico 'Evolucion Temporal'."""
    where, params = _monitoreo_where(disease_id, region_id, dias)
    rows = query(
        f"""
        SELECT c.report_date::text AS fecha, count(*) AS casos
        FROM cases c
        WHERE {where}
        GROUP BY c.report_date
        ORDER BY c.report_date
        """,
        tuple(params),
    )
    poblacion = _poblacion_ambito(region_id)
    acumulado = 0
    serie = []
    for r in rows:
        acumulado += r["casos"]
        serie.append({
            "fecha": r["fecha"],
            "casos": r["casos"],
            "incidencia_acum": round(acumulado / poblacion * 100000, 2) if poblacion else 0.0,
        })
    return serie


def get_monitoreo_edad(disease_id=None, region_id=None, dias=30):
    """Casos por grupo etario. Siempre devuelve los 6 grupos en orden, aunque
    alguno venga en cero, para que el eje del grafico no se mueva."""
    where, params = _monitoreo_where(disease_id, region_id, dias)
    rows = query(
        f"""
        SELECT {_GRUPO_EDAD_SQL} AS grupo, count(*) AS casos
        FROM cases c
        WHERE {where} AND c.age IS NOT NULL
        GROUP BY 1
        """,
        tuple(params),
    )
    conteo = {r["grupo"]: r["casos"] for r in rows}
    return [{"grupo": g, "casos": conteo.get(g, 0)} for g in GRUPOS_EDAD]


def get_monitoreo_sexo(disease_id=None, region_id=None, dias=30):
    where, params = _monitoreo_where(disease_id, region_id, dias)
    rows = query(
        f"""
        SELECT c.sex, count(*) AS casos
        FROM cases c
        WHERE {where}
        GROUP BY c.sex
        ORDER BY casos DESC
        """,
        tuple(params),
    )
    total = sum(r["casos"] for r in rows) or 1
    return [{
        "label": SEXO_LABEL.get(r["sex"], "No especificado"),
        "casos": r["casos"],
        "pct": round(r["casos"] / total * 100, 1),
    } for r in rows]


def get_monitoreo_totales(disease_id=None, region_id=None, dias=30):
    """Casos e incidencia del periodo vs el periodo previo de igual largo."""
    cond = ["c.status IN ('pendiente', 'validado')"]
    cond_params = []
    if region_id:
        cond.append("c.region_id = %s")
        cond_params.append(region_id)
    else:
        cond.append("""c.region_id IN (SELECT id FROM regions
                       WHERE parent_region_id = (SELECT id FROM regions WHERE code = %s))""")
        cond_params.append(NL_ESTADO_CODE)
    if disease_id:
        cond.append("c.disease_id = %s")
        cond_params.append(disease_id)

    # Los tres %s de los FILTER van antes que los del WHERE en el texto del SQL
    # (ver nota en get_monitoreo_zonas): el orden de la lista tiene que seguir
    # al texto, no a las clausulas.
    row = query(
        f"""
        SELECT count(*) FILTER (WHERE c.report_date >= current_date - %s) AS actual,
               count(*) FILTER (WHERE c.report_date <  current_date - %s
                                  AND c.report_date >= current_date - %s) AS previo
        FROM cases c
        WHERE {' AND '.join(cond)}
        """,
        tuple([dias - 1, dias - 1, 2 * dias - 1] + cond_params),
    )
    row = row[0] if row else {"actual": 0, "previo": 0}
    poblacion = _poblacion_ambito(region_id)
    actual, previo = row["actual"] or 0, row["previo"] or 0
    return {
        "casos": actual,
        "casos_previo": previo,
        "casos_pct": _pct_change(actual, previo),
        "incidencia": round(actual / poblacion * 100000, 1) if poblacion else 0.0,
        "incidencia_previa": round(previo / poblacion * 100000, 1) if poblacion else 0.0,
    }


ORDEN_ZONAS = {
    "casos": "casos DESC, r.name",
    "incidencia": "incid_orden DESC NULLS LAST, r.name",
}


def get_monitoreo_zonas(disease_id=None, region_id=None, dias=30, busqueda=None,
                        orden="casos", pagina=1, por_pagina=10):
    """Tabla 'Detalle por Zona Geografica': un renglon por municipio.

    La variacion es siempre a 7 dias (como el mock), independiente del periodo
    elegido, por eso el LEFT JOIN abre la ventana a max(dias, 14) dias y los
    recortes finos se hacen con FILTER.
    """
    ventana = max(dias, 14) - 1
    cond_join = ["c.region_id = r.id", "c.status IN ('pendiente', 'validado')",
                 "c.report_date >= current_date - %s"]
    cond_where = ["r.parent_region_id = (SELECT id FROM regions WHERE code = %s)"]
    pagina = max(1, pagina)

    # psycopg2 liga los %s por el orden en que aparecen en el TEXTO del SQL, no
    # por clausula: primero los dos FILTER del SELECT, luego el JOIN, luego el
    # WHERE y al final LIMIT/OFFSET. Armar la lista en otro orden hace que el
    # periodo y la ventana se crucen (bug real: con dias=7 la ventana quedaba
    # en 7 dias y prev7 salia siempre 0, o sea +100% / Critico en toda zona).
    params = [dias - 1, dias - 1, dias - 1, ventana]
    if disease_id:
        cond_join.append("c.disease_id = %s")
        params.append(disease_id)
    params.append(NL_ESTADO_CODE)
    if region_id:
        cond_where.append("r.id = %s")
        params.append(region_id)
    if busqueda:
        cond_where.append("r.name ILIKE %s")
        params.append(f"%{busqueda}%")
    params += [por_pagina, (pagina - 1) * por_pagina]

    rows = query(
        f"""
        SELECT r.id, r.name, r.population,
               count(c.id) FILTER (WHERE c.report_date >= current_date - %s) AS casos,
               count(c.id) FILTER (WHERE c.report_date >= current_date - %s
                                     AND c.severity = 'grave')               AS graves,
               count(c.id) FILTER (WHERE c.report_date >= current_date - %s)::numeric
                 / NULLIF(r.population, 0)                                   AS incid_orden,
               count(c.id) FILTER (WHERE c.report_date >= current_date - 6)  AS ult7,
               count(c.id) FILTER (WHERE c.report_date BETWEEN current_date - 13
                                                          AND current_date - 7) AS prev7,
               count(*) OVER () AS total_filtrado
        FROM regions r
        LEFT JOIN cases c ON {' AND '.join(cond_join)}
        WHERE {' AND '.join(cond_where)}
        GROUP BY r.id, r.name, r.population
        ORDER BY {ORDEN_ZONAS.get(orden, ORDEN_ZONAS['casos'])}
        LIMIT %s OFFSET %s
        """,
        tuple(params),
    )

    total = rows[0]["total_filtrado"] if rows else 0
    zonas = []
    for r in rows:
        casos = r["casos"] or 0
        variacion = _pct_change(r["ult7"] or 0, r["prev7"] or 0)
        zonas.append({
            "id": r["id"],
            "zona": r["name"],
            "casos": casos,
            "incidencia": round(casos / r["population"] * 100000, 1) if r["population"] else 0.0,
            "variacion": variacion,
            "graves": r["graves"] or 0,
            "estado": _clasifica_tendencia(variacion),
        })

    return {
        "zonas": zonas,
        "total": total,
        "pagina": pagina,
        "paginas": max(1, -(-total // por_pagina)),
        "desde": (pagina - 1) * por_pagina + 1 if total else 0,
        "hasta": min(pagina * por_pagina, total),
    }


def get_monitoreo_insights(zonas, edades, totales, dias):
    """Los 3 textos de las tarjetas de arriba. Son funcion pura de lo que ya
    se consulto -- no vuelve a pegarle a la base."""
    con_casos = [z for z in zonas if z["casos"]]
    if con_casos:
        top = max(con_casos, key=lambda z: z["variacion"])
        signo = "+" if top["variacion"] >= 0 else ""
        geografica = (f"El mayor cambio ({signo}{top['variacion']}%) se registra en "
                      f"{top['zona']} durante los últimos 7 días.")
    else:
        geografica = "Todavía no hay casos capturados en el periodo seleccionado."

    pct = totales["casos_pct"]
    verbo = "aumentó" if pct > 0 else ("disminuyó" if pct < 0 else "se mantuvo")
    global_txt = (f"La incidencia general {verbo} un {abs(pct)}% respecto al periodo "
                  f"anterior de {dias} días.")

    activos = [e for e in edades if e["casos"]]
    if activos:
        peor = max(activos, key=lambda e: e["casos"])
        critica = (f"El grupo con más casos es el de {peor['grupo']} años "
                   f"({peor['casos']:,} casos).")
    else:
        critica = "Sin casos con edad registrada en el periodo."

    return {"geografica": geografica, "global": global_txt, "critica": critica}


# ---------------------------------------------------------------------------
# Alta de casos (pantalla "+ Nuevo Reporte" del dashboard)
# ---------------------------------------------------------------------------
# Los dominios de abajo NO son invencion: son literalmente los CHECK que
# declara 005_casos.sql sobre `cases`. Se validan aqui para que un valor fuera
# de dominio devuelva un error legible en el formulario en vez de reventar en
# la base con un CheckViolation.

SEXOS = {"M": "Masculino", "F": "Femenino", "O": "Otro"}
RESULTADOS = {"positivo": "Positivo", "negativo": "Negativo",
              "pendiente": "Pendiente", "sin_prueba": "Sin prueba"}
SEVERIDADES = {"asintomatico": "Asintomático", "leve": "Leve",
               "grave": "Grave", "fallecido": "Fallecido"}


def get_enfermedades_para_captura():
    """Catalogo de enfermedades para el selector del reporte.

    NO se reutiliza get_enfermedades_catalogo(): esa hace JOIN contra `cases`
    y por lo tanto solo devuelve enfermedades que YA tienen casos. Para
    capturar serviria de poco -- una enfermedad recien dada de alta nunca
    podria recibir su primer reporte. Aqui van todas las del catalogo que
    esten vigentes (is_active), tengan casos o no.
    """
    return query(
        """
        SELECT id, name, code FROM diseases
        WHERE is_active
        ORDER BY name
        """
    )


def _entero(valor, minimo, maximo, etiqueta, errores, obligatorio=False):
    """Convierte y acota un entero de formulario. Devuelve None si viene vacio
    o si no pasa; los errores se acumulan en `errores`."""
    texto = (valor or "").strip()
    if not texto:
        if obligatorio:
            errores.append(f"{etiqueta} es obligatorio.")
        return None
    try:
        n = int(texto)
    except ValueError:
        errores.append(f"{etiqueta} debe ser un número entero.")
        return None
    if not (minimo <= n <= maximo):
        errores.append(f"{etiqueta} debe estar entre {minimo} y {maximo}.")
        return None
    return n


def _fecha(valor, etiqueta, errores, obligatorio=False):
    texto = (valor or "").strip()
    if not texto:
        if obligatorio:
            errores.append(f"{etiqueta} es obligatoria.")
        return None
    try:
        return date.fromisoformat(texto)
    except ValueError:
        errores.append(f"{etiqueta} no tiene un formato de fecha válido.")
        return None


def _decimal(valor, minimo, maximo, etiqueta, errores):
    texto = (valor or "").strip()
    if not texto:
        return None
    try:
        n = float(texto)
    except ValueError:
        errores.append(f"{etiqueta} debe ser un número.")
        return None
    if not (minimo <= n <= maximo):
        errores.append(f"{etiqueta} debe estar entre {minimo} y {maximo}.")
        return None
    return n


def valida_caso(form):
    """Valida el formulario contra los CHECK reales de `cases`.

    Devuelve (datos_limpios, errores). Los dominios cerrados (sexo, resultado,
    severidad) se comparan contra los diccionarios de arriba: lo que no este
    ahi se descarta, no se manda a la base.
    """
    errores = []
    datos = {
        "disease_id": _entero(form.get("disease_id"), 1, 2**31, "La enfermedad", errores, True),
        "region_id": _entero(form.get("region_id"), 1, 2**31, "El municipio", errores, True),
        "report_date": _fecha(form.get("report_date"), "La fecha de reporte", errores, True),
        "onset_date": _fecha(form.get("onset_date"), "La fecha de inicio de síntomas", errores),
        "age": _entero(form.get("age"), 0, 120, "La edad", errores),
        "latitude": _decimal(form.get("latitude"), -90, 90, "La latitud", errores),
        "longitude": _decimal(form.get("longitude"), -180, 180, "La longitud", errores),
    }

    for campo, dominio, etiqueta in (
        ("sex", SEXOS, "El sexo"),
        ("test_result", RESULTADOS, "El resultado de prueba"),
        ("severity", SEVERIDADES, "La severidad"),
    ):
        valor = (form.get(campo) or "").strip()
        if valor and valor not in dominio:
            errores.append(f"{etiqueta} no es un valor del catálogo.")
            valor = ""
        datos[campo] = valor or None

    # ck_cases_rezago: no se puede reportar un caso antes de que empiecen los
    # sintomas.
    if datos["onset_date"] and datos["report_date"] and datos["onset_date"] > datos["report_date"]:
        errores.append("El inicio de síntomas no puede ser posterior a la fecha de reporte.")

    # Esto no lo pide el esquema, pero un reporte con fecha futura no tiene
    # sentido y descuadraria las ventanas de 7/30/60 dias de las otras
    # pantallas, que cuentan hacia atras desde current_date.
    if datos["report_date"] and datos["report_date"] > date.today():
        errores.append("La fecha de reporte no puede estar en el futuro.")

    # ck_cases_coordenadas: la geolocalizacion viaja completa o no viaja.
    if (datos["latitude"] is None) != (datos["longitude"] is None):
        errores.append("La ubicación necesita latitud y longitud, o ninguna de las dos.")

    return datos, errores


def crear_caso(datos, reported_by):
    """Inserta el reporte. Devuelve (case_id, error).

    Dos columnas se dejan al DEFAULT del esquema a proposito:
      status     -> 'pendiente'. Un reporte capturado entra a validacion, no
                    nace validado. Es lo que asume el indice parcial
                    ix_cases_pendientes y lo que filtran las pantallas.
      created_at -> now()
    local_uuid lo genera la base con gen_random_uuid(): la columna es NOT NULL
    UNIQUE y en el modelo original la manda el dispositivo movil.
    """
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO cases (local_uuid, reported_by, disease_id, region_id,
                                       age, sex, onset_date, report_date,
                                       latitude, longitude, test_result, severity)
                    VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (reported_by, datos["disease_id"], datos["region_id"],
                     datos["age"], datos["sex"], datos["onset_date"], datos["report_date"],
                     datos["latitude"], datos["longitude"],
                     datos["test_result"], datos["severity"]),
                )
                nuevo_id = cur.fetchone()[0]
            conn.commit()
        return nuevo_id, None
    except psycopg2.errors.ForeignKeyViolation:
        return None, "La enfermedad o el municipio seleccionados ya no existen."
    except psycopg2.errors.CheckViolation as exc:
        return None, f"La base rechazó el reporte por una restricción: {exc.diag.constraint_name}."


def get_caso(case_id):
    """El reporte recien creado, ya resuelto a nombres, para el snapshot que
    va a audit_log y para el mensaje de confirmacion."""
    return query(
        """
        SELECT c.id, c.report_date, c.onset_date, c.age, c.sex,
               c.test_result, c.severity, c.status,
               d.name AS enfermedad, r.name AS municipio,
               c.latitude, c.longitude
        FROM cases c
        JOIN diseases d ON d.id = c.disease_id
        JOIN regions  r ON r.id = c.region_id
        WHERE c.id = %s
        """,
        (case_id,),
        one=True,
    )


def get_municipios_catalogo():
    """Municipios de Nuevo Leon para el selector geografico. Trae los 51, no
    solo los 10 con casos: filtrar por uno vacio es un resultado valido."""
    return query(
        """
        SELECT id, name FROM regions
        WHERE parent_region_id = (SELECT id FROM regions WHERE code = %s)
        ORDER BY name
        """,
        (NL_ESTADO_CODE,),
    )


# ---------------------------------------------------------------------------
# CRUD de usuarios (solo rol ADMINISTRADOR -- ver auth.admin_required)
# ---------------------------------------------------------------------------
# No modifica el esquema: usa users / roles / user_roles tal como los define
# 002_seguridad.sql. Las restricciones de esa migracion se respetan aqui:
#   ck_users_username_min / ck_users_email_min -> se normaliza a minusculas
#   ck_users_email_forma                       -> se valida el formato antes
#   uq_users_username / uq_users_email         -> se traduce el 23505 a mensaje
#
# Sobre el borrado: 6 tablas apuntan a users con ON DELETE RESTRICT
# (cases, case_attachments, vaccine_lots, scenarios, scenario_versions,
# simulation_batches). Un usuario que ya capturo informacion NO se puede
# borrar -- y esta bien que asi sea, porque romperia la trazabilidad de esos
# registros. Para ese caso existe la baja logica (is_active = FALSE).

RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# tabla -> (columna que apunta a users, etiqueta legible)
DEPENDENCIAS_RESTRICT = [
    ("cases", "reported_by", "casos capturados"),
    ("case_attachments", "uploaded_by", "evidencias subidas"),
    ("vaccine_lots", "scanned_by", "lotes de vacuna escaneados"),
    ("scenarios", "owner_id", "escenarios"),
    ("scenario_versions", "created_by", "versiones de escenario"),
    ("simulation_batches", "requested_by", "lotes de simulacion"),
    # audit_log NO va en esta lista: su FK es ON DELETE SET NULL y, tras
    # la migracion 011_fix_audit_log_delete.sql, el trigger de inmutabilidad permite ese
    # unico caso. Los eventos del usuario borrado se conservan, pero quedan
    # sin dueno (user_id NULL) -- ver la nota del README sobre esa perdida de
    # atribucion.
]


def get_usuario(user_id):
    """Un usuario con su rol actual, para la pantalla de edicion."""
    return query(
        """
        SELECT u.id, u.username, u.email, u.full_name, u.is_active,
               u.last_login_at, u.created_at,
               (SELECT ur.role_id FROM user_roles ur WHERE ur.user_id = u.id LIMIT 1) AS role_id
        FROM users u
        WHERE u.id = %s
        """,
        (user_id,),
        one=True,
    )


def valida_usuario(username, email, full_name, es_alta, password=None):
    """Devuelve una lista de errores legibles (vacia si todo bien)."""
    errores = []
    if es_alta:
        if not username or len(username.strip()) < 3:
            errores.append("El usuario debe tener al menos 3 caracteres.")
        elif len(username.strip()) > 60:
            errores.append("El usuario no puede pasar de 60 caracteres.")
        if not password or len(password) < 8:
            errores.append("La contraseña debe tener al menos 8 caracteres.")
    elif password is not None and password != "" and len(password) < 8:
        errores.append("La contraseña debe tener al menos 8 caracteres.")

    if not full_name or not full_name.strip():
        errores.append("El nombre completo es obligatorio.")
    elif len(full_name.strip()) > 160:
        errores.append("El nombre completo no puede pasar de 160 caracteres.")

    if not email or not RE_EMAIL.match(email.strip()):
        errores.append("El correo no tiene un formato valido.")
    elif len(email.strip()) > 160:
        errores.append("El correo no puede pasar de 160 caracteres.")

    return errores


def crear_usuario(username, email, full_name, password_hash, role_id, is_active=True):
    """Alta + asignacion de rol en una sola transaccion.

    Devuelve (user_id, error). Si el username o el correo ya existen, error
    trae el mensaje y user_id es None -- se detecta por el 23505 de Postgres
    en vez de con un SELECT previo, que tendria carrera.
    """
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (username, email, password_hash, full_name, is_active)
                    VALUES (lower(%s), lower(%s), %s, %s, %s)
                    RETURNING id
                    """,
                    (username.strip(), email.strip(), password_hash, full_name.strip(), is_active),
                )
                nuevo_id = cur.fetchone()[0]
                if role_id:
                    cur.execute(
                        "INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s)",
                        (nuevo_id, role_id),
                    )
            conn.commit()
        return nuevo_id, None
    except psycopg2.errors.UniqueViolation as exc:
        detalle = str(exc)
        if "uq_users_username" in detalle:
            return None, "Ya existe un usuario con ese nombre de usuario."
        if "uq_users_email" in detalle:
            return None, "Ya existe un usuario con ese correo."
        return None, "Ya existe un usuario con esos datos."
    except psycopg2.errors.CheckViolation:
        return None, "Los datos no cumplen las restricciones de la base."


def actualizar_usuario(user_id, email, full_name, is_active, role_id, password_hash=None):
    """Edicion. El username NO se cambia: es la llave con la que la gente
    inicia sesion y con la que quedaron firmados sus registros historicos.
    password_hash solo se toca si viene (None = conservar el actual).
    """
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                if password_hash:
                    cur.execute(
                        """
                        UPDATE users
                        SET email = lower(%s), full_name = %s, is_active = %s,
                            password_hash = %s
                        WHERE id = %s
                        """,
                        (email.strip(), full_name.strip(), is_active, password_hash, user_id),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE users
                        SET email = lower(%s), full_name = %s, is_active = %s
                        WHERE id = %s
                        """,
                        (email.strip(), full_name.strip(), is_active, user_id),
                    )
                # un solo rol por usuario en esta version: se reemplaza el que tenga
                cur.execute("DELETE FROM user_roles WHERE user_id = %s", (user_id,))
                if role_id:
                    cur.execute(
                        "INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s)",
                        (user_id, role_id),
                    )
            conn.commit()
        return True, None
    except psycopg2.errors.UniqueViolation:
        return False, "Ya existe otro usuario con ese correo."
    except psycopg2.errors.CheckViolation:
        return False, "Los datos no cumplen las restricciones de la base."


def dependencias_usuario(user_id):
    """Cuenta los registros que impiden borrar al usuario (FK RESTRICT).
    Devuelve [(etiqueta, cantidad), ...] solo con los que tienen > 0."""
    out = []
    for tabla, columna, etiqueta in DEPENDENCIAS_RESTRICT:
        row = query(
            f"SELECT count(*) AS n FROM {tabla} WHERE {columna} = %s",
            (user_id,),
            one=True,
        )
        if row["n"]:
            out.append((etiqueta, row["n"]))
    return out


def desactivar_usuario(user_id, activo=False):
    """Baja (o alta) logica. Es lo que se usa cuando el usuario ya tiene
    registros y no se puede borrar de verdad."""
    execute("UPDATE users SET is_active = %s WHERE id = %s", (activo, user_id))


def eliminar_usuario(user_id):
    """Borrado real. Solo procede si no hay dependencias; el llamador debe
    checarlas antes con dependencias_usuario(). Aun asi se atrapan los dos
    errores posibles por si algo se creo entre el chequeo y el borrado:
    la FK con RESTRICT y el trigger inmutable de audit_log.
    """
    try:
        execute("DELETE FROM users WHERE id = %s", (user_id,))
        return True, None
    except psycopg2.errors.ForeignKeyViolation:
        return False, ("No se puede eliminar: el usuario tiene registros "
                       "asociados. Usa la baja logica (desactivar).")
    except psycopg2.errors.RestrictViolation:
        return False, ("No se puede eliminar: la bitacora de auditoria rechazo "
                       "la operacion. Esta base no tiene la migracion 011: "
                       "vuelve a correr db/dump_completo.sql. Mientras tanto, "
                       "usa la baja logica (desactivar).")


# ---------------------------------------------------------------------------
# Catalogo de Regiones (Bloque C) -- Nuevo Leon y sus 51 municipios
# ---------------------------------------------------------------------------
# Consulta abierta a cualquier usuario autenticado. La edicion de poblacion
# (mas abajo) es exclusiva de ADMINISTRADOR -- el candado real vive en la ruta
# (admin_required), esto solo hace las consultas y la escritura.
#
# La fuente que se muestra distingue el dato censal original del ajuste
# manual: `region_population_adjustments` (019_correccion_manual_poblacion.sql)
# guarda ese ajuste vigente; si una region+campo no tiene fila ahi, la cifra
# sigue siendo la del censo: la trae la semilla nl_municipios_completos.sql
# al insertar el municipio, y 015/016 la corrigen en bases ya instaladas.

# Whitelist de columnas ordenables: nunca se interpola la entrada del usuario
# directamente en el SQL, solo se usa para elegir una de estas dos.
ORDEN_REGIONES = {
    "nombre": "r.name",
    "poblacion": "r.population",
}


def _fuente_campo(reason, adjusted_at, adjusted_by_name, fuente_censal):
    """Arma el texto de la columna Fuente de la poblacion total de un municipio.
    Si hay un ajuste manual vigente, se ve distinto a la fuente censal -- nunca
    se le atribuye a INEGI un valor que un administrador corrigio.

    Solo aplica a `population`: el 60 y mas se deriva de region_age_groups
    (migracion 022) y su fuente es siempre censal."""
    if reason is None:
        return {"tipo": "censal", "label": fuente_censal, "detalle": None}
    detalle = f"Corregido por {adjusted_by_name or 'un administrador'} el {_fecha_corta(adjusted_at)}: {reason}"
    return {"tipo": "manual", "label": "Corrección manual", "detalle": detalle}


def get_estado_nl():
    """Nuevo Leon como fila unica: su poblacion es el agregado de sus 51
    municipios (ver actualiza_poblacion_municipio), nunca se edita aparte."""
    row = query(
        "SELECT id, code, name, population, population_60plus FROM regions WHERE code = %s",
        (NL_ESTADO_CODE,),
        one=True,
    )
    if not row:
        return None
    return {
        "id": row["id"],
        "code": row["code"],
        "nombre": row["name"],
        "poblacion": row["population"],
        "poblacion_60": row["population_60plus"],
        "fuente_poblacion": {"tipo": "agregado", "label": "Suma de los 51 municipios", "detalle": None},
        "fuente_poblacion_60": {"tipo": "derivado",
                                "label": "Grupos 60-79 y 80+ del Censo 2020",
                                "detalle": "Se deriva de la poblacion por grupo de edad "
                                           "del estado; no se captura ni se edita aparte."},
    }


def get_regiones_catalogo(busqueda=None, orden="nombre", direccion="asc"):
    """Los 51 municipios de Nuevo Leon, con su poblacion, poblacion 60+ y
    fuente. Todo sale de PostgreSQL usando parent_region_id para la
    jerarquia -- nada de listas ni cifras hardcodeadas aqui.

    `orden` y `direccion` se validan contra listas fijas antes de ir al SQL:
    nunca se arma la consulta con la entrada del usuario directamente.
    """
    columna = ORDEN_REGIONES.get(orden, ORDEN_REGIONES["nombre"])
    direccion_sql = "DESC" if direccion == "desc" else "ASC"

    condiciones = ["r.parent_region_id = (SELECT id FROM regions WHERE code = %s)"]
    params = [NL_ESTADO_CODE]
    if busqueda:
        condiciones.append("(r.name ILIKE %s OR r.code ILIKE %s)")
        patron = f"%{busqueda}%"
        params += [patron, patron]
    where = " AND ".join(condiciones)

    rows = query(
        f"""
        SELECT r.id, r.code, r.name, r.population, r.population_60plus
        FROM regions r
        WHERE {where}
        ORDER BY {columna} {direccion_sql}, r.name ASC
        """,
        tuple(params),
    )

    # Una base existente puede no haber recibido aun 019. La consulta publica
    # sigue disponible con fuentes censales, sin referenciar una tabla ausente.
    # Solo `population` puede tener ajuste manual. `population_60plus` se deriva
    # de region_age_groups (migracion 022) y por eso no se consulta aqui: si
    # apareciera un ajuste historico de ese campo, atribuirselo al valor actual
    # seria mentir, porque el valor actual ya no sale de ahi.
    ajustes = {}
    tabla = query(
        "SELECT to_regclass('public.region_population_adjustments') AS nombre",
        one=True,
    )
    if tabla["nombre"] and rows:
        ajustes_rows = query(
            """
            SELECT a.region_id, a.field, a.reason, a.adjusted_at, u.full_name
            FROM region_population_adjustments a
            LEFT JOIN users u ON u.id = a.adjusted_by
            WHERE a.region_id = ANY(%s) AND a.field = 'population'
            """,
            ([r["id"] for r in rows],),
        )
        ajustes = {(a["region_id"], a["field"]): a for a in ajustes_rows}

    municipios = []
    for r in rows:
        ajuste_pob = ajustes.get((r["id"], "population"), {})
        municipios.append({
            "id": r["id"],
            "code": r["code"],
            "nombre": r["name"],
            "poblacion": r["population"],
            "poblacion_60": r["population_60plus"],
            "fuente_poblacion": _fuente_campo(
                ajuste_pob.get("reason"), ajuste_pob.get("adjusted_at"),
                ajuste_pob.get("full_name"),
                "INEGI, Censo 2020"),
            "fuente_poblacion_60": {"tipo": "derivado",
                                    "label": "Grupos 60-79 y 80+ del Censo 2020",
                                    "detalle": "Se calcula a partir de la poblacion por grupo de edad; no se captura ni se edita aparte."},
        })

    return {
        "municipios": municipios,
        "total": len(municipios),
        "busqueda": busqueda or "",
        "orden": orden if orden in ORDEN_REGIONES else "nombre",
        "direccion": direccion if direccion in ("asc", "desc") else "asc",
    }


def get_region_municipio(region_id):
    """Un municipio de Nuevo Leon para el formulario de edicion de poblacion.
    None si no existe o si no es un municipio de NL (nivel/padre incorrectos):
    asi la ruta no depende de confiar en el region_id que llega por la URL."""
    return query(
        """
        SELECT r.id, r.code, r.name, r.level, r.parent_region_id,
               r.population, r.population_60plus
        FROM regions r
        WHERE r.id = %s
          AND r.level = 'municipio'
          AND r.parent_region_id = (SELECT id FROM regions WHERE code = %s)
        """,
        (region_id, NL_ESTADO_CODE),
        one=True,
    )


def valida_poblacion_municipio(population_raw, motivo, poblacion_60_actual=None):
    """Valida los dos campos editables del formulario de correccion. Devuelve
    (population:int|None, errores:list). Con errores no vacios el primer valor
    no es de fiar -- el llamador debe conservar lo que la persona escribio (no
    lo que aqui se devuelve) para volver a mostrar el formulario.

    `poblacion_60_actual` es el 60 y mas derivado del municipio; solo se usa
    para rechazar una poblacion total que quedaria por debajo de el."""
    errores = []

    def _entero_no_negativo(valor, etiqueta):
        if valor is None or str(valor).strip() == "":
            errores.append(f"{etiqueta} es obligatoria.")
            return None
        try:
            n = int(str(valor).strip())
        except ValueError:
            errores.append(f"{etiqueta} debe ser un número entero.")
            return None
        if n < 0:
            errores.append(f"{etiqueta} no puede ser negativa.")
            return None
        return n

    poblacion = _entero_no_negativo(population_raw, "La población total")

    # La poblacion de 60 y mas ya no se captura: se deriva de region_age_groups
    # (migracion 022). Lo que si se valida es que la correccion no deje al
    # municipio con menos habitantes que su propio grupo de 60 y mas.
    if poblacion is not None and poblacion_60_actual is not None \
            and poblacion < poblacion_60_actual:
        errores.append(
            f"La población total no puede ser menor que las {poblacion_60_actual:,} "
            f"personas de 60 años o más que el censo registra en este municipio.")

    if not motivo or not motivo.strip():
        errores.append("Indica la fuente o el motivo de la corrección.")
    elif len(motivo.strip()) > 500:
        errores.append("La fuente o motivo no puede pasar de 500 caracteres.")

    return poblacion, errores


def actualiza_poblacion_municipio(region_id, population, motivo, admin_user_id,
                                  esperado_population):
    """Corrige la poblacion total de un municipio. Solo la debe llamar una ruta
    ya protegida con admin_required -- aqui no se vuelve a checar el rol.

    El 60 y mas NO se toca: desde la migracion 022 se deriva de
    region_age_groups y lo mantiene un trigger. Corregirlo significa corregir
    las bandas de edad, que son dato censal.

    Todo corre en UNA transaccion: el UPDATE de regions, el ajuste vigente en
    region_population_adjustments, el recalculo del agregado estatal y las
    entradas de audit_log se confirman juntos o no se confirma nada. Asi nunca
    queda una poblacion cambiada sin su registro de auditoria.

    Control de concurrencia optimista: `esperado_population` es el valor que el
    formulario tenia al abrirse. Si ya no coincide con lo que hay en la base
    (alguien mas corrigio el municipio mientras se llenaba el formulario), se
    rechaza el guardado en vez de sobreescribirlo en silencio.

    Devuelve (ok, error, resultado). `resultado` trae el antes/despues del
    municipio y, si aplico, del estado -- para el mensaje de confirmacion.
    """
    from flask import request

    from .audit import _serializa

    ip = request.remote_addr
    ua = (request.headers.get("User-Agent") or "")[:255]

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, name, level, parent_region_id, population, population_60plus
                       FROM regions WHERE id = %s FOR UPDATE""",
                    (region_id,),
                )
                fila = cur.fetchone()
                if not fila or fila[2] != "municipio":
                    return False, "Ese municipio ya no existe en el catálogo.", None
                _, nombre, _nivel, padre_id, pob_actual, pob60_actual = fila

                if pob_actual != esperado_population:
                    return False, (
                        "Otra persona corrigió este municipio mientras editabas el "
                        "formulario. Recarga la página y vuelve a intentarlo."
                    ), None

                antes_municipio = {
                    "id": region_id, "name": nombre,
                    "population": pob_actual, "population_60plus": pob60_actual,
                }

                cur.execute(
                    "UPDATE regions SET population = %s WHERE id = %s",
                    (population, region_id),
                )

                for campo, valor_antes, valor_nuevo in (
                    ("population", pob_actual, population),
                ):
                    if valor_antes == valor_nuevo:
                        continue
                    cur.execute(
                        """
                        INSERT INTO region_population_adjustments
                            (region_id, field, census_value, previous_value, new_value,
                             reason, adjusted_by, adjusted_at)
                        VALUES (%s, %s,
                                COALESCE((SELECT census_value FROM region_population_adjustments
                                          WHERE region_id = %s AND field = %s), %s),
                                %s, %s, %s, %s, now())
                        ON CONFLICT (region_id, field) DO UPDATE
                        SET previous_value = region_population_adjustments.new_value,
                            new_value       = EXCLUDED.new_value,
                            reason          = EXCLUDED.reason,
                            adjusted_by     = EXCLUDED.adjusted_by,
                            adjusted_at     = now()
                        """,
                        (region_id, campo, region_id, campo, valor_antes,
                         valor_antes, valor_nuevo, motivo.strip(), admin_user_id),
                    )

                cur.execute(
                    """
                    INSERT INTO audit_log (user_id, action, entity_type, entity_id,
                                           ip_address, user_agent, data_before, data_after)
                    VALUES (%s, 'UPDATE', 'regions', %s, %s::inet, %s, %s::jsonb, %s::jsonb)
                    """,
                    (
                        admin_user_id, str(region_id), ip, ua,
                        _serializa(antes_municipio),
                        _serializa({
                            "id": region_id, "name": nombre,
                            "population": population, "population_60plus": pob60_actual,
                            "fuente_motivo": motivo.strip(),
                        }),
                    ),
                )

                cur.execute(
                    "SELECT id, population, population_60plus FROM regions WHERE id = %s FOR UPDATE",
                    (padre_id,),
                )
                estado_antes_row = cur.fetchone()

                # El 60 y mas del estado NO se agrega aqui: sale de sus propias
                # bandas de edad, via el trigger de 022. Y sum() ignora los NULL,
                # asi que si a un municipio le faltara la poblacion el total
                # saldria mas bajo que el real y quedaria guardado como si fuera
                # bueno; por eso se cuentan los faltantes y en ese caso no se
                # recalcula nada.
                cur.execute(
                    """
                    UPDATE regions e
                    SET population = CASE WHEN sub.faltan_pob = 0
                                          THEN sub.total_pob ELSE e.population END
                    FROM (
                        SELECT sum(population) AS total_pob,
                               count(*) FILTER (WHERE population IS NULL) AS faltan_pob
                        FROM regions WHERE parent_region_id = %s
                    ) sub
                    WHERE e.id = %s
                    RETURNING e.population, e.population_60plus, sub.faltan_pob
                    """,
                    (padre_id, padre_id),
                )
                estado_despues_row = cur.fetchone()
                faltan_pob = estado_despues_row[2] if estado_despues_row else 0

                estado_cambio = (
                    estado_antes_row is not None and estado_despues_row is not None
                    and (estado_antes_row[1] != estado_despues_row[0]
                         or estado_antes_row[2] != estado_despues_row[1])
                )
                if estado_cambio:
                    cur.execute(
                        """
                        INSERT INTO audit_log (user_id, action, entity_type, entity_id,
                                               ip_address, user_agent, data_before, data_after)
                        VALUES (%s, 'UPDATE', 'regions', %s, %s::inet, %s, %s::jsonb, %s::jsonb)
                        """,
                        (
                            admin_user_id, str(padre_id), ip, ua,
                            _serializa({
                                "population": estado_antes_row[1],
                                "population_60plus": estado_antes_row[2],
                                "nota": "agregado de los 51 municipios de Nuevo León",
                            }),
                            _serializa({
                                "population": estado_despues_row[0],
                                "population_60plus": estado_despues_row[1],
                                "nota": f"recalculado tras corregir {nombre}",
                            }),
                        ),
                    )
            conn.commit()
        return True, None, {
            "municipio": nombre,
            "poblacion_antes": pob_actual, "poblacion_despues": population,
            "poblacion_60": pob60_actual,   # derivado: no cambia por esta edicion
            "estado_actualizado": estado_cambio,
            "municipios_sin_poblacion": faltan_pob,
        }
    except psycopg2.errors.UndefinedTable:
        return False, (
            "La edición requiere la migración 019_correccion_manual_poblacion.sql. "
            "Pide a la persona responsable de la base que la aplique."
        ), None
    except psycopg2.errors.CheckViolation:
        return False, "Los datos no cumplen las restricciones de la base.", None
