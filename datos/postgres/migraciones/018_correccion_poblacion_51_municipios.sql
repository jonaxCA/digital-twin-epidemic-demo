-- =============================================================================
-- 018_correccion_poblacion_51_municipios.sql
-- Dominio: catalogos.
--
-- Corrige un defecto de orden de instalacion (issue #49): 015 y 016 solo
-- actualizan por `code` las filas de `regions` que YA EXISTEN cuando corren.
-- Como dump_completo.sql (que las contiene) se ejecuta ANTES de
-- datos/postgres/semillas/nl_municipios_completos.sql, los 41 municipios que
-- esa semilla agrega nunca reciben la correccion: quedan con la poblacion
-- aproximada que el propio archivo advierte como PENDIENTE, y sin ningun
-- valor en population_60plus.
--
-- Esta migracion reaplica, para los 51 municipios, los mismos valores ya
-- verificados en 015_poblacion_censo_2020.sql y 016_poblacion_60mas.sql
-- (misma fuente: INEGI, Censo de Poblacion y Vivienda 2020, ver
-- datos/censo/nl_poblacion_municipios_1990_2020.tsv y
-- datos/censo/nl_poblacion_60mas_2020.tsv). No inventa cifras nuevas.
--
-- Debe ejecutarse DESPUES de nl_municipios_completos.sql (ver Paso 2 de
-- docs/INSTALACION.md, actualizado). En una base donde los 51 municipios ya
-- tienen la cifra correcta, este archivo no cambia nada: es idempotente.
--
-- No pisa correcciones manuales de un ADMINISTRADOR. Si la funcionalidad de
-- edicion de poblacion (Bloque C) ya esta instalada -- existe la tabla
-- `region_population_adjustments` -- este archivo respeta cualquier fila que
-- ya tenga un ajuste manual registrado para ese campo. Si esa tabla todavia
-- no existe (instalacion sin Bloque C), no hay ajustes que proteger y se
-- aplica la correccion censal sin condicion extra. La comprobacion se hace en
-- SQL dinamico (EXECUTE) precisamente para no fallar al analizar la consulta
-- cuando la tabla aun no existe.
-- =============================================================================

BEGIN;

CREATE TEMP TABLE _censo_2020_51_municipios (
    code VARCHAR(20),
    pob  INTEGER,
    p60  INTEGER
) ON COMMIT DROP;

INSERT INTO _censo_2020_51_municipios (code, pob, p60) VALUES
    ('19001',      2974,     328),   -- Abasolo
    ('19002',      3382,     878),   -- Agualeguas
    ('19003',      1407,     380),   -- Los Aldamas
    ('19004',     35289,    4687),   -- Allende
    ('19005',     18030,    2651),   -- Anáhuac
    ('19006',    656464,   40606),   -- Apodaca
    ('19007',     14992,    2755),   -- Aramberri
    ('19008',      3661,     669),   -- Bustamante
    ('19009',    122337,   12403),   -- Cadereyta Jiménez
    ('19010',    104478,    2810),   -- El Carmen
    ('19011',      7340,    1207),   -- Cerralvo
    ('19012',     68747,    2762),   -- Ciénega de Flores
    ('19013',      9930,    1777),   -- China
    ('19014',     36088,    5646),   -- Doctor Arroyo
    ('19015',      1360,     327),   -- Doctor Coss
    ('19016',      3256,     482),   -- Doctor González
    ('19017',     40903,    6380),   -- Galeana
    ('19018',    397205,   13037),   -- García
    ('19019',    132169,   25456),   -- San Pedro Garza García
    ('19020',      5506,     923),   -- General Bravo
    ('19021',    481213,   32366),   -- General Escobedo
    ('19022',     14109,    2905),   -- General Terán
    ('19023',      1808,     476),   -- General Treviño
    ('19024',      6282,     965),   -- General Zaragoza
    ('19025',    102149,    3162),   -- General Zuazua
    ('19026',    643143,  103783),   -- Guadalupe
    ('19027',      1959,     564),   -- Los Herreras
    ('19028',      1386,     249),   -- Higueras
    ('19029',      7026,    1256),   -- Hualahuises
    ('19030',      3298,     603),   -- Iturbide
    ('19031',    471523,   19180),   -- Juárez
    ('19032',      5351,     849),   -- Lampazos de Naranjo
    ('19033',     84666,   11279),   -- Linares
    ('19034',      5119,     638),   -- Marín
    ('19035',      1483,     305),   -- Melchor Ocampo
    ('19036',      7652,    1130),   -- Mier y Noriega
    ('19037',      6048,     713),   -- Mina
    ('19038',     67428,    9394),   -- Montemorelos
    ('19039',   1142994,  193946),   -- Monterrey
    ('19040',       906,     258),   -- Parás
    ('19041',    147624,    4459),   -- Pesquería
    ('19042',      5389,    1310),   -- Los Ramones
    ('19043',      2377,     476),   -- Rayones
    ('19044',     34709,    5386),   -- Sabinas Hidalgo
    ('19045',     86766,    4301),   -- Salinas Victoria
    ('19046',    412199,   83997),   -- San Nicolás de los Garza
    ('19047',     16086,    2149),   -- Hidalgo
    ('19048',    306322,   32877),   -- Santa Catarina
    ('19049',     46784,    7699),   -- Santiago
    ('19050',      1552,     378),   -- Vallecillo
    ('19051',      3573,     833);  -- Villaldama

DO $do$
BEGIN
    IF to_regclass('public.region_population_adjustments') IS NULL THEN
        -- Bloque C (edicion manual) todavia no esta instalado: nada que proteger.
        UPDATE regions r
        SET    population = t.pob
        FROM   _censo_2020_51_municipios t
        WHERE  r.code = t.code
          AND  r.population IS DISTINCT FROM t.pob;

        UPDATE regions r
        SET    population_60plus = t.p60
        FROM   _censo_2020_51_municipios t
        WHERE  r.code = t.code
          AND  r.population_60plus IS DISTINCT FROM t.p60;
    ELSE
        -- La tabla existe: no tocar los campos que ya tengan un ajuste manual
        -- registrado. SQL dinamico a proposito, para que esta rama solo se
        -- analice cuando la tabla ya esta presente.
        EXECUTE $sql$
            UPDATE regions r
            SET    population = t.pob
            FROM   _censo_2020_51_municipios t
            WHERE  r.code = t.code
              AND  r.population IS DISTINCT FROM t.pob
              AND  NOT EXISTS (
                     SELECT 1 FROM region_population_adjustments a
                     WHERE a.region_id = r.id AND a.field = 'population'
                   )
        $sql$;

        EXECUTE $sql$
            UPDATE regions r
            SET    population_60plus = t.p60
            FROM   _censo_2020_51_municipios t
            WHERE  r.code = t.code
              AND  r.population_60plus IS DISTINCT FROM t.p60
              AND  NOT EXISTS (
                     SELECT 1 FROM region_population_adjustments a
                     WHERE a.region_id = r.id AND a.field = 'population_60plus'
                   )
        $sql$;
    END IF;
END
$do$;

INSERT INTO schema_migrations (version, description)
VALUES ('018', 'Catalogos: corrige poblacion censal de los 51 municipios (issue #49, orden de instalacion)')
ON CONFLICT (version) DO NOTHING;

COMMIT;
