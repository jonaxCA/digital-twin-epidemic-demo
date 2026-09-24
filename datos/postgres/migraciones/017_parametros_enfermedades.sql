-- =============================================================================
-- 017_parametros_enfermedades.sql
-- Dominio: catalogos.
--
-- Carga los parametros epidemiologicos de COVID-19 (linaje ancestral) e
-- influenza estacional, cada uno con su fuente o con la marca explicita de
-- supuesto, en el formato que consume el motor:
--     {"valor": 1.28, "fuente": "...", "supuesto": false}
--
-- POR QUE UNA MIGRACION Y NO CAPTURA A MANO
-- Sin esto, los parametros solo existen en la base donde alguien los capturo:
-- una instalacion nueva deja las dos enfermedades sin poder simularse, que es
-- justo lo que bloquea el resto del flujo. Con la migracion, cualquier
-- instalacion arranca con las dos enfermedades listas.
--
-- QUE TRAE FUENTE Y QUE ES SUPUESTO
-- Cuatro parametros de cada enfermedad citan un articulo publicado; la cifra se
-- verifico en el texto de la fuente antes de capturarla. Los otros dos van
-- marcados como supuesto, y su campo "fuente" explica que dice el estudio y que
-- decidio el equipo:
--   - Influenza, tasa de hospitalizacion y letalidad: el CDC las publica por
--     caso sintomatico y el motor las necesita por infeccion. La conversion
--     (66.9% de infecciones sintomaticas, Carrat 2008) es del equipo.
--   - COVID, periodo infeccioso: Cevik 2021 reporta que no se aislo virus
--     viable despues del dia 9. Es un maximo, no un promedio.
--   - COVID, estancia hospitalaria: Rees 2020 reporta medianas de 4 a 21 dias;
--     elegir un punto del rango es decision del equipo.
--
-- Ninguno esta calibrado para Nuevo Leon: son estimaciones de literatura
-- internacional. Calibrar contra datos locales es trabajo posterior.
--
-- SE RESPETA LO QUE YA HAYA: el operador || fusiona, asi que las claves que no
-- se mencionan (transmisibilidad_base, letalidad_por_edad, prob_asintomatico)
-- quedan intactas. Y solo actua si la enfermedad todavia no tiene r0, para no
-- pisar parametros que alguien haya capturado o corregido desde la pantalla.
-- =============================================================================

BEGIN;

-- Influenza estacional A(H1N1)
UPDATE diseases
SET    default_params = default_params || '{
            "dias_hospitalizacion": {
                    "fuente": "Descamps et al. 2022, Eur Respir J 59(3):2100651. Mediana de estancia en 437 adultos hospitalizados con influenza, Francia 2017-2019. doi:10.1183/13993003.00651-2021",
                    "supuesto": false,
                    "valor": 6.0
            },
            "incubacion_dias": {
                    "fuente": "Lessler et al. 2009, Lancet Infect Dis 9(5):291-300. Mediana para influenza A. doi:10.1016/S1473-3099(09)70069-6",
                    "supuesto": false,
                    "valor": 1.4
            },
            "infeccioso_dias": {
                    "fuente": "Carrat et al. 2008, Am J Epidemiol 167(7):775-785. Duracion media de excrecion viral en voluntarios (IC 4.31-5.29). doi:10.1093/aje/kwm375",
                    "supuesto": false,
                    "valor": 4.8
            },
            "letalidad": {
                    "fuente": "DERIVADO POR EL EQUIPO: CDC temporada 2019-2020 estima 22,064 muertes entre 34,026,679 enfermedades sintomaticas (0.065% por caso sintomatico). Se convierte a por infeccion con 66.9% de infecciones sintomaticas (Carrat et al. 2008). La conversion no la publica el CDC.",
                    "supuesto": true,
                    "valor": 0.000434
            },
            "r0": {
                    "fuente": "Biggerstaff et al. 2014, BMC Infect Dis 14:480. Mediana de 47 estimaciones de influenza estacional (RIC 1.19-1.37). doi:10.1186/1471-2334-14-480",
                    "supuesto": false,
                    "valor": 1.28
            },
            "tasa_hospitalizacion": {
                    "fuente": "DERIVADO POR EL EQUIPO: CDC temporada 2019-2020 estima 381,099 hospitalizaciones entre 34,026,679 enfermedades sintomaticas (1.12% por caso sintomatico). Se convierte a por infeccion con 66.9% de infecciones sintomaticas (Carrat et al. 2008). La conversion no la publica el CDC.",
                    "supuesto": true,
                    "valor": 0.00749
            }
    }'::jsonb
WHERE  code = 'INFLUENZA_ESTACIONAL'
  AND  NOT (default_params ? 'r0');

-- SARS-CoV-2 (linaje ancestral)
UPDATE diseases
SET    default_params = default_params || '{
            "dias_hospitalizacion": {
                    "fuente": "SUPUESTO DEL EQUIPO dentro del rango de Rees et al. 2020, BMC Med 18:270: las medianas de estancia van de 4 a 21 dias fuera de China entre 45 estudios. El valor puntual lo elige el equipo. doi:10.1186/s12916-020-01726-3",
                    "supuesto": true,
                    "valor": 8.0
            },
            "incubacion_dias": {
                    "fuente": "Lauer et al. 2020, Ann Intern Med 172(9):577-582. Mediana 5.1 dias (IC 4.5-5.8), 181 casos confirmados. doi:10.7326/M20-0504",
                    "supuesto": false,
                    "valor": 5.1
            },
            "infeccioso_dias": {
                    "fuente": "SUPUESTO DEL EQUIPO sobre Cevik et al. 2021, Lancet Microbe 2(1):e13-e22: ningun estudio detecto virus viable despues del dia 9 de enfermedad. Eso es un maximo, no un promedio, asi que usarlo como duracion media sobreestima. doi:10.1016/S2666-5247(20)30172-5",
                    "supuesto": true,
                    "valor": 9.0
            },
            "letalidad": {
                    "fuente": "Salje et al. 2020, Science 369(6500):208-211. IFR 0.5% (IC 0.3-0.9), Francia, linaje ancestral. doi:10.1126/science.abc3517",
                    "supuesto": false,
                    "valor": 0.005
            },
            "r0": {
                    "fuente": "Billah et al. 2020, PLoS ONE 15(11):e0242128. Meta-analisis global, R0 agrupado 2.87 (IC 2.39-3.44). doi:10.1371/journal.pone.0242128",
                    "supuesto": false,
                    "valor": 2.87
            },
            "tasa_hospitalizacion": {
                    "fuente": "Salje et al. 2020, Science 369(6500):208-211. 2.9% de los infectados son hospitalizados, Francia, linaje ancestral. doi:10.1126/science.abc3517",
                    "supuesto": false,
                    "valor": 0.029
            }
    }'::jsonb
WHERE  code = 'SARS_COV_2_ANCESTRAL'
  AND  NOT (default_params ? 'r0');

INSERT INTO schema_migrations (version, description)
VALUES ('017', 'Catalogos: parametros de COVID-19 e influenza con su fuente')
ON CONFLICT (version) DO NOTHING;

COMMIT;
