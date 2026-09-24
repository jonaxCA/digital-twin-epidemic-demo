"""
Genera nl_municipios_completos.sql: agrega a la tabla `regions` los 41
municipios de Nuevo Leon que no vienen en 010_datos_iniciales.sql.

Requiere haber corrido antes scripts/build_municipios_inegi.py (usa su salida
data/geo/nl_centroides.json, que trae los 51 municipios con centroide
calculado sobre la geometria oficial de INEGI).

Poblacion: NO es dato de censo oficial verificado para los 41 municipios
nuevos -- es una aproximacion de orden de magnitud solo para que el calculo
de incidencia no falle (estos municipios no llevan casos sinteticos, asi que
el valor exacto no cambia nada visible). Si necesitas cifras reales, sustituye
POBLACION_APROX por datos del censo de INEGI.

Uso (desde la raiz del proyecto, despues de build_municipios_inegi.py):
    python3 scripts/build_regiones_sql.py > db/datos/nl_municipios_completos.sql
"""
import json
import os
import sys

# Raiz del proyecto: este script vive en scripts/.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEO_DIR = os.path.join(BASE_DIR, "data", "geo")

POBLACION_APROX = {
    "001": 2600, "002": 3500, "003": 1200, "004": 33000, "005": 19000,
    "007": 14000, "008": 3300, "009": 100000, "010": 40000, "011": 8300,
    "012": 50000, "013": 11500, "014": 36000, "015": 1300, "016": 3000,
    "017": 40000, "020": 5300, "022": 14000, "023": 1400, "024": 4700,
    "025": 50000, "027": 1500, "028": 1700, "029": 7300, "030": 3300,
    "032": 5000, "033": 90000, "034": 7500, "035": 1000, "036": 5500,
    "037": 5600, "038": 76000, "040": 700, "041": 26000, "042": 5900,
    "043": 2200, "044": 33000, "045": 76000, "047": 16000, "050": 700,
    "051": 4500,
}

YA_EXISTEN = {"006", "018", "019", "021", "026", "031", "039", "046", "048", "049"}


def main():
    sys.stdout.reconfigure(newline="\n")   # LF tambien en Windows
    centroides = json.load(open(os.path.join(GEO_DIR, "nl_centroides.json")))
    catalogo = json.load(open(os.path.join(GEO_DIR, "nl_catalogo_oficial.json")))

    lines = []
    lines.append("-- =============================================================================")
    lines.append("-- nl_municipios_completos.sql")
    lines.append("-- Agrega los 41 municipios de Nuevo Leon que no vienen en")
    lines.append("-- 010_datos_iniciales.sql (catalogo INEGI real, geometria real).")
    lines.append("-- Generado por build_regiones_sql.py: no editar a mano.")
    lines.append("-- PENDIENTE: la poblacion de estos 41 es aproximada, no es censo")
    lines.append("-- verificado -- ver docstring de build_regiones_sql.py.")
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
        pob = POBLACION_APROX[cod]
        nombre_sql = nombre.replace("'", "''")
        rows.append(f"    ('{region_code}', '{nombre_sql}', {pob}, {lat}, {lon})")

    lines.append(",\n".join(rows))
    lines.append(") AS v(code, name, pob, lat, lon)")
    lines.append("CROSS JOIN (SELECT id FROM regions WHERE code = '19') e")
    lines.append("ON CONFLICT (code) DO NOTHING;")
    lines.append("")
    lines.append("COMMIT;")

    print("\n".join(lines))


if __name__ == "__main__":
    main()
