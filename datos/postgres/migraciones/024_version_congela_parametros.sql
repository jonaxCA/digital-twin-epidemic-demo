-- =============================================================================
-- 024_version_congela_parametros.sql
-- Dominio: escenarios.
--
-- `scenario_versions.disease_params` guarda los parametros de la enfermedad con
-- los que se armo la version. Hasta ahora se leian del catalogo cada vez, asi
-- que corregir un parametro cambiaba el significado de todas las versiones
-- viejas -- incluidas las ya aprobadas y las ya simuladas.
--
-- Es el mismo problema que resolvieron `population_by_age` (023) y la poblacion
-- municipal: una version es una fotografia, no un puntero.
--
-- CUANDO SE CONGELA: AL SALIR DE BORRADOR
-- Mientras la version es un borrador, los parametros son los vivos del catalogo.
-- Es coherente con que todo lo demas de un borrador tambien se pueda cambiar: si
-- se congelaran al crearla, un borrador que espera dos dias mientras alguien
-- corrige el R0 se quedaria con el valor viejo, y tomar la correccion obligaria a
-- crear otra version.
--
-- En el instante en que deja de ser borrador -- el envio a revision -- se
-- congelan. Asi todo lo REVISABLE y todo lo SIMULABLE esta congelado: el trigger
-- fn_version_aprobada (014) solo deja simular versiones aprobadas, y para estar
-- aprobada hubo que pasar por el envio. La regla se resume en una linea:
--
--     editable  <->  parametros vivos
--     congelada <->  parametros de la fotografia
--
-- POR QUE NO HAY CHECK QUE LO OBLIGUE
-- Seria natural exigir "si status <> 'borrador' entonces disease_params NOT NULL",
-- pero las versiones que ya existen salieron de borrador antes de que esta columna
-- existiera y tienen NULL. Un CHECK normal fallaria al crearlo; uno NOT VALID
-- dejaria pasar esas filas, pero volveria a evaluarse en cuanto algo las
-- ACTUALICE -- y `crea_version` actualiza la version vigente para apagar su
-- is_current, asi que versionar el escenario de demostracion reventaria. Se deja
-- sin CHECK a proposito: quien congela es `envia_a_revision`, que es el unico
-- camino de salida de borrador.
--
-- NULL significa "esta version salio de borrador antes de que existiera la
-- fotografia". No se rellena con los parametros de hoy: eso afirmaria algo que
-- nadie puede verificar. La pantalla lo dice cuando pasa.
--
-- Es idempotente.
-- =============================================================================

BEGIN;

ALTER TABLE scenario_versions
    ADD COLUMN IF NOT EXISTS disease_params JSONB;

ALTER TABLE scenario_versions
    DROP CONSTRAINT IF EXISTS ck_scenario_versions_disease_params,
    ADD  CONSTRAINT ck_scenario_versions_disease_params CHECK (
        disease_params IS NULL OR jsonb_typeof(disease_params) = 'object');

COMMENT ON COLUMN scenario_versions.disease_params IS
    'Parametros de la enfermedad con los que se armo esta version, congelados al salir de borrador (envio a revision). Mientras la version es borrador vale NULL y se usan los vivos de diseases.default_params, que es coherente con que un borrador se pueda cambiar. NULL en una version que ya no es borrador significa que salio de borrador antes de que existiera esta columna: no se rellena, porque afirmaria algo no verificable.';

INSERT INTO schema_migrations (version, description)
VALUES ('024', 'Escenarios: la version congela los parametros de la enfermedad al salir de borrador')
ON CONFLICT (version) DO NOTHING;

COMMIT;
