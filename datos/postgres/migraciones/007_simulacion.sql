-- =============================================================================
-- 007_simulacion.sql
-- Dominio: simulacion.  Servicio propietario: simulation-service.
-- Tablas: simulation_batches, simulation_runs.
--
-- Aqui viven solo los metadatos. Las series diarias van a MongoDB y las
-- salidas voluminosas a Cloud Storage; esta base guarda unicamente el
-- identificador del documento y la ruta del artefacto.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- simulation_batches
-- -----------------------------------------------------------------------------
-- Un lote son entre 30 y 50 replicas de la misma version con semillas
-- distintas. El lote, no la corrida, es la unidad que se compara en la
-- frontera de eficiencia: una sola corrida de un modelo estocastico no
-- significa nada.
CREATE TABLE IF NOT EXISTS simulation_batches (
    id                  BIGSERIAL   PRIMARY KEY,
    scenario_version_id BIGINT      NOT NULL,
    requested_by        BIGINT      NOT NULL,
    replicas            SMALLINT    NOT NULL DEFAULT 30,
    engine              VARCHAR(20) NOT NULL DEFAULT 'numba',
    status              VARCHAR(20) NOT NULL DEFAULT 'encolado',
    summary_doc_id      VARCHAR(64),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at         TIMESTAMPTZ,

    CONSTRAINT fk_simulation_batches_version
        FOREIGN KEY (scenario_version_id) REFERENCES scenario_versions (id) ON DELETE RESTRICT,
    CONSTRAINT fk_simulation_batches_user
        FOREIGN KEY (requested_by)        REFERENCES users (id)             ON DELETE RESTRICT,
    -- Menos de 30 replicas no permite reportar mediana con banda de
    -- incertidumbre; mas de 200 satura la cola sin ganancia estadistica.
    CONSTRAINT ck_simulation_batches_replicas CHECK (replicas BETWEEN 30 AND 200),
    CONSTRAINT ck_simulation_batches_engine   CHECK (engine IN ('numba', 'cuda')),
    CONSTRAINT ck_simulation_batches_status   CHECK (status IN
        ('encolado', 'ejecutando', 'completado', 'fallido', 'cancelado')),
    CONSTRAINT ck_simulation_batches_fin CHECK (
        finished_at IS NULL OR finished_at >= created_at
    ),
    -- Un lote terminado tiene fecha de termino, y solo uno completado puede
    -- tener resumen agregado.
    CONSTRAINT ck_simulation_batches_terminal CHECK (
        (status IN ('completado', 'fallido', 'cancelado')) = (finished_at IS NOT NULL)
    ),
    CONSTRAINT ck_simulation_batches_resumen CHECK (
        summary_doc_id IS NULL OR status = 'completado'
    )
);

CREATE INDEX IF NOT EXISTS ix_simulation_batches_version
    ON simulation_batches (scenario_version_id);
CREATE INDEX IF NOT EXISTS ix_simulation_batches_user
    ON simulation_batches (requested_by, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_simulation_batches_activos
    ON simulation_batches (status) WHERE status IN ('encolado', 'ejecutando');

-- -----------------------------------------------------------------------------
-- simulation_runs
-- -----------------------------------------------------------------------------
-- id es el job_id que se devuelve al cliente en POST /api/v1/simulations.
-- El progreso en vivo se lleva en Redis (job:{id}:progress); la columna
-- progress guarda el valor consolidado para cuando Redis se reinicie.
CREATE TABLE IF NOT EXISTS simulation_runs (
    id                  BIGSERIAL    PRIMARY KEY,
    batch_id            BIGINT,
    scenario_version_id BIGINT       NOT NULL,
    seed                BIGINT       NOT NULL,
    replica_index       SMALLINT,
    status              VARCHAR(20)  NOT NULL DEFAULT 'encolado',
    progress            SMALLINT     NOT NULL DEFAULT 0,
    engine_version      VARCHAR(30),
    queued_at           TIMESTAMPTZ  NOT NULL DEFAULT now(),
    started_at          TIMESTAMPTZ,
    finished_at         TIMESTAMPTZ,
    result_doc_id       VARCHAR(64),
    artifacts_path      VARCHAR(255),
    error_message       TEXT,

    CONSTRAINT fk_simulation_runs_batch
        FOREIGN KEY (batch_id)            REFERENCES simulation_batches (id) ON DELETE CASCADE,
    CONSTRAINT fk_simulation_runs_version
        FOREIGN KEY (scenario_version_id) REFERENCES scenario_versions (id)  ON DELETE RESTRICT,
    CONSTRAINT ck_simulation_runs_status CHECK (status IN
        ('encolado', 'ejecutando', 'completado', 'fallido', 'cancelado')),
    CONSTRAINT ck_simulation_runs_progress CHECK (progress BETWEEN 0 AND 100),
    CONSTRAINT ck_simulation_runs_seed     CHECK (seed >= 0),
    CONSTRAINT ck_simulation_runs_replica  CHECK (replica_index IS NULL OR replica_index >= 0),
    -- Coherencia del ciclo de vida encolado -> ejecutando -> terminal.
    CONSTRAINT ck_simulation_runs_inicio CHECK (
        (status = 'encolado') = (started_at IS NULL)
    ),
    CONSTRAINT ck_simulation_runs_fin CHECK (
        (status IN ('completado', 'fallido', 'cancelado')) = (finished_at IS NOT NULL)
    ),
    CONSTRAINT ck_simulation_runs_tiempos CHECK (
        (started_at  IS NULL OR started_at  >= queued_at)
        AND (finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at)
    ),
    -- Una corrida fallida explica por que; una completada apunta a su
    -- documento de resultados en MongoDB.
    CONSTRAINT ck_simulation_runs_error CHECK (
        (status = 'fallido') = (error_message IS NOT NULL)
    ),
    CONSTRAINT ck_simulation_runs_resultado CHECK (
        result_doc_id IS NULL OR status = 'completado'
    ),
    -- Dentro de un lote, ni la semilla ni el numero de replica se repiten.
    CONSTRAINT uq_simulation_runs_replica UNIQUE (batch_id, replica_index),
    CONSTRAINT uq_simulation_runs_semilla UNIQUE (batch_id, seed)
);

-- El worker del motor pregunta por trabajos pendientes; el tablero pregunta
-- por las corridas de un lote.
CREATE INDEX IF NOT EXISTS ix_simulation_runs_pendientes
    ON simulation_runs (queued_at) WHERE status = 'encolado';
CREATE INDEX IF NOT EXISTS ix_simulation_runs_batch   ON simulation_runs (batch_id);
CREATE INDEX IF NOT EXISTS ix_simulation_runs_version ON simulation_runs (scenario_version_id);
CREATE INDEX IF NOT EXISTS ix_simulation_runs_status  ON simulation_runs (status);

INSERT INTO schema_migrations (version, description)
VALUES ('007', 'Simulacion: lotes y corridas')
ON CONFLICT (version) DO NOTHING;

COMMIT;
