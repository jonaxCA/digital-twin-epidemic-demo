"""Verifica que cada archivo de datos/postgres/migraciones/ sea identico a su
bloque dentro de datos/postgres/dump_completo.sql. Correr desde la raiz:
    python datos/scripts/verifica_migraciones.py
"""
import pathlib
import sys

base = pathlib.Path("datos/postgres")
dump = (base / "dump_completo.sql").read_text(encoding="utf-8").replace("\r\n", "\n")
difieren = []
for archivo in sorted((base / "migraciones").glob("*.sql")):
    texto = archivo.read_text(encoding="utf-8").replace("\r\n", "\n").strip("\n")
    ok = texto in dump
    print(("OK      " if ok else "DIFIERE ") + archivo.name)
    if not ok:
        difieren.append(archivo.name)
print(f"\n{len(difieren)} archivo(s) distinto(s) al dump")
sys.exit(1 if difieren else 0)
