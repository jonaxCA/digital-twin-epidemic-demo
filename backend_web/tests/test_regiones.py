"""
Pruebas de integracion contra PostgreSQL real (sin mocks, igual que el resto
del proyecto). Requieren DATABASE_URL apuntando a una base con el esquema de
datos/postgres/dump_completo.sql + datos/postgres/semillas/nl_municipios_completos.sql
+ datos/postgres/migraciones/018_correccion_poblacion_51_municipios.sql ya
cargados (ver docs/INSTALACION.md, Paso 2).

Ejecutar:
    DATABASE_URL=postgresql://postgres:postgres_pw@localhost:55432/simulador_epidemico \
        python -m unittest backend_web.tests.test_regiones -v
"""
import os
import unittest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

from backend_web import queries
from backend_web.db import get_conn, query


def _admin_id():
    row = query(
        """SELECT u.id FROM users u
           JOIN user_roles ur ON ur.user_id = u.id
           JOIN roles r ON r.id = ur.role_id
           WHERE r.code = 'ADMINISTRADOR' LIMIT 1""",
        one=True,
    )
    return row["id"] if row else None


class _FakeRequest:
    """Sustituye a flask.request dentro de queries.py sin levantar la app:
    actualiza_poblacion_municipio solo necesita remote_addr y headers."""
    remote_addr = "127.0.0.1"
    headers = {"User-Agent": "pytest"}


class RegionesCatalogoTests(unittest.TestCase):
    def test_51_municipios_y_estado(self):
        catalogo = queries.get_regiones_catalogo()
        self.assertEqual(catalogo["total"], 51)

        estado = queries.get_estado_nl()
        self.assertIsNotNone(estado)
        self.assertEqual(estado["code"], "19")

        suma_pob = sum(m["poblacion"] for m in catalogo["municipios"])
        suma_60 = sum(m["poblacion_60"] for m in catalogo["municipios"])
        self.assertEqual(suma_pob, estado["poblacion"])
        self.assertEqual(suma_60, estado["poblacion_60"])

    def test_busqueda_por_nombre(self):
        catalogo = queries.get_regiones_catalogo(busqueda="Monterrey")
        self.assertEqual(catalogo["total"], 1)
        self.assertEqual(catalogo["municipios"][0]["nombre"], "Monterrey")

    def test_busqueda_por_clave_inegi_conserva_ceros(self):
        catalogo = queries.get_regiones_catalogo(busqueda="19039")
        self.assertEqual(catalogo["total"], 1)
        self.assertEqual(catalogo["municipios"][0]["code"], "19039")

    def test_busqueda_sin_resultados(self):
        catalogo = queries.get_regiones_catalogo(busqueda="xxxxninguno")
        self.assertEqual(catalogo["total"], 0)
        self.assertEqual(catalogo["municipios"], [])

    def test_orden_poblacion_asc_y_desc(self):
        asc = queries.get_regiones_catalogo(orden="poblacion", direccion="asc")
        desc = queries.get_regiones_catalogo(orden="poblacion", direccion="desc")
        poblaciones_asc = [m["poblacion"] for m in asc["municipios"]]
        poblaciones_desc = [m["poblacion"] for m in desc["municipios"]]
        self.assertEqual(poblaciones_asc, sorted(poblaciones_asc))
        self.assertEqual(poblaciones_desc, sorted(poblaciones_desc, reverse=True))

    def test_orden_invalido_cae_a_nombre_sin_romper(self):
        # Simula lo que llegaria por query string si alguien manda un valor
        # fuera de la whitelist: no debe lanzar, debe caer al default.
        catalogo = queries.get_regiones_catalogo(orden="'; DROP TABLE regions; --")
        self.assertEqual(catalogo["orden"], "nombre")
        self.assertEqual(catalogo["total"], 51)

    def test_get_municipios_catalogo_no_se_rompe(self):
        """Requisito explicito: esta funcion la usan otras pantallas
        (Captura de casos) y no debe verse afectada por el Bloque C."""
        catalogo = queries.get_municipios_catalogo()
        self.assertEqual(len(catalogo), 51)
        self.assertIn("name", catalogo[0])
        self.assertNotIn("population", catalogo[0])


class ValidacionPoblacionTests(unittest.TestCase):
    def test_valores_validos(self):
        pob, pob60, errores = queries.valida_poblacion_municipio("1000", "200", "Fuente X")
        self.assertEqual((pob, pob60), (1000, 200))
        self.assertEqual(errores, [])

    def test_rechaza_negativos(self):
        _, _, errores = queries.valida_poblacion_municipio("-5", "1", "motivo")
        self.assertTrue(any("negativa" in e for e in errores))

    def test_rechaza_no_numerico(self):
        _, _, errores = queries.valida_poblacion_municipio("abc", "1", "motivo")
        self.assertTrue(any("entero" in e for e in errores))

    def test_rechaza_60_mayor_que_total(self):
        _, _, errores = queries.valida_poblacion_municipio("100", "200", "motivo")
        self.assertTrue(any("no puede ser mayor" in e for e in errores))

    def test_exige_motivo(self):
        _, _, errores = queries.valida_poblacion_municipio("100", "50", "   ")
        self.assertTrue(any("fuente o el motivo" in e for e in errores))


class ActualizaPoblacionMunicipioTests(unittest.TestCase):
    def setUp(self):
        import backend_web.queries as q
        self._orig_request = None
        self._patch_flask_request()
        self.admin_id = _admin_id()
        self.assertIsNotNone(self.admin_id, "seed de datos de demo no cargada (falta admin)")
        municipio = query(
            "SELECT id, population, population_60plus FROM regions WHERE code = '19011'",
            one=True,
        )  # Cerralvo: municipio chico, no lo tocan otras pruebas
        self.region_id = municipio["id"]
        self.pob_original = municipio["population"]
        self.pob60_original = municipio["population_60plus"]

    def tearDown(self):
        # Deja el municipio y el estado como estaban antes de la prueba.
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

    def _patch_flask_request(self):
        import backend_web.queries as qmod
        import flask

        self._flask_request_orig = flask.request
        flask.request = _FakeRequest()  # type: ignore[assignment]

    def test_correccion_exitosa_registra_ajuste_y_auditoria(self):
        nueva_pob = self.pob_original + 500
        nueva_pob60 = self.pob60_original + 10
        ok, error, resultado = queries.actualiza_poblacion_municipio(
            self.region_id, nueva_pob, nueva_pob60, "Conteo intercensal 2025",
            self.admin_id, self.pob_original, self.pob60_original,
        )
        self.assertTrue(ok, error)
        self.assertTrue(resultado["estado_actualizado"])

        fila = query(
            "SELECT population, population_60plus FROM regions WHERE id = %s",
            (self.region_id,), one=True,
        )
        self.assertEqual(fila["population"], nueva_pob)
        self.assertEqual(fila["population_60plus"], nueva_pob60)

        ajuste = query(
            "SELECT reason, adjusted_by, census_value FROM region_population_adjustments "
            "WHERE region_id = %s AND field = 'population'",
            (self.region_id,), one=True,
        )
        self.assertIsNotNone(ajuste)
        self.assertEqual(ajuste["reason"], "Conteo intercensal 2025")
        self.assertEqual(ajuste["adjusted_by"], self.admin_id)
        self.assertEqual(ajuste["census_value"], self.pob_original)

        evento = query(
            """SELECT data_before, data_after FROM audit_log
               WHERE entity_type = 'regions' AND entity_id = %s
               ORDER BY occurred_at DESC LIMIT 1""",
            (str(self.region_id),), one=True,
        )
        self.assertIsNotNone(evento)
        self.assertEqual(evento["data_before"]["population"], self.pob_original)
        self.assertEqual(evento["data_after"]["population"], nueva_pob)

        estado = queries.get_estado_nl()
        catalogo = queries.get_regiones_catalogo()
        suma = sum(m["poblacion"] for m in catalogo["municipios"])
        self.assertEqual(suma, estado["poblacion"])

        fuente_fila = next(m for m in catalogo["municipios"] if m["id"] == self.region_id)
        self.assertEqual(fuente_fila["fuente_poblacion"]["tipo"], "manual")

    def test_conflicto_de_concurrencia_no_sobreescribe(self):
        # "Otra pestaña" corrige primero.
        ok1, _, _ = queries.actualiza_poblacion_municipio(
            self.region_id, self.pob_original + 100, self.pob60_original,
            "Primer ajuste", self.admin_id, self.pob_original, self.pob60_original,
        )
        self.assertTrue(ok1)

        # La pestaña original, que cargo el formulario con los valores viejos,
        # intenta guardar tambien: debe rechazarse sin tocar la base.
        ok2, error2, _ = queries.actualiza_poblacion_municipio(
            self.region_id, self.pob_original + 999, self.pob60_original,
            "Segundo ajuste (deberia rechazarse)", self.admin_id,
            self.pob_original, self.pob60_original,
        )
        self.assertFalse(ok2)
        self.assertIn("Otra persona corrigió", error2)

        fila = query(
            "SELECT population FROM regions WHERE id = %s", (self.region_id,), one=True)
        self.assertEqual(fila["population"], self.pob_original + 100)

    def test_ajuste_manual_no_se_pisa_al_reaplicar_correccion_censal(self):
        """Reproduce el escenario de 018/019: un ajuste manual vigente debe
        sobrevivir a que se vuelva a correr la correccion censal masiva."""
        ok, _, _ = queries.actualiza_poblacion_municipio(
            self.region_id, 999999, 1000, "Ajuste de prueba", self.admin_id,
            self.pob_original, self.pob60_original,
        )
        self.assertTrue(ok)

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE regions SET population = %s
                    WHERE code = '19011'
                      AND NOT EXISTS (
                            SELECT 1 FROM region_population_adjustments a
                            WHERE a.region_id = regions.id AND a.field = 'population')
                    """,
                    (self.pob_original,),
                )
            conn.commit()

        fila = query("SELECT population FROM regions WHERE id = %s", (self.region_id,), one=True)
        self.assertEqual(fila["population"], 999999)


if __name__ == "__main__":
    unittest.main()
