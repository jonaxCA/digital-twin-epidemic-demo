-- =============================================================================
-- 013_escenarios_aprobacion.sql
-- Dominio: escenarios.  Servicio propietario: scenario-service.
--
-- Agrega a scenario_versions lo que le falta para el flujo que pide el
-- planteamiento del proyecto:
--
--     ANALISTA crea  ->  BORRADOR  ->  EN REVISION  ->  EPIDEMIOLOGO
--                                                        /        \
--                                                    APROBADO   RECHAZADO
--
-- Decision de diseno: el flujo de revision vive en la VERSION, no en el
-- escenario. scenarios.status ('borrador'/'publicado'/'archivado') se queda
-- como esta: describe el ciclo de publicacion del escenario completo. Lo que
-- se revisa y se aprueba es una version concreta e inmutable, que es tambien
-- lo unico que se puede simular de forma reproducible. Consecuencia buscada:
-- al crear la version siguiente de un escenario aprobado, esa version nueva
-- nace en 'borrador' y hay que volver a aprobarla.
--
-- Tambien agrega initial_infected, que el motor necesita y no existia en 006.
--
-- Es idempotente: columnas con IF NOT EXISTS y restricciones con
-- DROP CONSTRAINT IF EXISTS antes del ADD.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- Columnas nuevas
-- -----------------------------------------------------------------------------
ALTER TABLE scenario_versions
    ADD COLUMN IF NOT EXISTS initial_infected INTEGER     NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS status           VARCHAR(20) NOT NULL DEFAULT 'borrador',
    ADD COLUMN IF NOT EXISTS submitted_at     TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS reviewed_by      BIGINT,
    ADD COLUMN IF NOT EXISTS reviewed_at      TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS review_comment   TEXT;

-- -----------------------------------------------------------------------------
-- Reglas de negocio
-- -----------------------------------------------------------------------------
ALTER TABLE scenario_versions
    DROP CONSTRAINT IF EXISTS fk_scenario_versions_reviewer,
    ADD  CONSTRAINT fk_scenario_versions_reviewer
        FOREIGN KEY (reviewed_by) REFERENCES users (id) ON DELETE RESTRICT,

    DROP CONSTRAINT IF EXISTS ck_scenario_versions_status,
    ADD  CONSTRAINT ck_scenario_versions_status CHECK (status IN
        ('borrador', 'en_revision', 'aprobado', 'rechazado')),

    -- No se puede arrancar una epidemia con cero infectados, ni con mas
    -- infectados que habitantes.
    DROP CONSTRAINT IF EXISTS ck_scenario_versions_iniciales,
    ADD  CONSTRAINT ck_scenario_versions_iniciales
        CHECK (initial_infected BETWEEN 1 AND population_size),

    -- Un estado distinto de borrador implica que alguien la envio a revision.
    DROP CONSTRAINT IF EXISTS ck_scenario_versions_envio,
    ADD  CONSTRAINT ck_scenario_versions_envio
        CHECK (status = 'borrador' OR submitted_at IS NOT NULL),

    -- Coherencia del dictamen: una version resuelta sabe quien la resolvio y
    -- cuando; una que sigue en tramite no trae dictamen. Rechazar exige
    -- motivo, para que el analista sepa que corregir.
    DROP CONSTRAINT IF EXISTS ck_scenario_versions_revision,
    ADD  CONSTRAINT ck_scenario_versions_revision CHECK (
        CASE status
            WHEN 'borrador'    THEN reviewed_by IS NULL     AND reviewed_at IS NULL
            WHEN 'en_revision' THEN reviewed_by IS NULL     AND reviewed_at IS NULL
            WHEN 'aprobado'    THEN reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL
            WHEN 'rechazado'   THEN reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL
                                    AND review_comment IS NOT NULL
        END
    ),

    -- Separacion de responsabilidades: quien construye el escenario no es
    -- quien lo autoriza. La aplicacion ademas exige el rol EPIDEMIOLOGO, pero
    -- esta regla vive en la base para que ninguna via (script, psql, un
    -- servicio futuro) pueda saltarsela.
    DROP CONSTRAINT IF EXISTS ck_scenario_versions_no_autoaprobacion,
    ADD  CONSTRAINT ck_scenario_versions_no_autoaprobacion
        CHECK (reviewed_by IS NULL OR reviewed_by <> created_by);

-- Bandeja del epidemiologo: las versiones que esperan dictamen.
CREATE INDEX IF NOT EXISTS ix_scenario_versions_pendientes
    ON scenario_versions (submitted_at) WHERE status = 'en_revision';

CREATE INDEX IF NOT EXISTS ix_scenario_versions_revisor
    ON scenario_versions (reviewed_by);

-- -----------------------------------------------------------------------------
-- Documentacion embebida (mismo criterio que 008_comentarios.sql)
-- -----------------------------------------------------------------------------
COMMENT ON COLUMN scenario_versions.initial_infected IS
    'Infectados al dia 0 de la simulacion. Entre 1 y la poblacion de la version.';
COMMENT ON COLUMN scenario_versions.status IS
    'Flujo de revision de ESTA version: borrador -> en_revision -> aprobado | rechazado. Solo una version aprobada se puede simular.';
COMMENT ON COLUMN scenario_versions.submitted_at IS
    'Cuando el analista la envio a revision.';
COMMENT ON COLUMN scenario_versions.reviewed_by IS
    'Epidemiologo que aprobo o rechazo. Nunca puede ser el mismo que created_by.';
COMMENT ON COLUMN scenario_versions.reviewed_at IS
    'Fecha del dictamen.';
COMMENT ON COLUMN scenario_versions.review_comment IS
    'Motivo del dictamen. Obligatorio cuando se rechaza.';

INSERT INTO schema_migrations (version, description)
VALUES ('013', 'Escenarios: flujo de aprobacion por version e infectados iniciales')
ON CONFLICT (version) DO NOTHING;

COMMIT;
