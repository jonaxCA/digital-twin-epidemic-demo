-- =============================================================================
-- 020_letalidad_por_edad.sql
-- Dominio: catalogos.
-- Generado por datos/scripts/build_letalidad_edad.py: no editar a mano.
--
-- Reemplaza la tabla `letalidad_por_edad` de COVID-19 e influenza, que venia
-- con cifras redondas sin ninguna fuente, por uno derivado de literatura
-- publicada. Es el parametro que decide los fallecimientos de la simulacion y
-- el que mas varia entre grupos: del mas joven al mas viejo hay tres ordenes de
-- magnitud.
--
-- El motor lee esta tabla en lugar de la letalidad global cuando el escenario
-- trae la poblacion abierta por grupos de edad.
--
-- LAS DOS VAN MARCADAS COMO SUPUESTO. Las cifras por edad de las fuentes si
-- estan publicadas, pero ninguna publica los cinco grupos que usa el motor:
-- reagruparlas ponderando por la estructura de edad de Nuevo Leon es aritmetica
-- del equipo. El campo "fuente" de cada una explica el procedimiento completo.
--
-- NO PISA LO CAPTURADO A MANO: solo actua si la tabla que hay no tiene todavia
-- un campo "fuente", es decir si sigue siendo la inventada.
-- =============================================================================

BEGIN;

-- Influenza estacional A(H1N1)
UPDATE diseases
SET    default_params = default_params || '{
        "letalidad_por_edad": {
                "fuente": "DERIVADO POR EL EQUIPO a partir de CDC, Estimated Flu Disease Burden 2019-2020 (actualizado 15/11/2024), defunciones y enfermedades sintomaticas por grupo de edad. Dos pasos, ninguno publicado por el CDC: (1) letalidad por caso sintomatico = defunciones/enfermedades en cada banda del CDC, llevada a por infeccion con 66.9% de infecciones sintomaticas (Carrat et al. 2008, Am J Epidemiol 167(7):775-785, doi:10.1093/aje/kwm375), la misma conversion que usan los valores globales de esta enfermedad; (2) las bandas del CDC (0-4, 5-17, 18-49, 50-64, 65+) se reagruparon a los cinco grupos del motor ponderando por la estructura de edad de Nuevo Leon (Censo 2020, INEGI), suponiendo tasa constante dentro de cada banda del CDC y reparto parejo dentro del grupo quinquenal 15-19, que es el unico que queda partido. OJO: la banda mas alta del CDC es 65+, sin abrir los 80 y mas, asi que los grupos 60-79 y 80+ heredan la misma tasa de base y la tabla aplana el gradiente justo donde mas sube; el 80+ real es mas alto que este valor. Es la misma vintage del CDC de la que salen la letalidad y la tasa de hospitalizacion globales del catalogo. Estimacion de Estados Unidos: no esta calibrada para Nuevo Leon.",
                "supuesto": true,
                "valor": {
                        "0-19": 3.11e-05,
                        "20-39": 9.38e-05,
                        "40-59": 0.000217,
                        "60-79": 0.00338,
                        "80+": 0.00526
                }
        }
}'::jsonb
WHERE  code = 'INFLUENZA_ESTACIONAL'
  AND  NOT (default_params -> 'letalidad_por_edad' ? 'fuente');

-- SARS-CoV-2 (linaje ancestral)
UPDATE diseases
SET    default_params = default_params || '{
        "letalidad_por_edad": {
                "fuente": "DERIVADO POR EL EQUIPO a partir de Verity et al. 2020, Lancet Infect Dis 20(6):669-677, tabla 1, columna Infection fatality ratio (doi:10.1016/S1473-3099(20)30243-7). El estudio publica el IFR por decenio de edad: 0.00161% en 0-9 hasta 7.80% en 80+, con IFR global 0.657% (IC 0.389-1.33). El motor usa grupos de veinte anios, asi que cada par de decenios se promedio ponderando por la estructura de edad de Nuevo Leon (Censo 2020, INEGI). Los limites de los decenios coinciden con los del censo, asi que el reagrupamiento no parte ningun grupo. Lo publicado es el IFR por decenio; el promedio ponderado lo hace el equipo. Se revisaron las dos fe de erratas del articulo y ninguna toca esta tabla. Estimacion de China, principios de 2020, linaje ancestral: no esta calibrada para Nuevo Leon.",
                "supuesto": true,
                "valor": {
                        "0-19": 4.3e-05,
                        "20-39": 0.00056,
                        "40-59": 0.00346,
                        "60-79": 0.0273,
                        "80+": 0.078
                }
        }
}'::jsonb
WHERE  code = 'SARS_COV_2_ANCESTRAL'
  AND  NOT (default_params -> 'letalidad_por_edad' ? 'fuente');

INSERT INTO schema_migrations (version, description)
VALUES ('020', 'Catalogos: letalidad por grupo de edad de COVID-19 e influenza')
ON CONFLICT (version) DO NOTHING;

COMMIT;
