-- =============================================================================
-- 006_escenarios.sql
-- Dominio: escenarios.  Servicio propietario: scenario-service.
-- Tablas: scenarios, scenario_versions, scenario_interventions.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- scenarios
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scenarios (
    id          BIGSERIAL    PRIMARY KEY,
    name        VARCHAR(160) NOT NULL,
    description TEXT,
    disease_id  SMALLINT     NOT NULL,
    region_id   INTEGER      NOT NULL,
    owner_id    BIGINT       NOT NULL,
    status      VARCHAR(20)  NOT NULL DEFAULT 'borrador',
    is_public   BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT fk_scenarios_disease
        FOREIGN KEY (disease_id) REFERENCES diseases (id) ON DELETE RESTRICT,
    CONSTRAINT fk_scenarios_region
        FOREIGN KEY (region_id)  REFERENCES regions (id)  ON DELETE RESTRICT,
    CONSTRAINT fk_scenarios_owner
        FOREIGN KEY (owner_id)   REFERENCES users (id)    ON DELETE RESTRICT,
    CONSTRAINT ck_scenarios_status CHECK (status IN ('borrador', 'publicado', 'archivado')),
    -- Solo un escenario publicado puede aparecer en el sitio publico.
    CONSTRAINT ck_scenarios_publico CHECK (NOT is_public OR status = 'publicado'),
    -- Un mismo analista no puede tener dos escenarios con el mismo nombre.
    CONSTRAINT uq_scenarios_owner_name UNIQUE (owner_id, name)
);

DROP TRIGGER IF EXISTS tg_scenarios_updated_at ON scenarios;
CREATE TRIGGER tg_scenarios_updated_at
    BEFORE UPDATE ON scenarios
    FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

CREATE INDEX IF NOT EXISTS ix_scenarios_owner   ON scenarios (owner_id);
CREATE INDEX IF NOT EXISTS ix_scenarios_publicos ON scenarios (status) WHERE is_public;

-- -----------------------------------------------------------------------------
-- scenario_versions
-- -----------------------------------------------------------------------------
-- Una version es inmutable una vez creada: es lo que hace reproducible una
-- corrida. Si el analista cambia algo, se crea la version siguiente.
CREATE TABLE IF NOT EXISTS scenario_versions (
    id              BIGSERIAL    PRIMARY KEY,
    scenario_id     BIGINT       NOT NULL,
    version_number  INTEGER      NOT NULL DEFAULT 1,
    is_current      BOOLEAN      NOT NULL DEFAULT FALSE,
    xml_path        VARCHAR(255),
    xml_checksum    CHAR(64),
    population_size INTEGER      NOT NULL,
    horizon_days    SMALLINT     NOT NULL DEFAULT 365,
    notes           TEXT,
    created_by      BIGINT       NOT NULL,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT uq_scenario_versions_numero UNIQUE (scenario_id, version_number),
    CONSTRAINT fk_scenario_versions_scenario
        FOREIGN KEY (scenario_id) REFERENCES scenarios (id) ON DELETE CASCADE,
    CONSTRAINT fk_scenario_versions_author
        FOREIGN KEY (created_by)  REFERENCES users (id)     ON DELETE RESTRICT,
    CONSTRAINT ck_scenario_versions_numero CHECK (version_number >= 1),
    CONSTRAINT ck_scenario_versions_poblacion
        CHECK (population_size BETWEEN 1000 AND 5000000),
    CONSTRAINT ck_scenario_versions_horizonte
        CHECK (horizon_days BETWEEN 1 AND 1095),
    CONSTRAINT ck_scenario_versions_checksum
        CHECK (xml_checksum IS NULL OR xml_checksum ~ '^[0-9a-f]{64}$'),
    -- Si hay XML exportado tiene que haber huella, para poder demostrar que la
    -- corrida uso exactamente ese archivo.
    CONSTRAINT ck_scenario_versions_xml CHECK (
        (xml_path IS NULL AND xml_checksum IS NULL)
        OR (xml_path IS NOT NULL AND xml_checksum IS NOT NULL)
    )
);

-- Una sola version vigente por escenario. El indice parcial unico lo garantiza
-- sin bloquear las versiones historicas, que llevan is_current = FALSE.
CREATE UNIQUE INDEX IF NOT EXISTS uq_scenario_versions_vigente
    ON scenario_versions (scenario_id) WHERE is_current;

CREATE INDEX IF NOT EXISTS ix_scenario_versions_scenario
    ON scenario_versions (scenario_id, version_number DESC);

-- -----------------------------------------------------------------------------
-- scenario_interventions
-- -----------------------------------------------------------------------------
-- Calendario de intervenciones de una version: es el contenido que el motor
-- traduce a reglas por dia de simulacion.
CREATE TABLE IF NOT EXISTS scenario_interventions (
    id                   BIGSERIAL    PRIMARY KEY,
    scenario_version_id  BIGINT       NOT NULL,
    intervention_type_id SMALLINT     NOT NULL,
    target_region_id     INTEGER,
    start_day            SMALLINT     NOT NULL,
    end_day              SMALLINT,
    coverage             NUMERIC(4,3),
    compliance           NUMERIC(4,3),
    params               JSONB        NOT NULL DEFAULT '{}'::jsonb,
    order_index          SMALLINT     NOT NULL DEFAULT 0,

    CONSTRAINT fk_scenario_interventions_version
        FOREIGN KEY (scenario_version_id)  REFERENCES scenario_versions (id)  ON DELETE CASCADE,
    CONSTRAINT fk_scenario_interventions_type
        FOREIGN KEY (intervention_type_id) REFERENCES intervention_types (id) ON DELETE RESTRICT,
    CONSTRAINT fk_scenario_interventions_region
        FOREIGN KEY (target_region_id)     REFERENCES regions (id)            ON DELETE RESTRICT,
    CONSTRAINT ck_scenario_interventions_inicio CHECK (start_day >= 0),
    CONSTRAINT ck_scenario_interventions_rango  CHECK (end_day IS NULL OR end_day >= start_day),
    CONSTRAINT ck_scenario_interventions_cobertura
        CHECK (coverage   IS NULL OR coverage   BETWEEN 0 AND 1),
    CONSTRAINT ck_scenario_interventions_cumplimiento
        CHECK (compliance IS NULL OR compliance BETWEEN 0 AND 1),
    CONSTRAINT ck_scenario_interventions_params
        CHECK (jsonb_typeof(params) = 'object'),
    -- Dos intervenciones del mismo tipo que empiezan el mismo dia en la misma
    -- zona son casi siempre un error de captura del editor de escritorio.
    -- NULLS NOT DISTINCT hace que la regla aplique tambien cuando la zona es
    -- nula, es decir cuando la intervencion cubre toda la region del escenario.
    -- Requiere PostgreSQL 15 o superior.
    CONSTRAINT uq_scenario_interventions_unica
        UNIQUE NULLS NOT DISTINCT
        (scenario_version_id, intervention_type_id, start_day, target_region_id)
);

CREATE INDEX IF NOT EXISTS ix_scenario_interventions_version
    ON scenario_interventions (scenario_version_id, start_day);

INSERT INTO schema_migrations (version, description)
VALUES ('006', 'Escenarios, versionado e intervenciones programadas')
ON CONFLICT (version) DO NOTHING;

COMMIT;
