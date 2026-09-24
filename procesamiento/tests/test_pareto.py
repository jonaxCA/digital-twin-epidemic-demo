"""Pruebas de la comparacion de escenarios y la frontera de Pareto.

    python -m unittest discover -s tests -t . -v
"""

import json
import unittest

from motor import ComparacionInvalida, EscenarioInvalido, comparar, costo_escenario, frontera_pareto, simular
from tests.test_motor import escenario

COSTOS = {
    "CIERRE_ESCUELAS": {"valor": 10.0, "fuente": "prueba", "supuesto": True},
    "REDUCCION_AFORO": 4.0,
    "TESTEO_AISLAMIENTO": 2.0,
    "VACUNACION": {"valor": 300.0, "supuesto": True},
}


def pt(id_, costo, impacto):
    return {"id": id_, "costo": costo, "impacto": impacto}


def ids_dominados(resultado):
    return {p["id"] for p in resultado["puntos"] if p["dominado"]}


class Frontera(unittest.TestCase):
    def test_caso_basico(self):
        r = frontera_pareto([pt("A", 0, 100), pt("B", 10, 80), pt("C", 5, 90), pt("D", 12, 85)])
        self.assertEqual(ids_dominados(r), {"D"})
        self.assertEqual(r["frontera"], ["A", "C", "B"])
        self.assertEqual(next(p for p in r["puntos"] if p["id"] == "D")["dominado_por"], ["B"])

    def test_mismo_costo_menor_impacto_domina(self):
        r = frontera_pareto([pt("A", 5, 50), pt("B", 5, 40)])
        self.assertEqual(ids_dominados(r), {"A"})

    def test_mismo_impacto_menor_costo_domina(self):
        r = frontera_pareto([pt("A", 5, 40), pt("B", 3, 40)])
        self.assertEqual(ids_dominados(r), {"A"})

    def test_puntos_identicos_no_se_dominan(self):
        r = frontera_pareto([pt("A", 5, 40), pt("B", 5, 40)])
        self.assertEqual(ids_dominados(r), set())
        self.assertEqual(r["frontera"], ["A", "B"])

    def test_un_escenario_mejor_en_todo_domina_a_todos(self):
        r = frontera_pareto([pt("A", 1, 1), pt("B", 2, 5), pt("C", 9, 3)])
        self.assertEqual(r["frontera"], ["A"])
        self.assertEqual(ids_dominados(r), {"B", "C"})

    def test_frontera_no_contiene_pares_dominados(self):
        import random
        azar = random.Random(123)
        puntos = [pt(i, azar.randint(0, 50), azar.randint(0, 50)) for i in range(40)]
        r = frontera_pareto(puntos)
        frontera = [p for p in r["puntos"] if not p["dominado"]]
        for p in frontera:
            for q in frontera:
                self.assertFalse(q["costo"] <= p["costo"] and q["impacto"] <= p["impacto"]
                                 and (q["costo"] < p["costo"] or q["impacto"] < p["impacto"]))
        for p in r["puntos"]:
            if p["dominado"]:
                self.assertTrue(p["dominado_por"])

    def test_valida_entrada(self):
        with self.assertRaises(ComparacionInvalida):
            frontera_pareto([pt("A", 1, 1), pt("A", 2, 2)])
        with self.assertRaises(ComparacionInvalida):
            frontera_pareto([pt("A", -1, 1)])
        with self.assertRaises(ComparacionInvalida):
            frontera_pareto([pt("A", 1, float("nan"))])


class Costo(unittest.TestCase):
    def costo(self, esc, costos=COSTOS, semilla=1):
        return costo_escenario(esc, simular(esc, semilla), costos)

    def test_sin_intervenciones_cuesta_cero_sin_pedir_costos(self):
        self.assertEqual(self.costo(escenario(), costos={})["total"], 0)

    def test_capa_unitario_por_poblacion_por_intensidad_por_dias(self):
        esc = escenario(intervenciones=[
            {"tipo": "CIERRE_ESCUELAS", "dia_inicio": 7, "dia_fin": 45,
             "cobertura": 0.5, "cumplimiento": 0.8, "params": {"reduccion": 1.0}}])
        c = self.costo(esc)
        self.assertEqual(c["desglose"][0]["dias_activos"], 39)
        self.assertAlmostEqual(c["total"], 10.0 * 200_000 * 0.4 * 39, places=2)

    def test_reduccion_por_defecto_del_catalogo(self):
        esc = escenario(intervenciones=[{"tipo": "CIERRE_ESCUELAS", "dia_inicio": 1, "dia_fin": 1}])
        self.assertAlmostEqual(self.costo(esc)["total"], 10.0 * 200_000, places=2)

    def test_dias_recortados_al_horizonte(self):
        sin_fin = escenario(dias=60, intervenciones=[
            {"tipo": "REDUCCION_AFORO", "dia_inicio": 0, "params": {"reduccion": 0.5}}])
        largo = escenario(dias=60, intervenciones=[
            {"tipo": "REDUCCION_AFORO", "dia_inicio": 50, "dia_fin": 500, "params": {"reduccion": 0.5}}])
        self.assertEqual(self.costo(sin_fin)["desglose"][0]["dias_activos"], 60)
        self.assertEqual(self.costo(largo)["desglose"][0]["dias_activos"], 11)

    def test_testeo_se_cobra_por_deteccion(self):
        esc = escenario(intervenciones=[
            {"tipo": "TESTEO_AISLAMIENTO", "dia_inicio": 1, "dia_fin": 10,
             "params": {"deteccion": 0.3, "retraso_dias": 1}}])
        self.assertAlmostEqual(self.costo(esc)["total"], 2.0 * 200_000 * 0.3 * 10, places=2)

    def test_vacunacion_se_cobra_por_dosis_aplicadas(self):
        esc = escenario(intervenciones=[
            {"tipo": "VACUNACION", "dia_inicio": 5, "cobertura": 0.5,
             "params": {"eficacia": 0.8, "dosis_diarias": 1000, "edad_minima": 60}}])
        resultado = simular(esc, 2)
        c = costo_escenario(esc, resultado, COSTOS)
        dosis = resultado["resumen"]["dosis_aplicadas"]
        self.assertEqual(dosis, 15_000)
        self.assertAlmostEqual(c["total"], 300.0 * dosis, places=2)

    def test_sin_costos_por_defecto(self):
        esc = escenario(intervenciones=[{"tipo": "CIERRE_ESCUELAS", "dia_inicio": 1}])
        with self.assertRaises(ComparacionInvalida) as ctx:
            self.costo(esc, costos={})
        self.assertIn("CIERRE_ESCUELAS", str(ctx.exception))

    def test_costo_negativo_invalido(self):
        esc = escenario(intervenciones=[{"tipo": "CIERRE_ESCUELAS", "dia_inicio": 1}])
        with self.assertRaises(ComparacionInvalida):
            self.costo(esc, costos={"CIERRE_ESCUELAS": -5})

    def test_resultado_de_otro_escenario_se_rechaza(self):
        otro = simular(escenario(dias=90), 1)
        with self.assertRaises(ComparacionInvalida):
            costo_escenario(escenario(), otro, COSTOS)

    def test_escenario_invalido(self):
        esc = escenario(dias=0)
        with self.assertRaises(EscenarioInvalido):
            costo_escenario(esc, {"huella_escenario": ""}, COSTOS)


class Comparacion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cierre = {"tipo": "CIERRE_ESCUELAS", "dia_inicio": 7, "dia_fin": 60, "params": {"reduccion": 1.0}}
        vacuna = {"tipo": "VACUNACION", "dia_inicio": 10, "cobertura": 0.7,
                  "params": {"eficacia": 0.9, "dosis_diarias": 2000,
                             "prioridad": "edad_desc", "edad_minima": 60}}
        cls.entradas = []
        for id_, ivs in (("A", []), ("B", [cierre]), ("C", [vacuna]), ("D", [cierre, vacuna])):
            esc = escenario(intervenciones=ivs)
            cls.entradas.append({"id": id_, "nombre": f"Escenario {id_}",
                                 "escenario": esc, "resultado": simular(esc, 982314)})

    def test_estructura_y_json(self):
        r = comparar(self.entradas, COSTOS, base="A")
        json.dumps(r)
        self.assertEqual([f["id"] for f in r["filas"]], ["A", "B", "C", "D"])
        self.assertTrue(r["frontera"])
        self.assertEqual({t["tipo"] for t in r["trazabilidad_costos"]}, {"CIERRE_ESCUELAS", "VACUNACION"})

    def test_sin_intervencion_con_costo_cero_siempre_esta_en_la_frontera(self):
        self.assertIn("A", comparar(self.entradas, COSTOS)["frontera"])

    def test_frontera_coincide_con_frontera_pareto(self):
        r = comparar(self.entradas, COSTOS, metrica="hospitalizaciones")
        esperado = frontera_pareto([pt(f["id"], f["costo"], f["impacto"]) for f in r["filas"]])
        self.assertEqual(r["frontera"], esperado["frontera"])

    def test_impacto_evitado_contra_la_base(self):
        r = comparar(self.entradas, COSTOS, base="A")
        filas = {f["id"]: f for f in r["filas"]}
        self.assertIsNone(filas["A"]["impacto_evitado"])
        for id_ in "BCD":
            f = filas[id_]
            self.assertEqual(f["impacto_evitado"], filas["A"]["impacto"] - f["impacto"])
            self.assertAlmostEqual(f["costo_adicional"], f["costo"] - filas["A"]["costo"], places=2)
            if f["impacto_evitado"] > 0:
                self.assertAlmostEqual(f["costo_por_unidad_evitada"],
                                       f["costo_adicional"] / f["impacto_evitado"], places=1)

    def test_sin_evitados_no_hay_costo_por_evitado(self):
        entradas = [dict(e) for e in self.entradas[:2]]
        entradas.append({**self.entradas[0], "id": "A2"})
        r = comparar(entradas, COSTOS, base="A")
        a2 = next(f for f in r["filas"] if f["id"] == "A2")
        self.assertEqual(a2["impacto_evitado"], 0)
        self.assertIsNone(a2["costo_por_unidad_evitada"])

    def test_errores(self):
        with self.assertRaises(ComparacionInvalida):
            comparar(self.entradas[:1], COSTOS)
        with self.assertRaises(ComparacionInvalida):
            comparar(self.entradas, COSTOS, metrica="felicidad")
        with self.assertRaises(ComparacionInvalida):
            comparar(self.entradas, COSTOS, base="Z")
        with self.assertRaises(ComparacionInvalida) as ctx:
            comparar(self.entradas, {})
        self.assertIn("Escenario B", str(ctx.exception))

    def test_horizontes_distintos_no_son_comparables(self):
        corto = escenario(dias=60)
        entradas = self.entradas[:1] + [{"id": "X", "escenario": corto, "resultado": simular(corto, 1)}]
        with self.assertRaises(ComparacionInvalida):
            comparar(entradas, COSTOS)

    def test_aviso_por_poblaciones_distintas(self):
        chica = escenario(poblacion={"0-19": 30_000, "20-59": 55_000, "60+": 15_000})
        entradas = self.entradas[:1] + [{"id": "X", "escenario": chica, "resultado": simular(chica, 1)}]
        self.assertTrue(any("poblaciones" in a for a in comparar(entradas, COSTOS)["avisos"]))

    def test_aviso_por_costo_sin_fuente(self):
        r = comparar(self.entradas, {**COSTOS, "CIERRE_ESCUELAS": 10.0})
        self.assertTrue(any("CIERRE_ESCUELAS" in a for a in r["avisos"]))


if __name__ == "__main__":
    unittest.main()
