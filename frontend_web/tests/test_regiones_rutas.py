"""
Pruebas de integracion de rutas HTTP (Flask test client) contra PostgreSQL
real. Mismo requisito de base que backend_web/tests/test_regiones.py.

Ejecutar:
    DATABASE_URL=postgresql://postgres:postgres_pw@localhost:55432/simulador_epidemico \
    JWT_SECRET_KEY=test-secret \
        python -m unittest frontend_web.tests.test_regiones_rutas -v
"""
import os
import unittest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

from backend_web.db import get_conn, query
from frontend_web.app import create_app


class RegionesRutasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.testing = True

    def setUp(self):
        municipio = query(
            "SELECT id, population, population_60plus FROM regions WHERE code = '19003'",
            one=True,
        )  # Los Aldamas: municipio chico que no tocan otras pruebas
        self.region_id = municipio["id"]
        self.pob_original = municipio["population"]
        self.pob60_original = municipio["population_60plus"]

    def tearDown(self):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE regions SET population = %s, population_60plus = %s WHERE id = %s",
                    (self.pob_original, self.pob60_original, self.region_id),
                )
                cur.execute(
                    "DELETE FROM region_population_adjustments WHERE region_id = %s",
                    (self.region_id,),
                )
                cur.execute("SELECT id FROM regions WHERE code = '19'")
                estado_id = cur.fetchone()[0]
                cur.execute(
                    """UPDATE regions e SET population = sub.total_pob, population_60plus = sub.total_60
                       FROM (SELECT sum(population) AS total_pob, sum(population_60plus) AS total_60
                             FROM regions WHERE parent_region_id = %s) sub
                       WHERE e.id = %s""",
                    (estado_id, estado_id),
                )
            conn.commit()

    def _login(self, client, usuario, password):
        resp = client.post("/login", data={"usuario": usuario, "password": password},
                            follow_redirects=False)
        self.assertEqual(resp.status_code, 302, f"login de {usuario} fallo: {resp.data}")

    def test_usuario_autenticado_sin_admin_puede_consultar(self):
        with self.app.test_client() as client:
            self._login(client, "diana.flores", "Epidemia2026!")
            resp = client.get("/regiones")
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b"Regiones", resp.data)
            # El boton de editar no debe aparecer para un rol sin permiso.
            self.assertNotIn(b"Corregir poblaci\xc3\xb3n", resp.data)

    def test_usuario_sin_admin_no_puede_ver_formulario_get(self):
        with self.app.test_client() as client:
            self._login(client, "diana.flores", "Epidemia2026!")
            resp = client.get(f"/regiones/{self.region_id}/editar", follow_redirects=False)
            self.assertEqual(resp.status_code, 302)
            self.assertIn("/dashboard", resp.headers["Location"])

            evento = query(
                """SELECT action FROM audit_log
                   WHERE entity_type = 'regions' AND action = 'PERMISSION_DENIED'
                   ORDER BY occurred_at DESC LIMIT 1""",
                one=True,
            )
            self.assertIsNotNone(evento, "el intento denegado debe quedar en audit_log")

    def test_usuario_sin_admin_no_puede_editar_por_post_manual(self):
        with self.app.test_client() as client:
            self._login(client, "diana.flores", "Epidemia2026!")
            resp = client.post(
                f"/regiones/{self.region_id}/editar",
                data={
                    "population": str(self.pob_original + 12345),
                    "population_60plus": str(self.pob60_original),
                    "motivo": "Intento no autorizado",
                    "esperado_population": str(self.pob_original),
                    "esperado_population_60plus": str(self.pob60_original),
                },
                follow_redirects=False,
            )
            self.assertEqual(resp.status_code, 302)
            self.assertIn("/dashboard", resp.headers["Location"])

            fila = query("SELECT population FROM regions WHERE id = %s", (self.region_id,), one=True)
            self.assertEqual(fila["population"], self.pob_original, "un POST manual no debe cambiar la cifra")

    def test_anonimo_redirige_a_login(self):
        with self.app.test_client() as client:
            resp = client.get(f"/regiones/{self.region_id}/editar", follow_redirects=False)
            self.assertEqual(resp.status_code, 302)
            self.assertIn("/login", resp.headers["Location"])

    def test_admin_puede_editar_y_ver_fuente_actualizada(self):
        with self.app.test_client() as client:
            self._login(client, "admin", "Admin2026!")

            resp_get = client.get(f"/regiones/{self.region_id}/editar")
            self.assertEqual(resp_get.status_code, 200)

            nueva_pob = self.pob_original + 321
            nueva_pob60 = self.pob60_original + 5
            resp = client.post(
                f"/regiones/{self.region_id}/editar",
                data={
                    "population": str(nueva_pob),
                    "population_60plus": str(nueva_pob60),
                    "motivo": "Prueba automatizada de corrección",
                    "esperado_population": str(self.pob_original),
                    "esperado_population_60plus": str(self.pob60_original),
                },
                follow_redirects=True,
            )
            self.assertEqual(resp.status_code, 200)
            self.assertIn("actualizada".encode(), resp.data)

            fila = query(
                "SELECT population, population_60plus FROM regions WHERE id = %s",
                (self.region_id,), one=True,
            )
            self.assertEqual(fila["population"], nueva_pob)
            self.assertEqual(fila["population_60plus"], nueva_pob60)

            resp_listado = client.get("/regiones")
            self.assertIn("Corrección manual".encode(), resp_listado.data)

    def test_admin_datos_invalidos_no_cambian_nada_y_muestran_error(self):
        with self.app.test_client() as client:
            self._login(client, "admin", "Admin2026!")
            resp = client.post(
                f"/regiones/{self.region_id}/editar",
                data={
                    "population": "100",
                    "population_60plus": "999",  # mayor que el total: invalido
                    "motivo": "motivo cualquiera",
                    "esperado_population": str(self.pob_original),
                    "esperado_population_60plus": str(self.pob60_original),
                },
            )
            self.assertEqual(resp.status_code, 400)
            self.assertIn("no puede ser mayor".encode(), resp.data)

            fila = query("SELECT population FROM regions WHERE id = %s", (self.region_id,), one=True)
            self.assertEqual(fila["population"], self.pob_original)


if __name__ == "__main__":
    unittest.main()
