-- =============================================================================
-- nl_municipios_completos.sql
-- Agrega los 41 municipios de Nuevo Leon que no vienen en
-- 010_datos_iniciales.sql (catalogo INEGI real, geometria real).
-- Generado por build_regiones_sql.py: no editar a mano.
-- PENDIENTE: la poblacion de estos 41 es aproximada, no es censo
-- verificado -- ver docstring de build_regiones_sql.py.
-- =============================================================================

BEGIN;

INSERT INTO regions (code, name, level, parent_region_id, population, centroid_lat, centroid_lon)
SELECT v.code, v.name, 'municipio', e.id, v.pob, v.lat, v.lon
FROM (VALUES
    ('19001', 'Abasolo', 2600, 25.940267, -100.40595),
    ('19002', 'Agualeguas', 3500, 26.298727, -99.703122),
    ('19003', 'Los Aldamas', 1200, 26.091657, -99.27347),
    ('19004', 'Allende', 33000, 25.301434, -100.029546),
    ('19005', 'Anáhuac', 19000, 27.34198, -100.025272),
    ('19007', 'Aramberri', 14000, 24.225136, -99.886543),
    ('19008', 'Bustamante', 3300, 26.571888, -100.561761),
    ('19009', 'Cadereyta Jiménez', 100000, 25.524581, -99.914185),
    ('19010', 'El Carmen', 40000, 25.900667, -100.35691),
    ('19011', 'Cerralvo', 8300, 26.07236, -99.705482),
    ('19012', 'Ciénega de Flores', 50000, 25.977448, -100.185446),
    ('19013', 'China', 11500, 25.480134, -98.972451),
    ('19014', 'Doctor Arroyo', 36000, 23.860137, -100.306246),
    ('19015', 'Doctor Coss', 1300, 25.964035, -99.030752),
    ('19016', 'Doctor González', 3000, 25.849189, -99.80497),
    ('19017', 'Galeana', 40000, 24.760498, -100.39227),
    ('19020', 'General Bravo', 5300, 25.803304, -98.848417),
    ('19022', 'General Terán', 14000, 25.275921, -99.413089),
    ('19023', 'General Treviño', 1400, 26.212567, -99.445989),
    ('19024', 'General Zaragoza', 4700, 23.901028, -99.740136),
    ('19025', 'General Zuazua', 50000, 25.911416, -100.134689),
    ('19027', 'Los Herreras', 1500, 25.916103, -99.414209),
    ('19028', 'Higueras', 1700, 26.033086, -99.997439),
    ('19029', 'Hualahuises', 7300, 24.883856, -99.677987),
    ('19030', 'Iturbide', 3300, 24.638432, -99.848649),
    ('19032', 'Lampazos de Naranjo', 5000, 27.050721, -100.418202),
    ('19033', 'Linares', 90000, 24.851802, -99.529129),
    ('19034', 'Marín', 7500, 25.874423, -99.964649),
    ('19035', 'Melchor Ocampo', 1000, 26.048943, -99.493687),
    ('19036', 'Mier y Noriega', 5500, 23.417852, -100.16035),
    ('19037', 'Mina', 5600, 26.285456, -100.786227),
    ('19038', 'Montemorelos', 76000, 25.126355, -99.808448),
    ('19040', 'Parás', 700, 26.583195, -99.601733),
    ('19041', 'Pesquería', 26000, 25.736839, -99.977126),
    ('19042', 'Los Ramones', 5900, 25.653159, -99.587657),
    ('19043', 'Rayones', 2200, 25.065748, -100.127703),
    ('19044', 'Sabinas Hidalgo', 33000, 26.575116, -100.149273),
    ('19045', 'Salinas Victoria', 76000, 26.161076, -100.270268),
    ('19047', 'Hidalgo', 16000, 25.999394, -100.45308),
    ('19050', 'Vallecillo', 700, 26.648061, -99.884792),
    ('19051', 'Villaldama', 4500, 26.469608, -100.347971)
) AS v(code, name, pob, lat, lon)
CROSS JOIN (SELECT id FROM regions WHERE code = '19') e
ON CONFLICT (code) DO NOTHING;

COMMIT;
