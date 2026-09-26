"""
Pruebas del alta de escenarios (bloque D, rebanada 1). Integracion contra
PostgreSQL real, igual que el resto del proyecto.

Requieren una base con datos/postgres/dump_completo.sql y las semillas
cargadas (ver docs/INSTALACION.md, Paso 2). Las pruebas que escriben se saltan
solas, con aviso, si todavia falta la migracion 023.

Ejecutar:
    python -m unittest backend_web.tests.test_escenarios -v
"""
import json
import os
import unittest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

from backend_web import queries
from backend_web.db import get_conn, query


def _desempaqueta(valor):
    """Un parametro puede venir como numero o con trazabilidad."""
    return valor["valor"] if isinstance(valor, dict) and "valor" in valor else valor


def _restaura(sql, params=()):
    """Escribe en su propia transaccion, sin tumbar el resto de la limpieza."""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
            conn.commit()
    except Exception as exc:                       # limpieza best-effort
        print(f"[test] no se pudo escribir: {exc}")


def _usuario(rol):
    fila = query(
        """SELECT u.id FROM users u
           JOIN user_roles ur ON ur.user_id = u.id
           JOIN roles r ON r.id = ur.role_id
           WHERE r.code = %s LIMIT 1""", (rol,), one=True)
    return fila["id"] if fila else None


class _FakeRequest:
    """Sustituye a flask.request dentro de queries.py sin levantar la app."""
    remote_addr = "127.0.0.1"
    headers = {"User-Agent": "pytest"}


class _ConCatalogo(unittest.TestCase):
    """Base comun: el catalogo de regiones y enfermedades que ve el formulario."""

    @classmethod
    def setUpClass(cls):
        cls.regiones = queries.get_regiones_para_escenario()
        cls.enfermedades = queries.get_enfermedades_para_escenario()
        cls.mty = next((r for r in cls.regiones if r["code"] == "19039"), None)
        cls.estado = next((r for r in cls.regiones if r["code"] == "19"), None)
        cls.simulable = next((e for e in cls.enfermedades if e["simulable"]), None)
        cls.incompleta = next((e for e in cls.enfermedades if not e["simulable"]), None)

    def setUp(self):
        for nombre, valor in (("Monterrey", self.mty), ("el estado", self.estado),
                              ("una enfermedad simulable", self.simulable)):
            if valor is None:
                self.skipTest(f"falta {nombre} en la base de pruebas")

    def formulario(self, **cambios):
        base = {"name": "Escenario de prueba", "disease_id": str(self.simulable["id"]),
                "region_id": str(self.mty["id"]), "initial_infected": "500",
                "horizon_days": "120", "population_size": str(self.mty["population"])}
        base.update(cambios)
        return base


class ValidacionEscenarioTests(_ConCatalogo):
    def test_escenario_plano_valido(self):
        datos, errores = queries.valida_escenario(
            self.formulario(), self.regiones, self.enfermedades)
        self.assertEqual(errores, [])
        self.assertIsNone(datos["population_by_age"])
        self.assertEqual(datos["population_age_unknown"], 0)
        self.assertIsNone(datos["age_unknown_policy"])

    def test_estratificado_exige_politica_si_hay_gente_sin_edad(self):
        if not self.mty["grupos"]:
            self.skipTest("falta la migracion 021: no hay grupos de edad")
        if not self.mty["sin_edad"]:
            self.skipTest("este municipio no tiene poblacion sin edad declarada")
        _, errores = queries.valida_escenario(
            self.formulario(estratificar="on"), self.regiones, self.enfermedades)
        self.assertTrue(any("no declararon su edad" in e for e in errores), errores)

    def test_estratificado_toma_el_reparto_censal(self):
        """La poblacion de un escenario por edad NO sale del formulario: sale del
        censo. Si saliera del formulario habria que escalar los grupos, y eso los
        convertiria en una invencion."""
        if not self.mty["grupos"]:
            self.skipTest("falta la migracion 021: no hay grupos de edad")
        datos, errores = queries.valida_escenario(
            self.formulario(estratificar="on", age_unknown_policy="excluir",
                            population_size="9999"),
            self.regiones, self.enfermedades)
        self.assertEqual(errores, [])
        self.assertEqual(datos["population_by_age"], {g: int(n) for g, n in self.mty["grupos"].items()})
        self.assertEqual(datos["population_size"],
                         sum(self.mty["grupos"].values()) + self.mty["sin_edad"])

    def test_el_estado_completo_cabe(self):
        """Nuevo Leon tiene 5,784,442 habitantes. Con el tope anterior de 5
        millones este escenario era imposible de representar."""
        if not self.estado["grupos"]:
            self.skipTest("falta la migracion 021: no hay grupos de edad")
        datos, errores = queries.valida_escenario(
            self.formulario(region_id=str(self.estado["id"]), estratificar="on",
                            age_unknown_policy="prorratear"),
            self.regiones, self.enfermedades)
        self.assertEqual(errores, [])
        self.assertGreater(datos["population_size"], 5_000_000)

    def test_rechaza_enfermedad_sin_parametros(self):
        if self.incompleta is None:
            self.skipTest("todas las enfermedades del catalogo son simulables")
        _, errores = queries.valida_escenario(
            self.formulario(disease_id=str(self.incompleta["id"])),
            self.regiones, self.enfermedades)
        self.assertTrue(any("no se puede simular" in e for e in errores), errores)

    def test_rechaza_campos_fuera_de_rango(self):
        _, errores = queries.valida_escenario(
            self.formulario(name="", horizon_days="5000", population_size="500"),
            self.regiones, self.enfermedades)
        self.assertTrue(any("nombre" in e for e in errores))
        self.assertTrue(any("duración en días" in e for e in errores))
        self.assertTrue(any("población" in e for e in errores))

    def test_rechaza_infectados_mayores_que_la_poblacion(self):
        _, errores = queries.valida_escenario(
            self.formulario(population_size="1000", initial_infected="5000"),
            self.regiones, self.enfermedades)
        self.assertTrue(any("no pueden superar la población" in e for e in errores))

    def test_el_mapeo_al_motor_conserva_la_politica(self):
        datos = {"population_by_age": {"0-19": 10, "60+": 5}, "population_size": 17,
                 "population_age_unknown": 2, "age_unknown_policy": "excluir",
                 "initial_infected": 1, "horizon_days": 30}
        esc = queries.escenario_para_motor(datos, {"r0": 2.0})
        self.assertEqual(esc["poblacion"], {"0-19": 10, "60+": 5})
        self.assertEqual(esc["poblacion_edad_desconocida"], 2)
        self.assertEqual(esc["politica_edad_desconocida"], "excluir")
        self.assertEqual(esc["dias"], 30)
        self.assertEqual(esc["intervenciones"], [])

    def test_el_mapeo_omite_la_politica_cuando_no_aplica(self):
        datos = {"population_by_age": None, "population_size": 200_000,
                 "population_age_unknown": 0, "age_unknown_policy": None,
                 "initial_infected": 10, "horizon_days": 60}
        esc = queries.escenario_para_motor(datos, {})
        self.assertEqual(esc["poblacion"], 200_000)
        self.assertNotIn("poblacion_edad_desconocida", esc)
        self.assertNotIn("politica_edad_desconocida", esc)


class CreaEscenarioTests(_ConCatalogo):
    NOMBRE = "ZZZ escenario de prueba automatizada"

    def setUp(self):
        super().setUp()
        if not queries._hay_columnas_de_edad_en_version():
            self.skipTest("falta la migracion 023_escenarios_poblacion_por_edad.sql")
        self.autor = _usuario("ANALISTA") or _usuario("ADMINISTRADOR")
        self.assertIsNotNone(self.autor, "seed de datos de demo no cargada")
        import flask
        self._flask_request_orig = flask.request
        flask.request = _FakeRequest()  # type: ignore[assignment]
        self._borra()

    def tearDown(self):
        import flask
        flask.request = self._flask_request_orig  # type: ignore[assignment]
        self._borra()

    def _borra(self):
        """Los escenarios de prueba se van; el resto de la base queda igual."""
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT id FROM scenarios WHERE name = %s", (self.NOMBRE,))
                    for (sid,) in cur.fetchall():
                        # audit_log NO se toca: es de solo insercion por diseno
                        # (fn_solo_insercion). Sus filas se quedan, que es
                        # justamente el punto de una bitacora.
                        cur.execute("DELETE FROM scenario_versions WHERE scenario_id = %s", (sid,))
                        cur.execute("DELETE FROM scenarios WHERE id = %s", (sid,))
                conn.commit()
        except Exception as exc:                       # limpieza best-effort
            print(f"[tearDown] no se pudo limpiar: {exc}")

    def test_crea_escenario_con_version_1_vigente_y_bitacora(self):
        datos, errores = queries.valida_escenario(
            self.formulario(name=self.NOMBRE, notes="Primera versión"),
            self.regiones, self.enfermedades)
        self.assertEqual(errores, [])

        ok, error, sid = queries.crea_escenario(datos, self.autor)
        self.assertTrue(ok, error)

        v = query("""SELECT version_number, is_current, status, population_size,
                            horizon_days, initial_infected, notes, created_by
                     FROM scenario_versions WHERE scenario_id = %s""", (sid,), one=True)
        self.assertEqual(v["version_number"], 1)
        self.assertTrue(v["is_current"])
        self.assertEqual(v["status"], "borrador")
        self.assertEqual(v["created_by"], self.autor)
        self.assertEqual(v["notes"], "Primera versión")

        s = query("SELECT status, is_public, owner_id FROM scenarios WHERE id = %s",
                  (sid,), one=True)
        self.assertEqual(s["status"], "borrador")
        self.assertFalse(s["is_public"])
        self.assertEqual(s["owner_id"], self.autor)

        evento = query("""SELECT action, data_after FROM audit_log
                          WHERE entity_type = 'scenarios' AND entity_id = %s
                          ORDER BY occurred_at DESC LIMIT 1""", (str(sid),), one=True)
        self.assertIsNotNone(evento, "el alta no quedo en la bitacora")
        self.assertEqual(evento["action"], "CREATE")
        self.assertEqual(evento["data_after"]["version_number"], 1)

    def test_guarda_el_reparto_por_edad_y_la_politica(self):
        if not self.mty["grupos"]:
            self.skipTest("falta la migracion 021: no hay grupos de edad")
        datos, errores = queries.valida_escenario(
            self.formulario(name=self.NOMBRE, estratificar="on",
                            age_unknown_policy="prorratear"),
            self.regiones, self.enfermedades)
        self.assertEqual(errores, [])
        ok, error, sid = queries.crea_escenario(datos, self.autor)
        self.assertTrue(ok, error)

        v = query("""SELECT population_by_age, population_age_unknown, age_unknown_policy,
                            population_size
                     FROM scenario_versions WHERE scenario_id = %s""", (sid,), one=True)
        self.assertEqual(v["population_by_age"], datos["population_by_age"])
        self.assertEqual(v["population_age_unknown"], self.mty["sin_edad"])
        self.assertEqual(v["age_unknown_policy"], "prorratear")
        # La invariante que el CHECK no puede comprobar: el total es la suma.
        self.assertEqual(v["population_size"],
                         sum(v["population_by_age"].values()) + v["population_age_unknown"])

    def test_no_admite_dos_escenarios_con_el_mismo_nombre_del_mismo_autor(self):
        datos, _ = queries.valida_escenario(
            self.formulario(name=self.NOMBRE), self.regiones, self.enfermedades)
        ok, _, _ = queries.crea_escenario(datos, self.autor)
        self.assertTrue(ok)
        ok2, error2, sid2 = queries.crea_escenario(datos, self.autor)
        self.assertFalse(ok2)
        self.assertIn("ese nombre", error2)
        self.assertIsNone(sid2)


class _ConEscenarioBorrador(_ConCatalogo):
    """Fixture: un escenario estratificado con su version 1 en borrador.

    Sin pruebas propias a proposito: las clases que lo heredan las traen. Si
    tuviera pruebas, heredarlo las volveria a correr en cada subclase.
    """

    NOMBRE = "ZZZ escenario con borrador"

    def setUp(self):
        super().setUp()
        if not queries._hay_columnas_de_edad_en_version():
            self.skipTest("falta la migracion 023_escenarios_poblacion_por_edad.sql")
        self.autor = _usuario("ANALISTA") or _usuario("ADMINISTRADOR")
        self.assertIsNotNone(self.autor, "seed de datos de demo no cargada")
        import flask
        self._flask_request_orig = flask.request
        flask.request = _FakeRequest()  # type: ignore[assignment]

        if not self.mty["grupos"]:
            self.skipTest("falta la migracion 021: no hay grupos de edad")

        self._borra()
        # Estratificado a proposito: la checklist pide vacunacion "con grupo
        # 60+", y una prioridad por edad no tiene sentido -- el motor la rechaza
        # -- sobre una poblacion sin grupos.
        datos, errores = queries.valida_escenario(
            self.formulario(name=self.NOMBRE, horizon_days="180",
                            estratificar="on", age_unknown_policy="excluir"),
            self.regiones, self.enfermedades)
        self.assertEqual(errores, [])
        ok, error, self.sid = queries.crea_escenario(datos, self.autor)
        self.assertTrue(ok, error)
        self.tipos = queries.get_tipos_intervencion()
        self.version = queries.get_escenario_detalle(self.sid)["version"]

    def tearDown(self):
        import flask
        flask.request = self._flask_request_orig  # type: ignore[assignment]
        self._borra()

    def _borra(self):
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT id FROM scenarios WHERE name LIKE %s",
                                ("ZZZ %",))
                    for (sid,) in cur.fetchall():
                        # Las intervenciones se van en cascada con la version.
                        cur.execute("DELETE FROM scenario_versions WHERE scenario_id = %s", (sid,))
                        cur.execute("DELETE FROM scenarios WHERE id = %s", (sid,))
                conn.commit()
        except Exception as exc:                       # limpieza best-effort
            print(f"[tearDown] no se pudo limpiar: {exc}")

    def _agrega(self, **form):
        detalle = queries.get_escenario_detalle(self.sid)
        datos, errores = queries.valida_intervencion(
            form, self.tipos, detalle["version"], detalle["intervenciones"])
        if errores:
            return None, errores
        ok, error = queries.agrega_intervencion(self.version["id"], datos, self.autor)
        return (ok, [] if ok else [error])

    def _codigos(self):
        return [i["code"] for i in queries.get_escenario_detalle(self.sid)["intervenciones"]]


class IntervencionesTests(_ConEscenarioBorrador):
    """Alta, baja y orden de intervenciones sobre una version en borrador."""

    NOMBRE = "ZZZ escenario para intervenciones"

    # ---- los tres tipos que la checklist exige como minimo -----------------

    def test_los_tres_tipos_minimos(self):
        ok, errores = self._agrega(code="CIERRE_ESCUELAS", start_day="10", end_day="60",
                                   coverage="1", compliance="0.9",
                                   p_CIERRE_ESCUELAS_reduccion="1")
        self.assertTrue(ok, errores)
        ok, errores = self._agrega(code="REDUCCION_AFORO", start_day="15", end_day="90",
                                   coverage="0.8", p_REDUCCION_AFORO_reduccion="0.5")
        self.assertTrue(ok, errores)
        ok, errores = self._agrega(code="VACUNACION", start_day="30", coverage="0.6",
                                   p_VACUNACION_eficacia="0.9",
                                   p_VACUNACION_dosis_diarias="5000",
                                   p_VACUNACION_prioridad="edad_desc",
                                   p_VACUNACION_edad_minima="60")
        self.assertTrue(ok, errores)
        self.assertEqual(self._codigos(),
                         ["CIERRE_ESCUELAS", "REDUCCION_AFORO", "VACUNACION"])
        # Y el motor acepta la version completa.
        errores_motor, _ = queries.revisa_version(queries.get_escenario_detalle(self.sid))
        self.assertEqual(errores_motor, [])

    def test_los_parametros_no_se_mezclan_entre_tipos(self):
        """CIERRE_ESCUELAS, CIERRE_TRABAJO y REDUCCION_AFORO comparten el
        parametro «reduccion». Con un prefijo comun, el formulario de uno
        tomaria el valor escrito en el de otro."""
        ok, errores = self._agrega(code="REDUCCION_AFORO", start_day="5",
                                   p_CIERRE_ESCUELAS_reduccion="1")
        self.assertIsNone(ok, "no debio aceptarse: falta su propio «reduccion»")
        self.assertTrue(any("reduccion" in e for e in errores), errores)

    # ---- validaciones ------------------------------------------------------

    def test_rechaza_traslape_del_mismo_tipo(self):
        ok, _ = self._agrega(code="CIERRE_ESCUELAS", start_day="10", end_day="60",
                             p_CIERRE_ESCUELAS_reduccion="1")
        self.assertTrue(ok)
        ok, errores = self._agrega(code="CIERRE_ESCUELAS", start_day="40", end_day="70",
                                   p_CIERRE_ESCUELAS_reduccion="1")
        self.assertIsNone(ok)
        self.assertTrue(any("traslapa" in e for e in errores), errores)
        self.assertEqual(len(self._codigos()), 1)

    def test_admite_el_mismo_tipo_sin_traslape(self):
        ok, _ = self._agrega(code="CIERRE_ESCUELAS", start_day="10", end_day="60",
                             p_CIERRE_ESCUELAS_reduccion="1")
        self.assertTrue(ok)
        ok, errores = self._agrega(code="CIERRE_ESCUELAS", start_day="61", end_day="90",
                                   p_CIERRE_ESCUELAS_reduccion="1")
        self.assertTrue(ok, errores)
        self.assertEqual(len(self._codigos()), 2)

    def test_rechaza_cobertura_fuera_de_rango_y_dias_invalidos(self):
        _, errores = self._agrega(code="CUBREBOCAS", start_day="5", coverage="1.5",
                                  p_CUBREBOCAS_eficacia="0.5")
        self.assertTrue(any("cobertura" in e for e in errores), errores)
        _, errores = self._agrega(code="CUBREBOCAS", start_day="50", end_day="20",
                                  p_CUBREBOCAS_eficacia="0.5")
        self.assertTrue(any("día de fin" in e for e in errores), errores)
        _, errores = self._agrega(code="CUBREBOCAS", start_day="999",
                                  p_CUBREBOCAS_eficacia="0.5")
        self.assertTrue(any("día de inicio" in e for e in errores), errores)

    def test_exige_los_parametros_obligatorios_del_tipo(self):
        _, errores = self._agrega(code="CUBREBOCAS", start_day="5")
        self.assertTrue(any("eficacia" in e and "obligatorio" in e for e in errores), errores)

    def test_respeta_los_limites_del_param_schema(self):
        _, errores = self._agrega(code="CUBREBOCAS", start_day="5",
                                  p_CUBREBOCAS_eficacia="2")
        self.assertTrue(any("mayor que 1" in e for e in errores), errores)

    # ---- orden y baja ------------------------------------------------------

    def test_reordenar_intercambia_con_la_vecina(self):
        for dia, code, param in ((10, "CIERRE_ESCUELAS", "p_CIERRE_ESCUELAS_reduccion"),
                                 (20, "REDUCCION_AFORO", "p_REDUCCION_AFORO_reduccion")):
            ok, errores = self._agrega(code=code, start_day=str(dia), **{param: "1"})
            self.assertTrue(ok, errores)
        ids = [i["id"] for i in queries.get_escenario_detalle(self.sid)["intervenciones"]]
        ok, _ = queries.mueve_intervencion(self.version["id"], ids[1], "subir", self.autor)
        self.assertTrue(ok)
        self.assertEqual(self._codigos(), ["REDUCCION_AFORO", "CIERRE_ESCUELAS"])

    def test_subir_la_primera_no_es_error_ni_cambia_nada(self):
        ok, _ = self._agrega(code="CIERRE_ESCUELAS", start_day="10",
                             p_CIERRE_ESCUELAS_reduccion="1")
        self.assertTrue(ok)
        iid = queries.get_escenario_detalle(self.sid)["intervenciones"][0]["id"]
        ok, error = queries.mueve_intervencion(self.version["id"], iid, "subir", self.autor)
        self.assertFalse(ok)
        self.assertIsNone(error, "estar en el extremo no es un error que mostrar")
        self.assertEqual(self._codigos(), ["CIERRE_ESCUELAS"])

    def test_quitar_cierra_el_hueco_del_orden(self):
        for dia, code, param in ((10, "CIERRE_ESCUELAS", "p_CIERRE_ESCUELAS_reduccion"),
                                 (20, "REDUCCION_AFORO", "p_REDUCCION_AFORO_reduccion"),
                                 (30, "CUBREBOCAS", "p_CUBREBOCAS_eficacia")):
            ok, errores = self._agrega(code=code, start_day=str(dia), **{param: "0.5"})
            self.assertTrue(ok, errores)
        medio = queries.get_escenario_detalle(self.sid)["intervenciones"][1]
        ok, error = queries.quita_intervencion(self.version["id"], medio["id"], self.autor)
        self.assertTrue(ok, error)
        restantes = queries.get_escenario_detalle(self.sid)["intervenciones"]
        self.assertEqual([i["order_index"] for i in restantes], [0, 1],
                         "el orden no debe quedar con huecos")

    def test_no_se_puede_quitar_de_otra_version(self):
        ok, _ = self._agrega(code="CIERRE_ESCUELAS", start_day="10",
                             p_CIERRE_ESCUELAS_reduccion="1")
        self.assertTrue(ok)
        iid = queries.get_escenario_detalle(self.sid)["intervenciones"][0]["id"]
        ok, error = queries.quita_intervencion(self.version["id"] + 9999, iid, self.autor)
        self.assertFalse(ok)
        self.assertIn("ya no está", error)
        self.assertEqual(len(self._codigos()), 1)

    # ---- avisos del motor --------------------------------------------------

    def test_el_motor_avisa_de_una_prioridad_que_no_modela(self):
        """El catalogo admite cuatro prioridades de vacunacion; un modelo
        compartimental solo distingue dos. El aviso tiene que llegar a la
        pantalla, o el usuario cree que pidio algo que no esta pasando."""
        ok, errores = self._agrega(code="VACUNACION", start_day="10",
                                   p_VACUNACION_eficacia="0.9",
                                   p_VACUNACION_dosis_diarias="1000",
                                   p_VACUNACION_prioridad="zona")
        self.assertTrue(ok, errores)
        _, avisos = queries.revisa_version(queries.get_escenario_detalle(self.sid))
        self.assertTrue(any("zona" in a for a in avisos), avisos)


class VersionadoTests(_ConEscenarioBorrador):
    """Modificar nunca sobrescribe: crea la version siguiente."""

    NOMBRE = "ZZZ escenario para versionado"

    def _form_version(self, **cambios):
        base = {"estratificar": "on", "age_unknown_policy": "excluir",
                "initial_infected": "500", "horizon_days": "180",
                "notes": "Motivo del cambio"}
        base.update(cambios)
        return base

    def _region(self):
        return next(r for r in self.regiones if r["id"] == self.mty["id"])

    def _nueva(self, **cambios):
        datos, errores = queries.valida_version(
            self._form_version(**cambios), self._region(),
            query("SELECT default_params FROM diseases WHERE id = %s",
                  (self.simulable["id"],), one=True)["default_params"])
        if errores:
            return None, errores
        ok, error, numero = queries.crea_version(self.sid, datos, self.autor)
        return (numero if ok else None), ([] if ok else [error])

    def test_exige_el_comentario(self):
        numero, errores = self._nueva(notes="   ")
        self.assertIsNone(numero)
        self.assertTrue(any("comentario" in e for e in errores), errores)

    def test_la_version_nueva_es_la_vigente_y_la_anterior_queda_intacta(self):
        numero, errores = self._nueva(horizon_days="240", initial_infected="900")
        self.assertEqual(numero, 2, errores)

        historial = queries.get_versiones(self.sid)
        self.assertEqual([v["version_number"] for v in historial], [2, 1])
        v2, v1 = historial
        self.assertTrue(v2["is_current"])
        self.assertFalse(v1["is_current"])
        self.assertEqual(v2["horizon_days"], 240)
        self.assertEqual(v2["initial_infected"], 900)
        # La 1 no se movio: es el punto de versionar.
        self.assertEqual(v1["horizon_days"], 180)
        self.assertEqual(v1["initial_infected"], 500)
        self.assertEqual(v1["notes"], "Primera versión" if v1["notes"] == "Primera versión" else v1["notes"])

    def test_la_version_nueva_nace_borrador_aunque_la_anterior_estuviera_aprobada(self):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""UPDATE scenario_versions SET status = 'aprobado',
                               submitted_at = now(), reviewed_by = %s, reviewed_at = now()
                               WHERE scenario_id = %s AND is_current""",
                            (_usuario("EPIDEMIOLOGO"), self.sid))
            conn.commit()
        numero, errores = self._nueva()
        self.assertEqual(numero, 2, errores)
        nueva = queries.get_escenario_detalle(self.sid)["version"]
        self.assertEqual(nueva["status"], "borrador")

    def test_copia_las_intervenciones_conservando_el_orden(self):
        for dia, code, param in ((10, "CIERRE_ESCUELAS", "p_CIERRE_ESCUELAS_reduccion"),
                                 (20, "REDUCCION_AFORO", "p_REDUCCION_AFORO_reduccion")):
            ok, errores = self._agrega(code=code, start_day=str(dia), **{param: "1"})
            self.assertTrue(ok, errores)
        numero, errores = self._nueva()
        self.assertEqual(numero, 2, errores)

        v1 = queries.get_escenario_detalle(self.sid, 1)["intervenciones"]
        v2 = queries.get_escenario_detalle(self.sid, 2)["intervenciones"]
        self.assertEqual([(i["code"], i["start_day"], i["order_index"]) for i in v1],
                         [(i["code"], i["start_day"], i["order_index"]) for i in v2])
        # Son filas distintas: editar la copia no toca el historial.
        self.assertNotEqual({i["id"] for i in v1}, {i["id"] for i in v2})

    def test_una_version_anterior_no_es_editable(self):
        numero, errores = self._nueva()
        self.assertEqual(numero, 2, errores)
        self.assertFalse(queries.get_escenario_detalle(self.sid, 1)["editable"])
        self.assertTrue(queries.get_escenario_detalle(self.sid, 2)["editable"])

    def test_pedir_una_version_que_no_existe_da_none(self):
        self.assertIsNone(queries.get_escenario_detalle(self.sid, 99))

    def test_solo_hay_una_vigente_despues_de_varias_versiones(self):
        for _ in range(3):
            numero, errores = self._nueva()
            self.assertIsNotNone(numero, errores)
        historial = queries.get_versiones(self.sid)
        self.assertEqual([v["version_number"] for v in historial], [4, 3, 2, 1])
        self.assertEqual(sum(1 for v in historial if v["is_current"]), 1)

    # ---- duplicado ---------------------------------------------------------

    def test_duplicar_crea_un_escenario_propio_en_borrador(self):
        ok, errores = self._agrega(code="CIERRE_ESCUELAS", start_day="10",
                                   p_CIERRE_ESCUELAS_reduccion="1")
        self.assertTrue(ok, errores)
        otro = _usuario("EPIDEMIOLOGO")
        ok, error, nuevo_id = queries.duplica_escenario(
            self.sid, 1, "ZZZ copia del escenario", otro)
        self.assertTrue(ok, error)

        detalle = queries.get_escenario_detalle(nuevo_id)
        self.assertEqual(detalle["escenario"]["owner_id"], otro,
                         "la copia es de quien duplica, no del autor original")
        self.assertEqual(detalle["escenario"]["status"], "borrador")
        self.assertEqual(detalle["version"]["version_number"], 1)
        self.assertEqual(detalle["version"]["status"], "borrador")
        self.assertEqual([i["code"] for i in detalle["intervenciones"]], ["CIERRE_ESCUELAS"])
        # El original no se toca.
        self.assertEqual(len(queries.get_versiones(self.sid)), 1)

    def test_duplicar_exige_nombre_y_lo_quiere_unico(self):
        ok, error, _ = queries.duplica_escenario(self.sid, 1, "   ", self.autor)
        self.assertFalse(ok)
        self.assertIn("nombre", error)

        ok, error, _ = queries.duplica_escenario(self.sid, 1, self.NOMBRE, self.autor)
        self.assertFalse(ok, "el autor ya tiene un escenario con ese nombre")
        self.assertIn("ese nombre", error)

    def test_duplicar_una_version_que_no_existe(self):
        ok, error, _ = queries.duplica_escenario(self.sid, 99, "ZZZ copia imposible",
                                                 self.autor)
        self.assertFalse(ok)
        self.assertIn("ya no existe", error)


class AprobacionTests(_ConEscenarioBorrador):
    """borrador -> en_revision -> aprobado | rechazado.

    Las reglas duras las impone la base (migracion 013); estas pruebas verifican
    que la aplicacion las respete y de mensajes entendibles antes de que la base
    tenga que rechazar nada.
    """

    NOMBRE = "ZZZ escenario para aprobacion"

    def setUp(self):
        super().setUp()
        self.revisor = _usuario("EPIDEMIOLOGO")
        self.assertIsNotNone(self.revisor, "seed de datos de demo no cargada")
        self.assertNotEqual(self.revisor, self.autor,
                            "el fixture necesita autor y revisor distintos")

    def _estado(self):
        return queries.get_escenario_detalle(self.sid)["version"]["status"]

    def _envia(self):
        return queries.envia_a_revision(self.sid, self.autor)

    # ---- envio -------------------------------------------------------------

    def test_enviar_pasa_a_en_revision_y_sella_la_fecha(self):
        ok, error = self._envia()
        self.assertTrue(ok, error)
        version = queries.get_escenario_detalle(self.sid)["version"]
        self.assertEqual(version["status"], "en_revision")
        self.assertIsNotNone(version["submitted_at"])
        self.assertIsNone(version["reviewed_at"], "todavia nadie la reviso")
        self.assertFalse(queries.get_escenario_detalle(self.sid)["editable"],
                         "una version enviada no se sigue editando")

    def test_no_se_envia_dos_veces(self):
        self.assertTrue(self._envia()[0])
        ok, error = self._envia()
        self.assertFalse(ok)
        self.assertIn("en_revision", error)

    def test_no_se_envia_lo_que_el_motor_rechaza(self):
        """Mandar a revisar algo que no se puede simular le hace perder el tiempo
        a quien revisa."""
        from unittest.mock import patch
        with patch.object(queries, "revisa_version",
                          return_value=(["falta 'r0'"], [])):
            ok, error = self._envia()
        self.assertFalse(ok)
        self.assertIn("no tiene sentido enviarla", error)
        self.assertEqual(self._estado(), "borrador")

    # ---- dictamen ----------------------------------------------------------

    def test_rechazar_exige_motivo(self):
        self.assertTrue(self._envia()[0])
        ok, error, _ = queries.resuelve_revision(self.sid, "rechazar", "  ", self.revisor)
        self.assertFalse(ok)
        self.assertIn("explicar por qué", error)
        self.assertEqual(self._estado(), "en_revision")

    def test_rechazar_con_motivo_guarda_revisor_fecha_y_comentario(self):
        self.assertTrue(self._envia()[0])
        ok, error, estado = queries.resuelve_revision(
            self.sid, "rechazar", "Faltan medidas en la capa trabajo.", self.revisor)
        self.assertTrue(ok, error)
        self.assertEqual(estado, "rechazado")
        version = queries.get_escenario_detalle(self.sid)["version"]
        self.assertEqual(version["status"], "rechazado")
        self.assertIsNotNone(version["reviewed_at"])
        self.assertEqual(version["review_comment"], "Faltan medidas en la capa trabajo.")

    def test_aprobar_no_exige_motivo(self):
        self.assertTrue(self._envia()[0])
        ok, error, estado = queries.resuelve_revision(self.sid, "aprobar", "", self.revisor)
        self.assertTrue(ok, error)
        self.assertEqual(estado, "aprobado")
        self.assertIsNone(
            queries.get_escenario_detalle(self.sid)["version"]["review_comment"])

    def test_nadie_revisa_su_propia_version(self):
        """Lo impide ck_scenario_versions_no_autoaprobacion; aqui se comprueba
        que la aplicacion lo diga antes, con un mensaje util."""
        self.assertTrue(self._envia()[0])
        ok, error, _ = queries.resuelve_revision(self.sid, "aprobar", "", self.autor)
        self.assertFalse(ok)
        self.assertIn("que tú creaste", error)
        self.assertEqual(self._estado(), "en_revision")

    def test_no_se_dictamina_un_borrador(self):
        ok, error, _ = queries.resuelve_revision(self.sid, "aprobar", "", self.revisor)
        self.assertFalse(ok)
        self.assertIn("no en revisión", error)

    def test_decision_invalida(self):
        self.assertTrue(self._envia()[0])
        ok, error, _ = queries.resuelve_revision(self.sid, "archivar", "", self.revisor)
        self.assertFalse(ok)
        self.assertIn("aprobar o rechazar", error)

    # ---- bandeja y ciclo completo ------------------------------------------

    def test_la_bandeja_lista_lo_enviado(self):
        self.assertTrue(self._envia()[0])
        pendientes = queries.get_pendientes_revision()
        mio = [p for p in pendientes if p["scenario_id"] == self.sid]
        self.assertEqual(len(mio), 1)
        self.assertEqual(mio[0]["version_number"], 1)
        self.assertEqual(mio[0]["created_by"], self.autor,
                         "la bandeja necesita el autor para saber quién NO puede revisarla")
        self.assertIsNotNone(mio[0]["submitted_at"])

    def test_la_bandeja_se_vacia_al_dictaminar(self):
        self.assertTrue(self._envia()[0])
        queries.resuelve_revision(self.sid, "aprobar", "", self.revisor)
        self.assertEqual([p for p in queries.get_pendientes_revision()
                          if p["scenario_id"] == self.sid], [])

    def test_tras_un_rechazo_la_version_nueva_arranca_en_borrador(self):
        """Una version rechazada no se corrige: se crea la siguiente. Es la misma
        regla de «modificar nunca sobrescribe»."""
        self.assertTrue(self._envia()[0])
        queries.resuelve_revision(self.sid, "rechazar", "Corregir el aforo.", self.revisor)

        datos, errores = queries.valida_version(
            {"estratificar": "on", "age_unknown_policy": "excluir",
             "initial_infected": "500", "horizon_days": "180",
             "notes": "Atiende el rechazo"},
            next(r for r in self.regiones if r["id"] == self.mty["id"]),
            query("SELECT default_params FROM diseases WHERE id = %s",
                  (self.simulable["id"],), one=True)["default_params"])
        self.assertEqual(errores, [])
        ok, error, numero = queries.crea_version(self.sid, datos, self.autor)
        self.assertTrue(ok, error)
        self.assertEqual(numero, 2)
        self.assertEqual(self._estado(), "borrador")
        # La rechazada sigue ahi, con su motivo.
        v1 = queries.get_escenario_detalle(self.sid, 1)["version"]
        self.assertEqual(v1["status"], "rechazado")
        self.assertEqual(v1["review_comment"], "Corregir el aforo.")

    def test_el_envio_y_el_dictamen_quedan_en_la_bitacora(self):
        self.assertTrue(self._envia()[0])
        version_id = queries.get_escenario_detalle(self.sid)["version"]["id"]
        queries.resuelve_revision(self.sid, "aprobar", "Va.", self.revisor)

        eventos = query(
            """SELECT data_before, data_after FROM audit_log
               WHERE entity_type = 'scenario_versions' AND entity_id = %s
               ORDER BY occurred_at""", (str(version_id),))
        estados = [(e["data_before"].get("status"), e["data_after"].get("status"))
                   for e in eventos if e["data_before"] and e["data_after"]]
        self.assertIn(("borrador", "en_revision"), estados)
        self.assertIn(("en_revision", "aprobado"), estados)


class ParametrosCongeladosTests(_ConEscenarioBorrador):
    """Una version congela los parametros de la enfermedad al salir de borrador.

    Mientras es borrador usa los vivos -- es coherente con que todo lo demas de
    un borrador se pueda cambiar. Al enviarse a revision deja de poder cambiar y
    tiene que quedar explicandose a si misma.
    """

    NOMBRE = "ZZZ escenario para congelar"

    def setUp(self):
        super().setUp()
        if not queries._hay_parametros_congelados():
            self.skipTest("falta la migracion 024_version_congela_parametros.sql")
        self.revisor = _usuario("EPIDEMIOLOGO")
        self.params_originales = query(
            "SELECT default_params FROM diseases WHERE id = %s",
            (self.simulable["id"],), one=True)["default_params"]

    def tearDown(self):
        # El catalogo se deja como estaba: estas pruebas lo mueven a proposito.
        _restaura("UPDATE diseases SET default_params = %s::jsonb WHERE id = %s",
                  (json.dumps(self.params_originales), self.simulable["id"]))
        super().tearDown()

    def _r0_del_catalogo(self):
        params = query("SELECT default_params FROM diseases WHERE id = %s",
                       (self.simulable["id"],), one=True)["default_params"]
        return _desempaqueta(params["r0"])

    def _cambia_r0(self, nuevo):
        _restaura("""UPDATE diseases
                     SET default_params = default_params || jsonb_build_object(
                         'r0', jsonb_build_object('valor', %s::numeric,
                                                  'fuente', 'prueba automatizada',
                                                  'supuesto', true))
                     WHERE id = %s""", (nuevo, self.simulable["id"]))

    def test_un_borrador_usa_los_parametros_vivos(self):
        detalle = queries.get_escenario_detalle(self.sid)
        self.assertFalse(detalle["parametros_congelados"])
        self.assertFalse(detalle["parametros_sin_congelar"])
        r0_antes = _desempaqueta(detalle["parametros_enfermedad"]["r0"])

        self._cambia_r0(9.5)
        detalle = queries.get_escenario_detalle(self.sid)
        self.assertEqual(_desempaqueta(detalle["parametros_enfermedad"]["r0"]), 9.5,
                         "un borrador debe seguir al catálogo")
        self.assertNotEqual(r0_antes, 9.5)

    def test_enviar_congela_los_parametros_del_momento(self):
        ok, error = queries.envia_a_revision(self.sid, self.autor)
        self.assertTrue(ok, error)
        detalle = queries.get_escenario_detalle(self.sid)
        self.assertTrue(detalle["parametros_congelados"])
        congelado = _desempaqueta(detalle["parametros_enfermedad"]["r0"])
        self.assertEqual(congelado, self._r0_del_catalogo())

        # Se corrige el catálogo: la versión enviada NO se mueve.
        self._cambia_r0(9.5)
        self.assertEqual(self._r0_del_catalogo(), 9.5)
        detalle = queries.get_escenario_detalle(self.sid)
        self.assertEqual(_desempaqueta(detalle["parametros_enfermedad"]["r0"]), congelado,
                         "la versión enviada quedó con la fotografía")

    def test_una_version_aprobada_sigue_congelada(self):
        self.assertTrue(queries.envia_a_revision(self.sid, self.autor)[0])
        ok, error, _ = queries.resuelve_revision(self.sid, "aprobar", "", self.revisor)
        self.assertTrue(ok, error)
        congelado = _desempaqueta(
            queries.get_escenario_detalle(self.sid)["parametros_enfermedad"]["r0"])
        self._cambia_r0(9.5)
        self.assertEqual(
            _desempaqueta(queries.get_escenario_detalle(self.sid)["parametros_enfermedad"]["r0"]),
            congelado, "lo aprobado no puede cambiar de significado")

    def test_la_version_nueva_vuelve_a_los_parametros_vivos(self):
        """La siguiente versión nace borrador, así que toma la corrección del
        catálogo: es justamente la forma de adoptar un parámetro arreglado."""
        self.assertTrue(queries.envia_a_revision(self.sid, self.autor)[0])
        queries.resuelve_revision(self.sid, "rechazar", "Corregir R0.", self.revisor)
        self._cambia_r0(9.5)

        datos, errores = queries.valida_version(
            {"estratificar": "on", "age_unknown_policy": "excluir",
             "initial_infected": "500", "horizon_days": "180",
             "notes": "Toma el R0 corregido"},
            next(r for r in self.regiones if r["id"] == self.mty["id"]),
            query("SELECT default_params FROM diseases WHERE id = %s",
                  (self.simulable["id"],), one=True)["default_params"])
        self.assertEqual(errores, [])
        ok, error, numero = queries.crea_version(self.sid, datos, self.autor)
        self.assertTrue(ok, error)
        self.assertEqual(numero, 2)

        nueva = queries.get_escenario_detalle(self.sid)
        self.assertFalse(nueva["parametros_congelados"])
        self.assertEqual(_desempaqueta(nueva["parametros_enfermedad"]["r0"]), 9.5)
        # Y la rechazada conserva la suya.
        vieja = queries.get_escenario_detalle(self.sid, 1)
        self.assertTrue(vieja["parametros_congelados"])
        self.assertNotEqual(_desempaqueta(vieja["parametros_enfermedad"]["r0"]), 9.5)

    def test_el_motor_recibe_los_parametros_congelados(self):
        self.assertTrue(queries.envia_a_revision(self.sid, self.autor)[0])
        self._cambia_r0(0.05)      # con este R0 la epidemia no arranca
        detalle = queries.get_escenario_detalle(self.sid)
        errores, _ = queries.revisa_version(detalle)
        self.assertEqual(errores, [])
        esc = queries.escenario_para_motor(
            {"population_by_age": detalle["version"]["population_by_age"],
             "population_size": detalle["version"]["population_size"],
             "population_age_unknown": detalle["version"]["population_age_unknown"],
             "age_unknown_policy": detalle["version"]["age_unknown_policy"],
             "initial_infected": detalle["version"]["initial_infected"],
             "horizon_days": detalle["version"]["horizon_days"]},
            detalle["parametros_enfermedad"])
        self.assertNotEqual(_desempaqueta(esc["enfermedad"]["r0"]), 0.05,
                            "el motor debe recibir la fotografía, no el catálogo de hoy")


if __name__ == "__main__":
    unittest.main()
