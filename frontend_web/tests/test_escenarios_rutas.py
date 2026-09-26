"""
Pruebas de las rutas de escenarios (bloque D, rebanada 1). Flask test client
contra PostgreSQL real; mismo requisito de base que las demas.

El POST de alta se salta solo, con aviso, si falta la migracion 023.

Ejecutar:
    python -m unittest frontend_web.tests.test_escenarios_rutas -v
"""
import os
import unittest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

from backend_web import queries
from backend_web.db import get_conn, query
from frontend_web.app import create_app

NOMBRE = "ZZZ escenario de prueba de rutas"


class EscenariosRutasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.testing = True

    def setUp(self):
        self.mty = query("SELECT id, population FROM regions WHERE code = '19039'", one=True)
        fila = query("""SELECT id FROM diseases WHERE is_active
                        ORDER BY name""")
        self.enfermedad = next(
            (d["id"] for d in fila
             if queries.estado_parametros(
                 query("SELECT default_params FROM diseases WHERE id = %s",
                       (d["id"],), one=True)["default_params"])["simulable"]), None)
        self._borra()

    def tearDown(self):
        self._borra()

    def _borra(self):
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT id FROM scenarios WHERE name = %s", (NOMBRE,))
                    for (sid,) in cur.fetchall():
                        # audit_log NO se toca: es de solo insercion por diseno
                        # (fn_solo_insercion). Sus filas se quedan, que es
                        # justamente el punto de una bitacora.
                        cur.execute("DELETE FROM scenario_versions WHERE scenario_id = %s", (sid,))
                        cur.execute("DELETE FROM scenarios WHERE id = %s", (sid,))
                conn.commit()
        except Exception as exc:                       # limpieza best-effort
            print(f"[tearDown] no se pudo limpiar: {exc}")

    def _login(self, client, usuario, password):
        resp = client.post("/login", data={"usuario": usuario, "password": password},
                           follow_redirects=False)
        self.assertEqual(resp.status_code, 302, f"login de {usuario} fallo: {resp.data}")

    def test_anonimo_no_ve_escenarios(self):
        with self.app.test_client() as client:
            for ruta in ("/escenarios", "/escenarios/nuevo"):
                resp = client.get(ruta, follow_redirects=False)
                self.assertEqual(resp.status_code, 302, ruta)
                self.assertIn("/login", resp.headers["Location"], ruta)

    def test_listado_y_formulario_cargan(self):
        with self.app.test_client() as client:
            self._login(client, "diana.flores", "Epidemia2026!")
            self.assertEqual(client.get("/escenarios").status_code, 200)
            resp = client.get("/escenarios/nuevo")
            self.assertEqual(resp.status_code, 200)
            html = resp.data.decode("utf-8", "replace")
            # El select de region trae la poblacion de cada una, para prellenar.
            self.assertIn('data-poblacion', html)
            # Una enfermedad incompleta se lista, pero avisada.
            self.assertIn("no simulable", html)

    def test_alta_invalida_no_guarda_y_muestra_los_errores(self):
        with self.app.test_client() as client:
            self._login(client, "diana.flores", "Epidemia2026!")
            resp = client.post("/escenarios/nuevo", data={
                "name": "", "disease_id": str(self.enfermedad or 1),
                "region_id": str(self.mty["id"]), "population_size": "500",
                "initial_infected": "1", "horizon_days": "5000"})
            self.assertEqual(resp.status_code, 400)
            html = resp.data.decode("utf-8", "replace")
            self.assertIn("nombre del escenario es obligatorio", html)
            self.assertIn("duración en días", html)
            self.assertEqual(query("SELECT count(*) n FROM scenarios WHERE name = %s",
                                   (NOMBRE,), one=True)["n"], 0)

    def test_alta_valida_crea_escenario_y_version_1(self):
        if not queries._hay_columnas_de_edad_en_version():
            self.skipTest("falta la migracion 023_escenarios_poblacion_por_edad.sql")
        if self.enfermedad is None:
            self.skipTest("ninguna enfermedad del catalogo es simulable")
        with self.app.test_client() as client:
            self._login(client, "diana.flores", "Epidemia2026!")
            resp = client.post("/escenarios/nuevo", data={
                "name": NOMBRE, "description": "Alta desde la prueba de rutas",
                "disease_id": str(self.enfermedad), "region_id": str(self.mty["id"]),
                "population_size": str(self.mty["population"]),
                "initial_infected": "500", "horizon_days": "120",
                "notes": "Versión inicial"}, follow_redirects=True)
            self.assertEqual(resp.status_code, 200)
            self.assertIn("versión 1", resp.data.decode("utf-8", "replace"))

            fila = query("""SELECT s.id, v.version_number, v.is_current, v.status
                            FROM scenarios s JOIN scenario_versions v ON v.scenario_id = s.id
                            WHERE s.name = %s""", (NOMBRE,), one=True)
            self.assertIsNotNone(fila, "el escenario no se guardo")
            self.assertEqual(fila["version_number"], 1)
            self.assertTrue(fila["is_current"])
            self.assertEqual(fila["status"], "borrador")

            # Y aparece en el listado.
            self.assertIn(NOMBRE, client.get("/escenarios").data.decode("utf-8", "replace"))


class IntervencionesRutasTests(unittest.TestCase):
    """El editor vive en el detalle del escenario. Tres cosas tienen que
    cumplirse para editar: el rol, que la version siga en borrador y ser dueno
    del escenario (o ADMINISTRADOR)."""

    NOMBRE = "ZZZ escenario de rutas con intervenciones"

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.testing = True

    def setUp(self):
        if not queries._hay_columnas_de_edad_en_version():
            self.skipTest("falta la migracion 023_escenarios_poblacion_por_edad.sql")
        self._borra()
        self.mty = query("SELECT id, population FROM regions WHERE code = '19039'", one=True)
        self.enfermedad = query(
            "SELECT id FROM diseases WHERE code = 'SARS_COV_2_ANCESTRAL'", one=True)["id"]
        with self.app.test_client() as client:
            self._login(client, "alex.cavazos", "Epidemia2026!")
            resp = client.post("/escenarios/nuevo", data={
                "name": self.NOMBRE, "disease_id": str(self.enfermedad),
                "region_id": str(self.mty["id"]), "estratificar": "on",
                "age_unknown_policy": "excluir", "initial_infected": "500",
                "horizon_days": "180"}, follow_redirects=False)
            self.assertEqual(resp.status_code, 302, resp.data[:400])
        fila = query("SELECT id FROM scenarios WHERE name = %s", (self.NOMBRE,), one=True)
        self.assertIsNotNone(fila, "no se creo el escenario de prueba")
        self.sid = fila["id"]

    def tearDown(self):
        self._borra()

    def _borra(self):
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT id FROM scenarios WHERE name = %s", (self.NOMBRE,))
                    for (sid,) in cur.fetchall():
                        cur.execute("DELETE FROM scenario_versions WHERE scenario_id = %s", (sid,))
                        cur.execute("DELETE FROM scenarios WHERE id = %s", (sid,))
                conn.commit()
        except Exception as exc:                       # limpieza best-effort
            print(f"[tearDown] no se pudo limpiar: {exc}")

    def _login(self, client, usuario, password):
        resp = client.post("/login", data={"usuario": usuario, "password": password},
                           follow_redirects=False)
        self.assertEqual(resp.status_code, 302, f"login de {usuario} fallo")

    def _n(self):
        return len(queries.get_escenario_detalle(self.sid)["intervenciones"])

    def test_anonimo_no_ve_el_detalle(self):
        with self.app.test_client() as client:
            resp = client.get(f"/escenarios/{self.sid}", follow_redirects=False)
            self.assertEqual(resp.status_code, 302)
            self.assertIn("/login", resp.headers["Location"])

    def test_el_dueno_agrega_y_la_linea_de_tiempo_la_dibuja(self):
        with self.app.test_client() as client:
            self._login(client, "alex.cavazos", "Epidemia2026!")
            resp = client.post(f"/escenarios/{self.sid}/intervenciones", data={
                "code": "CIERRE_ESCUELAS", "start_day": "10", "end_day": "60",
                "coverage": "1", "compliance": "0.9",
                "p_CIERRE_ESCUELAS_reduccion": "1"}, follow_redirects=True)
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(self._n(), 1)
            html = resp.data.decode("utf-8", "replace")
            self.assertIn("lt-barra", html, "no se dibujo la linea de tiempo")
            self.assertIn("Cierre de escuelas", html)

    def test_alta_invalida_devuelve_400_y_no_guarda(self):
        with self.app.test_client() as client:
            self._login(client, "alex.cavazos", "Epidemia2026!")
            resp = client.post(f"/escenarios/{self.sid}/intervenciones", data={
                "code": "CUBREBOCAS", "start_day": "5"})       # falta «eficacia»
            self.assertEqual(resp.status_code, 400)
            self.assertIn("eficacia", resp.data.decode("utf-8", "replace"))
            self.assertEqual(self._n(), 0)

    def test_quien_no_es_dueno_no_edita(self):
        """diana.flores tiene el rol, pero el escenario es de alex.cavazos."""
        with self.app.test_client() as client:
            self._login(client, "diana.flores", "Epidemia2026!")
            resp = client.post(f"/escenarios/{self.sid}/intervenciones", data={
                "code": "CIERRE_ESCUELAS", "start_day": "10",
                "p_CIERRE_ESCUELAS_reduccion": "1"}, follow_redirects=True)
            self.assertEqual(resp.status_code, 200)
            self.assertIn("Solo quien creó el escenario", resp.data.decode("utf-8", "replace"))
            self.assertEqual(self._n(), 0)

    def test_el_administrador_si_edita_lo_ajeno(self):
        with self.app.test_client() as client:
            self._login(client, "admin", "Admin2026!")
            resp = client.post(f"/escenarios/{self.sid}/intervenciones", data={
                "code": "CIERRE_ESCUELAS", "start_day": "10",
                "p_CIERRE_ESCUELAS_reduccion": "1"}, follow_redirects=True)
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(self._n(), 1)

    def test_una_version_que_no_es_borrador_no_se_edita(self):
        """El escenario 1 de la semilla tiene su version aprobada. Cambiarle las
        intervenciones dejaria al revisor habiendo aprobado algo distinto."""
        aprobado = query("""SELECT s.id FROM scenarios s
                            JOIN scenario_versions v ON v.scenario_id = s.id
                            WHERE v.is_current AND v.status <> 'borrador' LIMIT 1""", one=True)
        if not aprobado:
            self.skipTest("no hay un escenario con version fuera de borrador")
        with self.app.test_client() as client:
            self._login(client, "admin", "Admin2026!")
            resp = client.post(f"/escenarios/{aprobado['id']}/intervenciones", data={
                "code": "CIERRE_ESCUELAS", "start_day": "10",
                "p_CIERRE_ESCUELAS_reduccion": "1"}, follow_redirects=True)
            html = resp.data.decode("utf-8", "replace")
            self.assertIn("ya no es un borrador", html)
            self.assertEqual(
                len(queries.get_escenario_detalle(aprobado["id"])["intervenciones"]), 0)


class VersionadoRutasTests(IntervencionesRutasTests):
    """El historial, la version nueva y el duplicado por HTTP.

    Reusa el escenario en borrador de alex.cavazos que arma la clase de
    intervenciones; las pruebas heredadas se saltan con un filtro por nombre.
    """

    NOMBRE = "ZZZ escenario de rutas con versiones"

    # Las pruebas de la clase padre ya corren en su propia clase: aqui solo
    # interesa el fixture. Se anulan para no repetirlas.
    test_anonimo_no_ve_el_detalle = None
    test_el_dueno_agrega_y_la_linea_de_tiempo_la_dibuja = None
    test_alta_invalida_devuelve_400_y_no_guarda = None
    test_quien_no_es_dueno_no_edita = None
    test_el_administrador_si_edita_lo_ajeno = None
    test_una_version_que_no_es_borrador_no_se_edita = None

    def _crea_version(self, client, **cambios):
        datos = {"estratificar": "on", "age_unknown_policy": "excluir",
                 "initial_infected": "600", "horizon_days": "200",
                 "notes": "Ajuste de prueba"}
        datos.update(cambios)
        return client.post(f"/escenarios/{self.sid}/versiones/nueva", data=datos,
                           follow_redirects=True)

    def test_el_historial_aparece_en_el_detalle(self):
        with self.app.test_client() as client:
            self._login(client, "alex.cavazos", "Epidemia2026!")
            html = client.get(f"/escenarios/{self.sid}").data.decode("utf-8", "replace")
            self.assertIn("Historial de versiones", html)
            self.assertIn("Nueva versión", html)
            self.assertIn("Duplicar", html)

    def test_crear_version_por_http_y_ver_la_anterior(self):
        with self.app.test_client() as client:
            self._login(client, "alex.cavazos", "Epidemia2026!")
            client.post(f"/escenarios/{self.sid}/intervenciones", data={
                "code": "CIERRE_ESCUELAS", "start_day": "10",
                "p_CIERRE_ESCUELAS_reduccion": "1"})
            resp = self._crea_version(client)
            self.assertEqual(resp.status_code, 200)
            self.assertIn("Versión 2 creada", resp.data.decode("utf-8", "replace"))

            historial = queries.get_versiones(self.sid)
            self.assertEqual([v["version_number"] for v in historial], [2, 1])
            self.assertEqual(historial[0]["n_intervenciones"], 1,
                             "la version nueva debe traer copiadas las intervenciones")

            # La 1 se abre, de solo lectura.
            html = client.get(f"/escenarios/{self.sid}?version=1").data.decode("utf-8", "replace")
            self.assertIn("Estás viendo la", html)
            self.assertNotIn("Agregar intervención", html)

    def test_version_sin_comentario_devuelve_400(self):
        with self.app.test_client() as client:
            self._login(client, "alex.cavazos", "Epidemia2026!")
            resp = client.post(f"/escenarios/{self.sid}/versiones/nueva", data={
                "estratificar": "on", "age_unknown_policy": "excluir",
                "initial_infected": "600", "horizon_days": "200"})
            self.assertEqual(resp.status_code, 400)
            self.assertIn("comentario", resp.data.decode("utf-8", "replace"))
            self.assertEqual(len(queries.get_versiones(self.sid)), 1)

    def test_quien_no_es_dueno_no_versiona(self):
        with self.app.test_client() as client:
            self._login(client, "diana.flores", "Epidemia2026!")
            resp = self._crea_version(client)
            self.assertIn("Solo quien creó el escenario",
                          resp.data.decode("utf-8", "replace"))
            self.assertEqual(len(queries.get_versiones(self.sid)), 1)

    def test_una_version_inexistente_da_404_amable(self):
        with self.app.test_client() as client:
            self._login(client, "alex.cavazos", "Epidemia2026!")
            resp = client.get(f"/escenarios/{self.sid}?version=99", follow_redirects=True)
            self.assertEqual(resp.status_code, 200)
            self.assertIn("no existe", resp.data.decode("utf-8", "replace"))

    def test_duplicar_por_http_lleva_al_escenario_nuevo(self):
        copia = "ZZZ escenario de rutas con versiones (copia)"
        try:
            with self.app.test_client() as client:
                self._login(client, "diana.flores", "Epidemia2026!")
                resp = client.post(f"/escenarios/{self.sid}/duplicar",
                                   data={"version": "1", "name": copia},
                                   follow_redirects=True)
                self.assertEqual(resp.status_code, 200)
                html = resp.data.decode("utf-8", "replace")
                self.assertIn("Escenario duplicado", html)
                self.assertIn(copia, html)
            fila = query("SELECT id, owner_id FROM scenarios WHERE name = %s",
                         (copia,), one=True)
            self.assertIsNotNone(fila, "no se creo la copia")
            diana = query("""SELECT u.id FROM users u WHERE u.username = 'diana.flores'""",
                          one=True)["id"]
            self.assertEqual(fila["owner_id"], diana, "la copia es de quien duplica")
        finally:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT id FROM scenarios WHERE name = %s", (copia,))
                    for (sid,) in cur.fetchall():
                        cur.execute("DELETE FROM scenario_versions WHERE scenario_id = %s", (sid,))
                        cur.execute("DELETE FROM scenarios WHERE id = %s", (sid,))
                conn.commit()


class AprobacionRutasTests(IntervencionesRutasTests):
    """Enviar es de quien armo el escenario; dictaminar, del EPIDEMIOLOGO."""

    NOMBRE = "ZZZ escenario de rutas para aprobar"

    # El fixture es lo que interesa heredar; las pruebas del padre ya corren en
    # su propia clase.
    test_anonimo_no_ve_el_detalle = None
    test_el_dueno_agrega_y_la_linea_de_tiempo_la_dibuja = None
    test_alta_invalida_devuelve_400_y_no_guarda = None
    test_quien_no_es_dueno_no_edita = None
    test_el_administrador_si_edita_lo_ajeno = None
    test_una_version_que_no_es_borrador_no_se_edita = None

    def _estado(self):
        return queries.get_escenario_detalle(self.sid)["version"]["status"]

    def _envia(self, client):
        return client.post(f"/escenarios/{self.sid}/enviar", follow_redirects=True)

    def test_el_analista_no_entra_a_la_bandeja(self):
        with self.app.test_client() as client:
            self._login(client, "alex.cavazos", "Epidemia2026!")
            resp = client.get("/revisiones", follow_redirects=False)
            self.assertEqual(resp.status_code, 302)
            self.assertIn("/dashboard", resp.headers["Location"])

    def test_el_epidemiologo_ve_la_bandeja_con_lo_enviado(self):
        with self.app.test_client() as autor:
            self._login(autor, "alex.cavazos", "Epidemia2026!")
            self._envia(autor)
        self.assertEqual(self._estado(), "en_revision")
        with self.app.test_client() as revisor:
            self._login(revisor, "diana.flores", "Epidemia2026!")
            html = revisor.get("/revisiones").data.decode("utf-8", "replace")
            self.assertIn(self.NOMBRE, html)
            self.assertIn("Pendientes de revisión", html)

    def test_el_analista_no_dictamina(self):
        with self.app.test_client() as autor:
            self._login(autor, "alex.cavazos", "Epidemia2026!")
            self._envia(autor)
            autor.post(f"/escenarios/{self.sid}/revisar", data={"decision": "aprobar"},
                       follow_redirects=True)
        self.assertEqual(self._estado(), "en_revision",
                         "un ANALISTA no puede aprobar")
        denegados = query(
            """SELECT count(*) n FROM audit_log
               WHERE action = 'PERMISSION_DENIED' AND entity_type = 'scenario_versions'""",
            one=True)["n"]
        self.assertGreater(denegados, 0, "el intento debe quedar en la bitácora")

    def test_ciclo_completo_por_http(self):
        with self.app.test_client() as autor:
            self._login(autor, "alex.cavazos", "Epidemia2026!")
            autor.post(f"/escenarios/{self.sid}/intervenciones", data={
                "code": "CIERRE_ESCUELAS", "start_day": "10",
                "p_CIERRE_ESCUELAS_reduccion": "1"})
            self._envia(autor)
        with self.app.test_client() as revisor:
            self._login(revisor, "diana.flores", "Epidemia2026!")
            # El panel de dictamen aparece para quien puede decidir.
            html = revisor.get(f"/escenarios/{self.sid}").data.decode("utf-8", "replace")
            self.assertIn("Dictamen", html)

            resp = revisor.post(f"/escenarios/{self.sid}/revisar",
                                data={"decision": "rechazar",
                                      "comentario": "Falta la capa trabajo."},
                                follow_redirects=True)
            self.assertIn("Versión rechazada", resp.data.decode("utf-8", "replace"))
        self.assertEqual(self._estado(), "rechazado")

        with self.app.test_client() as autor:
            self._login(autor, "alex.cavazos", "Epidemia2026!")
            autor.post(f"/escenarios/{self.sid}/versiones/nueva", data={
                "estratificar": "on", "age_unknown_policy": "excluir",
                "initial_infected": "500", "horizon_days": "180",
                "notes": "Atiende el rechazo"}, follow_redirects=True)
            self.assertEqual(self._estado(), "borrador")
            self._envia(autor)
        with self.app.test_client() as revisor:
            self._login(revisor, "diana.flores", "Epidemia2026!")
            resp = revisor.post(f"/escenarios/{self.sid}/revisar",
                                data={"decision": "aprobar", "comentario": "Va."},
                                follow_redirects=True)
            html = resp.data.decode("utf-8", "replace")
            self.assertIn("Versión aprobada", html)
            self.assertIn("Ya se puede simular", html)
        self.assertEqual(self._estado(), "aprobado")
        self.assertFalse(queries.get_escenario_detalle(self.sid)["editable"])

    def test_el_administrador_ve_la_bandeja_pero_no_dictamina(self):
        with self.app.test_client() as autor:
            self._login(autor, "alex.cavazos", "Epidemia2026!")
            self._envia(autor)
        with self.app.test_client() as admin:
            self._login(admin, "admin", "Admin2026!")
            self.assertEqual(admin.get("/revisiones").status_code, 200)
            html = admin.get(f"/escenarios/{self.sid}").data.decode("utf-8", "replace")
            self.assertNotIn("Dictamen", html,
                             "quien opera el sistema no valida la epidemiología")
            admin.post(f"/escenarios/{self.sid}/revisar", data={"decision": "aprobar"},
                       follow_redirects=True)
        self.assertEqual(self._estado(), "en_revision")


if __name__ == "__main__":
    unittest.main()
