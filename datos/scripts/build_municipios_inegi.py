"""
Construye frontend_web/app/static/js/nl_municipios.json (geometria de los municipios de Nuevo
Leon) a partir de la capa municipal oficial del Marco Geoestadistico de INEGI.

Sustituye a build_municipios_full.py, cuya fuente (geojson comunitario por
nombre de municipio) solo traia 50 de los 51 municipios -- le faltaba
Hualahuises -- y venia ya generalizada.

Entrada:
  - datos/geo/inegi_mg2024/19mun.shp     capa municipal del Marco Geoestadistico
    2024, entidad 19. Descargada de:
    https://www.inegi.org.mx/contenidos/productos/prod_serv/contenidos/espanol/
      bvinegi/productos/geografia/marcogeo/794551132173/19_nuevoleon.zip
    (el zip completo son ~98 MB con todas las capas; aqui solo se guardo
    19mun.* porque es la unica que usa el mapa)
  - datos/geo/nl_catalogo_oficial.json    catalogo INEGI clave -> nombre oficial

Dos detalles de la fuente que hay que respetar:
  - El .cpg original dice "iso 88591" (mal escrito, sin guion) y pyshp truena
    al leerlo, por eso aqui se fuerza latin-1.
  - La geometria viene proyectada en Lambert Conica Conforme (EPSG:6372,
    "Mexico ITRF2008 / LCC"), en metros. Highcharts necesita lon/lat, asi que
    se reproyecta a EPSG:4326 leyendo el CRS del propio .prj.

A diferencia de la fuente anterior, CVEGEO ya trae la clave completa de 5
digitos ('19029'), que es exactamente el formato de regions.code -- no hace
falta emparejar por nombre. El catalogo solo se usa para que el nombre que se
dibuja en el mapa sea el mismo que el de la base.

Salida:
  - frontend_web/app/static/js/nl_municipios.json   el geojson que consume Highcharts Maps
  - datos/geo/nl_centroides.json    codigo -> {name, lat, lon}, insumo de
                                   datos/scripts/build_regiones_sql.py

Dependencias (solo de build -- no van en requirements.txt, que es el runtime
de la app):
    pip install pyshp pyproj shapely

Uso (las rutas se resuelven desde la raiz del proyecto, no desde donde se corra):
    python3 datos/scripts/build_municipios_inegi.py [--tolerancia GRADOS] [--sweep]

La tolerancia es el argumento de shapely.simplify, en grados. El default
(0.0012) deja el error de simplificacion por debajo del pixel a la escala a la
que se dibuja el estado, asi que las fronteras compartidas no abren huecos
visibles. --sweep no escribe nada: solo tabula tamano vs tolerancia.
"""
import argparse
import gzip
import json
import os
import warnings

import shapefile
from pyproj import CRS, Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform as shapely_transform

# Carpeta datos/: este script vive en datos/scripts/.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEO_DIR = os.path.join(BASE_DIR, "geo")
SHP = os.path.join(GEO_DIR, "inegi_mg2024", "19mun")
CATALOGO = os.path.join(GEO_DIR, "nl_catalogo_oficial.json")
OUT_GEOJSON = os.path.join(os.path.dirname(BASE_DIR), "frontend_web", "app", "static", "js", "nl_municipios.json")
OUT_CENTROIDES = os.path.join(GEO_DIR, "nl_centroides.json")

TOLERANCIA_DEFAULT = 0.0012


def cargar_municipios():
    """Lee el shapefile y devuelve [(region_code, nombre, geometria lon/lat)],
    ya reproyectado a WGS84 pero sin simplificar."""
    with open(SHP + ".prj", encoding="utf-8") as f:
        crs_origen = CRS.from_wkt(f.read())
    transformer = Transformer.from_crs(crs_origen, CRS.from_epsg(4326), always_xy=True)

    catalogo = json.load(open(CATALOGO, encoding="utf-8"))

    # encoding explicito: el .cpg de INEGI trae un nombre de codec invalido
    # ("iso 88591"). Se ignora el aviso de pyshp por discrepancia con el .cpg.
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*different to encoding read from .cpg.*")
        reader = shapefile.Reader(SHP, encoding="latin-1")

    salida = []
    for sr in reader.iterShapeRecords():
        rec = sr.record.as_dict()
        cve_mun = rec["CVE_MUN"]
        region_code = rec["CVEGEO"]
        nombre = catalogo.get(cve_mun, rec["NOMGEO"])

        geom = shape(sr.shape.__geo_interface__)
        if not geom.is_valid:
            geom = geom.buffer(0)
        geom = shapely_transform(transformer.transform, geom)
        if not geom.is_valid:
            geom = geom.buffer(0)
        salida.append((region_code, nombre, geom))

    salida.sort(key=lambda x: x[0])
    return salida, catalogo


def contar_vertices(geom):
    m = mapping(geom)
    polys = [m["coordinates"]] if m["type"] == "Polygon" else m["coordinates"]
    return sum(len(anillo) for poly in polys for anillo in poly)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tolerancia", type=float, default=TOLERANCIA_DEFAULT)
    ap.add_argument("--sweep", action="store_true")
    args = ap.parse_args()

    municipios, catalogo = cargar_municipios()
    print(f"leidos: {len(municipios)} municipios de {len(catalogo)} en el catalogo")
    faltantes = set(catalogo) - {c[2:] for c, _, _ in municipios}
    if faltantes:
        print(f"AVISO -- sin geometria: {sorted(faltantes)}")

    if args.sweep:
        print()
        print(f"{'tolerancia':>12} {'vertices':>10} {'crudo KB':>10} {'gzip KB':>9}")
        for tol in (0.0, 0.0005, 0.0008, 0.0012, 0.0020, 0.0030, 0.0050):
            feats = []
            verts = 0
            for code, nombre, geom in municipios:
                g = geom.simplify(tol, preserve_topology=True) if tol else geom
                verts += contar_vertices(g)
                feats.append({"type": "Feature",
                              "properties": {"region_code": code, "name": nombre},
                              "geometry": mapping(g)})
            blob = json.dumps({"type": "FeatureCollection", "features": feats}).encode()
            print(f"{tol:>12} {verts:>10,} {len(blob)/1024:>10,.0f} "
                  f"{len(gzip.compress(blob, 9))/1024:>9,.0f}")
        return

    features = []
    centroides = {}
    verts = 0
    for code, nombre, geom in municipios:
        g = geom.simplify(args.tolerancia, preserve_topology=True)
        if g.is_empty:
            print(f"AVISO -- {code} {nombre} quedo vacio al simplificar; se usa sin simplificar")
            g = geom
        verts += contar_vertices(g)
        c = g.centroid
        features.append({
            "type": "Feature",
            "properties": {"region_code": code, "name": nombre},
            "geometry": mapping(g),
        })
        centroides[code] = {"name": nombre, "lat": round(c.y, 6), "lon": round(c.x, 6)}

    with open(OUT_GEOJSON, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f)
    with open(OUT_CENTROIDES, "w", encoding="utf-8") as f:
        json.dump(centroides, f, ensure_ascii=False, indent=2)

    tam = os.path.getsize(OUT_GEOJSON)
    print(f"tolerancia: {args.tolerancia}  vertices: {verts:,}")
    print(f"guardado: {OUT_GEOJSON} ({tam/1024:,.0f} KB)")
    print(f"guardado: {OUT_CENTROIDES}")


if __name__ == "__main__":
    main()
