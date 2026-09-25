"""
Pruebas de integracion contra PostgreSQL real (sin mocks, igual que el resto
del proyecto). Requieren DATABASE_URL apuntando a una base con el esquema de
datos/postgres/dump_completo.sql + datos/postgres/semillas/nl_municipios_completos.sql
ya cargados (ver docs/INSTALACION.md, Paso 2). La semilla trae la poblacion y el
dato de 60 y mas de los 51 municipios, asi que no hace falta ningun archivo de
correccion aparte.

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


def _restaura(sql, params=()):
    """Restaura estado en su PROPIA transaccion, sin dejar que un fallo tumbe el
    resto de la limpieza.

    Un tearDown que corre todo en una sola transaccion pierde la restauracion
    ENTERA si una sola sentencia falla -- y deja municipios en NULL que rompen
    las pruebas de la corrida siguiente, con un error que no tiene nada que ver
    con la causa real. Paso exactamente eso cuando faltaba el GRANT sobre
    region_population_adjustments.
    """
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
            conn.commit()
    except Exception as exc:  # limpieza best-effort: se reporta y se sigue
        print(f"[tearDown] no se pudo restaurar: {exc}")


def _restaura_estado():
    """Recalcula el agregado de Nuevo Leon saltandose el campo incompleto, igual
    que produccion: con un municipio en NULL, sum() daria un total mas bajo que
    el real y lo dejaria guardado como si fuera bueno."""
    _restaura(
        """
        UPDATE regions e
        SET population = sub.total_pob,
            population_60plus = CASE WHEN sub.faltan = 0
                                     THEN sub.total_60 ELSE e.population_60plus END
        FROM (SELECT sum(population) AS total_pob,
                     sum(population_60plus) AS total_60,
                     count(*) FILTER (WHERE population_60plus IS NULL) AS faltan
              FROM regions
              WHERE parent_region_id = (SELECT id FROM regions WHERE code = '19')) sub
        WHERE e.code = '19'
        """)


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
        # Deja el municipio y el estado como estaban antes de la prueba. Cada
        # sentencia va aparte: ver _restaura.
        import flask
        flask.request = self._flask_request_orig  # type: ignore[assignment]
        _restaura(
            "UPDATE regions SET population = %s, population_60plus = %s WHERE id = %s",
            (self.pob_original, self.pob60_original, self.region_id))
        _restaura(
            "DELETE FROM region_population_adjustments WHERE region_id = %s",
            (self.region_id,))
        _restaura_estado()

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


class PoblacionSinDatoTests(unittest.TestCase):
    """Un municipio puede llegar con `population_60plus` en NULL: la columna es
    opcional y las correcciones censales masivas solo alcanzan a las filas que
    ya existen cuando corren. Estas pruebas fijan que ese estado no rompa la
    edicion ni corrompa el total del estado."""

    def setUp(self):
        self._flask_request_orig = None
        import flask
        self._flask_request_orig = flask.request
        flask.request = _FakeRequest()  # type: ignore[assignment]

        self.admin_id = _admin_id()
        self.assertIsNotNone(self.admin_id, "seed de datos de demo no cargada (falta admin)")

        # Cerralvo (el que se edita) y Villaldama (el que se deja sin dato).
        self.objetivo = query(
            "SELECT id, population, population_60plus FROM regions WHERE code = '19011'",
            one=True)
        self.vecino = query(
            "SELECT id, population, population_60plus FROM regions WHERE code = '19051'",
            one=True)
        self.estado_id = query("SELECT id FROM regions WHERE code = '19'", one=True)["id"]

    def tearDown(self):
        import flask
        flask.request = self._flask_request_orig  # type: ignore[assignment]
        for fila in (self.objetivo, self.vecino):
            _restaura(
                "UPDATE regions SET population = %s, population_60plus = %s WHERE id = %s",
                (fila["population"], fila["population_60plus"], fila["id"]))
            _restaura(
                "DELETE FROM region_population_adjustments WHERE region_id = %s",
                (fila["id"],))
        _restaura_estado()

    def _vacia_60(self, region_id):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE regions SET population_60plus = NULL WHERE id = %s", (region_id,))
            conn.commit()

    def test_se_puede_capturar_el_60_cuando_estaba_vacio(self):
        """Antes esto era imposible: el valor esperado llegaba como None y la
        ruta lo trataba como formulario invalido, dejando el municipio sin
        forma de corregirse."""
        self._vacia_60(self.objetivo["id"])

        ok, error, resultado = queries.actualiza_poblacion_municipio(
            self.objetivo["id"], self.objetivo["population"], 1207,
            "Captura inicial desde ITER 2020", self.admin_id,
            self.objetivo["population"], None,   # <- lo que el formulario traia: vacio
        )
        self.assertTrue(ok, error)

        fila = query("SELECT population_60plus FROM regions WHERE id = %s",
                     (self.objetivo["id"],), one=True)
        self.assertEqual(fila["population_60plus"], 1207)

        ajuste = query(
            """SELECT census_value, previous_value, new_value
               FROM region_population_adjustments
               WHERE region_id = %s AND field = 'population_60plus'""",
            (self.objetivo["id"],), one=True)
        self.assertIsNotNone(ajuste, "no quedo registrado el ajuste manual")
        self.assertEqual(ajuste["new_value"], 1207)
        # No habia cifra censal previa: decir que era 0 seria inventarla.
        self.assertIsNone(ajuste["census_value"])
        self.assertIsNone(ajuste["previous_value"])

    def test_el_total_del_estado_no_se_recalcula_con_un_municipio_sin_dato(self):
        """sum() ignora los NULL. Si se recalculara igual, Nuevo Leon quedaria
        con un total mas bajo que el real y guardado como si fuera el bueno."""
        self._vacia_60(self.vecino["id"])
        estado_antes = query(
            "SELECT population, population_60plus FROM regions WHERE id = %s",
            (self.estado_id,), one=True)

        ok, error, resultado = queries.actualiza_poblacion_municipio(
            self.objetivo["id"], self.objetivo["population"] + 100,
            self.objetivo["population_60plus"], "Conteo intercensal 2025",
            self.admin_id, self.objetivo["population"], self.objetivo["population_60plus"],
        )
        self.assertTrue(ok, error)
        self.assertGreaterEqual(resultado["municipios_sin_60"], 1)

        estado_despues = query(
            "SELECT population, population_60plus FROM regions WHERE id = %s",
            (self.estado_id,), one=True)
        # El de 60+ se queda como estaba; el total si se recalcula, porque ahi
        # no falta ningun dato.
        self.assertEqual(estado_despues["population_60plus"],
                         estado_antes["population_60plus"])
        self.assertEqual(estado_despues["population"], estado_antes["population"] + 100)


if __name__ == "__main__":
    unittest.main()
