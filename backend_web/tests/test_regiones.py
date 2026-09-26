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
        pob, errores = queries.valida_poblacion_municipio("1000", "Fuente X")
        self.assertEqual(pob, 1000)
        self.assertEqual(errores, [])

    def test_rechaza_negativos(self):
        _, errores = queries.valida_poblacion_municipio("-5", "motivo")
        self.assertTrue(any("negativa" in e for e in errores))

    def test_rechaza_no_numerico(self):
        _, errores = queries.valida_poblacion_municipio("abc", "motivo")
        self.assertTrue(any("entero" in e for e in errores))

    def test_rechaza_total_menor_que_el_60_derivado(self):
        """El 60 y mas ya no se captura, pero sigue acotando por abajo: un
        municipio no puede tener menos habitantes que sus propios mayores."""
        _, errores = queries.valida_poblacion_municipio("100", "motivo", 200)
        self.assertTrue(any("no puede ser menor" in e for e in errores))

    def test_sin_60_derivado_no_estorba(self):
        _, errores = queries.valida_poblacion_municipio("100", "motivo", None)
        self.assertEqual(errores, [])

    def test_exige_motivo(self):
        _, errores = queries.valida_poblacion_municipio("100", "   ")
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
        ok, error, resultado = queries.actualiza_poblacion_municipio(
            self.region_id, nueva_pob, "Conteo intercensal 2025",
            self.admin_id, self.pob_original,
        )
        self.assertTrue(ok, error)
        self.assertTrue(resultado["estado_actualizado"])

        fila = query(
            "SELECT population, population_60plus FROM regions WHERE id = %s",
            (self.region_id,), one=True,
        )
        self.assertEqual(fila["population"], nueva_pob)
        # El 60 y mas es derivado: corregir la poblacion total no lo toca.
        self.assertEqual(fila["population_60plus"], self.pob60_original)

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
            self.region_id, self.pob_original + 100, "Primer ajuste",
            self.admin_id, self.pob_original,
        )
        self.assertTrue(ok1)

        # La pestaña original, que cargo el formulario con los valores viejos,
        # intenta guardar tambien: debe rechazarse sin tocar la base.
        ok2, error2, _ = queries.actualiza_poblacion_municipio(
            self.region_id, self.pob_original + 999,
            "Segundo ajuste (deberia rechazarse)", self.admin_id, self.pob_original,
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
            self.region_id, 999999, "Ajuste de prueba", self.admin_id,
            self.pob_original,
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
    """`population_60plus` es derivada desde la migracion 022, y `population`
    puede faltar en una region que aun no se haya capturado. Estas pruebas fijan
    que ninguno de los dos casos rompa la edicion ni corrompa el total estatal."""

    def setUp(self):
        import flask
        self._flask_request_orig = flask.request
        flask.request = _FakeRequest()  # type: ignore[assignment]

        self.admin_id = _admin_id()
        self.assertIsNotNone(self.admin_id, "seed de datos de demo no cargada (falta admin)")
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

    def test_el_60_derivado_no_lo_toca_una_correccion_de_poblacion(self):
        """Antes las dos cifras se editaban juntas y podian quedar incoherentes.
        Ahora el 60 y mas sale de region_age_groups y la pantalla no lo ofrece."""
        ok, error, _ = queries.actualiza_poblacion_municipio(
            self.objetivo["id"], self.objetivo["population"] + 1_000,
            "Conteo intercensal 2025", self.admin_id, self.objetivo["population"])
        self.assertTrue(ok, error)

        fila = query("SELECT population, population_60plus FROM regions WHERE id = %s",
                     (self.objetivo["id"],), one=True)
        self.assertEqual(fila["population"], self.objetivo["population"] + 1_000)
        self.assertEqual(fila["population_60plus"], self.objetivo["population_60plus"])

        ajustes = query(
            "SELECT field FROM region_population_adjustments WHERE region_id = %s",
            (self.objetivo["id"],))
        self.assertEqual([a["field"] for a in ajustes], ["population"],
                         "no debe registrarse un ajuste manual de population_60plus")

    def test_el_total_del_estado_no_se_recalcula_con_un_municipio_sin_poblacion(self):
        """sum() ignora los NULL. Si se recalculara igual, Nuevo Leon quedaria
        con un total mas bajo que el real y guardado como si fuera el bueno."""
        _restaura("UPDATE regions SET population = NULL WHERE id = %s",
                  (self.vecino["id"],))
        estado_antes = query("SELECT population FROM regions WHERE id = %s",
                             (self.estado_id,), one=True)["population"]

        ok, error, resultado = queries.actualiza_poblacion_municipio(
            self.objetivo["id"], self.objetivo["population"] + 100,
            "Conteo intercensal 2025", self.admin_id, self.objetivo["population"])
        self.assertTrue(ok, error)
        self.assertGreaterEqual(resultado["municipios_sin_poblacion"], 1)

        estado_despues = query("SELECT population FROM regions WHERE id = %s",
                               (self.estado_id,), one=True)["population"]
        self.assertEqual(estado_despues, estado_antes)


if __name__ == "__main__":
    unittest.main()
