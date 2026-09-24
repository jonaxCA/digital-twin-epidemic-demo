"""
Genera db/datos/nl_municipios_completos.sql: agrega a la tabla `regions` los 41
municipios de Nuevo Leon que no vienen en 010_datos_iniciales.sql.

Entradas:
  - data/censo/nl_poblacion_municipios_1990_2020.tsv  poblacion oficial (INEGI,
    censos 1990-2020). Ver el encabezado del archivo para la fuente exacta.
  - data/geo/nl_centroides.json       centroides calculados sobre la geometria
    oficial; lo genera scripts/build_municipios_inegi.py
  - data/geo/nl_catalogo_oficial.json catalogo INEGI de clave -> nombre

La poblacion ya NO es aproximada: sale del censo. Antes estos 41 municipios
llevaban cifras de orden de magnitud, con errores de hasta 82% (Pesqueria tenia
26,000 contra 147,624 reales), lo que distorsionaba la incidencia por cada
100,000 habitantes justo en los municipios de mayor crecimiento.

Cada corrida verifica que la suma de los 51 municipios cuadre con el total
estatal en TODOS los anios censales del archivo. Si un dato se corrompe al
editarlo, el script falla en vez de generar un SQL con cifras mal.

Uso (desde la raiz del proyecto, despues de build_municipios_inegi.py):
    python3 scripts/build_regiones_sql.py > db/datos/nl_municipios_completos.sql
"""
import json
import os
import sys
import unicodedata

# Raiz del proyecto: este script vive en scripts/.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEO_DIR = os.path.join(BASE_DIR, "data", "geo")
CENSO = os.path.join(BASE_DIR, "data", "censo", "nl_poblacion_municipios_1990_2020.tsv")

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


def main():
    sys.stdout.reconfigure(newline="\n")   # LF tambien en Windows
    centroides = json.load(open(os.path.join(GEO_DIR, "nl_centroides.json"), encoding="utf-8"))
    catalogo = json.load(open(os.path.join(GEO_DIR, "nl_catalogo_oficial.json"), encoding="utf-8"))
    poblacion = lee_censo(catalogo)

    lines = []
    lines.append("-- =============================================================================")
    lines.append("-- nl_municipios_completos.sql")
    lines.append("-- Agrega los 41 municipios de Nuevo Leon que no vienen en")
    lines.append("-- 010_datos_iniciales.sql (catalogo INEGI real, geometria real).")
    lines.append("-- Generado por scripts/build_regiones_sql.py: no editar a mano.")
    lines.append(f"-- Poblacion: Censo de Poblacion y Vivienda {ANIO}, INEGI.")
    lines.append("-- Ver data/censo/nl_poblacion_municipios_1990_2020.tsv para la fuente.")
    lines.append("-- =============================================================================")
    lines.append("")
    lines.append("BEGIN;")
    lines.append("")
    lines.append("INSERT INTO regions (code, name, level, parent_region_id, population, centroid_lat, centroid_lon)")
    lines.append("SELECT v.code, v.name, 'municipio', e.id, v.pob, v.lat, v.lon")
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
        rows.append(f"    ('{region_code}', '{nombre_sql}', {poblacion[cod]}, {lat}, {lon})")

    lines.append(",\n".join(rows))
    lines.append(") AS v(code, name, pob, lat, lon)")
    lines.append("CROSS JOIN (SELECT id FROM regions WHERE code = '19') e")
    lines.append("ON CONFLICT (code) DO NOTHING;")
    lines.append("")
    lines.append("COMMIT;")

    print("\n".join(lines))


if __name__ == "__main__":
    main()
