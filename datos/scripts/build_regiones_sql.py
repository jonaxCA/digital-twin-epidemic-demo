"""
Genera datos/postgres/semillas/nl_municipios_completos.sql: agrega a la tabla `regions` los 41
municipios de Nuevo Leon que no vienen en 010_datos_iniciales.sql.

Entradas:
  - datos/censo/nl_poblacion_municipios_1990_2020.tsv poblacion oficial (INEGI,
    censos 1990-2020). Ver el encabezado del archivo para la fuente exacta.
  - datos/censo/nl_poblacion_60mas_2020.tsv  personas de 60 anios y mas por
    municipio (INEGI, ITER 2020).
  - datos/censo/nl_estructura_edad_2020.tsv  estructura por edad del estado;
    solo se usa para validar la suma de 60 y mas.
  - datos/geo/nl_centroides.json       centroides calculados sobre la geometria
    oficial; lo genera datos/scripts/build_municipios_inegi.py
  - datos/geo/nl_catalogo_oficial.json catalogo INEGI de clave -> nombre

La poblacion ya NO es aproximada: sale del censo. Antes estos 41 municipios
llevaban cifras de orden de magnitud, con errores de hasta 82% (Pesqueria tenia
26,000 contra 147,624 reales), lo que distorsionaba la incidencia por cada
100,000 habitantes justo en los municipios de mayor crecimiento.

POR QUE LA SEMILLA TRAE TAMBIEN population_60plus
Las migraciones 015 y 016 corrigen por `code` las filas que YA existen cuando
corren, y viven dentro de dump_completo.sql, que se carga ANTES que esta
semilla. Los 41 municipios que agrega este archivo nacen despues, asi que esas
migraciones nunca los alcanzan: si la cifra no viene aqui, quedan con poblacion
aproximada y sin ningun dato de 60 y mas (issue #49). Traerla desde el INSERT
cierra el hueco sin agregar un paso mas a la instalacion.

Cada corrida valida, y falla en vez de generar un SQL con cifras mal:
  - la suma de los 51 municipios cuadra con el total estatal en TODOS los anios
    censales del tabulado de serie;
  - el POBTOT del ITER coincide, municipio por municipio, con ese tabulado
    (son dos productos distintos del mismo censo);
  - la suma de los 51 valores de 60 y mas cuadra con el total estatal que sale
    de la estructura por edad, que es un tercer archivo;
  - ningun municipio tiene mas gente de 60 y mas que habitantes, que es ademas
    el CHECK que impone la base.

Uso (desde la raiz del proyecto, despues de build_municipios_inegi.py):
    python3 datos/scripts/build_regiones_sql.py > datos/postgres/semillas/nl_municipios_completos.sql
"""
import json
import os
import sys
import unicodedata

# Carpeta de datos: este script vive en datos/scripts/, y tanto la geometria
# como el censo cuelgan de datos/ (no de la raiz del repositorio).
DATOS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEO_DIR = os.path.join(DATOS_DIR, "geo")
CENSO = os.path.join(DATOS_DIR, "censo", "nl_poblacion_municipios_1990_2020.tsv")
CENSO_60 = os.path.join(DATOS_DIR, "censo", "nl_poblacion_60mas_2020.tsv")
ESTRUCTURA_EDAD = os.path.join(DATOS_DIR, "censo", "nl_estructura_edad_2020.tsv")

# Edad, en anios cumplidos, a partir de la cual cuenta como poblacion mayor.
EDAD_MAYOR = 60

ANIO = "2020"

# Los 10 municipios que ya siembra 010_datos_iniciales.sql. La migracion
# 015 es la que corrige su poblacion; aqui solo se insertan los que faltan.
YA_EXISTEN = {"006", "018", "019", "021", "026", "031", "039", "046", "048", "049"}

# El tabulado usa el nombre corto; el catalogo oficial, el completo.
ALIAS = {"carmen": "el carmen"}


def normaliza(s):
    s = unicodedata.normalize("NFKD", s.strip().lower())
    return " ".join(s.encode("ascii", "ignore").decode("ascii").split())


def lee_censo(catalogo):
    """{clave INEGI de 3 digitos: poblacion} para ANIO, ya validado."""
    filas = []
    with open(CENSO, encoding="utf-8") as f:
        for linea in f:
            if linea.startswith("#") or not linea.strip():
                continue
            filas.append(linea.rstrip("\n").split("\t"))

    municipios = filas[0][2:]
    por_nombre = {normaliza(v): k for k, v in catalogo.items()}
    claves = []
    for nombre in municipios:
        clave = por_nombre.get(ALIAS.get(normaliza(nombre), normaliza(nombre)))
        if clave is None:
            raise SystemExit(f"'{nombre}' no esta en el catalogo oficial de INEGI")
        claves.append(clave)

    if len(set(claves)) != len(catalogo):
        raise SystemExit(f"el tabulado trae {len(set(claves))} municipios, "
                         f"el catalogo {len(catalogo)}")

    def num(x):
        return int(float(x.replace(",", "")))

    poblacion = {}
    for fila in filas[1:]:
        anio, estatal, valores = fila[0], num(fila[1]), [num(v) for v in fila[2:]]
        # Invariante del dataset: los municipios suman el estado, cada anio.
        if sum(valores) != estatal:
            raise SystemExit(f"{anio}: los municipios suman {sum(valores):,} pero el "
                             f"total estatal es {estatal:,} "
                             f"(diferencia {estatal - sum(valores):+,})")
        if anio == ANIO:
            poblacion = dict(zip(claves, valores))

    if not poblacion:
        raise SystemExit(f"el tabulado no trae el anio {ANIO}")
    return poblacion


def _filas_tsv(ruta):
    """Filas utiles de un TSV del censo: sin comentarios ni lineas en blanco."""
    with open(ruta, encoding="utf-8") as f:
        crudas = f.read().splitlines()
    return [l.split("	") for l in crudas
            if not l.startswith("#") and l.strip()]


def total_60mas_estatal():
    """Personas de 60 y mas en todo Nuevo Leon, sumando los grupos quinquenales
    del tabulado de estructura por edad.

    Es un archivo distinto del ITER, asi que sirve de control independiente: si
    alguien edita el detalle municipal, la suma deja de cuadrar y el script
    falla en vez de sembrar cifras mal.
    """
    total = 0
    for fila in _filas_tsv(ESTRUCTURA_EDAD)[1:]:
        # "Total" y "No especificado" no empiezan con un numero: se saltan.
        edad = fila[0].strip().split(" ", 1)[0]
        if edad.isdigit() and int(edad) >= EDAD_MAYOR:
            total += int(fila[1])
    if total <= 0:
        raise SystemExit(f"no se pudo leer el total de {EDAD_MAYOR}+ en "
                         f"{ESTRUCTURA_EDAD}")
    return total


def lee_60mas(poblacion):
    """{clave INEGI de 3 digitos: personas de 60 y mas}, ya validado.

    `poblacion` es lo que devolvio lee_censo(); se usa para cruzar el POBTOT del
    ITER contra el tabulado de serie censal, municipio por municipio.
    """
    p60, pobtot = {}, {}
    for fila in _filas_tsv(CENSO_60)[1:]:      # la primera fila es el encabezado
        clave = fila[0].strip()
        if not clave.isdigit():
            continue
        clave = clave.zfill(3)
        pobtot[clave] = int(fila[2])
        p60[clave] = int(fila[3])

    if len(p60) != len(poblacion):
        raise SystemExit(f"el ITER trae {len(p60)} municipios y el tabulado de "
                         f"serie censal {len(poblacion)}")

    discrepan = [(c, pobtot[c], poblacion[c]) for c in sorted(p60)
                 if pobtot[c] != poblacion.get(c)]
    if discrepan:
        detalle = ", ".join(f"{c}: ITER {a:,} vs serie {b:,}"
                            for c, a, b in discrepan[:5])
        raise SystemExit(f"{len(discrepan)} municipio(s) con poblacion distinta "
                         f"entre los dos tabulados del censo -- {detalle}")

    esperado = total_60mas_estatal()
    suma = sum(p60.values())
    if suma != esperado:
        raise SystemExit(f"los municipios suman {suma:,} personas de "
                         f"{EDAD_MAYOR}+ pero la estructura por edad da "
                         f"{esperado:,} (diferencia {esperado - suma:+,})")

    imposibles = [(c, p60[c], poblacion[c]) for c in sorted(p60)
                  if p60[c] > poblacion[c]]
    if imposibles:
        raise SystemExit(f"municipios con mas gente de {EDAD_MAYOR}+ que "
                         f"habitantes: {imposibles[:5]}")
    return p60


def main():
    sys.stdout.reconfigure(newline="\n")   # LF tambien en Windows
    centroides = json.load(open(os.path.join(GEO_DIR, "nl_centroides.json"), encoding="utf-8"))
    catalogo = json.load(open(os.path.join(GEO_DIR, "nl_catalogo_oficial.json"), encoding="utf-8"))
    poblacion = lee_censo(catalogo)
    poblacion_60 = lee_60mas(poblacion)

    lines = []
    lines.append("-- =============================================================================")
    lines.append("-- nl_municipios_completos.sql")
    lines.append("-- Agrega los 41 municipios de Nuevo Leon que no vienen en")
    lines.append("-- 010_datos_iniciales.sql (catalogo INEGI real, geometria real).")
    lines.append("-- Generado por datos/scripts/build_regiones_sql.py: no editar a mano.")
    lines.append(f"-- Poblacion: Censo de Poblacion y Vivienda {ANIO}, INEGI.")
    lines.append(f"-- Poblacion de {EDAD_MAYOR} y mas: ITER {ANIO}, INEGI.")
    lines.append("-- Fuentes: datos/censo/nl_poblacion_municipios_1990_2020.tsv y")
    lines.append("--          datos/censo/nl_poblacion_60mas_2020.tsv")
    lines.append("--")
    lines.append("-- Las cifras van en el INSERT y no en una migracion posterior porque")
    lines.append("-- dump_completo.sql (donde viven 015 y 016) se carga ANTES que este")
    lines.append("-- archivo, y esas migraciones solo alcanzan filas que ya existen.")
    lines.append("-- =============================================================================")
    lines.append("")
    lines.append("BEGIN;")
    lines.append("")
    lines.append("INSERT INTO regions (code, name, level, parent_region_id, population,")
    lines.append("                     population_60plus, centroid_lat, centroid_lon)")
    lines.append("SELECT v.code, v.name, 'municipio', e.id, v.pob, v.pob60, v.lat, v.lon")
    lines.append("FROM (VALUES")

    rows = []
    for cod, nombre in catalogo.items():
        if cod in YA_EXISTEN:
            continue
        region_code = f"19{cod}"
        if region_code not in centroides:
            raise SystemExit(f"sin centroide para {cod} {nombre}")
        lat = centroides[region_code]["lat"]
        lon = centroides[region_code]["lon"]
        nombre_sql = nombre.replace("'", "''")
        rows.append(f"    ('{region_code}', '{nombre_sql}', {poblacion[cod]}, "
                    f"{poblacion_60[cod]}, {lat}, {lon})")

    lines.append(",\n".join(rows))
    lines.append(") AS v(code, name, pob, pob60, lat, lon)")
    lines.append("CROSS JOIN (SELECT id FROM regions WHERE code = '19') e")
    lines.append("ON CONFLICT (code) DO NOTHING;")
    lines.append("")
    lines.append("COMMIT;")

    print("\n".join(lines))


if __name__ == "__main__":
    main()
