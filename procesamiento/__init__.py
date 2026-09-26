"""Componente de procesamiento: el motor de simulacion de referencia.

Existe como paquete para que la aplicacion web pueda importarlo desde la raiz
del repositorio (`from procesamiento.motor import validar_escenario`) sin tocar
sys.path. Las pruebas del motor se siguen corriendo desde dentro de esta carpeta
(`cd procesamiento && python -m unittest discover -s tests -t .`), donde `motor`
es un paquete de primer nivel; este archivo no cambia eso.
"""
