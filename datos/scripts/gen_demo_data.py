"""
Genera demo_datos_nl.sql: datos SINTETICOS para la demo local de las 4 pantallas
(dashboard publico, login, dashboard autenticado, mapa de Nuevo Leon).

No es parte de la migracion oficial (001-010). Es justo lo que 010_datos_iniciales.sql
dice que va "en un archivo aparte de datos de demostracion". Se puede volver a correr:
al inicio trunca las tablas que llena, asi que es seguro repetirlo sobre la misma base.

Requiere haber corrido antes datos/postgres/dump_completo.sql.

Uso (desde la raiz del proyecto):
  python3 datos/scripts/gen_demo_data.py > datos/postgres/semillas/demo_datos_nl.sql
  psql -d simulador_epidemico -v ON_ERROR_STOP=1 -f datos/postgres/semillas/demo_datos_nl.sql

Ojo: cada corrida genera un hash bcrypt nuevo para la usuaria de demostracion,
asi que regenerar el archivo cambia esa linea aunque los datos sean los mismos.
"""
import random
import datetime
import bcrypt

random.seed(42)

TODAY = datetime.date(2026, 9, 3)  # fecha "de hoy" para la demo, fija y reproducible
DAYS_BACK = 45

# code, poblacion, lat, lon (centroides ya cargados por 010_datos_iniciales.sql),
# multiplicador fijo de intensidad (heterogeneidad entre municipios: sin esto, la
# incidencia por 100k sale casi identica en los 10 y el mapa no muestra variedad).
NL_MUNICIPIOS = [
    ("19039", 1142994, 25.6866, -100.3161, 1.3),  # Monterrey
    ("19019", 132169,  25.6579, -100.4022, 0.5),  # San Pedro Garza Garcia
    ("19026", 643143,  25.6768, -100.2597, 1.6),  # Guadalupe
    ("19006", 656464,  25.7819, -100.1886, 1.4),  # Apodaca
    ("19021", 481157,  25.7954, -100.3181, 1.7),  # General Escobedo
    ("19048", 306322,  25.6731, -100.4583, 0.8),  # Santa Catarina
    ("19046", 412199,  25.7417, -100.3028, 1.1),  # San Nicolas de los Garza
    ("19031", 466465,  25.6466, -100.0961, 0.9),  # Juarez
    ("19018", 412199,  25.8133, -100.5856, 0.6),  # Garcia
    ("19049", 45988,   25.4247, -100.1472, 0.3),  # Santiago
]

# code, peso_base (casos por 100k por dia, ventana estable), tendencia (multiplicador
# de la ultima semana sobre la base -- >1 sube, <1 baja, =1 estable)
DISEASES = [
    ("INFLUENZA_ESTACIONAL", 0.55, 2.30),
    ("DENGUE_DEMO",           0.22, 1.55),
    ("SARS_COV_2_ANCESTRAL",  0.40, 0.60),
    ("ZIKA_DEMO",             0.06, 1.00),
    ("MALARIA_DEMO",          0.12, 1.60),
    # PATOGENO_X queda sin casos: es el "escenario de preparacion" del catalogo original.
]

SEV_CHOICES = [("asintomatico", 0.30), ("leve", 0.55), ("grave", 0.13), ("fallecido", 0.02)]
RESULT_CHOICES = [("positivo", 0.75), ("pendiente", 0.15), ("negativo", 0.10)]


def weighted_choice(pairs):
    r = random.random()
    acc = 0.0
    for value, w in pairs:
        acc += w
        if r <= acc:
            return value
    return pairs[-1][0]


def gen_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(12)).decode("utf-8")


def main():
    out = []
    out.append("-- =============================================================================")
    out.append("-- demo_datos_nl.sql  (NO es parte de la migracion oficial 001-010)")
    out.append("-- Datos SINTETICOS para la demo local: dashboard publico, login, dashboard")
    out.append("-- autenticado y mapa epidemiologico -- alcance Nuevo Leon unicamente.")
    out.append(f"-- Generado por gen_demo_data.py, seed fija (42), 'hoy' simulado = {TODAY.isoformat()}.")
    out.append("-- Seguro de volver a correr: trunca antes de insertar.")
    out.append("--")
    out.append("-- Requiere: dump_completo.sql ya aplicado (schema + catalogos + admin).")
    out.append("-- =============================================================================")
    out.append("")
    out.append("BEGIN;")
    out.append("")

    out.append("-- Reinicio limpio de las tablas que toca esta demo. No toca users/roles reales")
    out.append("-- salvo por el INSERT del usuario de demo mas abajo (ON CONFLICT DO NOTHING).")
    out.append("TRUNCATE case_attachments, cases, scenario_interventions, simulation_runs,")
    out.append("         simulation_batches, scenario_versions, scenarios RESTART IDENTITY CASCADE;")
    out.append("")

    out.append("-- ---------------------------------------------------------------------------")
    out.append("-- Enfermedades adicionales, solo para variedad visual en 'Resumen de Situacion'.")
    out.append("-- Parametros de literatura general, NO calibrados -- mismo criterio que 010.")
    out.append("-- ---------------------------------------------------------------------------")
    out.append("""INSERT INTO diseases (code, name, description, default_params) VALUES
    ('DENGUE_DEMO', 'Dengue',
     'Arbovirus transmitido por Aedes aegypti. Parametros de referencia, no calibrados.',
     '{"incubacion_dias": {"dist": "lognormal", "media": 5.5, "desv": 1.5},
       "infeccioso_dias": {"dist": "lognormal", "media": 5.0, "desv": 1.0},
       "prob_asintomatico": 0.60, "transmisibilidad_base": 0.015}'::jsonb),
    ('ZIKA_DEMO', 'Zika',
     'Arbovirus transmitido por Aedes. Parametros de referencia, no calibrados.',
     '{"incubacion_dias": {"dist": "lognormal", "media": 6.0, "desv": 2.0},
       "infeccioso_dias": {"dist": "lognormal", "media": 5.0, "desv": 1.5},
       "prob_asintomatico": 0.80, "transmisibilidad_base": 0.010}'::jsonb),
    ('MALARIA_DEMO', 'Malaria',
     'Transmitida por Anopheles. Parametros de referencia, no calibrados.',
     '{"incubacion_dias": {"dist": "lognormal", "media": 12.0, "desv": 3.0},
       "infeccioso_dias": {"dist": "lognormal", "media": 14.0, "desv": 4.0},
       "prob_asintomatico": 0.20, "transmisibilidad_base": 0.008}'::jsonb)
ON CONFLICT (code) DO NOTHING;
""")

    demo_password = "Epidemia2026!"
    admin_password = "Admin2026!"
    hash_epidemiologa = gen_password_hash(demo_password)
    hash_analista = gen_password_hash(demo_password)
    hash_admin = gen_password_hash(admin_password)
    out.append("-- ---------------------------------------------------------------------------")
    out.append("-- Usuarios de demostracion para el recorrido. Passwords reales (bcrypt).")
    out.append("-- Son dos personas distintas a proposito: el flujo de aprobacion exige que")
    out.append("-- quien construye el escenario no sea quien lo autoriza (ver migracion 013).")
    out.append("--   analista:      alex.cavazos   (rol ANALISTA)")
    out.append("--   epidemiologa:  diana.flores   (rol EPIDEMIOLOGO)")
    out.append(f"--   password de ambos:  {demo_password}   (documentada tambien en README.md)")
    out.append("-- Mas abajo se le pone contrasena tambien a 'admin', que 010 crea con un")
    out.append("-- marcador invalido a proposito.")
    out.append("-- SOLO para el entorno local -- no usar este patron en un ambiente real.")
    out.append("-- ---------------------------------------------------------------------------")
    out.append(f"""INSERT INTO users (username, email, password_hash, full_name, is_active)
VALUES ('diana.flores', 'diana.flores@salud.nl.gob.mx', '{hash_epidemiologa}',
        'Diana Flores', TRUE),
       ('alex.cavazos', 'alex.cavazos@salud.nl.gob.mx', '{hash_analista}',
        'Alex Cavazos', TRUE)
ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash;

INSERT INTO user_roles (user_id, role_id)
SELECT u.id, r.id FROM users u CROSS JOIN roles r
WHERE u.username = 'diana.flores' AND r.code = 'EPIDEMIOLOGO'
ON CONFLICT DO NOTHING;

INSERT INTO user_roles (user_id, role_id)
SELECT u.id, r.id FROM users u CROSS JOIN roles r
WHERE u.username = 'alex.cavazos' AND r.code = 'ANALISTA'
ON CONFLICT DO NOTHING;

-- Cuenta de administracion. 010_datos_iniciales.sql la crea con el marcador
-- invalido REEMPLAZAR_ANTES_DE_DESPLEGAR justamente para que el esquema nunca
-- viaje con una contrasena por defecto que funcione. Aqui se le pone una real
-- porque esto son datos de demostracion: quien instale solo las migraciones,
-- sin este archivo, sigue sin poder entrar con esa cuenta.
--   usuario:   admin
--   password:  {admin_password}
UPDATE users SET password_hash = '{hash_admin}' WHERE username = 'admin';

-- Red de seguridad: 010 ya le asigna el rol; esto solo cubre una base donde se
-- haya perdido la asignacion.
INSERT INTO user_roles (user_id, role_id)
SELECT u.id, r.id FROM users u CROSS JOIN roles r
WHERE u.username = 'admin' AND r.code = 'ADMINISTRADOR'
ON CONFLICT DO NOTHING;
""")

    out.append("-- ---------------------------------------------------------------------------")
    out.append("-- Un escenario publicado + 3 lotes de simulacion en distintos estados, para que")
    out.append("-- la tarjeta 'SIMULACIONES' cuente corridas reales (encolado/ejecutando).")
    out.append("-- ---------------------------------------------------------------------------")
    out.append("""INSERT INTO scenarios (name, description, disease_id, region_id, owner_id, status, is_public)
SELECT 'Ola Influenza ZMM - otono 2026',
       'Escenario de demostracion: proyeccion de la temporada de influenza en el area metropolitana.',
       d.id, r.id, u.id, 'publicado', TRUE
FROM diseases d, regions r, users u
WHERE d.code = 'INFLUENZA_ESTACIONAL' AND r.code = '19' AND u.username = 'alex.cavazos';

-- La version la construye el analista y la aprueba la epidemiologa: dos
-- personas distintas, como exige ck_scenario_versions_no_autoaprobacion (013).
-- Tiene que quedar aprobada porque abajo cuelgan corridas de simulacion, y
-- fn_version_aprobada (014) rechaza simular cualquier otra cosa.
INSERT INTO scenario_versions (scenario_id, version_number, is_current, population_size,
                               horizon_days, initial_infected, notes, created_by,
                               status, submitted_at, reviewed_by, reviewed_at, review_comment)
SELECT s.id, 1, TRUE, 500000, 180, 100, 'Version inicial para el entorno local.', autor.id,
       'aprobado', now() - interval '3 days', revisor.id, now() - interval '2 days',
       'Parametros consistentes con la temporada anterior.'
FROM scenarios s, users autor, users revisor
WHERE s.name = 'Ola Influenza ZMM - otono 2026'
  AND autor.username = 'alex.cavazos'
  AND revisor.username = 'diana.flores';
""")

    batch_rows = [
        (40, "numba", "ejecutando", 35, False),
        (30, "numba", "encolado", 4, False),
        (30, "numba", "completado", 240, True),
    ]
    for replicas, engine, status, minutes_ago, done in batch_rows:
        summary = "'run_summaries:demo-001'" if done else "NULL"
        finished = f"now() - interval '{max(minutes_ago - 20, 1)} minutes'" if done else "NULL"
        out.append(f"""INSERT INTO simulation_batches (scenario_version_id, requested_by, replicas, engine, status, summary_doc_id, created_at, finished_at)
SELECT sv.id, u.id, {replicas}, '{engine}', '{status}', {summary},
       now() - interval '{minutes_ago} minutes', {finished}
FROM scenario_versions sv
JOIN scenarios s ON s.id = sv.scenario_id AND s.name = 'Ola Influenza ZMM - otono 2026'
JOIN users u ON u.username = 'alex.cavazos';""")

    out.append("")
    out.append("-- Corridas individuales por lote, respetando las reglas de la 007:")
    out.append("-- encolado => started_at NULL; terminal => finished_at NOT NULL; etc.")
    out.append("""DO $$
DECLARE
    v_batch_ejecutando BIGINT;
    v_batch_encolado   BIGINT;
    v_batch_completado BIGINT;
    v_version_id       BIGINT;
    v_user_id          BIGINT;
    i INT;
BEGIN
    SELECT sv.id INTO v_version_id
    FROM scenario_versions sv
    JOIN scenarios s ON s.id = sv.scenario_id AND s.name = 'Ola Influenza ZMM - otono 2026';

    SELECT id INTO v_user_id FROM users WHERE username = 'alex.cavazos';

    SELECT id INTO v_batch_ejecutando FROM simulation_batches WHERE status = 'ejecutando' LIMIT 1;
    SELECT id INTO v_batch_encolado   FROM simulation_batches WHERE status = 'encolado'   LIMIT 1;
    SELECT id INTO v_batch_completado FROM simulation_batches WHERE status = 'completado' LIMIT 1;

    FOR i IN 0..39 LOOP
        IF i < 25 THEN
            INSERT INTO simulation_runs
                (batch_id, scenario_version_id, requested_by, seed, replica_index, status, progress, started_at, queued_at)
            VALUES (v_batch_ejecutando, v_version_id, v_user_id, 10000 + i, i, 'ejecutando',
                    (random() * 80)::smallint, now() - interval '20 minutes', now() - interval '35 minutes');
        ELSE
            INSERT INTO simulation_runs
                (batch_id, scenario_version_id, requested_by, seed, replica_index, status, progress, queued_at)
            VALUES (v_batch_ejecutando, v_version_id, v_user_id, 10000 + i, i, 'encolado', 0, now() - interval '35 minutes');
        END IF;
    END LOOP;

    FOR i IN 0..29 LOOP
        INSERT INTO simulation_runs
            (batch_id, scenario_version_id, requested_by, seed, replica_index, status, progress, queued_at)
        VALUES (v_batch_encolado, v_version_id, v_user_id, 20000 + i, i, 'encolado', 0, now() - interval '4 minutes');
    END LOOP;

    FOR i IN 0..29 LOOP
        INSERT INTO simulation_runs
            (batch_id, scenario_version_id, requested_by, seed, replica_index, status, progress,
             queued_at, started_at, finished_at, result_doc_id)
        VALUES (v_batch_completado, v_version_id, v_user_id, 30000 + i, i, 'completado', 100,
                now() - interval '240 minutes', now() - interval '230 minutes',
                now() - interval '210 minutes', 'run_results:demo-' || i);
    END LOOP;
END;
$$;
""")

    out.append("-- ---------------------------------------------------------------------------")
    out.append(f"-- Casos sinteticos, Nuevo Leon, ultimos {DAYS_BACK} dias. Un renglon de VALUES por caso.")
    out.append("-- disease_id/region_id se resuelven por codigo (no por id numerico) para que")
    out.append("-- este script no dependa del orden exacto en que se insertaron los catalogos.")
    out.append("-- ---------------------------------------------------------------------------")

    case_rows = []
    for mun_code, poblacion, lat, lon, mun_mult in NL_MUNICIPIOS:
        for dis_code, peso_base, tendencia in DISEASES:
            for day_offset in range(DAYS_BACK, -1, -1):
                report_date = TODAY - datetime.timedelta(days=day_offset)
                # semana actual (0-6) vs semana previa (7-13) a tasa base: comparacion
                # limpia, sin rampa, para que el % semanal que ve el dashboard sea
                # directamente el de la tendencia definida arriba.
                factor = tendencia if day_offset <= 6 else 1.0
                lam = (poblacion / 100000.0) * peso_base * factor * mun_mult
                n_casos = int(random.gauss(lam, max(lam * 0.22, 0.4)) + 0.5)
                n_casos = max(0, n_casos)
                for _ in range(n_casos):
                    age = max(0, min(95, int(random.gauss(34, 20))))
                    sex = random.choice(["M", "F"])
                    onset_lag = random.randint(0, 4)
                    onset_date = report_date - datetime.timedelta(days=onset_lag)
                    jlat = lat + random.uniform(-0.05, 0.05)
                    jlon = lon + random.uniform(-0.05, 0.05)
                    severity = weighted_choice(SEV_CHOICES)
                    result = weighted_choice(RESULT_CHOICES)
                    status = "validado" if random.random() < 0.85 else "pendiente"
                    case_rows.append(
                        f"('{dis_code}','{mun_code}',{age},'{sex}','{onset_date.isoformat()}',"
                        f"'{report_date.isoformat()}',{jlat:.6f},{jlon:.6f},'{result}','{severity}','{status}')"
                    )

    out.append(f"-- total de casos generados: {len(case_rows)}")
    out.append("INSERT INTO cases (local_uuid, reported_by, disease_id, region_id, age, sex, "
                "onset_date, report_date, latitude, longitude, test_result, severity, status, created_at)")
    out.append("SELECT gen_random_uuid(), u.id, d.id, r.id, t.age, t.sex, t.onset_date::date, "
                "t.report_date::date, t.lat, t.lon, t.test_result, t.severity, t.status, "
                "t.report_date::timestamptz + time '08:00'")
    out.append("FROM (VALUES")
    out.append(",\n".join("    " + row for row in case_rows))
    out.append(") AS t(disease_code, region_code, age, sex, onset_date, report_date, lat, lon, test_result, severity, status)")
    out.append("JOIN diseases d ON d.code = t.disease_code")
    out.append("JOIN regions  r ON r.code  = t.region_code")
    out.append("CROSS JOIN (SELECT id FROM users WHERE username = 'diana.flores') u;")
    out.append("")
    out.append("COMMIT;")

    print("\n".join(out))


if __name__ == "__main__":
    main()
