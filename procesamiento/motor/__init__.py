"""Motor epidemiologico de referencia de EPIDEMIA (python-ref).

Modelo compartimental SEIR con hospitalizados, fallecidos y vacunados
protegidos, estratificado por grupo de edad, estocastico y reproducible:
la misma entrada con la misma semilla produce exactamente la misma salida
bajo la misma ENGINE_VERSION.

El paquete no depende de Flask ni de la base de datos. Recibe un diccionario
con el escenario y regresa un diccionario serializable a JSON; la capa web se
encarga de leer la version del escenario, guardar la corrida y sus estados.
Asi, cuando el motor pase a ser un worker o microservicio, se mueve tal cual.

Uso minimo:

    from motor import simular
    resultado = simular(escenario, semilla=982314)
    resultado["resumen"]["fallecimientos"]
"""

from .modelo import AVISO_SIMULACION, ENGINE_VERSION, ErrorMotor, simular
from .parametros import CAPAS_CONTACTO_SUPUESTO, EscenarioInvalido, validar_escenario
from .pareto import (METRICAS_IMPACTO, ComparacionInvalida, comparar, costo_escenario,
                     frontera_pareto)

__all__ = [
    "AVISO_SIMULACION",
    "ENGINE_VERSION",
    "CAPAS_CONTACTO_SUPUESTO",
    "METRICAS_IMPACTO",
    "ComparacionInvalida",
    "ErrorMotor",
    "EscenarioInvalido",
    "comparar",
    "costo_escenario",
    "frontera_pareto",
    "simular",
    "validar_escenario",
]
