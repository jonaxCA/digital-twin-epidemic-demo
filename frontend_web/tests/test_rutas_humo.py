"""
Prueba de humo de todas las rutas: ninguna debe responder 500.

POR QUE EXISTE
Una funcion nueva en `backend_web/queries.py` se llamo igual que otra que ya
estaba, con distinta firma. Python se queda con la ultima, asi que la captura de
casos empezo a responder 500 y ninguna prueba lo noto: las suites cubrian
regiones, enfermedades y escenarios, pero nadie pedia /reportes/nuevo. Esta
prueba recorre el mapa de rutas de Flask y pide todas las que puede, para que un
error de importacion o de firma salga a la primera.

No valida contenido: solo que la ruta no explote. Lo que cada pantalla muestra lo
verifican sus propias pruebas.

Ejecutar:
    python -m unittest frontend_web.tests.test_rutas_humo -v
"""
import os
import unittest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

from backend_web.db import get_conn, query
from frontend_web.app import create_app

# Rutas que cambian estado y no se pueden pedir a ciegas: tienen su propia
# prueba. Se listan para que quede claro que la omision es a proposito.
FUERA_DEL_HUMO = {"main.logout"}


class RutasHumoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.testing = True

    def _login(self, client):
        resp = client.post("/login", data={"usuario": "admin", "password": "Admin2026!"},
                           follow_redirects=False)
        self.assertEqual(resp.status_code, 302, "login de admin fallo")

    def _sustituciones(self):
        """Un id real para cada parametro de ruta que exista en el mapa."""
        escenario = query("SELECT id FROM scenarios ORDER BY id LIMIT 1", one=True)
        return {
            "disease_id": query("SELECT id FROM diseases LIMIT 1", one=True)["id"],
            "region_id": query("SELECT id FROM regions WHERE level = 'municipio' LIMIT 1",
                               one=True)["id"],
            "user_id": query("SELECT id FROM users LIMIT 1", one=True)["id"],
            "scenario_id": escenario["id"] if escenario else 1,
            "name": "demo",
        }

    def test_ningun_get_responde_500(self):
        valores = self._sustituciones()
        revisadas, saltadas = [], []
        with self.app.test_client() as client:
            self._login(client)
            for regla in self.app.url_map.iter_rules():
                if "GET" not in (regla.methods or set()) or regla.endpoint in FUERA_DEL_HUMO:
                    continue
                if regla.endpoint == "static":
                    continue
                faltan = set(regla.arguments) - set(valores)
                if faltan:
                    saltadas.append((str(regla), sorted(faltan)))
                    continue
                url = regla.build({a: valores[a] for a in regla.arguments},
                                  append_unknown=False)[1]
                resp = client.get(url)
                self.assertLess(resp.status_code, 500,
                                f"{url} respondio {resp.status_code}")
                revisadas.append(url)
        self.assertGreater(len(revisadas), 10,
                           f"se revisaron muy pocas rutas: {revisadas}")
        self.assertEqual(saltadas, [], f"rutas sin id de prueba: {saltadas}")

    def test_la_captura_de_casos_sigue_viva(self):
        """El POST que rompio el shadowing de `_entero`. Se limpia el caso que
        crea, para no ensuciar los datos de demostracion."""
        valores = self._sustituciones()
        datos = {"disease_id": str(valores["disease_id"]),
                 "region_id": str(valores["region_id"]), "age": "30", "sex": "F",
                 "report_date": "2026-09-02", "onset_date": "2026-08-31",
                 "test_result": "positivo", "severity": "leve"}
        try:
            with self.app.test_client() as client:
                self._login(client)
                resp = client.post("/reportes/nuevo", data=datos, follow_redirects=False)
                self.assertIn(resp.status_code, (200, 302, 400),
                              f"respondio {resp.status_code}")
        finally:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""DELETE FROM cases WHERE report_date = %s
                                   AND onset_date = %s AND age = 30 AND sex = 'F'""",
                                (datos["report_date"], datos["onset_date"]))
                conn.commit()


if __name__ == "__main__":
    unittest.main()
