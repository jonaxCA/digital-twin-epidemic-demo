"""
Genera datos/postgres/migraciones/020_letalidad_por_edad.sql: la letalidad por
infeccion (IFR) desglosada por grupo de edad para COVID-19 (linaje ancestral) e
influenza estacional.

POR QUE
El catalogo ya traia `letalidad_por_edad` en las dos enfermedades, pero con
cifras redondas sin ninguna fuente (0.1, 0.03, 0.003, 0.0002, 0.00002 para
COVID). Eso contradice la regla del proyecto -- ningun valor epidemiologico sin
procedencia -- justo en el parametro que decide el numero de fallecimientos, y
justo donde mas importa el detalle: entre el grupo mas joven y el mas viejo hay
tres ordenes de magnitud de diferencia.

QUE HACE
Toma las tablas por edad que SI publican las fuentes y las reagrupa a los cinco
grupos que usa el motor, ponderando por la estructura de edad real de Nuevo Leon
(Censo 2020). Reagrupar es aritmetica del equipo, no un dato publicado, asi que
las dos entradas salen marcadas como supuesto con la explicacion completa en su
campo "fuente".

Entradas:
  - las tablas publicadas, mas abajo en este archivo, con su cita y su DOI;
  - datos/censo/nl_estructura_edad_2020.tsv, para los pesos por edad.

Uso (desde la raiz del proyecto):
    python3 datos/scripts/build_letalidad_edad.py > datos/postgres/migraciones/020_letalidad_por_edad.sql

El detalle del calculo se imprime en stderr, para poder revisarlo sin abrir el
SQL generado.
"""
import json
import os
import sys

DATOS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ESTRUCTURA_EDAD = os.path.join(DATOS_DIR, "censo", "nl_estructura_edad_2020.tsv")

EDAD_MAX = 100          # ultimo grupo del tabulado: "100 anios y mas"

# Los cinco grupos que usa el motor, tal como estan capturados en `diseases`.
GRUPOS = [("0-19", 0, 19), ("20-39", 20, 39), ("40-59", 40, 59),
          ("60-79", 60, 79), ("80+", 80, EDAD_MAX)]

# ---------------------------------------------------------------------------
# COVID-19, linaje ancestral
# ---------------------------------------------------------------------------
# Verity R, Okell LC, Dorigatti I, et al. "Estimates of the severity of
# coronavirus disease 2019: a model-based analysis". Lancet Infect Dis 2020;
# 20(6):669-677. doi:10.1016/S1473-3099(20)30243-7
# Tabla 1, columna "Infection fatality ratio", en porcentaje. Se revisaron las
# dos fe de erratas del articulo (doi 10.1016/S1473-3099(20)30309-1, que corrige
# una linea del resumen, y doi 10.1016/S1473-3099(20)30368-6, que corrige la
# referencia 18 y la cita de la tabla 3): ninguna toca esta tabla.
# IFR global del estudio: 0.657% (IC 0.389-1.33).
VERITY_IFR_PCT = [
    ((0, 9),          0.00161),
    ((10, 19),        0.00695),
    ((20, 29),        0.0309),
    ((30, 39),        0.0844),
    ((40, 49),        0.161),
    ((50, 59),        0.595),
    ((60, 69),        1.93),
    ((70, 79),        4.28),
    ((80, EDAD_MAX),  7.80),
]

# ---------------------------------------------------------------------------
# Influenza estacional
# ---------------------------------------------------------------------------
# CDC. "Estimated Flu Disease Burden, 2019-2020 Flu Season", actualizado el
# 15/11/2024. Enfermedades sintomaticas y defunciones por grupo de edad.
# Es la MISMA vintage de la que salieron la letalidad y la tasa de
# hospitalizacion globales que ya estan en el catalogo (017): sus totales dan
# 34,026,679 enfermedades y 22,064 defunciones. Mezclarla con otra revision del
# CDC daria una tabla incoherente con el escalar.
CDC_2019_20 = [
    ((0, 4),          3_483_917,    280),
    ((5, 17),         6_451_335,    124),
    ((18, 49),       13_772_745,  1_932),
    ((50, 64),        8_421_049,  4_805),
    ((65, EDAD_MAX),  1_897_633, 14_924),
]
CDC_TOTAL_ENFERMEDADES = 34_026_679
CDC_TOTAL_DEFUNCIONES = 22_064

# Carrat F, Vergu E, Ferguson NM, et al. Am J Epidemiol 2008; 167(7):775-785.
# doi:10.1093/aje/kwm375 -- 66.9% de las infecciones son sintomaticas. El CDC
# publica sus tasas por caso sintomatico y el motor las necesita por infeccion.
# Es la misma conversion que ya usan los valores globales de influenza.
FRACCION_SINTOMATICA = 0.669


def poblacion_por_anio_de_edad():
    """Poblacion de Nuevo Leon repartida por anio de edad, 0 a EDAD_MAX.

    El tabulado viene en grupos quinquenales, asi que dentro de cada grupo se
    reparte parejo. La suposicion solo pesa cuando un limite cae a media hora de
    grupo: con Verity nunca pasa (sus decenios coinciden con los quinquenios), y
    con el CDC pasa una sola vez, al partir 15-19 en 15-17 y 18-19.
    """
    pesos = [0.0] * (EDAD_MAX + 1)
    with open(ESTRUCTURA_EDAD, encoding="utf-8") as f:
        filas = [l.rstrip("\n").split("\t") for l in f
                 if not l.startswith("#") and l.strip()]
    for fila in filas[1:]:
        etiqueta, total = fila[0].strip(), int(fila[1])
        partes = etiqueta.split()
        if not partes[0].isdigit():         # "Total", "No especificado"
            continue
        ini = int(partes[0])
        fin = int(partes[2]) if len(partes) > 2 and partes[2].isdigit() else EDAD_MAX
        for edad in range(ini, fin + 1):
            pesos[edad] += total / (fin - ini + 1)
    if sum(pesos) <= 0:
        raise SystemExit(f"no se pudo leer la estructura por edad de {ESTRUCTURA_EDAD}")
    return pesos


def tasa_por_anio(tabla):
    """Expande [( (ini,fin), tasa ), ...] a una tasa por cada anio de edad."""
    tasas = [None] * (EDAD_MAX + 1)
    for (ini, fin), tasa in tabla:
        for edad in range(ini, min(fin, EDAD_MAX) + 1):
            tasas[edad] = tasa
    faltan = [e for e, t in enumerate(tasas) if t is None]
    if faltan:
        raise SystemExit(f"la tabla de origen no cubre las edades {faltan[:5]}")
    return tasas


def reagrupa(tabla, pesos):
    """Promedia la tasa de cada grupo del motor, ponderando por poblacion."""
    por_anio = tasa_por_anio(tabla)
    salida = {}
    for nombre, ini, fin in GRUPOS:
        peso = sum(pesos[ini:fin + 1])
        if peso <= 0:
            raise SystemExit(f"el grupo {nombre} no tiene poblacion")
        salida[nombre] = sum(por_anio[e] * pesos[e] for e in range(ini, fin + 1)) / peso
    return salida


def ifr_influenza():
    """IFR por banda del CDC: defunciones / enfermedades sintomaticas, llevado
    de 'por caso sintomatico' a 'por infeccion'."""
    enfermos = sum(e for _, e, _ in CDC_2019_20)
    muertes = sum(m for _, _, m in CDC_2019_20)
    if enfermos != CDC_TOTAL_ENFERMEDADES:
        raise SystemExit(f"las enfermedades por edad suman {enfermos:,} y el CDC "
                         f"publica {CDC_TOTAL_ENFERMEDADES:,}")
    if abs(muertes - CDC_TOTAL_DEFUNCIONES) > 1:
        raise SystemExit(f"las defunciones por edad suman {muertes:,} y el CDC "
                         f"publica {CDC_TOTAL_DEFUNCIONES:,}")
    return [(banda, (m / e) * FRACCION_SINTOMATICA) for banda, e, m in CDC_2019_20], muertes


def redondea(valor):
    """Tres cifras significativas: mas precision seria fingir que la tenemos."""
    return float(f"{valor:.3g}")


FUENTE_COVID = (
    "DERIVADO POR EL EQUIPO a partir de Verity et al. 2020, Lancet Infect Dis "
    "20(6):669-677, tabla 1, columna Infection fatality ratio "
    "(doi:10.1016/S1473-3099(20)30243-7). El estudio publica el IFR por decenio "
    "de edad: 0.00161% en 0-9 hasta 7.80% en 80+, con IFR global 0.657% "
    "(IC 0.389-1.33). El motor usa grupos de veinte anios, asi que cada par de "
    "decenios se promedio ponderando por la estructura de edad de Nuevo Leon "
    "(Censo 2020, INEGI). Los limites de los decenios coinciden con los del "
    "censo, asi que el reagrupamiento no parte ningun grupo. Lo publicado es el "
    "IFR por decenio; el promedio ponderado lo hace el equipo. Se revisaron las "
    "dos fe de erratas del articulo y ninguna toca esta tabla. Estimacion de "
    "China, principios de 2020, linaje ancestral: no esta calibrada para "
    "Nuevo Leon."
)

FUENTE_INFLUENZA = (
    "DERIVADO POR EL EQUIPO a partir de CDC, Estimated Flu Disease Burden "
    "2019-2020 (actualizado 15/11/2024), defunciones y enfermedades "
    "sintomaticas por grupo de edad. Dos pasos, ninguno publicado por el CDC: "
    "(1) letalidad por caso sintomatico = defunciones/enfermedades en cada "
    "banda del CDC, llevada a por infeccion con 66.9% de infecciones "
    "sintomaticas (Carrat et al. 2008, Am J Epidemiol 167(7):775-785, "
    "doi:10.1093/aje/kwm375), la misma conversion que usan los valores globales "
    "de esta enfermedad; (2) las bandas del CDC (0-4, 5-17, 18-49, 50-64, 65+) "
    "se reagruparon a los cinco grupos del motor ponderando por la estructura "
    "de edad de Nuevo Leon (Censo 2020, INEGI), suponiendo tasa constante "
    "dentro de cada banda del CDC y reparto parejo dentro del grupo quinquenal "
    "15-19, que es el unico que queda partido. OJO: la banda mas alta del CDC "
    "es 65+, sin abrir los 80 y mas, asi que los grupos 60-79 y 80+ heredan la "
    "misma tasa de base y la tabla aplana el gradiente justo donde mas sube; el "
    "80+ real es mas alto que este valor. Es la misma vintage del CDC de la que "
    "salen la letalidad y la tasa de hospitalizacion globales del catalogo. "
    "Estimacion de Estados Unidos: no esta calibrada para Nuevo Leon."
)


def bloque_sql(code, nombre, tabla, fuente):
    cuerpo = json.dumps({"letalidad_por_edad": {"valor": tabla, "fuente": fuente,
                                                "supuesto": True}},
                        indent=8, ensure_ascii=True, sort_keys=True)
    return f"""-- {nombre}
UPDATE diseases
SET    default_params = default_params || '{cuerpo}'::jsonb
WHERE  code = '{code}'
  AND  NOT (default_params -> 'letalidad_por_edad' ? 'fuente');
"""


def main():
    sys.stdout.reconfigure(newline="\n")
    pesos = poblacion_por_anio_de_edad()

    covid = reagrupa([(b, p / 100.0) for b, p in VERITY_IFR_PCT], pesos)
    tabla_flu, muertes_cdc = ifr_influenza()
    influenza = reagrupa(tabla_flu, pesos)
    covid = {g: redondea(v) for g, v in covid.items()}
    influenza = {g: redondea(v) for g, v in influenza.items()}

    # Resumen auditable, a stderr para no ensuciar el SQL.
    poblacion = sum(pesos)
    log = sys.stderr
    print(f"pesos: {poblacion:,.0f} personas con edad conocida "
          f"({os.path.basename(ESTRUCTURA_EDAD)}; el renglon "
          f"'No especificado' no se reparte)", file=log)
    if muertes_cdc != CDC_TOTAL_DEFUNCIONES:
        print(f"aviso: las defunciones por edad del CDC suman {muertes_cdc:,} y el "
              f"total publicado es {CDC_TOTAL_DEFUNCIONES:,} (redondeo de la fuente)",
              file=log)
    print(f"\n{'grupo':<8}{'COVID-19':>12}{'influenza':>12}", file=log)
    for nombre, _, _ in GRUPOS:
        print(f"{nombre:<8}{covid[nombre] * 100:>11.4g}%{influenza[nombre] * 100:>11.4g}%",
              file=log)
    for etiqueta, tabla in (("COVID-19", covid), ("influenza", influenza)):
        global_ = sum(tabla[n] * sum(pesos[i:f + 1]) for n, i, f in GRUPOS) / poblacion
        print(f"IFR implicito para la estructura de Nuevo Leon, {etiqueta}: "
              f"{global_:.4%}", file=log)

    print(f"""-- =============================================================================
-- 020_letalidad_por_edad.sql
-- Dominio: catalogos.
-- Generado por datos/scripts/build_letalidad_edad.py: no editar a mano.
--
-- Reemplaza la tabla `letalidad_por_edad` de COVID-19 e influenza, que venia
-- con cifras redondas sin ninguna fuente, por uno derivado de literatura
-- publicada. Es el parametro que decide los fallecimientos de la simulacion y
-- el que mas varia entre grupos: del mas joven al mas viejo hay tres ordenes de
-- magnitud.
--
-- El motor lee esta tabla en lugar de la letalidad global cuando el escenario
-- trae la poblacion abierta por grupos de edad.
--
-- LAS DOS VAN MARCADAS COMO SUPUESTO. Las cifras por edad de las fuentes si
-- estan publicadas, pero ninguna publica los cinco grupos que usa el motor:
-- reagruparlas ponderando por la estructura de edad de Nuevo Leon es aritmetica
-- del equipo. El campo "fuente" de cada una explica el procedimiento completo.
--
-- NO PISA LO CAPTURADO A MANO: solo actua si la tabla que hay no tiene todavia
-- un campo "fuente", es decir si sigue siendo la inventada.
-- =============================================================================

BEGIN;

{bloque_sql("INFLUENZA_ESTACIONAL", "Influenza estacional A(H1N1)", influenza, FUENTE_INFLUENZA)}
{bloque_sql("SARS_COV_2_ANCESTRAL", "SARS-CoV-2 (linaje ancestral)", covid, FUENTE_COVID)}
INSERT INTO schema_migrations (version, description)
VALUES ('020', 'Catalogos: letalidad por grupo de edad de COVID-19 e influenza')
ON CONFLICT (version) DO NOTHING;

COMMIT;""")


if __name__ == "__main__":
    main()
