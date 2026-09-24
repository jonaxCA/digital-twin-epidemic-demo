-- =============================================================================
-- 015_poblacion_censo_2020.sql
-- Dominio: catalogos.
--
-- Pone la poblacion de los 51 municipios en la cifra del Censo de Poblacion y
-- Vivienda 2020 de INEGI.
--
-- POR QUE
-- Los 41 municipios que carga nl_municipios_completos.sql llevaban
-- aproximaciones de orden de magnitud, con errores de hasta 82%: Pesqueria
-- tenia 26,000 habitantes contra 147,624 reales, El Carmen 40,000 contra
-- 104,478 y General Zuazua 50,000 contra 102,149. Como la incidencia se calcula
-- por cada 100,000 habitantes, esos municipios aparecian con una incidencia
-- inflada hasta seis veces justo donde mas ha crecido la poblacion.
-- Ademas, cuatro de los 10 municipios de 010 tampoco eran censales; el caso mas
-- claro era Garcia, que traia 412,199, exactamente la poblacion de San Nicolas.
--
-- Los archivos de instalacion ya traen las cifras correctas, asi que en una
-- base nueva esta migracion no cambia nada. Existe para las bases ya creadas.
-- Es idempotente: solo toca las filas cuyo valor difiere.
--
-- FUENTE: INEGI, Censo de Poblacion y Vivienda 2020. Ver
-- data/censo/nl_poblacion_municipios_1990_2020.tsv, que documenta la consulta y
-- de donde salio cada cifra. La suma de los 51 municipios es 5,784,442,
-- identica al total estatal del censo.
-- =============================================================================

BEGIN;

UPDATE regions r
SET    population = v.pob
FROM (VALUES
    ('19001',      2974),   -- Abasolo
    ('19002',      3382),   -- Agualeguas
    ('19003',      1407),   -- Los Aldamas
    ('19004',     35289),   -- Allende
    ('19005',     18030),   -- Anáhuac
    ('19006',    656464),   -- Apodaca
    ('19007',     14992),   -- Aramberri
    ('19008',      3661),   -- Bustamante
    ('19009',    122337),   -- Cadereyta Jiménez
    ('19010',    104478),   -- El Carmen
    ('19011',      7340),   -- Cerralvo
    ('19012',     68747),   -- Ciénega de Flores
    ('19013',      9930),   -- China
    ('19014',     36088),   -- Doctor Arroyo
    ('19015',      1360),   -- Doctor Coss
    ('19016',      3256),   -- Doctor González
    ('19017',     40903),   -- Galeana
    ('19018',    397205),   -- García
    ('19019',    132169),   -- San Pedro Garza García
    ('19020',      5506),   -- General Bravo
    ('19021',    481213),   -- General Escobedo
    ('19022',     14109),   -- General Terán
    ('19023',      1808),   -- General Treviño
    ('19024',      6282),   -- General Zaragoza
    ('19025',    102149),   -- General Zuazua
    ('19026',    643143),   -- Guadalupe
    ('19027',      1959),   -- Los Herreras
    ('19028',      1386),   -- Higueras
    ('19029',      7026),   -- Hualahuises
    ('19030',      3298),   -- Iturbide
    ('19031',    471523),   -- Juárez
    ('19032',      5351),   -- Lampazos de Naranjo
    ('19033',     84666),   -- Linares
    ('19034',      5119),   -- Marín
    ('19035',      1483),   -- Melchor Ocampo
    ('19036',      7652),   -- Mier y Noriega
    ('19037',      6048),   -- Mina
    ('19038',     67428),   -- Montemorelos
    ('19039',   1142994),   -- Monterrey
    ('19040',       906),   -- Parás
    ('19041',    147624),   -- Pesquería
    ('19042',      5389),   -- Los Ramones
    ('19043',      2377),   -- Rayones
    ('19044',     34709),   -- Sabinas Hidalgo
    ('19045',     86766),   -- Salinas Victoria
    ('19046',    412199),   -- San Nicolás de los Garza
    ('19047',     16086),   -- Hidalgo
    ('19048',    306322),   -- Santa Catarina
    ('19049',     46784),   -- Santiago
    ('19050',      1552),   -- Vallecillo
    ('19051',      3573)   -- Villaldama
) AS v(code, pob)
WHERE  r.code = v.code
  AND  r.population IS DISTINCT FROM v.pob;

INSERT INTO schema_migrations (version, description)
VALUES ('015', 'Catalogos: poblacion municipal del Censo 2020 de INEGI')
ON CONFLICT (version) DO NOTHING;

COMMIT;
