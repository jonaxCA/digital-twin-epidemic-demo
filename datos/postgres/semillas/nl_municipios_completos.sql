-- =============================================================================
-- nl_municipios_completos.sql
-- Agrega los 41 municipios de Nuevo Leon que no vienen en
-- 010_datos_iniciales.sql (catalogo INEGI real, geometria real).
-- Generado por datos/scripts/build_regiones_sql.py: no editar a mano.
-- Poblacion: Censo de Poblacion y Vivienda 2020, INEGI.
-- Poblacion de 60 y mas: ITER 2020, INEGI.
-- Fuentes: datos/censo/nl_poblacion_municipios_1990_2020.tsv y
--          datos/censo/nl_poblacion_60mas_2020.tsv
--
-- Las cifras van en el INSERT y no en una migracion posterior porque
-- dump_completo.sql (donde viven 015 y 016) se carga ANTES que este
-- archivo, y esas migraciones solo alcanzan filas que ya existen.
-- =============================================================================

BEGIN;

INSERT INTO regions (code, name, level, parent_region_id, population,
                     population_60plus, centroid_lat, centroid_lon)
SELECT v.code, v.name, 'municipio', e.id, v.pob, v.pob60, v.lat, v.lon
FROM (VALUES
    ('19001', 'Abasolo', 2974, 328, 25.940267, -100.40595),
    ('19002', 'Agualeguas', 3382, 878, 26.298727, -99.703122),
    ('19003', 'Los Aldamas', 1407, 380, 26.091657, -99.27347),
    ('19004', 'Allende', 35289, 4687, 25.301434, -100.029546),
    ('19005', 'Anáhuac', 18030, 2651, 27.34198, -100.025272),
    ('19007', 'Aramberri', 14992, 2755, 24.225136, -99.886543),
    ('19008', 'Bustamante', 3661, 669, 26.571888, -100.561761),
    ('19009', 'Cadereyta Jiménez', 122337, 12403, 25.524581, -99.914185),
    ('19010', 'El Carmen', 104478, 2810, 25.900667, -100.35691),
    ('19011', 'Cerralvo', 7340, 1207, 26.07236, -99.705482),
    ('19012', 'Ciénega de Flores', 68747, 2762, 25.977448, -100.185446),
    ('19013', 'China', 9930, 1777, 25.480134, -98.972451),
    ('19014', 'Doctor Arroyo', 36088, 5646, 23.860137, -100.306246),
    ('19015', 'Doctor Coss', 1360, 327, 25.964035, -99.030752),
    ('19016', 'Doctor González', 3256, 482, 25.849189, -99.80497),
    ('19017', 'Galeana', 40903, 6380, 24.760498, -100.39227),
    ('19020', 'General Bravo', 5506, 923, 25.803304, -98.848417),
    ('19022', 'General Terán', 14109, 2905, 25.275921, -99.413089),
    ('19023', 'General Treviño', 1808, 476, 26.212567, -99.445989),
    ('19024', 'General Zaragoza', 6282, 965, 23.901028, -99.740136),
    ('19025', 'General Zuazua', 102149, 3162, 25.911416, -100.134689),
    ('19027', 'Los Herreras', 1959, 564, 25.916103, -99.414209),
    ('19028', 'Higueras', 1386, 249, 26.033086, -99.997439),
    ('19029', 'Hualahuises', 7026, 1256, 24.883856, -99.677987),
    ('19030', 'Iturbide', 3298, 603, 24.638432, -99.848649),
    ('19032', 'Lampazos de Naranjo', 5351, 849, 27.050721, -100.418202),
    ('19033', 'Linares', 84666, 11279, 24.851802, -99.529129),
    ('19034', 'Marín', 5119, 638, 25.874423, -99.964649),
    ('19035', 'Melchor Ocampo', 1483, 305, 26.048943, -99.493687),
    ('19036', 'Mier y Noriega', 7652, 1130, 23.417852, -100.16035),
    ('19037', 'Mina', 6048, 713, 26.285456, -100.786227),
    ('19038', 'Montemorelos', 67428, 9394, 25.126355, -99.808448),
    ('19040', 'Parás', 906, 258, 26.583195, -99.601733),
    ('19041', 'Pesquería', 147624, 4459, 25.736839, -99.977126),
    ('19042', 'Los Ramones', 5389, 1310, 25.653159, -99.587657),
    ('19043', 'Rayones', 2377, 476, 25.065748, -100.127703),
    ('19044', 'Sabinas Hidalgo', 34709, 5386, 26.575116, -100.149273),
    ('19045', 'Salinas Victoria', 86766, 4301, 26.161076, -100.270268),
    ('19047', 'Hidalgo', 16086, 2149, 25.999394, -100.45308),
    ('19050', 'Vallecillo', 1552, 378, 26.648061, -99.884792),
    ('19051', 'Villaldama', 3573, 833, 26.469608, -100.347971)
) AS v(code, name, pob, pob60, lat, lon)
CROSS JOIN (SELECT id FROM regions WHERE code = '19') e
ON CONFLICT (code) DO NOTHING;

COMMIT;
