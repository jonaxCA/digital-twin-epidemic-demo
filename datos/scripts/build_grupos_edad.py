"""
Genera, a partir del ITER 2020 de INEGI:

  - datos/censo/nl_estructura_edad_municipios_2020.tsv
  - datos/postgres/migraciones/021_poblacion_por_grupo_edad.sql

POR QUE
`regions` solo guarda poblacion total y poblacion de 60 y mas, o sea dos grupos.
La tabla de letalidad del catalogo (020) esta abierta en cinco: 0-19, 20-39,
40-59, 60-79 y 80+. Un escenario municipal estratificado por edad se rechazaba
porque los grupos no coinciden ("letalidad no define los grupos: 0-59, 60+").
Con esto, cada municipio trae los cinco grupos que el motor espera.

LAS CIFRAS NO SE DERIVAN DE NADA: los cinco grupos son sumas exactas de las
columnas quinquenales que publica el ITER. Ningun limite queda partido, asi que
no hay ningun supuesto de reparto.

    0-19  = P_0A4 + P_5A9 + P_10A14 + P_15A19
    20-39 = P_20A24 + P_25A29 + P_30A34 + P_35A39
    40-59 = P_40A44 + P_45A49 + P_50A54 + P_55A59
    60-79 = P_60A64 + P_65A69 + P_70A74 + P_75A79
    80+   = P_80A84 + P_85YMAS

OJO CON LA EDAD NO ESPECIFICADA
Las columnas de edad del ITER no suman POBTOT: el censo deja fuera a quien no
declaro su edad. En Nuevo Leon son 18,132 personas (0.31%), repartidas en 30 de
los 51 municipios. Este script NO las reparte entre los grupos, porque eso seria
inventar en que edad estan: los cinco grupos son dato censal observado y una
imputacion los volveria estimaciones. Van como una sexta categoria propia,
`edad_no_especificada`, con lower_bound NULL para que ninguna consulta la
confunda con una banda de edad. Quien arme un escenario tiene que decidir
explicitamente que hace con ella; el motor no la reparte solo.

VALIDACIONES, en cada corrida; si una falla, no se escribe nada:
  - los 51 municipios, sin celdas censuradas con asterisco;
  - los cinco grupos suman POBTOT menos la edad no especificada, municipio por
    municipio;
  - 60-79 + 80+ coincide con P_60YMAS del propio ITER, y con la columna
    `population_60plus` que ya cargo la migracion 016;
  - el total estatal da 5,784,442 habitantes y 654,050 de 60 y mas.

ENTRADA
El archivo de datos del ITER no se guarda en el repositorio (3.4 MB de 276
indicadores por localidad). Se descarga de
https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/iter/
como iter_19_cpv2020_csv.zip y se le pasa la ruta al CSV descomprimido.

Uso (desde la raiz del proyecto):
    python3 datos/scripts/build_grupos_edad.py <ruta>/conjunto_de_datos_iter_19CSV20.csv

Escribe los dos archivos y resume en pantalla lo que valido. No usa redireccion
de salida, a diferencia de los otros generadores, porque produce dos archivos.
"""
import csv
import hashlib
import io
import os
import sys

DATOS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TSV_SALIDA = os.path.join(DATOS_DIR, "censo", "nl_estructura_edad_municipios_2020.tsv")
SQL_SALIDA = os.path.join(DATOS_DIR, "postgres", "migraciones",
                          "021_poblacion_por_grupo_edad.sql")
CENSO_60 = os.path.join(DATOS_DIR, "censo", "nl_poblacion_60mas_2020.tsv")

ENTIDAD = "19"
ESTADO_CODE = "19"
POBLACION_ESTATAL = 5_784_442
SESENTA_MAS_ESTATAL = 654_050

# Categoria administrativa, NO un grupo de edad: quien no declaro su edad. Va en
# la misma tabla para que el dato este donde se usa, pero con lower_bound NULL,
# que es lo que la distingue de una banda real en cualquier consulta.
GRUPO_SIN_EDAD = "edad_no_especificada"

# grupo del motor -> columnas quinquenales del ITER que lo forman
GRUPOS = [
    ("0-19",   0, ["P_0A4", "P_5A9", "P_10A14", "P_15A19"]),
    ("20-39", 20, ["P_20A24", "P_25A29", "P_30A34", "P_35A39"]),
    ("40-59", 40, ["P_40A44", "P_45A49", "P_50A54", "P_55A59"]),
    ("60-79", 60, ["P_60A64", "P_65A69", "P_70A74", "P_75A79"]),
    ("80+",   80, ["P_80A84", "P_85YMAS"]),
]


def lee_iter(ruta):
    """Filas de total municipal del ITER: LOC 0000 y MUN distinto de 000."""
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            with io.open(ruta, encoding=enc, newline="") as f:
                filas = list(csv.reader(f))
            break
        except UnicodeDecodeError:
            continue
    else:
        raise SystemExit(f"no se pudo leer {ruta} con ninguna codificacion conocida")

    ix = {c: i for i, c in enumerate(filas[0])}
    faltan = [c for _, _, cols in GRUPOS for c in cols if c not in ix]
    if faltan:
        raise SystemExit(f"al CSV le faltan columnas del ITER: {faltan}")
    return ix, [f for f in filas[1:]
                if f[ix["LOC"]].strip() == "0000" and f[ix["MUN"]].strip() != "000"]


def entero(celda, contexto):
    """El ITER censura con asterisco las localidades de una o dos viviendas. En
    un total municipal no deberia pasar nunca; si pasa, es mejor fallar."""
    crudo = celda.strip()
    if not crudo.isdigit():
        raise SystemExit(f"valor no numerico en {contexto}: {crudo!r}")
    return int(crudo)


def sesenta_mas_cargado():
    """{clave de 3 digitos: P_60YMAS} del extracto que ya esta en el repositorio."""
    salida = {}
    with io.open(CENSO_60, encoding="utf-8") as f:
        for linea in f:
            if linea.startswith("#") or not linea.strip():
                continue
            campos = linea.rstrip("\n").split("\t")
            if campos[0].strip().isdigit():
                salida[campos[0].strip().zfill(3)] = int(campos[3])
    return salida


def arma(ix, filas):
    p60_repo = sesenta_mas_cargado()
    municipios = []
    for f in filas:
        clave = f[ix["MUN"]].strip().zfill(3)
        nombre = f[ix["NOM_MUN"]].strip()
        pobtot = entero(f[ix["POBTOT"]], f"{clave} POBTOT")
        grupos = {g: sum(entero(f[ix[c]], f"{clave} {c}") for c in cols)
                  for g, _, cols in GRUPOS}

        suma = sum(grupos.values())
        if suma > pobtot:
            raise SystemExit(f"{clave} {nombre}: los grupos suman {suma:,} y POBTOT "
                             f"es {pobtot:,}")
        p60_iter = entero(f[ix["P_60YMAS"]], f"{clave} P_60YMAS")
        if grupos["60-79"] + grupos["80+"] != p60_iter:
            raise SystemExit(f"{clave} {nombre}: 60-79 + 80+ da "
                             f"{grupos['60-79'] + grupos['80+']:,} y P_60YMAS es "
                             f"{p60_iter:,}")
        if clave in p60_repo and p60_repo[clave] != p60_iter:
            raise SystemExit(f"{clave} {nombre}: el ITER da {p60_iter:,} de 60+ y el "
                             f"extracto del repositorio {p60_repo[clave]:,}")

        municipios.append({"clave": clave, "nombre": nombre, "pobtot": pobtot,
                           "grupos": grupos, "sin_edad": pobtot - suma})

    if len(municipios) != 51:
        raise SystemExit(f"se encontraron {len(municipios)} municipios, no 51")
    total = sum(m["pobtot"] for m in municipios)
    if total != POBLACION_ESTATAL:
        raise SystemExit(f"el estado suma {total:,} y el censo da {POBLACION_ESTATAL:,}")
    total60 = sum(m["grupos"]["60-79"] + m["grupos"]["80+"] for m in municipios)
    if total60 != SESENTA_MAS_ESTATAL:
        raise SystemExit(f"el estado suma {total60:,} de 60+ y el censo da "
                         f"{SESENTA_MAS_ESTATAL:,}")
    return municipios


def escribe_tsv(municipios, huella):
    nombres = [g for g, _, _ in GRUPOS]
    sin_edad = sum(m["sin_edad"] for m in municipios)
    lineas = [
        "# Poblacion por grupo de edad y municipio, Nuevo Leon. Censo 2020.",
        "#",
        "# FUENTE",
        "#   INEGI. Censo de Poblacion y Vivienda 2020, ITER (Principales resultados",
        "#   por localidad), entidad 19. Archivo iter_19_cpv2020_csv.zip de los datos",
        "#   abiertos del censo, descargado de:",
        "#   https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/iter/",
        f"#   sha256 del CSV de datos usado: {huella}",
        "#",
        "#   Se tomaron las filas de total municipal (LOC 0000) y las 18 columnas",
        "#   quinquenales, agrupadas en los cinco grupos que usa el motor. Cada grupo",
        "#   es una suma exacta de columnas publicadas: ningun limite queda partido y",
        "#   no hay ningun reparto supuesto.",
        "#",
        "# EDAD NO ESPECIFICADA",
        "#   Las columnas de edad del ITER no suman POBTOT: quien no declaro su edad",
        f"#   queda fuera. En Nuevo Leon son {sin_edad:,} personas",
        f"#   ({sin_edad / POBLACION_ESTATAL:.2%}), en "
        f"{sum(1 for m in municipios if m['sin_edad']):,} de los 51 municipios.",
        "#   No se reparten entre los grupos, porque no se sabe que edad tienen; van",
        "#   en su propia columna para que el dato quede a la vista.",
        "#",
        "# VALIDACION, hecha al generar el archivo",
        "#   - los cinco grupos suman POBTOT menos la edad no especificada, en los 51;",
        "#   - 60-79 + 80+ coincide con P_60YMAS del ITER y con",
        "#     nl_poblacion_60mas_2020.tsv, en los 51;",
        f"#   - el estado suma {POBLACION_ESTATAL:,} habitantes y "
        f"{SESENTA_MAS_ESTATAL:,} de 60 y mas.",
        "#",
        "# Generado por datos/scripts/build_grupos_edad.py: no editar a mano.",
        "",
        "\t".join(["clave", "municipio", "poblacion_total",
                   *[g.replace("+", "ymas").replace("-", "_") for g in nombres],
                   "edad_no_especificada"]),
    ]
    for m in sorted(municipios, key=lambda x: x["clave"]):
        lineas.append("\t".join([m["clave"], m["nombre"], str(m["pobtot"]),
                                 *[str(m["grupos"][g]) for g in nombres],
                                 str(m["sin_edad"])]))
    io.open(TSV_SALIDA, "w", encoding="utf-8", newline="\n").write("\n".join(lineas) + "\n")


def escribe_sql(municipios):
    filas = []
    for m in sorted(municipios, key=lambda x: x["clave"]):
        for grupo, inicio, _ in GRUPOS:
            filas.append(f"    ('19{m['clave']}', '{grupo}', {inicio}, "
                         f"{m['grupos'][grupo]})")
        filas.append(f"    ('19{m['clave']}', '{GRUPO_SIN_EDAD}', NULL, "
                     f"{m['sin_edad']})")
    # El estado: la suma de sus 51 municipios, para poder armar escenarios
    # estatales con los mismos grupos.
    for grupo, inicio, _ in GRUPOS:
        total = sum(m["grupos"][grupo] for m in municipios)
        filas.append(f"    ('{ESTADO_CODE}', '{grupo}', {inicio}, {total})")
    filas.append(f"    ('{ESTADO_CODE}', '{GRUPO_SIN_EDAD}', NULL, "
                 f"{sum(m['sin_edad'] for m in municipios)})")

    sin_edad = sum(m["sin_edad"] for m in municipios)
    con_sin_edad = sum(1 for m in municipios if m["sin_edad"])
    cuerpo = f"""-- =============================================================================
-- 021_poblacion_por_grupo_edad.sql
-- Dominio: catalogos.
-- Generado por datos/scripts/build_grupos_edad.py: no editar a mano.
--
-- Agrega `region_age_groups`: la poblacion de cada region abierta en los cinco
-- grupos de edad que usa el motor (0-19, 20-39, 40-59, 60-79, 80+), y la llena
-- con el Censo 2020 para los 51 municipios de Nuevo Leon y para el estado.
--
-- PARA QUE
-- `regions` solo guarda poblacion total y poblacion de 60 y mas, o sea dos
-- grupos. La tabla de letalidad por edad del catalogo (020) esta abierta en
-- cinco. Un escenario municipal estratificado se rechazaba porque los grupos no
-- coinciden. Con esta tabla, armar un escenario por edad sobre un municipio deja
-- de depender de inventar el reparto.
--
-- Los grupos van en una tabla hija y no en columnas de `regions` porque el
-- conjunto de grupos es una decision del modelo, no del catalogo de regiones:
-- cambiarlo no deberia costar un ALTER TABLE ni tocar el resto de las consultas.
--
-- FUENTE: INEGI, Censo 2020, ITER de la entidad 19, filas de total municipal.
-- Cada grupo es una suma exacta de columnas quinquenales publicadas; no hay
-- ningun reparto supuesto. Ver datos/censo/nl_estructura_edad_municipios_2020.tsv,
-- que documenta la descarga y las validaciones.
--
-- LA EDAD NO ESPECIFICADA ES UNA SEXTA CATEGORIA, NO UN SEXTO GRUPO.
-- El censo deja fuera de las columnas de edad a quien no declaro la suya:
-- {sin_edad:,} personas en el estado ({sin_edad / POBLACION_ESTATAL:.2%}), en
-- {con_sin_edad} de los 51 municipios. No se reparten entre los grupos, porque
-- los cinco grupos son dato observado y prorratearlos los convertiria en una
-- imputacion. Se guardan como `{GRUPO_SIN_EDAD}` con `lower_bound` NULL, que es
-- lo que la distingue de una banda de edad:
--
--     grupos de edad reales   ->  WHERE lower_bound IS NOT NULL
--     poblacion con edad      ->  sum(population) FILTER (WHERE lower_bound IS NOT NULL)
--     total de la region      ->  sum(population)  (cuadra con regions.population)
--
-- Quien arme un escenario tiene que decidir explicitamente que hace con ella.
-- El motor no la reparte por su cuenta: exige que el escenario declare la
-- politica (`excluir` o `prorratear`) y, si se prorratea, lo registra como
-- supuesto en la trazabilidad de la corrida.
--
-- Es idempotente: no pisa filas que ya existan.
-- =============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS region_age_groups (
    region_id   INTEGER      NOT NULL,
    age_group   VARCHAR(20)  NOT NULL,
    lower_bound SMALLINT,          -- NULL solo en la categoria administrativa
    population  INTEGER      NOT NULL,

    CONSTRAINT pk_region_age_groups PRIMARY KEY (region_id, age_group),
    CONSTRAINT fk_rag_region
        FOREIGN KEY (region_id) REFERENCES regions (id) ON DELETE CASCADE,
    CONSTRAINT ck_rag_population CHECK (population >= 0),
    CONSTRAINT ck_rag_lower_bound CHECK (lower_bound BETWEEN 0 AND 120),
    -- Una categoria administrativa no tiene edad de inicio, y una banda de edad
    -- siempre la tiene. Ligar las dos cosas impide que alguien meta
    -- 'edad_no_especificada' con un lower_bound inventado, o una banda sin el.
    CONSTRAINT ck_rag_sin_edad CHECK (
        (age_group = '{GRUPO_SIN_EDAD}') = (lower_bound IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS ix_rag_region ON region_age_groups (region_id);

COMMENT ON TABLE region_age_groups IS
    'Poblacion de una region abierta por grupo de edad, en los mismos grupos que usa el motor y que la tabla de letalidad por edad del catalogo, mas la categoria edad_no_especificada. Censo 2020 de INEGI (ITER). La suma de TODAS las filas cuadra con regions.population; la suma de las bandas de edad (lower_bound NOT NULL) es menor, por la gente que no declaro su edad.';
COMMENT ON COLUMN region_age_groups.age_group IS
    'Etiqueta del grupo tal como la espera el motor: 0-19, 20-39, 40-59, 60-79, 80+; o edad_no_especificada, que no es un grupo de edad sino una categoria administrativa. Las cinco primeras tienen que coincidir con las claves de diseases.default_params -> letalidad_por_edad.';
COMMENT ON COLUMN region_age_groups.lower_bound IS
    'Edad con la que empieza el grupo, o NULL en edad_no_especificada. Permite ordenar, resolver intervenciones por edad_minima y distinguir bandas reales de la categoria administrativa sin interpretar la etiqueta.';

-- Los permisos de 009 y los del rol de la aplicacion se otorgaron sobre las
-- tablas que existian entonces, asi que una tabla nueva nace sin acceso para el
-- rol con el que corre la app (ver 019: sin esto, la pantalla falla con
-- "permiso denegado" aunque la migracion no de un solo error).
DO $grants$
DECLARE
    r TEXT;
BEGIN
    FOREACH r IN ARRAY ARRAY['app_catalog', 'epidemia_app']
    LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format(
                'GRANT SELECT, INSERT, UPDATE, DELETE ON region_age_groups TO %I', r);
        END IF;
    END LOOP;
END
$grants$;

INSERT INTO region_age_groups (region_id, age_group, lower_bound, population)
SELECT r.id, v.grupo, v.inicio, v.pob
FROM (VALUES
{",\n".join(filas)}
) AS v(code, grupo, inicio, pob)
JOIN regions r ON r.code = v.code
ON CONFLICT (region_id, age_group) DO NOTHING;

INSERT INTO schema_migrations (version, description)
VALUES ('021', 'Catalogos: poblacion por grupo de edad de los 51 municipios y el estado (Censo 2020)')
ON CONFLICT (version) DO NOTHING;

COMMIT;
"""
    io.open(SQL_SALIDA, "w", encoding="utf-8", newline="\n").write(cuerpo)


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__.strip().splitlines()[-4].strip())
    ruta = sys.argv[1]
    huella = hashlib.sha256(open(ruta, "rb").read()).hexdigest()

    ix, filas = lee_iter(ruta)
    municipios = arma(ix, filas)
    escribe_tsv(municipios, huella)
    escribe_sql(municipios)

    sin_edad = sum(m["sin_edad"] for m in municipios)
    print(f"{len(municipios)} municipios validados")
    print(f"  poblacion total   {sum(m['pobtot'] for m in municipios):,}")
    for grupo, _, _ in GRUPOS:
        total = sum(m["grupos"][grupo] for m in municipios)
        print(f"  {grupo:<6}          {total:>11,}")
    print(f"  edad no especif.  {sin_edad:>11,}  ({sin_edad / POBLACION_ESTATAL:.2%}, "
          f"en {sum(1 for m in municipios if m['sin_edad'])} municipios)")
    print(f"\nescrito: {os.path.relpath(TSV_SALIDA, os.path.dirname(DATOS_DIR))}")
    print(f"escrito: {os.path.relpath(SQL_SALIDA, os.path.dirname(DATOS_DIR))}")


if __name__ == "__main__":
    main()
