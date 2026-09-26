-- =============================================================================
-- 022_poblacion_60plus_derivada.sql
-- Dominio: catalogos.
--
-- `regions.population_60plus` deja de ser un dato independiente y pasa a ser un
-- valor derivado:
--
--     population_60plus = suma de region_age_groups con lower_bound >= 60
--                       = grupo 60-79 + grupo 80+
--
-- POR QUE
-- Desde 021 la misma poblacion esta en dos lugares: la columna y las bandas de
-- edad. Mientras las dos se puedan editar por separado, nada impide que
-- discrepen, y entonces la pantalla de Regiones y un escenario estratificado
-- dirian cosas distintas sobre el mismo municipio. Un valor derivado no puede
-- desalinearse: si cambia la fuente, cambia el derivado.
--
-- COMO SE MANTIENE
-- Un trigger sobre `region_age_groups` recalcula la columna cada vez que
-- cambian las bandas de una region. La regla vive en la base y no en Flask
-- porque cualquier script o migracion que toque las bandas tiene que dejar la
-- columna coherente, no solo la pantalla.
--
-- QUE PASA CON LA EDICION MANUAL
-- La pantalla de Regiones ya no ofrece editar el 60 y mas: corregirlo ahora
-- significa corregir las bandas de edad, que son el dato censal. La poblacion
-- total sigue siendo editable, con su motivo y su registro en
-- `region_population_adjustments`.
--
-- Los ajustes historicos con field = 'population_60plus' que pueda haber en esa
-- tabla se conservan: son el registro de lo que se hizo antes de este cambio, y
-- el CHECK que los admite se deja como esta. Lo que ya no habra son nuevos.
--
-- Es idempotente.
-- =============================================================================

BEGIN;

CREATE OR REPLACE FUNCTION fn_sincroniza_poblacion_60plus()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_region INTEGER := COALESCE(NEW.region_id, OLD.region_id);
BEGIN
    -- Solo las bandas de edad cuentan: `edad_no_especificada` tiene
    -- lower_bound NULL y queda fuera de la comparacion, que es justo lo que se
    -- quiere -- no se sabe si esa gente tiene 60 o mas.
    UPDATE regions r
    SET    population_60plus = (
               SELECT sum(g.population)
               FROM   region_age_groups g
               WHERE  g.region_id = v_region
                 AND  g.lower_bound >= 60)
    WHERE  r.id = v_region;
    RETURN NULL;
END;
$$;

COMMENT ON FUNCTION fn_sincroniza_poblacion_60plus() IS
    'Mantiene regions.population_60plus como la suma de las bandas de 60 y mas de region_age_groups. Se dispara al cambiar las bandas de una region.';

DROP TRIGGER IF EXISTS trg_rag_sincroniza_60plus ON region_age_groups;
CREATE TRIGGER trg_rag_sincroniza_60plus
    AFTER INSERT OR UPDATE OR DELETE ON region_age_groups
    FOR EACH ROW EXECUTE FUNCTION fn_sincroniza_poblacion_60plus();

-- Recalculo inicial: 021 cargo las bandas antes de que existiera el trigger.
-- Solo toca las filas que difieren, asi que en una base ya coherente no cambia
-- nada. Las regiones sin bandas cargadas (una AGEB, por ejemplo) se quedan como
-- estan: no hay de donde derivar.
UPDATE regions r
SET    population_60plus = s.p60
FROM  (SELECT region_id, sum(population) AS p60
       FROM   region_age_groups
       WHERE  lower_bound >= 60
       GROUP  BY region_id) s
WHERE  s.region_id = r.id
  AND  r.population_60plus IS DISTINCT FROM s.p60;

COMMENT ON COLUMN regions.population_60plus IS
    'Personas de 60 anios y mas. DERIVADA: la mantiene el trigger trg_rag_sincroniza_60plus como la suma de las bandas de 60 y mas de region_age_groups. No se edita a mano; corregirla significa corregir esas bandas. Grupo objetivo de las campanias de vacunacion por edad.';

INSERT INTO schema_migrations (version, description)
VALUES ('022', 'Catalogos: population_60plus pasa a derivarse de region_age_groups')
ON CONFLICT (version) DO NOTHING;

COMMIT;
