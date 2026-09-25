"""Verifica que cada archivo de datos/postgres/migraciones/ sea identico a su
bloque dentro de datos/postgres/dump_completo.sql. Correr desde la raiz:
    python datos/scripts/verifica_migraciones.py

Una migracion puede quedar fuera del dump a proposito cuando depende de algo
que el dump todavia no cargo (por ejemplo, una semilla que corre despues). Esas
van en FUERA_DEL_DUMP con el motivo, se reportan como APARTE y no hacen fallar
la verificacion; lo que si falla es que ESTEN dentro del dump pese a figurar
aqui, porque entonces correrian dos veces y en el orden equivocado.
"""
import pathlib
import sys

# nombre de archivo -> por que no esta (ni debe estar) en el dump
FUERA_DEL_DUMP = {
    "018_correccion_poblacion_51_municipios.sql":
        "depende de semillas/nl_municipios_completos.sql, que se carga despues "
        "del dump (ver docs/INSTALACION.md, Paso 2)",
}

base = pathlib.Path("datos/postgres")
dump = (base / "dump_completo.sql").read_text(encoding="utf-8").replace("\r\n", "\n")

problemas = []
for archivo in sorted((base / "migraciones").glob("*.sql")):
    texto = archivo.read_text(encoding="utf-8").replace("\r\n", "\n").strip("\n")
    dentro = texto in dump
    motivo = FUERA_DEL_DUMP.get(archivo.name)

    if motivo:
        if dentro:
            print(f"SOBRA   {archivo.name} -- esta en el dump y no deberia: {motivo}")
            problemas.append(archivo.name)
        else:
            print(f"APARTE  {archivo.name} -- {motivo}")
    elif dentro:
        print(f"OK      {archivo.name}")
    else:
        print(f"DIFIERE {archivo.name}")
        problemas.append(archivo.name)

print(f"\n{len(problemas)} archivo(s) con problema")
sys.exit(1 if problemas else 0)
