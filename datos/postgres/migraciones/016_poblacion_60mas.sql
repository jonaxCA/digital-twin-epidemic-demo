-- =============================================================================
-- 016_poblacion_60mas.sql
-- Dominio: catalogos.
--
-- Agrega a `regions` la poblacion de 60 anios y mas y la llena con el Censo
-- 2020 de INEGI para los 51 municipios y para el estado.
--
-- PARA QUE
-- El motor prioriza la vacunacion por edad (parametro edad_minima). Para
-- dimensionar una campania dirigida a 60+ en un municipio hace falta saber
-- cuanta gente de esa edad vive ahi, no la proporcion del estado: va de 2.7% en
-- El Carmen a 28.8% en Los Herreras, diez veces de diferencia. Usar el promedio
-- estatal (654,050 / 5,784,442 = 11.31%) subestimaria el grupo de riesgo en
-- los municipios rurales y lo sobrestimaria en los de crecimiento reciente.
--
-- FUENTE: INEGI, Censo 2020, ITER de la entidad 19, filas "Total del
-- Municipio", columna P_60YMAS. Ver data/censo/nl_poblacion_60mas_2020.tsv,
-- que documenta la descarga y las dos validaciones cruzadas que se le hicieron.
--
-- La columna queda opcional: una region sin el dato (una AGEB, por ejemplo) es
-- valida. Lo que no se admite es mas gente de 60+ que habitantes.
-- Es idempotente.
-- =============================================================================

BEGIN;

ALTER TABLE regions
    ADD COLUMN IF NOT EXISTS population_60plus INTEGER;

ALTER TABLE regions
    DROP CONSTRAINT IF EXISTS ck_regions_poblacion_60,
    ADD  CONSTRAINT ck_regions_poblacion_60 CHECK (
        population_60plus IS NULL
        OR (population_60plus >= 0
            AND (population IS NULL OR population_60plus <= population))
    );

COMMENT ON COLUMN regions.population_60plus IS
    'Personas de 60 anios y mas (Censo 2020, INEGI). Grupo objetivo de las campanias de vacunacion por edad.';

UPDATE regions r
SET    population_60plus = v.p60
FROM (VALUES
    ('19001',     328),   -- Abasolo
    ('19002',     878),   -- Agualeguas
    ('19003',     380),   -- Los Aldamas
    ('19004',    4687),   -- Allende
    ('19005',    2651),   -- Anáhuac
    ('19006',   40606),   -- Apodaca
    ('19007',    2755),   -- Aramberri
    ('19008',     669),   -- Bustamante
    ('19009',   12403),   -- Cadereyta Jiménez
    ('19010',    2810),   -- El Carmen
    ('19011',    1207),   -- Cerralvo
    ('19012',    2762),   -- Ciénega de Flores
    ('19013',    1777),   -- China
    ('19014',    5646),   -- Doctor Arroyo
    ('19015',     327),   -- Doctor Coss
    ('19016',     482),   -- Doctor González
    ('19017',    6380),   -- Galeana
    ('19018',   13037),   -- García
    ('19019',   25456),   -- San Pedro Garza García
    ('19020',     923),   -- General Bravo
    ('19021',   32366),   -- General Escobedo
    ('19022',    2905),   -- General Terán
    ('19023',     476),   -- General Treviño
    ('19024',     965),   -- General Zaragoza
    ('19025',    3162),   -- General Zuazua
    ('19026',  103783),   -- Guadalupe
    ('19027',     564),   -- Los Herreras
    ('19028',     249),   -- Higueras
    ('19029',    1256),   -- Hualahuises
    ('19030',     603),   -- Iturbide
    ('19031',   19180),   -- Juárez
    ('19032',     849),   -- Lampazos de Naranjo
    ('19033',   11279),   -- Linares
    ('19034',     638),   -- Marín
    ('19035',     305),   -- Melchor Ocampo
    ('19036',    1130),   -- Mier y Noriega
    ('19037',     713),   -- Mina
    ('19038',    9394),   -- Montemorelos
    ('19039',  193946),   -- Monterrey
    ('19040',     258),   -- Parás
    ('19041',    4459),   -- Pesquería
    ('19042',    1310),   -- Los Ramones
    ('19043',     476),   -- Rayones
    ('19044',    5386),   -- Sabinas Hidalgo
    ('19045',    4301),   -- Salinas Victoria
    ('19046',   83997),   -- San Nicolás de los Garza
    ('19047',    2149),   -- Hidalgo
    ('19048',   32877),   -- Santa Catarina
    ('19049',    7699),   -- Santiago
    ('19050',     378),   -- Vallecillo
    ('19051',     833)   -- Villaldama
) AS v(code, p60)
WHERE  r.code = v.code
  AND  r.population_60plus IS DISTINCT FROM v.p60;

-- El estado: la suma de los 51 municipios, que coincide con el tabulado
-- estatal por grupo quinquenal de edad.
UPDATE regions
SET    population_60plus = 654050
WHERE  code = '19'
  AND  population_60plus IS DISTINCT FROM 654050;

INSERT INTO schema_migrations (version, description)
VALUES ('016', 'Catalogos: poblacion de 60 anios y mas por municipio (Censo 2020)')
ON CONFLICT (version) DO NOTHING;

COMMIT;
