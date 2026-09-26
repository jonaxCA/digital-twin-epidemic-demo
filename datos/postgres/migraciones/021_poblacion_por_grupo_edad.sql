-- =============================================================================
-- 021_poblacion_por_grupo_edad.sql
-- Dominio: catalogos.
-- Generado por datos/scripts/build_grupos_edad.py: no editar a mano.
--
-- Agrega `region_age_groups`: la poblacion de cada region abierta en los cinco
-- grupos de edad que usa el motor (0-19, 20-39, 40-59, 60-79, 80+), y la llena
-- con el Censo 2020 para los 51 municipios de Nuevo Leon y para el estado.
--
-- PARA QUE
-- `regions` solo guarda poblacion total y poblacion de 60 y mas, o sea dos
-- grupos. La tabla de letalidad por edad del catalogo (020) esta abierta en
-- cinco. Un escenario municipal estratificado se rechazaba porque los grupos no
-- coinciden. Con esta tabla, armar un escenario por edad sobre un municipio deja
-- de depender de inventar el reparto.
--
-- Los grupos van en una tabla hija y no en columnas de `regions` porque el
-- conjunto de grupos es una decision del modelo, no del catalogo de regiones:
-- cambiarlo no deberia costar un ALTER TABLE ni tocar el resto de las consultas.
--
-- FUENTE: INEGI, Censo 2020, ITER de la entidad 19, filas de total municipal.
-- Cada grupo es una suma exacta de columnas quinquenales publicadas; no hay
-- ningun reparto supuesto. Ver datos/censo/nl_estructura_edad_municipios_2020.tsv,
-- que documenta la descarga y las validaciones.
--
-- LA EDAD NO ESPECIFICADA ES UNA SEXTA CATEGORIA, NO UN SEXTO GRUPO.
-- El censo deja fuera de las columnas de edad a quien no declaro la suya:
-- 18,132 personas en el estado (0.31%), en
-- 30 de los 51 municipios. No se reparten entre los grupos, porque
-- los cinco grupos son dato observado y prorratearlos los convertiria en una
-- imputacion. Se guardan como `edad_no_especificada` con `lower_bound` NULL, que es
-- lo que la distingue de una banda de edad:
--
--     grupos de edad reales   ->  WHERE lower_bound IS NOT NULL
--     poblacion con edad      ->  sum(population) FILTER (WHERE lower_bound IS NOT NULL)
--     total de la region      ->  sum(population)  (cuadra con regions.population)
--
-- Quien arme un escenario tiene que decidir explicitamente que hace con ella.
-- El motor no la reparte por su cuenta: exige que el escenario declare la
-- politica (`excluir` o `prorratear`) y, si se prorratea, lo registra como
-- supuesto en la trazabilidad de la corrida.
--
-- Es idempotente: no pisa filas que ya existan.
-- =============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS region_age_groups (
    region_id   INTEGER      NOT NULL,
    age_group   VARCHAR(20)  NOT NULL,
    lower_bound SMALLINT,          -- NULL solo en la categoria administrativa
    population  INTEGER      NOT NULL,

    CONSTRAINT pk_region_age_groups PRIMARY KEY (region_id, age_group),
    CONSTRAINT fk_rag_region
        FOREIGN KEY (region_id) REFERENCES regions (id) ON DELETE CASCADE,
    CONSTRAINT ck_rag_population CHECK (population >= 0),
    CONSTRAINT ck_rag_lower_bound CHECK (lower_bound BETWEEN 0 AND 120),
    -- Una categoria administrativa no tiene edad de inicio, y una banda de edad
    -- siempre la tiene. Ligar las dos cosas impide que alguien meta
    -- 'edad_no_especificada' con un lower_bound inventado, o una banda sin el.
    CONSTRAINT ck_rag_sin_edad CHECK (
        (age_group = 'edad_no_especificada') = (lower_bound IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS ix_rag_region ON region_age_groups (region_id);

COMMENT ON TABLE region_age_groups IS
    'Poblacion de una region abierta por grupo de edad, en los mismos grupos que usa el motor y que la tabla de letalidad por edad del catalogo, mas la categoria edad_no_especificada. Censo 2020 de INEGI (ITER). La suma de TODAS las filas cuadra con regions.population; la suma de las bandas de edad (lower_bound NOT NULL) es menor, por la gente que no declaro su edad.';
COMMENT ON COLUMN region_age_groups.age_group IS
    'Etiqueta del grupo tal como la espera el motor: 0-19, 20-39, 40-59, 60-79, 80+; o edad_no_especificada, que no es un grupo de edad sino una categoria administrativa. Las cinco primeras tienen que coincidir con las claves de diseases.default_params -> letalidad_por_edad.';
COMMENT ON COLUMN region_age_groups.lower_bound IS
    'Edad con la que empieza el grupo, o NULL en edad_no_especificada. Permite ordenar, resolver intervenciones por edad_minima y distinguir bandas reales de la categoria administrativa sin interpretar la etiqueta.';

-- Los permisos de 009 y los del rol de la aplicacion se otorgaron sobre las
-- tablas que existian entonces, asi que una tabla nueva nace sin acceso para el
-- rol con el que corre la app (ver 019: sin esto, la pantalla falla con
-- "permiso denegado" aunque la migracion no de un solo error).
DO $grants$
DECLARE
    r TEXT;
BEGIN
    FOREACH r IN ARRAY ARRAY['app_catalog', 'epidemia_app']
    LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format(
                'GRANT SELECT, INSERT, UPDATE, DELETE ON region_age_groups TO %I', r);
        END IF;
    END LOOP;
END
$grants$;

INSERT INTO region_age_groups (region_id, age_group, lower_bound, population)
SELECT r.id, v.grupo, v.inicio, v.pob
FROM (VALUES
    ('19001', '0-19', 0, 1071),
    ('19001', '20-39', 20, 841),
    ('19001', '40-59', 40, 732),
    ('19001', '60-79', 60, 271),
    ('19001', '80+', 80, 57),
    ('19001', 'edad_no_especificada', NULL, 2),
    ('19002', '0-19', 0, 887),
    ('19002', '20-39', 20, 699),
    ('19002', '40-59', 40, 918),
    ('19002', '60-79', 60, 699),
    ('19002', '80+', 80, 179),
    ('19002', 'edad_no_especificada', NULL, 0),
    ('19003', '0-19', 0, 381),
    ('19003', '20-39', 20, 285),
    ('19003', '40-59', 40, 361),
    ('19003', '60-79', 60, 303),
    ('19003', '80+', 80, 77),
    ('19003', 'edad_no_especificada', NULL, 0),
    ('19004', '0-19', 0, 11620),
    ('19004', '20-39', 20, 10327),
    ('19004', '40-59', 40, 8642),
    ('19004', '60-79', 60, 3925),
    ('19004', '80+', 80, 762),
    ('19004', 'edad_no_especificada', NULL, 13),
    ('19005', '0-19', 0, 6496),
    ('19005', '20-39', 20, 4583),
    ('19005', '40-59', 40, 4300),
    ('19005', '60-79', 60, 2203),
    ('19005', '80+', 80, 448),
    ('19005', 'edad_no_especificada', NULL, 0),
    ('19006', '0-19', 0, 224106),
    ('19006', '20-39', 20, 219602),
    ('19006', '40-59', 40, 171924),
    ('19006', '60-79', 60, 36836),
    ('19006', '80+', 80, 3770),
    ('19006', 'edad_no_especificada', NULL, 226),
    ('19007', '0-19', 0, 5231),
    ('19007', '20-39', 20, 3492),
    ('19007', '40-59', 40, 3514),
    ('19007', '60-79', 60, 2072),
    ('19007', '80+', 80, 683),
    ('19007', 'edad_no_especificada', NULL, 0),
    ('19008', '0-19', 0, 1211),
    ('19008', '20-39', 20, 900),
    ('19008', '40-59', 40, 876),
    ('19008', '60-79', 60, 540),
    ('19008', '80+', 80, 129),
    ('19008', 'edad_no_especificada', NULL, 5),
    ('19009', '0-19', 0, 41453),
    ('19009', '20-39', 20, 39579),
    ('19009', '40-59', 40, 28817),
    ('19009', '60-79', 60, 10709),
    ('19009', '80+', 80, 1694),
    ('19009', 'edad_no_especificada', NULL, 85),
    ('19010', '0-19', 0, 42220),
    ('19010', '20-39', 20, 42879),
    ('19010', '40-59', 40, 16512),
    ('19010', '60-79', 60, 2554),
    ('19010', '80+', 80, 256),
    ('19010', 'edad_no_especificada', NULL, 57),
    ('19011', '0-19', 0, 2347),
    ('19011', '20-39', 20, 1973),
    ('19011', '40-59', 40, 1813),
    ('19011', '60-79', 60, 982),
    ('19011', '80+', 80, 225),
    ('19011', 'edad_no_especificada', NULL, 0),
    ('19012', '0-19', 0, 27014),
    ('19012', '20-39', 20, 26737),
    ('19012', '40-59', 40, 12226),
    ('19012', '60-79', 60, 2460),
    ('19012', '80+', 80, 302),
    ('19012', 'edad_no_especificada', NULL, 8),
    ('19013', '0-19', 0, 3103),
    ('19013', '20-39', 20, 2542),
    ('19013', '40-59', 40, 2508),
    ('19013', '60-79', 60, 1483),
    ('19013', '80+', 80, 294),
    ('19013', 'edad_no_especificada', NULL, 0),
    ('19014', '0-19', 0, 14069),
    ('19014', '20-39', 20, 8706),
    ('19014', '40-59', 40, 7582),
    ('19014', '60-79', 60, 4334),
    ('19014', '80+', 80, 1312),
    ('19014', 'edad_no_especificada', NULL, 85),
    ('19015', '0-19', 0, 387),
    ('19015', '20-39', 20, 301),
    ('19015', '40-59', 40, 345),
    ('19015', '60-79', 60, 268),
    ('19015', '80+', 80, 59),
    ('19015', 'edad_no_especificada', NULL, 0),
    ('19016', '0-19', 0, 1096),
    ('19016', '20-39', 20, 882),
    ('19016', '40-59', 40, 796),
    ('19016', '60-79', 60, 396),
    ('19016', '80+', 80, 86),
    ('19016', 'edad_no_especificada', NULL, 0),
    ('19017', '0-19', 0, 15089),
    ('19017', '20-39', 20, 10132),
    ('19017', '40-59', 40, 9300),
    ('19017', '60-79', 60, 5019),
    ('19017', '80+', 80, 1361),
    ('19017', 'edad_no_especificada', NULL, 2),
    ('19018', '0-19', 0, 158069),
    ('19018', '20-39', 20, 150314),
    ('19018', '40-59', 40, 75651),
    ('19018', '60-79', 60, 11963),
    ('19018', '80+', 80, 1074),
    ('19018', 'edad_no_especificada', NULL, 134),
    ('19019', '0-19', 0, 30205),
    ('19019', '20-39', 20, 40332),
    ('19019', '40-59', 40, 31451),
    ('19019', '60-79', 60, 21290),
    ('19019', '80+', 80, 4166),
    ('19019', 'edad_no_especificada', NULL, 4725),
    ('19020', '0-19', 0, 1885),
    ('19020', '20-39', 20, 1448),
    ('19020', '40-59', 40, 1241),
    ('19020', '60-79', 60, 783),
    ('19020', '80+', 80, 140),
    ('19020', 'edad_no_especificada', NULL, 9),
    ('19021', '0-19', 0, 171093),
    ('19021', '20-39', 20, 158445),
    ('19021', '40-59', 40, 119025),
    ('19021', '60-79', 60, 29459),
    ('19021', '80+', 80, 2907),
    ('19021', 'edad_no_especificada', NULL, 284),
    ('19022', '0-19', 0, 4273),
    ('19022', '20-39', 20, 3469),
    ('19022', '40-59', 40, 3462),
    ('19022', '60-79', 60, 2358),
    ('19022', '80+', 80, 547),
    ('19022', 'edad_no_especificada', NULL, 0),
    ('19023', '0-19', 0, 454),
    ('19023', '20-39', 20, 415),
    ('19023', '40-59', 40, 463),
    ('19023', '60-79', 60, 382),
    ('19023', '80+', 80, 94),
    ('19023', 'edad_no_especificada', NULL, 0),
    ('19024', '0-19', 0, 2459),
    ('19024', '20-39', 20, 1591),
    ('19024', '40-59', 40, 1267),
    ('19024', '60-79', 60, 793),
    ('19024', '80+', 80, 172),
    ('19024', 'edad_no_especificada', NULL, 0),
    ('19025', '0-19', 0, 40377),
    ('19025', '20-39', 20, 40185),
    ('19025', '40-59', 40, 18396),
    ('19025', '60-79', 60, 2917),
    ('19025', '80+', 80, 245),
    ('19025', 'edad_no_especificada', NULL, 29),
    ('19026', '0-19', 0, 177669),
    ('19026', '20-39', 20, 189903),
    ('19026', '40-59', 40, 171703),
    ('19026', '60-79', 60, 90655),
    ('19026', '80+', 80, 13128),
    ('19026', 'edad_no_especificada', NULL, 85),
    ('19027', '0-19', 0, 488),
    ('19027', '20-39', 20, 410),
    ('19027', '40-59', 40, 496),
    ('19027', '60-79', 60, 451),
    ('19027', '80+', 80, 113),
    ('19027', 'edad_no_especificada', NULL, 1),
    ('19028', '0-19', 0, 454),
    ('19028', '20-39', 20, 345),
    ('19028', '40-59', 40, 338),
    ('19028', '60-79', 60, 209),
    ('19028', '80+', 80, 40),
    ('19028', 'edad_no_especificada', NULL, 0),
    ('19029', '0-19', 0, 2237),
    ('19029', '20-39', 20, 1802),
    ('19029', '40-59', 40, 1730),
    ('19029', '60-79', 60, 994),
    ('19029', '80+', 80, 262),
    ('19029', 'edad_no_especificada', NULL, 1),
    ('19030', '0-19', 0, 1133),
    ('19030', '20-39', 20, 799),
    ('19030', '40-59', 40, 763),
    ('19030', '60-79', 60, 472),
    ('19030', '80+', 80, 131),
    ('19030', 'edad_no_especificada', NULL, 0),
    ('19031', '0-19', 0, 182163),
    ('19031', '20-39', 20, 167670),
    ('19031', '40-59', 40, 102033),
    ('19031', '60-79', 60, 17428),
    ('19031', '80+', 80, 1752),
    ('19031', 'edad_no_especificada', NULL, 477),
    ('19032', '0-19', 0, 1863),
    ('19032', '20-39', 20, 1384),
    ('19032', '40-59', 40, 1255),
    ('19032', '60-79', 60, 714),
    ('19032', '80+', 80, 135),
    ('19032', 'edad_no_especificada', NULL, 0),
    ('19033', '0-19', 0, 28395),
    ('19033', '20-39', 20, 24665),
    ('19033', '40-59', 40, 20315),
    ('19033', '60-79', 60, 9250),
    ('19033', '80+', 80, 2029),
    ('19033', 'edad_no_especificada', NULL, 12),
    ('19034', '0-19', 0, 1783),
    ('19034', '20-39', 20, 1464),
    ('19034', '40-59', 40, 1233),
    ('19034', '60-79', 60, 559),
    ('19034', '80+', 80, 79),
    ('19034', 'edad_no_especificada', NULL, 1),
    ('19035', '0-19', 0, 405),
    ('19035', '20-39', 20, 381),
    ('19035', '40-59', 40, 392),
    ('19035', '60-79', 60, 261),
    ('19035', '80+', 80, 44),
    ('19035', 'edad_no_especificada', NULL, 0),
    ('19036', '0-19', 0, 3245),
    ('19036', '20-39', 20, 1875),
    ('19036', '40-59', 40, 1402),
    ('19036', '60-79', 60, 860),
    ('19036', '80+', 80, 270),
    ('19036', 'edad_no_especificada', NULL, 0),
    ('19037', '0-19', 0, 2214),
    ('19037', '20-39', 20, 1719),
    ('19037', '40-59', 40, 1402),
    ('19037', '60-79', 60, 582),
    ('19037', '80+', 80, 131),
    ('19037', 'edad_no_especificada', NULL, 0),
    ('19038', '0-19', 0, 21760),
    ('19038', '20-39', 20, 19611),
    ('19038', '40-59', 40, 16450),
    ('19038', '60-79', 60, 7864),
    ('19038', '80+', 80, 1530),
    ('19038', 'edad_no_especificada', NULL, 213),
    ('19039', '0-19', 0, 307729),
    ('19039', '20-39', 20, 336615),
    ('19039', '40-59', 40, 296312),
    ('19039', '60-79', 60, 163060),
    ('19039', '80+', 80, 30886),
    ('19039', 'edad_no_especificada', NULL, 8392),
    ('19040', '0-19', 0, 241),
    ('19040', '20-39', 20, 210),
    ('19040', '40-59', 40, 197),
    ('19040', '60-79', 60, 201),
    ('19040', '80+', 80, 57),
    ('19040', 'edad_no_especificada', NULL, 0),
    ('19041', '0-19', 0, 57315),
    ('19041', '20-39', 20, 62397),
    ('19041', '40-59', 40, 23442),
    ('19041', '60-79', 60, 4048),
    ('19041', '80+', 80, 411),
    ('19041', 'edad_no_especificada', NULL, 11),
    ('19042', '0-19', 0, 1507),
    ('19042', '20-39', 20, 1156),
    ('19042', '40-59', 40, 1416),
    ('19042', '60-79', 60, 1076),
    ('19042', '80+', 80, 234),
    ('19042', 'edad_no_especificada', NULL, 0),
    ('19043', '0-19', 0, 750),
    ('19043', '20-39', 20, 541),
    ('19043', '40-59', 40, 610),
    ('19043', '60-79', 60, 375),
    ('19043', '80+', 80, 101),
    ('19043', 'edad_no_especificada', NULL, 0),
    ('19044', '0-19', 0, 10801),
    ('19044', '20-39', 20, 9870),
    ('19044', '40-59', 40, 8634),
    ('19044', '60-79', 60, 4484),
    ('19044', '80+', 80, 902),
    ('19044', 'edad_no_especificada', NULL, 18),
    ('19045', '0-19', 0, 33003),
    ('19045', '20-39', 20, 33316),
    ('19045', '40-59', 40, 16070),
    ('19045', '60-79', 60, 3796),
    ('19045', '80+', 80, 505),
    ('19045', 'edad_no_especificada', NULL, 76),
    ('19046', '0-19', 0, 95691),
    ('19046', '20-39', 20, 124806),
    ('19046', '40-59', 40, 107642),
    ('19046', '60-79', 60, 73987),
    ('19046', '80+', 80, 10010),
    ('19046', 'edad_no_especificada', NULL, 63),
    ('19047', '0-19', 0, 5309),
    ('19047', '20-39', 20, 4432),
    ('19047', '40-59', 40, 4194),
    ('19047', '60-79', 60, 1799),
    ('19047', '80+', 80, 350),
    ('19047', 'edad_no_especificada', NULL, 2),
    ('19048', '0-19', 0, 95435),
    ('19048', '20-39', 20, 97319),
    ('19048', '40-59', 40, 78064),
    ('19048', '60-79', 60, 29179),
    ('19048', '80+', 80, 3698),
    ('19048', 'edad_no_especificada', NULL, 2627),
    ('19049', '0-19', 0, 13703),
    ('19049', '20-39', 20, 12778),
    ('19049', '40-59', 40, 12118),
    ('19049', '60-79', 60, 6525),
    ('19049', '80+', 80, 1174),
    ('19049', 'edad_no_especificada', NULL, 486),
    ('19050', '0-19', 0, 433),
    ('19050', '20-39', 20, 356),
    ('19050', '40-59', 40, 385),
    ('19050', '60-79', 60, 309),
    ('19050', '80+', 80, 69),
    ('19050', 'edad_no_especificada', NULL, 0),
    ('19051', '0-19', 0, 1022),
    ('19051', '20-39', 20, 781),
    ('19051', '40-59', 40, 934),
    ('19051', '60-79', 60, 658),
    ('19051', '80+', 80, 175),
    ('19051', 'edad_no_especificada', NULL, 3),
    ('19', '0-19', 0, 1853344),
    ('19', '20-39', 20, 1867264),
    ('19', '40-59', 40, 1391652),
    ('19', '60-79', 60, 564795),
    ('19', '80+', 80, 89255),
    ('19', 'edad_no_especificada', NULL, 18132)
) AS v(code, grupo, inicio, pob)
JOIN regions r ON r.code = v.code
ON CONFLICT (region_id, age_group) DO NOTHING;

INSERT INTO schema_migrations (version, description)
VALUES ('021', 'Catalogos: poblacion por grupo de edad de los 51 municipios y el estado (Censo 2020)')
ON CONFLICT (version) DO NOTHING;

COMMIT;
