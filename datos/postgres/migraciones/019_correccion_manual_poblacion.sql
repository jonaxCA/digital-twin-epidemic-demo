-- =============================================================================
-- 019_correccion_manual_poblacion.sql
-- Dominio: catalogos.
--
-- Bloque C: soporta la correccion manual de poblacion de un municipio desde
-- la pantalla de Regiones (solo ADMINISTRADOR).
--
-- `region_population_adjustments` guarda, por region y campo (`population` o
-- `population_60plus`), el ajuste VIGENTE: quien lo hizo, cuando y con que
-- fuente/motivo. Es la fuente de verdad persistente para que la columna
-- "Fuente" de la pantalla siga siendo correcta despues de reiniciar la app
-- (no vive en memoria) y para que una reinstalacion no la pise (ver
-- 018_correccion_poblacion_51_municipios.sql, que la respeta si existe).
--
-- Guarda tambien `census_value`: la cifra original de INEGI/ITER 2020 con la
-- que arranco esa fila, para no perder la referencia censal aunque se corrija
-- mas de una vez. El historial completo de cada correccion (antes/despues,
-- usuario, IP, fecha) queda en `audit_log`, como el resto del CRUD de la app;
-- esta tabla es solo el "estado vigente" que la pantalla necesita leer rapido.
--
-- Un municipio sin fila aqui sigue mostrando la fuente censal original
-- (INEGI Censo 2020 / ITER 2020). Una fila aqui significa "este valor ya no
-- es el del censo, es una correccion administrativa".
-- =============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS region_population_adjustments (
    id             SERIAL       PRIMARY KEY,
    region_id      INTEGER      NOT NULL,
    field          VARCHAR(30)  NOT NULL,
    census_value   INTEGER      NOT NULL,
    previous_value INTEGER      NOT NULL,
    new_value      INTEGER      NOT NULL,
    reason         TEXT         NOT NULL,
    adjusted_by    INTEGER,
    adjusted_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT fk_rpa_region
        FOREIGN KEY (region_id) REFERENCES regions (id) ON DELETE RESTRICT,
    CONSTRAINT fk_rpa_adjusted_by
        FOREIGN KEY (adjusted_by) REFERENCES users (id) ON DELETE SET NULL,
    CONSTRAINT uq_rpa_region_field UNIQUE (region_id, field),
    CONSTRAINT ck_rpa_field CHECK (field IN ('population', 'population_60plus')),
    CONSTRAINT ck_rpa_census_value CHECK (census_value >= 0),
    CONSTRAINT ck_rpa_previous_value CHECK (previous_value >= 0),
    CONSTRAINT ck_rpa_new_value CHECK (new_value >= 0),
    CONSTRAINT ck_rpa_reason CHECK (length(btrim(reason)) > 0)
);

CREATE INDEX IF NOT EXISTS ix_rpa_region ON region_population_adjustments (region_id);

COMMENT ON TABLE region_population_adjustments IS
    'Ajuste vigente de poblacion por region+campo, hecho a mano por un ADMINISTRADOR desde la pantalla de Regiones. El historial detallado de cada cambio vive en audit_log; esta tabla es el estado actual que la pantalla lee para mostrar la fuente real.';
COMMENT ON COLUMN region_population_adjustments.field IS
    'population o population_60plus: a cual de las dos columnas de regions corresponde este ajuste.';
COMMENT ON COLUMN region_population_adjustments.census_value IS
    'Valor censal original (INEGI Censo 2020 / ITER 2020) antes de cualquier correccion manual. No se sobreescribe en correcciones posteriores.';
COMMENT ON COLUMN region_population_adjustments.reason IS
    'Fuente o motivo de la correccion, capturado obligatoriamente en el formulario de edicion.';

INSERT INTO schema_migrations (version, description)
VALUES ('019', 'Catalogos: tabla de ajustes manuales de poblacion (Bloque C, issue #50)')
ON CONFLICT (version) DO NOTHING;

COMMIT;
