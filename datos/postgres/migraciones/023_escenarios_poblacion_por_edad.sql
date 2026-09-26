-- =============================================================================
-- 023_escenarios_poblacion_por_edad.sql
-- Dominio: escenarios.
--
-- Prepara `scenario_versions` para lo que el motor ya sabe consumir: poblacion
-- abierta por grupo de edad y una decision explicita sobre la gente sin edad
-- declarada. Hasta ahora la version guardaba un solo entero, asi que un
-- escenario estratificado no se podia representar ni, por lo tanto, reproducir.
--
-- 1) EL TOPE DE POBLACION SUBE DE 5 A 20 MILLONES
-- Nuevo Leon tiene 5,784,442 habitantes, asi que con el tope anterior un
-- escenario del estado completo era imposible de guardar -- y es el primero que
-- alguien va a pedir. Ningun municipio se acercaba al tope, de ahi que no se
-- hubiera notado. Se pone en 20,000,000: cubre con margen a la entidad mas
-- poblada del pais (Estado de Mexico, 16,992,418 en el Censo 2020), asi que el
-- limite deja de ser un obstaculo sin volverse un cheque en blanco. El mismo
-- numero esta en POBLACION_MAX del motor; los dos tienen que moverse juntos.
--
-- 2) POBLACION POR GRUPO DE EDAD, GUARDADA EN LA VERSION
-- `population_by_age` guarda el reparto que se USO, no un puntero a la region.
-- Es la misma decision que ya tomaron `population_size`, `horizon_days` e
-- `initial_infected`: una version es una fotografia. Si manana se corrige la
-- poblacion de un municipio, las corridas viejas siguen explicando su propio
-- resultado. Queda NULL cuando el escenario no se estratifica.
--
-- 3) LA EDAD NO DECLARADA EXIGE POLITICA
-- `population_age_unknown` son las personas que el censo cuenta sin ponerles
-- edad (21 de cada 1,000 en Nuevo Leon). `age_unknown_policy` dice que se hizo
-- con ellas: 'excluir' las deja fuera de la corrida, 'prorratear' las reparte
-- entre los grupos -- una imputacion, que el motor reporta como supuesto. El
-- CHECK las ata: si hay gente sin edad hay politica, y si no hay, no.
--
-- Lo que la base NO puede comprobar es que population_size sea igual a la suma
-- de los grupos mas los sin edad, porque un CHECK no admite subconsultas y
-- sumar un JSONB las necesita. Eso lo valida `queries.valida_escenario`.
--
-- Es idempotente.
-- =============================================================================

BEGIN;

ALTER TABLE scenario_versions
    DROP CONSTRAINT IF EXISTS ck_scenario_versions_poblacion,
    ADD  CONSTRAINT ck_scenario_versions_poblacion CHECK (
        population_size >= 1000 AND population_size <= 20000000);

ALTER TABLE scenario_versions
    ADD COLUMN IF NOT EXISTS population_by_age      JSONB,
    ADD COLUMN IF NOT EXISTS population_age_unknown INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS age_unknown_policy     VARCHAR(20);

ALTER TABLE scenario_versions
    DROP CONSTRAINT IF EXISTS ck_scenario_versions_edad,
    ADD  CONSTRAINT ck_scenario_versions_edad CHECK (
        population_age_unknown >= 0
        -- Sin grupos de edad no hay "sin edad": ese entero solo significa algo
        -- frente a un reparto por grupos.
        AND (population_age_unknown = 0 OR population_by_age IS NOT NULL)
        -- Politica exactamente cuando hace falta: ni de mas ni de menos.
        AND (population_age_unknown = 0) = (age_unknown_policy IS NULL)
        AND (age_unknown_policy IS NULL
             OR age_unknown_policy IN ('excluir', 'prorratear'))
        AND (population_by_age IS NULL
             OR jsonb_typeof(population_by_age) = 'object'));

COMMENT ON COLUMN scenario_versions.population_by_age IS
    'Poblacion por grupo de edad que uso esta version, como {"0-19": 307729, ...}. Es una fotografia, no un puntero a region_age_groups: si la poblacion de la region se corrige despues, esta version sigue explicando su propio resultado. NULL cuando el escenario no se estratifica por edad. Las claves tienen que coincidir con las de diseases.default_params -> letalidad_por_edad.';
COMMENT ON COLUMN scenario_versions.population_age_unknown IS
    'Personas que el censo cuenta sin edad declarada y que por eso no caen en ningun grupo. Cero cuando el escenario no se estratifica.';
COMMENT ON COLUMN scenario_versions.age_unknown_policy IS
    'Que se hizo con la poblacion sin edad declarada: excluir (queda fuera de la corrida) o prorratear (se reparte entre los grupos, lo que es una imputacion y el motor la reporta como supuesto). Obligatoria si population_age_unknown > 0, prohibida si es cero.';
COMMENT ON COLUMN scenario_versions.population_size IS
    'Poblacion total de la version. Cuando hay reparto por edad, es la suma de population_by_age mas population_age_unknown; lo verifica la aplicacion, porque un CHECK no puede sumar un JSONB.';

INSERT INTO schema_migrations (version, description)
VALUES ('023', 'Escenarios: poblacion por grupo de edad, politica de edad desconocida y tope de 20 millones')
ON CONFLICT (version) DO NOTHING;

COMMIT;
