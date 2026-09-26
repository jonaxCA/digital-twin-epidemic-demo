"""
Integridad de los modulos: que ningun nombre de nivel superior tape a otro.

POR QUE EXISTE
`backend_web/queries.py` llego a tener dos funciones `_entero` con firmas
distintas. Python se queda con la ultima, asi que los llamadores de la primera
empezaron a recibir TypeError y la captura de casos respondia 500. El archivo
compilaba, ninguna prueba fallaba y el error solo aparecia al usar esa pantalla.

Esta prueba no necesita base de datos: lee el codigo con `ast`.

Ejecutar:
    python -m unittest backend_web.tests.test_integridad -v
"""
import ast
import os
import pathlib
import unittest

RAIZ = pathlib.Path(__file__).resolve().parents[2]

MODULOS = [
    "backend_web/queries.py",
    "backend_web/db.py",
    "backend_web/auth.py",
    "backend_web/audit.py",
    "frontend_web/app/routes.py",
    "frontend_web/app/permisos.py",
    "procesamiento/motor/parametros.py",
    "procesamiento/motor/modelo.py",
    "procesamiento/motor/indicadores.py",
    "procesamiento/motor/pareto.py",
]


def _definiciones(ruta):
    """(nombre -> [lineas]) de funciones y clases de nivel superior."""
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    salida = {}
    for nodo in arbol.body:
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            salida.setdefault(nodo.name, []).append(nodo.lineno)
    return salida


class SinNombresTapadosTests(unittest.TestCase):
    def test_ningun_modulo_define_dos_veces_el_mismo_nombre(self):
        problemas = []
        for rel in MODULOS:
            ruta = RAIZ / rel
            if not ruta.exists():
                continue
            for nombre, lineas in _definiciones(ruta).items():
                if len(lineas) > 1:
                    problemas.append(f"{rel}: '{nombre}' en las lineas "
                                     + ", ".join(str(l) for l in lineas))
        self.assertEqual(problemas, [],
                         "hay definiciones que tapan a otras:\n  " + "\n  ".join(problemas))

    def test_la_lista_de_modulos_apunta_a_archivos_reales(self):
        """Si un archivo se renombra, la prueba dejaria de cubrirlo en silencio."""
        faltan = [rel for rel in MODULOS if not (RAIZ / rel).exists()]
        self.assertEqual(faltan, [], f"módulos que ya no existen: {faltan}")


if __name__ == "__main__":
    unittest.main()
