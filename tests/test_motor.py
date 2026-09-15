"""Pruebas del motor de referencia.

    python -m unittest discover -s tests -t . -v

Las comparaciones entre escenarios promedian varias semillas para no depender
de la suerte de una sola corrida estocastica.
"""

import copy
import json
import unittest

from motor import ENGINE_VERSION, EscenarioInvalido, simular, validar_escenario

SEMILLAS = range(1, 7)

ENFERMEDAD = {
    "r0": {"valor": 1.8, "fuente": "prueba", "supuesto": True},
    "incubacion_dias": 2.0,
    "infeccioso_dias": 5.0,
    "dias_hospitalizacion": 6.0,
    "tasa_hospitalizacion": {"0-19": 0.002, "20-59": 0.01, "60+": 0.08},
    "letalidad": {"0-19": 0.00005, "20-59": 0.001, "60+": 0.03},
}


def escenario(**cambios):
    base = {
        "poblacion": {"0-19": 60_000, "20-59": 110_000, "60+": 30_000},
        "infectados_iniciales": 50,
        "dias": 120,
        "enfermedad": copy.deepcopy(ENFERMEDAD),
        "intervenciones": [],
    }
    base.update(cambios)
    return base


def promedio(esc, campo):
    return sum(simular(esc, s)["resumen"][campo] for s in SEMILLAS) / len(SEMILLAS)


class Reproducibilidad(unittest.TestCase):
    def test_misma_semilla_mismo_resultado(self):
        self.assertEqual(simular(escenario(), 982314), simular(escenario(), 982314))

    def test_semilla_distinta_cambia_la_corrida(self):
        self.assertNotEqual(simular(escenario(), 1)["serie"], simular(escenario(), 2)["serie"])

    def test_metadatos_de_corrida(self):
        r = simular(escenario(), 42)
        self.assertEqual(r["engine_version"], ENGINE_VERSION)
        self.assertEqual(r["semilla"], 42)
        self.assertEqual(len(r["huella_escenario"]), 64)
        self.assertEqual(r["huella_escenario"], simular(escenario(), 7)["huella_escenario"])

    def test_salida_serializable_a_json(self):
        json.dumps(simular(escenario(), 3))

    def test_semilla_invalida(self):
        for mala in (-1, 1.5, "1", True):
            with self.assertRaises(ValueError):
                simular(escenario(), mala)


class Conservacion(unittest.TestCase):
    def test_poblacion_constante_todos_los_dias(self):
        r = simular(escenario(intervenciones=[
            {"tipo": "VACUNACION", "dia_inicio": 10, "params": {"eficacia": 0.8, "dosis_diarias": 2000}},
        ]), 11)
        for f in r["serie"]:
            self.assertEqual(f["S"] + f["E"] + f["I"] + f["R"] + f["H"] + f["D"] + f["V"], 200_000)

    def test_serie_cubre_dia_0_a_horizonte(self):
        r = simular(escenario(dias=30), 1)
        self.assertEqual([f["dia"] for f in r["serie"]], list(range(31)))

    def test_acumulados_igual_a_quienes_dejaron_de_ser_susceptibles(self):
        r = simular(escenario(), 5)
        fin = r["serie"][-1]
        self.assertEqual(r["resumen"]["casos_acumulados"], 200_000 - fin["S"] - fin["V"])

    def test_desglose_suma_el_total(self):
        s = simular(escenario(), 5)["resumen"]
        self.assertEqual(sum(g["casos"] for g in s["desglose_por_grupo"]), s["casos_acumulados"])
        self.assertEqual(sum(g["fallecimientos"] for g in s["desglose_por_grupo"]), s["fallecimientos"])


class Indicadores(unittest.TestCase):
    def test_pico_coincide_con_la_serie(self):
        r = simular(escenario(), 9)
        s = r["resumen"]
        maximo = max(f["casos_activos"] for f in r["serie"])
        primer_dia = next(f["dia"] for f in r["serie"] if f["casos_activos"] == maximo)
        self.assertEqual((s["pico_casos_activos"], s["dia_pico"]), (maximo, primer_dia))

    def test_tasa_de_ataque(self):
        s = simular(escenario(), 9)["resumen"]
        self.assertAlmostEqual(s["tasa_ataque"], s["casos_acumulados"] / 200_000, places=6)


class Epidemiologia(unittest.TestCase):
    def test_r0_menor_a_1_no_genera_brote(self):
        esc = escenario()
        esc["enfermedad"]["r0"] = 0.5
        self.assertLess(promedio(esc, "tasa_ataque"), 0.005)

    def test_mayor_r0_mayor_tasa_de_ataque(self):
        bajo, alto = escenario(), escenario()
        bajo["enfermedad"]["r0"] = 1.4
        alto["enfermedad"]["r0"] = 2.5
        self.assertLess(promedio(bajo, "tasa_ataque"), promedio(alto, "tasa_ataque"))

    def test_cierre_escolar_reduce_casos(self):
        cierre = escenario(intervenciones=[
            {"tipo": "CIERRE_ESCUELAS", "dia_inicio": 7, "dia_fin": 90, "params": {"reduccion": 1.0}}])
        self.assertLess(promedio(cierre, "casos_acumulados"),
                        0.9 * promedio(escenario(), "casos_acumulados"))

    def test_vacunar_60_mas_reduce_fallecimientos(self):
        vacuna = escenario(intervenciones=[
            {"tipo": "VACUNACION", "dia_inicio": 10, "cobertura": 0.7,
             "params": {"eficacia": 0.9, "dosis_diarias": 2000,
                        "prioridad": "edad_desc", "edad_minima": 60}}])
        self.assertLess(promedio(vacuna, "fallecimientos"),
                        0.8 * promedio(escenario(), "fallecimientos"))

    def test_priorizar_mayores_salva_mas_que_aleatorio(self):
        def con(prioridad):
            return escenario(intervenciones=[
                {"tipo": "VACUNACION", "dia_inicio": 10, "dia_fin": 20,
                 "params": {"eficacia": 0.9, "dosis_diarias": 1500, "prioridad": prioridad}}])
        self.assertLess(promedio(con("edad_desc"), "fallecimientos"),
                        promedio(con("aleatorio"), "fallecimientos"))

    def test_dosis_no_rebasan_la_cobertura(self):
        r = simular(escenario(intervenciones=[
            {"tipo": "VACUNACION", "dia_inicio": 1, "cobertura": 0.7,
             "params": {"eficacia": 1.0, "dosis_diarias": 50_000, "edad_minima": 60}}]), 4)
        grupos = {g["grupo"]: g for g in r["resumen"]["desglose_por_grupo"]}
        self.assertLessEqual(grupos["60+"]["dosis_aplicadas"], 21_000)
        self.assertEqual(grupos["0-19"]["dosis_aplicadas"], 0)
        self.assertEqual(grupos["20-59"]["dosis_aplicadas"], 0)

    def test_intervencion_despues_del_horizonte_no_cambia_nada(self):
        tarde = escenario(dias=60, intervenciones=[
            {"tipo": "CIERRE_ESCUELAS", "dia_inicio": 80, "params": {}}])
        r = simular(tarde, 8)
        self.assertEqual(r["serie"], simular(escenario(dias=60), 8)["serie"])
        self.assertTrue(any("horizonte" in a for a in r["avisos"]))


class Validacion(unittest.TestCase):
    def test_escenario_valido_sin_errores(self):
        self.assertEqual(validar_escenario(escenario()), [])

    def test_junta_todos_los_errores(self):
        esc = escenario(dias=0, intervenciones=[
            {"tipo": "INVENTADA", "dia_inicio": 1},
            {"tipo": "CIERRE_ESCUELAS", "dia_inicio": 10, "dia_fin": 5},
        ])
        del esc["enfermedad"]["r0"]
        esc["enfermedad"]["letalidad"] = 1.5
        errores = validar_escenario(esc)
        self.assertGreaterEqual(len(errores), 5, errores)

    def test_sin_valores_epidemiologicos_por_defecto(self):
        for clave in ("r0", "incubacion_dias", "infeccioso_dias", "dias_hospitalizacion",
                      "tasa_hospitalizacion", "letalidad"):
            esc = escenario()
            del esc["enfermedad"][clave]
            with self.subTest(clave=clave), self.assertRaises(EscenarioInvalido):
                simular(esc, 1)

    def test_transmisibilidad_base_no_se_convierte_en_r0(self):
        esc = escenario()
        del esc["enfermedad"]["r0"]
        esc["enfermedad"]["transmisibilidad_base"] = 0.045
        self.assertTrue(any("transmisibilidad_base" in e for e in validar_escenario(esc)))

    def test_limites_de_scenario_versions(self):
        self.assertTrue(validar_escenario(escenario(poblacion=500)))
        self.assertTrue(validar_escenario(escenario(dias=2000)))
        self.assertTrue(validar_escenario(escenario(infectados_iniciales=0)))

    def test_tasas_por_grupo_deben_cubrir_todos_los_grupos(self):
        esc = escenario()
        esc["enfermedad"]["letalidad"] = {"0-19": 0.0001}
        self.assertTrue(any("no define los grupos" in e for e in validar_escenario(esc)))

    def test_edad_minima_requiere_poblacion_por_edad(self):
        esc = escenario(poblacion=200_000, intervenciones=[
            {"tipo": "VACUNACION", "dia_inicio": 1,
             "params": {"eficacia": 0.9, "dosis_diarias": 100, "edad_minima": 60}}])
        esc["enfermedad"]["tasa_hospitalizacion"] = 0.01
        esc["enfermedad"]["letalidad"] = 0.001
        self.assertTrue(any("edad_minima" in e for e in validar_escenario(esc)))

    def test_parametros_obligatorios_de_intervencion(self):
        esc = escenario(intervenciones=[{"tipo": "REDUCCION_AFORO", "dia_inicio": 3, "params": {}}])
        self.assertTrue(any("reduccion" in e for e in validar_escenario(esc)))


class Trazabilidad(unittest.TestCase):
    def test_estado_de_cada_parametro(self):
        r = simular(escenario(), 1)
        estados = {t["parametro"]: t["estado"] for t in r["trazabilidad_parametros"]}
        self.assertEqual(estados["r0"], "supuesto")
        self.assertEqual(estados["incubacion_dias"], "sin_fuente")
        self.assertEqual(estados["capas_contacto"], "supuesto")
        self.assertTrue(any("sin fuente" in a for a in r["avisos"]))

    def test_parametro_con_fuente(self):
        esc = escenario()
        esc["enfermedad"]["incubacion_dias"] = {"valor": 2.0, "fuente": "Articulo X"}
        estados = {t["parametro"]: t["estado"] for t in simular(esc, 1)["trazabilidad_parametros"]}
        self.assertEqual(estados["incubacion_dias"], "con_fuente")

    def test_acepta_formato_de_distribucion_de_010(self):
        esc = escenario()
        esc["enfermedad"]["incubacion_dias"] = {"dist": "lognormal", "media": 2.0, "desv": 0.8}
        self.assertEqual(validar_escenario(esc), [])


if __name__ == "__main__":
    unittest.main()
