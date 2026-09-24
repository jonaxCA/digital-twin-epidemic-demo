-- =============================================================================
-- 005_vigilancia.sql
-- Dominio: vigilancia de campo.  Servicio propietario: surveillance-service.
-- Tablas: vaccine_lots, cases, case_attachments.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- vaccine_lots
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vaccine_lots (
    id           BIGSERIAL    PRIMARY KEY,
    lot_code     VARCHAR(60)  NOT NULL,
    manufacturer VARCHAR(120),
    disease_id   SMALLINT     NOT NULL,
    region_id    INTEGER,
    doses_total  INTEGER      NOT NULL,
    doses_used   INTEGER      NOT NULL DEFAULT 0,
    expires_on   DATE,
    scanned_by   BIGINT       NOT NULL,
    scanned_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT uq_vaccine_lots_code UNIQUE (lot_code),
    CONSTRAINT fk_vaccine_lots_disease
        FOREIGN KEY (disease_id) REFERENCES diseases (id) ON DELETE RESTRICT,
    CONSTRAINT fk_vaccine_lots_region
        FOREIGN KEY (region_id)  REFERENCES regions (id)  ON DELETE SET NULL,
    CONSTRAINT fk_vaccine_lots_scanner
        FOREIGN KEY (scanned_by) REFERENCES users (id)    ON DELETE RESTRICT,
    CONSTRAINT ck_vaccine_lots_total CHECK (doses_total > 0),
    -- Invariante de negocio: nunca se pueden aplicar mas dosis de las que trae
    -- el lote. La base lo garantiza, no el cliente movil.
    CONSTRAINT ck_vaccine_lots_usadas CHECK (doses_used BETWEEN 0 AND doses_total)
);

CREATE INDEX IF NOT EXISTS ix_vaccine_lots_region  ON vaccine_lots (region_id);
CREATE INDEX IF NOT EXISTS ix_vaccine_lots_disease ON vaccine_lots (disease_id);

-- -----------------------------------------------------------------------------
-- cases
-- -----------------------------------------------------------------------------
-- local_uuid lo genera la app Android antes de tener red. Es la llave de
-- deduplicacion: si WorkManager reintenta un envio, el segundo choca contra la
-- restriccion unica y el servicio responde 409 en vez de duplicar el caso.
CREATE TABLE IF NOT EXISTS cases (
    id             BIGSERIAL     PRIMARY KEY,
    local_uuid     UUID          NOT NULL,
    device_id      BIGINT,
    reported_by    BIGINT        NOT NULL,
    disease_id     SMALLINT      NOT NULL,
    region_id      INTEGER       NOT NULL,
    vaccine_lot_id BIGINT,
    age            SMALLINT,
    sex            CHAR(1),
    onset_date     DATE,
    report_date    DATE          NOT NULL,
    latitude       NUMERIC(9,6),
    longitude      NUMERIC(9,6),
    test_result    VARCHAR(20),
    severity       VARCHAR(20),
    status         VARCHAR(20)   NOT NULL DEFAULT 'pendiente',
    created_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),
    synced_at      TIMESTAMPTZ,

    CONSTRAINT uq_cases_local_uuid UNIQUE (local_uuid),
    CONSTRAINT fk_cases_device
        FOREIGN KEY (device_id)      REFERENCES devices (id)      ON DELETE SET NULL,
    CONSTRAINT fk_cases_reporter
        FOREIGN KEY (reported_by)    REFERENCES users (id)        ON DELETE RESTRICT,
    CONSTRAINT fk_cases_disease
        FOREIGN KEY (disease_id)     REFERENCES diseases (id)     ON DELETE RESTRICT,
    CONSTRAINT fk_cases_region
        FOREIGN KEY (region_id)      REFERENCES regions (id)      ON DELETE RESTRICT,
    CONSTRAINT fk_cases_vaccine_lot
        FOREIGN KEY (vaccine_lot_id) REFERENCES vaccine_lots (id) ON DELETE SET NULL,

    CONSTRAINT ck_cases_age    CHECK (age IS NULL OR age BETWEEN 0 AND 120),
    CONSTRAINT ck_cases_sex    CHECK (sex IS NULL OR sex IN ('M', 'F', 'O')),
    CONSTRAINT ck_cases_result CHECK (test_result IS NULL OR test_result IN
        ('positivo', 'negativo', 'pendiente', 'sin_prueba')),
    CONSTRAINT ck_cases_severity CHECK (severity IS NULL OR severity IN
        ('asintomatico', 'leve', 'grave', 'fallecido')),
    CONSTRAINT ck_cases_status CHECK (status IN
        ('pendiente', 'validado', 'duplicado', 'descartado')),
    -- El rezago de notificacion es positivo por definicion: no se puede
    -- reportar un caso antes de que empiecen los sintomas.
    CONSTRAINT ck_cases_rezago CHECK (onset_date IS NULL OR onset_date <= report_date),
    CONSTRAINT ck_cases_lat CHECK (latitude  IS NULL OR latitude  BETWEEN -90 AND 90),
    CONSTRAINT ck_cases_lon CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180),
    -- La geolocalizacion viaja completa o no viaja.
    CONSTRAINT ck_cases_coordenadas CHECK (
        (latitude IS NULL AND longitude IS NULL)
        OR (latitude IS NOT NULL AND longitude IS NOT NULL)
    )
);

-- La curva epidemica se arma por fecha; el mapa de incidencia por zona y fecha.
CREATE INDEX IF NOT EXISTS ix_cases_report_date  ON cases (report_date DESC);
CREATE INDEX IF NOT EXISTS ix_cases_region_fecha ON cases (region_id, report_date);
CREATE INDEX IF NOT EXISTS ix_cases_disease_onset ON cases (disease_id, onset_date);
CREATE INDEX IF NOT EXISTS ix_cases_pendientes   ON cases (status) WHERE status = 'pendiente';
CREATE INDEX IF NOT EXISTS ix_cases_reporter     ON cases (reported_by);

-- -----------------------------------------------------------------------------
-- case_attachments
-- -----------------------------------------------------------------------------
-- El archivo vive en Cloud Storage. Aqui solo viaja la ruta y los metadatos
-- que exige la materia: identificador, ruta, tipo, tamanio, propietario,
-- fecha, hash, nivel de privacidad.
CREATE TABLE IF NOT EXISTS case_attachments (
    id           BIGSERIAL    PRIMARY KEY,
    case_id      BIGINT       NOT NULL,
    storage_path VARCHAR(255) NOT NULL,
    mime_type    VARCHAR(80)  NOT NULL,
    size_bytes   BIGINT       NOT NULL,
    sha256       CHAR(64)     NOT NULL,
    privacy      VARCHAR(20)  NOT NULL DEFAULT 'privado',
    uploaded_by  BIGINT       NOT NULL,
    uploaded_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT uq_case_attachments_path UNIQUE (storage_path),
    CONSTRAINT fk_case_attachments_case
        FOREIGN KEY (case_id)     REFERENCES cases (id) ON DELETE CASCADE,
    CONSTRAINT fk_case_attachments_uploader
        FOREIGN KEY (uploaded_by) REFERENCES users (id) ON DELETE RESTRICT,
    CONSTRAINT ck_case_attachments_size CHECK (size_bytes > 0),
    -- Limite de 20 MB por evidencia, alineado con el limite del cliente movil.
    CONSTRAINT ck_case_attachments_max  CHECK (size_bytes <= 20971520),
    CONSTRAINT ck_case_attachments_mime CHECK (mime_type IN
        ('image/jpeg', 'image/png', 'image/webp', 'application/pdf')),
    CONSTRAINT ck_case_attachments_hash CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_case_attachments_privacy CHECK (privacy IN ('privado', 'publico'))
);

CREATE INDEX IF NOT EXISTS ix_case_attachments_case ON case_attachments (case_id);
-- Detecta la misma foto subida dos veces desde dispositivos distintos.
CREATE INDEX IF NOT EXISTS ix_case_attachments_hash ON case_attachments (sha256);

INSERT INTO schema_migrations (version, description)
VALUES ('005', 'Vigilancia de campo: lotes, casos y evidencias')
ON CONFLICT (version) DO NOTHING;

COMMIT;
