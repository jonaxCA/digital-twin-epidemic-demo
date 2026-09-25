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
-- (no vive en memoria).
--
-- OJO con las reinstalaciones: ni la semilla ni 015/016 consultan esta tabla, y
-- volver a correr dump_completo.sql reaplica 015/016 sobre `regions`. Una
-- correccion manual sobrevive a la semilla (que usa ON CONFLICT DO NOTHING)
-- pero NO a una reejecucion del dump. Si eso llega a importar, la guarda va en
-- 015/016, no aqui.
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
    census_value   INTEGER,
    previous_value INTEGER,
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

-- -----------------------------------------------------------------------------
-- Privilegios sobre la tabla nueva
-- -----------------------------------------------------------------------------
-- 009_roles_bd.sql otorga permisos sobre las tablas que existian cuando corrio y
-- deja ALTER DEFAULT PRIVILEGES solo con SELECT, asi que una tabla creada por una
-- migracion posterior nace sin permiso de escritura para nadie. Y `epidemia_app`
-- (el rol del monolito, que se crea a mano en el Paso 3 de docs/INSTALACION.md y
-- no aparece en 009) nace sin ningun permiso.
--
-- Sin este bloque, la pantalla de Regiones falla con "permiso denegado a la tabla
-- region_population_adjustments" pese a que la migracion corrio sin un solo error,
-- y el catalogo entero deja de cargar porque la consulta de ajustes revienta.
--
-- Los roles se recorren con un guard: en un despliegue por microservicios no
-- existe `epidemia_app`, y en el monolito no se usan los `app_*`.
DO $grants$
DECLARE
    r TEXT;
BEGIN
    FOREACH r IN ARRAY ARRAY['app_catalog', 'epidemia_app']
    LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format(
                'GRANT SELECT, INSERT, UPDATE, DELETE ON region_population_adjustments TO %I', r);
            EXECUTE format(
                'GRANT USAGE, SELECT ON SEQUENCE region_population_adjustments_id_seq TO %I', r);
        END IF;
    END LOOP;
END
$grants$;

COMMENT ON TABLE region_population_adjustments IS
    'Ajuste vigente de poblacion por region+campo, hecho a mano por un ADMINISTRADOR desde la pantalla de Regiones. El historial detallado de cada cambio vive en audit_log; esta tabla es el estado actual que la pantalla lee para mostrar la fuente real.';
COMMENT ON COLUMN region_population_adjustments.field IS
    'population o population_60plus: a cual de las dos columnas de regions corresponde este ajuste.';
COMMENT ON COLUMN region_population_adjustments.census_value IS
    'Valor censal original (INEGI Censo 2020 / ITER 2020) antes de cualquier correccion manual. No se sobreescribe en correcciones posteriores. NULL cuando la columna nunca tuvo cifra censal: un municipio al que no le llego el dato de ITER queda en NULL, y decir que su valor censal era 0 seria inventarlo.';
COMMENT ON COLUMN region_population_adjustments.previous_value IS
    'Valor que tenia la columna justo antes de esta correccion. NULL si estaba vacia, que es el caso de un municipio al que se le captura el dato por primera vez desde la pantalla.';
COMMENT ON COLUMN region_population_adjustments.reason IS
    'Fuente o motivo de la correccion, capturado obligatoriamente en el formulario de edicion.';

INSERT INTO schema_migrations (version, description)
VALUES ('019', 'Catalogos: tabla de ajustes manuales de poblacion (Bloque C, issue #50)')
ON CONFLICT (version) DO NOTHING;

COMMIT;
