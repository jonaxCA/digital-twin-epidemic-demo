-- =============================================================================
-- 014_simulacion_resultados.sql
-- Dominio: simulacion.  Servicio propietario: simulation-service.
--
-- 007_simulacion.sql modelo la simulacion pensando en el motor definitivo
-- (numba/cuda, lotes de 30+ replicas) y en guardar las series en MongoDB.
-- Para el monolito de este avance eso no aplica todavia:
--
--   (1) el motor es python-ref (motor/, ENGINE_VERSION = 'python-ref-0.1'),
--   (2) se ejecuta una corrida a la vez, no lotes de replicas,
--   (3) NO hay MongoDB: los resultados se guardan aqui, en PostgreSQL.
--
-- Esta migracion ajusta esos tres puntos, agrega el usuario que pidio cada
-- corrida y lleva a la base la regla "solo se simula una version aprobada".
--
-- Tambien agrega a intervention_types el costo unitario que necesita la
-- frontera de Pareto (motor/pareto.py). Se agregan las columnas y la unidad
-- de cada tipo, pero NO un costo: inventar cifras economicas es justo lo que
-- el proyecto no debe hacer. Los captura el equipo con su fuente.
--
-- Es idempotente.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- simulation_batches: admitir el motor de referencia y corridas sueltas
-- -----------------------------------------------------------------------------
-- El limite de 30 replicas nacio de un motor estocastico donde una sola
-- corrida no significa nada. Sigue siendo cierto para el motor definitivo,
-- pero python-ref es reproducible por semilla y en esta etapa se ejecuta una
-- corrida por escenario, asi que el piso baja a 1.
ALTER TABLE simulation_batches
    DROP CONSTRAINT IF EXISTS ck_simulation_batches_engine,
    ADD  CONSTRAINT ck_simulation_batches_engine
        CHECK (engine IN ('python-ref', 'numba', 'cuda')),

    DROP CONSTRAINT IF EXISTS ck_simulation_batches_replicas,
    ADD  CONSTRAINT ck_simulation_batches_replicas
        CHECK (replicas BETWEEN 1 AND 200);

ALTER TABLE simulation_batches ALTER COLUMN engine SET DEFAULT 'python-ref';

-- -----------------------------------------------------------------------------
-- simulation_runs: quien pidio la corrida
-- -----------------------------------------------------------------------------
-- Hasta ahora el usuario solo vivia en el lote. Una corrida suelta no tenia
-- dueno, y la reproducibilidad exige saber quien la lanzo.
ALTER TABLE simulation_runs
    ADD COLUMN IF NOT EXISTS requested_by BIGINT;

UPDATE simulation_runs r
SET    requested_by = b.requested_by
FROM   simulation_batches b
WHERE  b.id = r.batch_id AND r.requested_by IS NULL;

DO $$
DECLARE
    huerfanas INTEGER;
BEGIN
    SELECT count(*) INTO huerfanas FROM simulation_runs WHERE requested_by IS NULL;
    IF huerfanas = 0 THEN
        ALTER TABLE simulation_runs ALTER COLUMN requested_by SET NOT NULL;
    ELSE
        -- No se tumba la migracion por datos viejos: se avisa y se deja
        -- opcional hasta que alguien les asigne dueno.
        RAISE NOTICE '014: % corridas sin usuario. requested_by queda opcional; '
                     'asignalas y luego corre: ALTER TABLE simulation_runs '
                     'ALTER COLUMN requested_by SET NOT NULL;', huerfanas;
    END IF;
END
$$;

ALTER TABLE simulation_runs
    DROP CONSTRAINT IF EXISTS fk_simulation_runs_user,
    ADD  CONSTRAINT fk_simulation_runs_user
        FOREIGN KEY (requested_by) REFERENCES users (id) ON DELETE RESTRICT;

CREATE INDEX IF NOT EXISTS ix_simulation_runs_user
    ON simulation_runs (requested_by, queued_at DESC);

-- -----------------------------------------------------------------------------
-- Regla: solo se simula una version APROBADA
-- -----------------------------------------------------------------------------
-- El planteamiento del proyecto separa quien construye el escenario de quien
-- lo autoriza. Si la regla vive solo en Flask, cualquier script que inserte
-- directo en simulation_runs se la salta. Aqui no.
CREATE OR REPLACE FUNCTION fn_version_aprobada()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_status VARCHAR(20);
BEGIN
    SELECT status INTO v_status
    FROM scenario_versions
    WHERE id = NEW.scenario_version_id;

    IF v_status IS DISTINCT FROM 'aprobado' THEN
        RAISE EXCEPTION
            'La version de escenario % no esta aprobada (estado: %); no se puede simular.',
            NEW.scenario_version_id, COALESCE(v_status, 'inexistente')
            USING ERRCODE = 'restrict_violation';
    END IF;

    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION fn_version_aprobada() IS
    'Trigger BEFORE INSERT: rechaza corridas y lotes sobre versiones de escenario que no esten aprobadas.';

DROP TRIGGER IF EXISTS tg_simulation_runs_version_aprobada ON simulation_runs;
CREATE TRIGGER tg_simulation_runs_version_aprobada
    BEFORE INSERT ON simulation_runs
    FOR EACH ROW EXECUTE FUNCTION fn_version_aprobada();

DROP TRIGGER IF EXISTS tg_simulation_batches_version_aprobada ON simulation_batches;
CREATE TRIGGER tg_simulation_batches_version_aprobada
    BEFORE INSERT ON simulation_batches
    FOR EACH ROW EXECUTE FUNCTION fn_version_aprobada();

-- -----------------------------------------------------------------------------
-- simulation_results: los resultados que iban a MongoDB
-- -----------------------------------------------------------------------------
-- Una fila por corrida. resumen y serie son exactamente lo que devuelve
-- motor.simular(): el resumen de indicadores y la serie diaria completa.
-- Las columnas generadas sacan del JSON los indicadores que la pantalla de
-- comparacion necesita ordenar y graficar, sin tener que abrir el documento.
CREATE TABLE IF NOT EXISTS simulation_results (
    run_id            BIGINT      PRIMARY KEY,
    engine_version    VARCHAR(30) NOT NULL,
    scenario_checksum CHAR(64),
    resumen           JSONB       NOT NULL,
    serie             JSONB       NOT NULL,
    trazabilidad      JSONB       NOT NULL DEFAULT '[]'::jsonb,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    casos_acumulados   INTEGER      GENERATED ALWAYS AS ((resumen->>'casos_acumulados')::integer)   STORED,
    hospitalizaciones  INTEGER      GENERATED ALWAYS AS ((resumen->>'hospitalizaciones')::integer)  STORED,
    fallecimientos     INTEGER      GENERATED ALWAYS AS ((resumen->>'fallecimientos')::integer)     STORED,
    pico_casos_activos INTEGER      GENERATED ALWAYS AS ((resumen->>'pico_casos_activos')::integer) STORED,
    dia_pico           SMALLINT     GENERATED ALWAYS AS ((resumen->>'dia_pico')::smallint)          STORED,
    tasa_ataque        NUMERIC(8,6) GENERATED ALWAYS AS ((resumen->>'tasa_ataque')::numeric)        STORED,

    CONSTRAINT fk_simulation_results_run
        FOREIGN KEY (run_id) REFERENCES simulation_runs (id) ON DELETE CASCADE,
    CONSTRAINT ck_simulation_results_resumen CHECK (jsonb_typeof(resumen) = 'object'),
    CONSTRAINT ck_simulation_results_serie   CHECK (jsonb_typeof(serie)   = 'array'),
    CONSTRAINT ck_simulation_results_traza   CHECK (jsonb_typeof(trazabilidad) = 'array'),
    -- La huella del escenario permite demostrar que dos corridas simularon
    -- exactamente la misma entrada (motor.huella_escenario()).
    CONSTRAINT ck_simulation_results_checksum
        CHECK (scenario_checksum IS NULL OR scenario_checksum ~ '^[0-9a-f]{64}$')
);

COMMENT ON TABLE simulation_results IS
    'Resultado de una corrida: indicadores resumen y serie diaria. Sustituye al documento de MongoDB mientras el sistema sea monolitico.';
COMMENT ON COLUMN simulation_results.resumen IS
    'Objeto con casos_acumulados, pico, dia_pico, hospitalizaciones, fallecimientos, tasa_ataque y desglose por grupo de edad.';
COMMENT ON COLUMN simulation_results.serie IS
    'Arreglo con un objeto por dia: S, E, I, R, H, D, V, casos activos y nuevos casos.';
COMMENT ON COLUMN simulation_results.trazabilidad IS
    'Parametros usados, con su fuente o su marca de supuesto, tal como los reporto el motor.';
COMMENT ON COLUMN simulation_results.scenario_checksum IS
    'SHA-256 de la entrada canonica del motor. Misma huella + misma semilla + mismo engine_version => mismo resultado.';

-- -----------------------------------------------------------------------------
-- intervention_types: costo unitario para la frontera de Pareto
-- -----------------------------------------------------------------------------
ALTER TABLE intervention_types
    ADD COLUMN IF NOT EXISTS unit_cost          NUMERIC(12,2),
    ADD COLUMN IF NOT EXISTS cost_unit          VARCHAR(30),
    ADD COLUMN IF NOT EXISTS cost_source        TEXT,
    ADD COLUMN IF NOT EXISTS cost_is_assumption BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE intervention_types
    DROP CONSTRAINT IF EXISTS ck_intervention_types_cost_unit,
    ADD  CONSTRAINT ck_intervention_types_cost_unit
        CHECK (cost_unit IS NULL OR cost_unit IN ('por_habitante_dia', 'por_dosis')),

    -- Misma regla que para los parametros de enfermedad: un costo se guarda
    -- con su fuente, o marcado explicitamente como supuesto. Nunca "a secas".
    DROP CONSTRAINT IF EXISTS ck_intervention_types_cost,
    ADD  CONSTRAINT ck_intervention_types_cost CHECK (
        unit_cost IS NULL
        OR (unit_cost >= 0
            AND cost_unit IS NOT NULL
            AND (cost_is_assumption OR cost_source IS NOT NULL))
    );

-- La unidad si se puede declarar sin inventar nada: se desprende de como
-- actua cada intervencion. El importe queda en NULL a proposito.
UPDATE intervention_types SET cost_unit = 'por_dosis'
WHERE  code = 'VACUNACION' AND cost_unit IS NULL;

UPDATE intervention_types SET cost_unit = 'por_habitante_dia'
WHERE  code <> 'VACUNACION' AND cost_unit IS NULL;

COMMENT ON COLUMN intervention_types.unit_cost IS
    'Costo unitario de aplicar la intervencion. NULL = sin capturar: la comparacion de costos no se puede calcular hasta que se defina.';
COMMENT ON COLUMN intervention_types.cost_unit IS
    'Unidad del costo: por_habitante_dia (intervenciones sobre capas de contacto y testeo) o por_dosis (vacunacion).';
COMMENT ON COLUMN intervention_types.cost_source IS
    'De donde salio la cifra. Obligatoria si el costo no esta marcado como supuesto.';
COMMENT ON COLUMN intervention_types.cost_is_assumption IS
    'TRUE si la cifra es un supuesto del equipo y no un dato con respaldo.';

INSERT INTO schema_migrations (version, description)
VALUES ('014', 'Simulacion: motor de referencia, resultados en PostgreSQL y costos de intervencion')
ON CONFLICT (version) DO NOTHING;

COMMIT;
