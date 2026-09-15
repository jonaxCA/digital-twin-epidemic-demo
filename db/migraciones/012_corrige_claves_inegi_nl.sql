-- =============================================================================
-- 012_corrige_claves_inegi_nl.sql
-- Dominio: catalogos.
--
-- La version anterior de 010_datos_iniciales.sql cargo intercambiadas las
-- claves INEGI de dos municipios. Segun el catalogo oficial de INEGI:
--     19046 = San Nicolas de los Garza
--     19048 = Santa Catarina
--
-- 010_datos_iniciales.sql ya trae las claves correctas, asi que en una
-- instalacion nueva esta migracion no cambia nada. Existe solo para las bases
-- creadas con la version anterior de 010: detecta el intercambio por nombre y
-- lo corrige.
--
-- Es idempotente: solo actua si encuentra el intercambio, asi que correrla dos
-- veces no vuelve a invertir las claves. Cambia unicamente regions.code; las
-- tablas que apuntan a regions (cases, scenarios, ...) usan el id, no la clave,
-- asi que siguen ligadas al mismo renglon.
-- =============================================================================

BEGIN;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM regions WHERE code = '19046' AND name = 'Santa Catarina')
       AND EXISTS (SELECT 1 FROM regions WHERE code = '19048' AND name = 'San Nicolas de los Garza')
    THEN
        -- Clave temporal para no chocar con uq_regions_code a mitad del cambio.
        UPDATE regions SET code = '19-tmp' WHERE code = '19046';
        UPDATE regions SET code = '19046'  WHERE code = '19048';
        UPDATE regions SET code = '19048'  WHERE code = '19-tmp';
        RAISE NOTICE '012: claves 19046 y 19048 corregidas.';
    END IF;
END
$$;

INSERT INTO schema_migrations (version, description)
VALUES ('012', 'Catalogos: corrige claves INEGI de Santa Catarina y San Nicolas de los Garza')
ON CONFLICT (version) DO NOTHING;

COMMIT;
