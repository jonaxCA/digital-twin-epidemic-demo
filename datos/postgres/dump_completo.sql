-- =============================================================================
-- dump_completo.sql
-- Simulador de respuesta a epidemias — construccion completa de la base
--
-- Archivo generado automaticamente concatenando, en orden, las 14 migraciones
-- numeradas del proyecto:
--   001_base.sql            006_escenarios.sql        011_fix_audit_log_delete.sql
--   002_seguridad.sql       007_simulacion.sql        012_corrige_claves_inegi_nl.sql
--   003_sistema.sql         008_comentarios.sql       013_escenarios_aprobacion.sql
--   004_catalogos.sql       009_roles_bd.sql          014_simulacion_resultados.sql
--   005_vigilancia.sql      010_datos_iniciales.sql
--
-- Cada bloque original conserva su propio BEGIN/COMMIT y su propio INSERT en
-- schema_migrations, asi que este archivo se comporta exactamente igual que
-- correr los 14 .sql uno por uno, pero en una sola pasada.
--
-- Una base creada con una version anterior de este archivo se actualiza
-- volviendolo a correr completo: lo existente no se duplica y se aplican las
-- migraciones que falten.
--
-- MODO DE USO
--   psql -h <host> -U <usuario_con_privilegios> -d <base_destino> \
--        -v ON_ERROR_STOP=1 -f dump_completo.sql
--
-- Requisitos:
--   - PostgreSQL 15 o superior (006_escenarios.sql usa UNIQUE NULLS NOT
--     DISTINCT).
--   - El rol que ejecuta este script necesita permiso para CREATE EXTENSION,
--     CREATE ROLE y GRANT (normalmente el superusuario o el dueno de la BD).
--   - Correrlo con psql, no con una herramienta que fragmente el script por
--     ";" de forma ingenua: hay bloques DO $$ ... $$ en 009_roles_bd.sql que
--     deben viajar completos.
--
-- Es idempotente: cada CREATE usa IF NOT EXISTS / OR REPLACE y cada INSERT de
-- datos usa ON CONFLICT DO NOTHING, asi que se puede volver a correr sobre una
-- base ya construida sin duplicar nada ni tronar.
--
-- IMPORTANTE (heredado de 009_roles_bd.sql y 010_datos_iniciales.sql):
--   - Las contrasenas de los roles de aplicacion se crean con el marcador
--     'cambiar_en_despliegue'. Cambialas antes de usar esto fuera de un
--     entorno local.
--   - El usuario admin inicial se crea con password_hash =
--     'REEMPLAZAR_ANTES_DE_DESPLEGAR', que es invalido a proposito: no podra
--     iniciar sesion hasta que generes un hash real y lo sustituyas.
-- =============================================================================

-- =============================================================================
-- 001_base.sql
-- Simulador de respuesta a epidemias
-- Extensiones, funciones compartidas y control de migraciones.
--
-- Ejecutar en orden numerico. Cada archivo es idempotente: se puede volver a
-- correr sin romper una base ya creada.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- Extensiones
-- -----------------------------------------------------------------------------
-- pgcrypto: gen_random_uuid() para identificadores de correlacion y llaves
-- naturales generadas en el servidor. En PostgreSQL 13+ gen_random_uuid() ya es
-- nativa, pero la extension se mantiene por compatibilidad con 12 y porque
-- ofrece digest() para verificar hashes de archivos.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- -----------------------------------------------------------------------------
-- Control de migraciones
-- -----------------------------------------------------------------------------
-- El equipo no usa Alembic: las migraciones son archivos SQL numerados y esta
-- tabla registra cuales ya se aplicaron. Antes de correr un archivo nuevo,
-- consultar esta tabla; al final de cada archivo se inserta su propio registro.
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     VARCHAR(20)  PRIMARY KEY,
    description VARCHAR(160) NOT NULL,
    applied_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

COMMENT ON TABLE schema_migrations IS
    'Registro de migraciones aplicadas. Una fila por archivo SQL ejecutado.';

-- -----------------------------------------------------------------------------
-- Funcion: mantener updated_at
-- -----------------------------------------------------------------------------
-- Se dispara antes de cada UPDATE en las tablas que llevan updated_at, para que
-- ningun servicio pueda olvidarse de actualizarlo.
CREATE OR REPLACE FUNCTION fn_set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION fn_set_updated_at() IS
    'Trigger BEFORE UPDATE: fija updated_at = now() en la fila modificada.';

-- -----------------------------------------------------------------------------
-- Funcion: bitacora inmutable
-- -----------------------------------------------------------------------------
-- audit_log es solo de insercion. Los permisos de base de datos ya lo impiden
-- (ver 009_roles_bd.sql), pero este trigger protege tambien contra un error
-- cometido con el usuario propietario o durante una sesion de mantenimiento.
CREATE OR REPLACE FUNCTION fn_solo_insercion()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'La tabla % es de solo insercion: no admite % ',
        TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$;

COMMENT ON FUNCTION fn_solo_insercion() IS
    'Trigger BEFORE UPDATE OR DELETE: bloquea cualquier modificacion de la fila.';

INSERT INTO schema_migrations (version, description)
VALUES ('001', 'Extensiones, funciones compartidas y control de migraciones')
ON CONFLICT (version) DO NOTHING;

COMMIT;
-- =============================================================================
-- 002_seguridad.sql
-- Dominio: seguridad y accesos.  Servicio propietario: auth-service.
-- Tablas: users, roles, permissions, user_roles, role_permissions,
--         password_resets, devices.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- users
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id              BIGSERIAL     PRIMARY KEY,
    username        VARCHAR(60)   NOT NULL,
    email           VARCHAR(160)  NOT NULL,
    password_hash   VARCHAR(255)  NOT NULL,
    full_name       VARCHAR(160)  NOT NULL,
    is_active       BOOLEAN       NOT NULL DEFAULT TRUE,
    failed_attempts SMALLINT      NOT NULL DEFAULT 0,
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),

    CONSTRAINT uq_users_username     UNIQUE (username),
    CONSTRAINT uq_users_email        UNIQUE (email),
    -- Se guardan normalizados a minusculas para que la unicidad sea de hecho
    -- insensible a mayusculas sin necesidad de un indice funcional.
    CONSTRAINT ck_users_username_min CHECK (username = lower(username)),
    CONSTRAINT ck_users_email_min    CHECK (email = lower(email)),
    CONSTRAINT ck_users_email_forma  CHECK (email LIKE '%_@_%._%'),
    CONSTRAINT ck_users_intentos     CHECK (failed_attempts BETWEEN 0 AND 100)
);

DROP TRIGGER IF EXISTS tg_users_updated_at ON users;
CREATE TRIGGER tg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

-- Las consultas de administracion filtran casi siempre por cuentas activas.
CREATE INDEX IF NOT EXISTS ix_users_activos ON users (is_active) WHERE is_active;

-- -----------------------------------------------------------------------------
-- roles
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS roles (
    id          SMALLSERIAL  PRIMARY KEY,
    code        VARCHAR(40)  NOT NULL,
    name        VARCHAR(80)  NOT NULL,
    description TEXT,
    is_system   BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT uq_roles_code      UNIQUE (code),
    CONSTRAINT ck_roles_code_may  CHECK (code = upper(code))
);

-- -----------------------------------------------------------------------------
-- permissions
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS permissions (
    id          SMALLSERIAL  PRIMARY KEY,
    code        VARCHAR(80)  NOT NULL,
    resource    VARCHAR(60)  NOT NULL,
    action      VARCHAR(30)  NOT NULL,
    description TEXT,

    CONSTRAINT uq_permissions_code   UNIQUE (code),
    -- code debe ser exactamente recurso.accion: evita que dos permisos
    -- distintos apunten al mismo par y que el JWT lleve claves inventadas.
    CONSTRAINT ck_permissions_code   CHECK (code = resource || '.' || action),
    CONSTRAINT ck_permissions_accion CHECK (action IN
        ('read', 'create', 'update', 'delete', 'publish', 'run', 'export', 'approve'))
);

-- -----------------------------------------------------------------------------
-- user_roles  (tabla puente)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_roles (
    user_id     BIGINT      NOT NULL,
    role_id     SMALLINT    NOT NULL,
    assigned_by BIGINT,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT pk_user_roles PRIMARY KEY (user_id, role_id),
    CONSTRAINT fk_user_roles_user
        FOREIGN KEY (user_id)     REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT fk_user_roles_role
        FOREIGN KEY (role_id)     REFERENCES roles (id) ON DELETE RESTRICT,
    CONSTRAINT fk_user_roles_asignador
        FOREIGN KEY (assigned_by) REFERENCES users (id) ON DELETE SET NULL
);

-- La llave primaria ya indexa (user_id, role_id); falta el sentido inverso
-- para responder "que usuarios tienen el rol X".
CREATE INDEX IF NOT EXISTS ix_user_roles_role ON user_roles (role_id);

-- -----------------------------------------------------------------------------
-- role_permissions  (tabla puente: es la matriz de permisos)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS role_permissions (
    role_id       SMALLINT NOT NULL,
    permission_id SMALLINT NOT NULL,

    CONSTRAINT pk_role_permissions PRIMARY KEY (role_id, permission_id),
    CONSTRAINT fk_role_permissions_role
        FOREIGN KEY (role_id)       REFERENCES roles (id)       ON DELETE CASCADE,
    CONSTRAINT fk_role_permissions_permission
        FOREIGN KEY (permission_id) REFERENCES permissions (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_role_permissions_permission
    ON role_permissions (permission_id);

-- -----------------------------------------------------------------------------
-- password_resets
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS password_resets (
    id           BIGSERIAL    PRIMARY KEY,
    user_id      BIGINT       NOT NULL,
    token_hash   VARCHAR(255) NOT NULL,
    expires_at   TIMESTAMPTZ  NOT NULL,
    used_at      TIMESTAMPTZ,
    requested_ip INET,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT uq_password_resets_token UNIQUE (token_hash),
    CONSTRAINT fk_password_resets_user
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT ck_password_resets_vigencia CHECK (expires_at > created_at),
    CONSTRAINT ck_password_resets_uso      CHECK (used_at IS NULL OR used_at >= created_at)
);

-- Un usuario no deberia tener dos solicitudes vivas al mismo tiempo: el indice
-- parcial permite reemitir despues de usar o vencer, pero no acumular.
CREATE INDEX IF NOT EXISTS ix_password_resets_pendientes
    ON password_resets (user_id) WHERE used_at IS NULL;

-- -----------------------------------------------------------------------------
-- devices
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS devices (
    id           BIGSERIAL    PRIMARY KEY,
    user_id      BIGINT       NOT NULL,
    device_uid   VARCHAR(128) NOT NULL,
    platform     VARCHAR(20)  NOT NULL DEFAULT 'android',
    model        VARCHAR(80),
    app_version  VARCHAR(20),
    push_token   VARCHAR(255),
    is_revoked   BOOLEAN      NOT NULL DEFAULT FALSE,
    last_seen_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT uq_devices_uid UNIQUE (device_uid),
    CONSTRAINT fk_devices_user
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT ck_devices_platform CHECK (platform IN ('android', 'ios', 'desktop'))
);

CREATE INDEX IF NOT EXISTS ix_devices_user ON devices (user_id);

INSERT INTO schema_migrations (version, description)
VALUES ('002', 'Dominio de seguridad y accesos')
ON CONFLICT (version) DO NOTHING;

COMMIT;
-- =============================================================================
-- 003_sistema.sql
-- Dominio: sistema y auditoria.  Propietario: sistema web (escritura de
-- configuracion) y todos los servicios (escritura de bitacora).
-- Tablas: audit_log, notifications, system_settings.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- audit_log
-- -----------------------------------------------------------------------------
-- Tabla de solo insercion. La escriben todos los microservicios; nadie la
-- actualiza ni la borra. correlation_id permite reconstruir una operacion
-- completa a traves de varios servicios a partir del header X-Correlation-ID.
CREATE TABLE IF NOT EXISTS audit_log (
    id             BIGSERIAL    PRIMARY KEY,
    user_id        BIGINT,
    action         VARCHAR(60)  NOT NULL,
    entity_type    VARCHAR(60)  NOT NULL,
    entity_id      VARCHAR(64),
    correlation_id UUID,
    ip_address     INET,
    user_agent     VARCHAR(255),
    data_before    JSONB,
    data_after     JSONB,
    occurred_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT fk_audit_log_user
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL,
    CONSTRAINT ck_audit_log_action CHECK (action IN
        ('LOGIN', 'LOGOUT', 'LOGIN_FAILED', 'CREATE', 'UPDATE', 'DELETE',
         'PUBLISH', 'RUN', 'CANCEL', 'EXPORT', 'SYNC', 'PERMISSION_DENIED')),
    -- Un alta no tiene estado previo y una baja no tiene estado posterior,
    -- pero al menos uno de los dos debe existir en operaciones de datos.
    CONSTRAINT ck_audit_log_datos CHECK (
        action NOT IN ('CREATE', 'UPDATE', 'DELETE')
        OR data_before IS NOT NULL OR data_after IS NOT NULL
    )
);

DROP TRIGGER IF EXISTS tg_audit_log_inmutable ON audit_log;
CREATE TRIGGER tg_audit_log_inmutable
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION fn_solo_insercion();

-- El tablero de auditoria consulta por fecha descendente; las investigaciones
-- puntuales buscan por entidad o por identificador de correlacion.
CREATE INDEX IF NOT EXISTS ix_audit_log_fecha       ON audit_log (occurred_at DESC);
CREATE INDEX IF NOT EXISTS ix_audit_log_entidad     ON audit_log (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS ix_audit_log_correlacion ON audit_log (correlation_id)
    WHERE correlation_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_audit_log_user        ON audit_log (user_id, occurred_at DESC);

-- -----------------------------------------------------------------------------
-- notifications
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS notifications (
    id         BIGSERIAL    PRIMARY KEY,
    user_id    BIGINT       NOT NULL,
    type       VARCHAR(40)  NOT NULL,
    title      VARCHAR(160) NOT NULL,
    body       TEXT,
    payload    JSONB,
    read_at    TIMESTAMPTZ,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT fk_notifications_user
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT ck_notifications_type CHECK (type IN
        ('RUN_FINISHED', 'RUN_FAILED', 'THRESHOLD_EXCEEDED', 'ASSIGNMENT',
         'SCENARIO_PUBLISHED', 'SYSTEM')),
    CONSTRAINT ck_notifications_lectura CHECK (read_at IS NULL OR read_at >= created_at)
);

-- La campana del portal solo pregunta por los no leidos de un usuario.
CREATE INDEX IF NOT EXISTS ix_notifications_pendientes
    ON notifications (user_id, created_at DESC) WHERE read_at IS NULL;

-- -----------------------------------------------------------------------------
-- system_settings
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS system_settings (
    key         VARCHAR(80)  PRIMARY KEY,
    value       JSONB        NOT NULL,
    description TEXT,
    updated_by  BIGINT,
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT fk_system_settings_user
        FOREIGN KEY (updated_by) REFERENCES users (id) ON DELETE SET NULL
);

DROP TRIGGER IF EXISTS tg_system_settings_updated_at ON system_settings;
CREATE TRIGGER tg_system_settings_updated_at
    BEFORE UPDATE ON system_settings
    FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

INSERT INTO schema_migrations (version, description)
VALUES ('003', 'Auditoria, notificaciones y configuracion del sistema')
ON CONFLICT (version) DO NOTHING;

COMMIT;
-- =============================================================================
-- 004_catalogos.sql
-- Dominio: catalogos.  Servicio propietario: catalog-service.
-- Tablas: diseases, regions, intervention_types.
-- Los demas servicios los leen; ninguno los escribe.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- diseases
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS diseases (
    id             SMALLSERIAL  PRIMARY KEY,
    code           VARCHAR(30)  NOT NULL,
    name           VARCHAR(120) NOT NULL,
    description    TEXT,
    default_params JSONB        NOT NULL DEFAULT '{}'::jsonb,
    is_active      BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT uq_diseases_code   UNIQUE (code),
    CONSTRAINT ck_diseases_params CHECK (jsonb_typeof(default_params) = 'object')
);

-- -----------------------------------------------------------------------------
-- regions
-- -----------------------------------------------------------------------------
-- Jerarquia geografica autorreferencial: estado -> municipio -> AGEB.
-- code es la clave oficial de INEGI, que es tambien la llave de union con los
-- datos censales usados para generar la poblacion sintetica.
CREATE TABLE IF NOT EXISTS regions (
    id               SERIAL        PRIMARY KEY,
    code             VARCHAR(20)   NOT NULL,
    name             VARCHAR(160)  NOT NULL,
    level            VARCHAR(20)   NOT NULL,
    parent_region_id INTEGER,
    population       INTEGER,
    centroid_lat     NUMERIC(9,6),
    centroid_lon     NUMERIC(9,6),
    created_at       TIMESTAMPTZ   NOT NULL DEFAULT now(),

    CONSTRAINT uq_regions_code UNIQUE (code),
    CONSTRAINT fk_regions_parent
        FOREIGN KEY (parent_region_id) REFERENCES regions (id) ON DELETE RESTRICT,
    CONSTRAINT ck_regions_level CHECK (level IN ('estado', 'municipio', 'ageb')),
    -- Solo el nivel estado puede carecer de padre; asi se evita que una zona
    -- quede desconectada del arbol por descuido.
    CONSTRAINT ck_regions_raiz CHECK (
        (level = 'estado' AND parent_region_id IS NULL)
        OR (level <> 'estado' AND parent_region_id IS NOT NULL)
    ),
    CONSTRAINT ck_regions_no_autopadre CHECK (parent_region_id IS DISTINCT FROM id),
    CONSTRAINT ck_regions_poblacion CHECK (population IS NULL OR population >= 0),
    CONSTRAINT ck_regions_lat CHECK (centroid_lat IS NULL OR centroid_lat BETWEEN -90 AND 90),
    CONSTRAINT ck_regions_lon CHECK (centroid_lon IS NULL OR centroid_lon BETWEEN -180 AND 180)
);

CREATE INDEX IF NOT EXISTS ix_regions_parent ON regions (parent_region_id);
CREATE INDEX IF NOT EXISTS ix_regions_level  ON regions (level);

-- -----------------------------------------------------------------------------
-- intervention_types
-- -----------------------------------------------------------------------------
-- primitive declara como compila la intervencion en el motor:
--   edge_modifier -> apaga o atenua contactos de una capa
--   node_attr     -> cambia un atributo del agente (susceptibilidad, aislamiento)
-- Declararlo en el catalogo permite validar el escenario antes de encolarlo.
CREATE TABLE IF NOT EXISTS intervention_types (
    id           SMALLSERIAL  PRIMARY KEY,
    code         VARCHAR(40)  NOT NULL,
    name         VARCHAR(120) NOT NULL,
    target_layer VARCHAR(20)  NOT NULL,
    primitive    VARCHAR(20)  NOT NULL,
    param_schema JSONB        NOT NULL DEFAULT '{}'::jsonb,
    description  TEXT,
    is_active    BOOLEAN      NOT NULL DEFAULT TRUE,

    CONSTRAINT uq_intervention_types_code UNIQUE (code),
    CONSTRAINT ck_intervention_types_layer CHECK (target_layer IN
        ('hogar', 'escuela', 'trabajo', 'comunidad', 'todas')),
    CONSTRAINT ck_intervention_types_primitive CHECK (primitive IN
        ('edge_modifier', 'node_attr')),
    CONSTRAINT ck_intervention_types_schema CHECK (jsonb_typeof(param_schema) = 'object')
);

INSERT INTO schema_migrations (version, description)
VALUES ('004', 'Catalogos: enfermedades, regiones y tipos de intervencion')
ON CONFLICT (version) DO NOTHING;

COMMIT;
-- =============================================================================
-- 005_vigilancia.sql
-- Dominio: vigilancia de campo.  Servicio propietario: surveillance-service.
-- Tablas: vaccine_lots, cases, case_attachments.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- vaccine_lots
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vaccine_lots (
    id           BIGSERIAL    PRIMARY KEY,
    lot_code     VARCHAR(60)  NOT NULL,
    manufacturer VARCHAR(120),
    disease_id   SMALLINT     NOT NULL,
    region_id    INTEGER,
    doses_total  INTEGER      NOT NULL,
    doses_used   INTEGER      NOT NULL DEFAULT 0,
    expires_on   DATE,
    scanned_by   BIGINT       NOT NULL,
    scanned_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT uq_vaccine_lots_code UNIQUE (lot_code),
    CONSTRAINT fk_vaccine_lots_disease
        FOREIGN KEY (disease_id) REFERENCES diseases (id) ON DELETE RESTRICT,
    CONSTRAINT fk_vaccine_lots_region
        FOREIGN KEY (region_id)  REFERENCES regions (id)  ON DELETE SET NULL,
    CONSTRAINT fk_vaccine_lots_scanner
        FOREIGN KEY (scanned_by) REFERENCES users (id)    ON DELETE RESTRICT,
    CONSTRAINT ck_vaccine_lots_total CHECK (doses_total > 0),
    -- Invariante de negocio: nunca se pueden aplicar mas dosis de las que trae
    -- el lote. La base lo garantiza, no el cliente movil.
    CONSTRAINT ck_vaccine_lots_usadas CHECK (doses_used BETWEEN 0 AND doses_total)
);

CREATE INDEX IF NOT EXISTS ix_vaccine_lots_region  ON vaccine_lots (region_id);
CREATE INDEX IF NOT EXISTS ix_vaccine_lots_disease ON vaccine_lots (disease_id);

-- -----------------------------------------------------------------------------
-- cases
-- -----------------------------------------------------------------------------
-- local_uuid lo genera la app Android antes de tener red. Es la llave de
-- deduplicacion: si WorkManager reintenta un envio, el segundo choca contra la
-- restriccion unica y el servicio responde 409 en vez de duplicar el caso.
CREATE TABLE IF NOT EXISTS cases (
    id             BIGSERIAL     PRIMARY KEY,
    local_uuid     UUID          NOT NULL,
    device_id      BIGINT,
    reported_by    BIGINT        NOT NULL,
    disease_id     SMALLINT      NOT NULL,
    region_id      INTEGER       NOT NULL,
    vaccine_lot_id BIGINT,
    age            SMALLINT,
    sex            CHAR(1),
    onset_date     DATE,
    report_date    DATE          NOT NULL,
    latitude       NUMERIC(9,6),
    longitude      NUMERIC(9,6),
    test_result    VARCHAR(20),
    severity       VARCHAR(20),
    status         VARCHAR(20)   NOT NULL DEFAULT 'pendiente',
    created_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),
    synced_at      TIMESTAMPTZ,

    CONSTRAINT uq_cases_local_uuid UNIQUE (local_uuid),
    CONSTRAINT fk_cases_device
        FOREIGN KEY (device_id)      REFERENCES devices (id)      ON DELETE SET NULL,
    CONSTRAINT fk_cases_reporter
        FOREIGN KEY (reported_by)    REFERENCES users (id)        ON DELETE RESTRICT,
    CONSTRAINT fk_cases_disease
        FOREIGN KEY (disease_id)     REFERENCES diseases (id)     ON DELETE RESTRICT,
    CONSTRAINT fk_cases_region
        FOREIGN KEY (region_id)      REFERENCES regions (id)      ON DELETE RESTRICT,
    CONSTRAINT fk_cases_vaccine_lot
        FOREIGN KEY (vaccine_lot_id) REFERENCES vaccine_lots (id) ON DELETE SET NULL,

    CONSTRAINT ck_cases_age    CHECK (age IS NULL OR age BETWEEN 0 AND 120),
    CONSTRAINT ck_cases_sex    CHECK (sex IS NULL OR sex IN ('M', 'F', 'O')),
    CONSTRAINT ck_cases_result CHECK (test_result IS NULL OR test_result IN
        ('positivo', 'negativo', 'pendiente', 'sin_prueba')),
    CONSTRAINT ck_cases_severity CHECK (severity IS NULL OR severity IN
        ('asintomatico', 'leve', 'grave', 'fallecido')),
    CONSTRAINT ck_cases_status CHECK (status IN
        ('pendiente', 'validado', 'duplicado', 'descartado')),
    -- El rezago de notificacion es positivo por definicion: no se puede
    -- reportar un caso antes de que empiecen los sintomas.
    CONSTRAINT ck_cases_rezago CHECK (onset_date IS NULL OR onset_date <= report_date),
    CONSTRAINT ck_cases_lat CHECK (latitude  IS NULL OR latitude  BETWEEN -90 AND 90),
    CONSTRAINT ck_cases_lon CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180),
    -- La geolocalizacion viaja completa o no viaja.
    CONSTRAINT ck_cases_coordenadas CHECK (
        (latitude IS NULL AND longitude IS NULL)
        OR (latitude IS NOT NULL AND longitude IS NOT NULL)
    )
);

-- La curva epidemica se arma por fecha; el mapa de incidencia por zona y fecha.
CREATE INDEX IF NOT EXISTS ix_cases_report_date  ON cases (report_date DESC);
CREATE INDEX IF NOT EXISTS ix_cases_region_fecha ON cases (region_id, report_date);
CREATE INDEX IF NOT EXISTS ix_cases_disease_onset ON cases (disease_id, onset_date);
CREATE INDEX IF NOT EXISTS ix_cases_pendientes   ON cases (status) WHERE status = 'pendiente';
CREATE INDEX IF NOT EXISTS ix_cases_reporter     ON cases (reported_by);

-- -----------------------------------------------------------------------------
-- case_attachments
-- -----------------------------------------------------------------------------
-- El archivo vive en Cloud Storage. Aqui solo viaja la ruta y los metadatos
-- que exige la materia: identificador, ruta, tipo, tamanio, propietario,
-- fecha, hash, nivel de privacidad.
CREATE TABLE IF NOT EXISTS case_attachments (
    id           BIGSERIAL    PRIMARY KEY,
    case_id      BIGINT       NOT NULL,
    storage_path VARCHAR(255) NOT NULL,
    mime_type    VARCHAR(80)  NOT NULL,
    size_bytes   BIGINT       NOT NULL,
    sha256       CHAR(64)     NOT NULL,
    privacy      VARCHAR(20)  NOT NULL DEFAULT 'privado',
    uploaded_by  BIGINT       NOT NULL,
    uploaded_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT uq_case_attachments_path UNIQUE (storage_path),
    CONSTRAINT fk_case_attachments_case
        FOREIGN KEY (case_id)     REFERENCES cases (id) ON DELETE CASCADE,
    CONSTRAINT fk_case_attachments_uploader
        FOREIGN KEY (uploaded_by) REFERENCES users (id) ON DELETE RESTRICT,
    CONSTRAINT ck_case_attachments_size CHECK (size_bytes > 0),
    -- Limite de 20 MB por evidencia, alineado con el limite del cliente movil.
    CONSTRAINT ck_case_attachments_max  CHECK (size_bytes <= 20971520),
    CONSTRAINT ck_case_attachments_mime CHECK (mime_type IN
        ('image/jpeg', 'image/png', 'image/webp', 'application/pdf')),
    CONSTRAINT ck_case_attachments_hash CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_case_attachments_privacy CHECK (privacy IN ('privado', 'publico'))
);

CREATE INDEX IF NOT EXISTS ix_case_attachments_case ON case_attachments (case_id);
-- Detecta la misma foto subida dos veces desde dispositivos distintos.
CREATE INDEX IF NOT EXISTS ix_case_attachments_hash ON case_attachments (sha256);

INSERT INTO schema_migrations (version, description)
VALUES ('005', 'Vigilancia de campo: lotes, casos y evidencias')
ON CONFLICT (version) DO NOTHING;

COMMIT;
-- =============================================================================
-- 006_escenarios.sql
-- Dominio: escenarios.  Servicio propietario: scenario-service.
-- Tablas: scenarios, scenario_versions, scenario_interventions.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- scenarios
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scenarios (
    id          BIGSERIAL    PRIMARY KEY,
    name        VARCHAR(160) NOT NULL,
    description TEXT,
    disease_id  SMALLINT     NOT NULL,
    region_id   INTEGER      NOT NULL,
    owner_id    BIGINT       NOT NULL,
    status      VARCHAR(20)  NOT NULL DEFAULT 'borrador',
    is_public   BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT fk_scenarios_disease
        FOREIGN KEY (disease_id) REFERENCES diseases (id) ON DELETE RESTRICT,
    CONSTRAINT fk_scenarios_region
        FOREIGN KEY (region_id)  REFERENCES regions (id)  ON DELETE RESTRICT,
    CONSTRAINT fk_scenarios_owner
        FOREIGN KEY (owner_id)   REFERENCES users (id)    ON DELETE RESTRICT,
    CONSTRAINT ck_scenarios_status CHECK (status IN ('borrador', 'publicado', 'archivado')),
    -- Solo un escenario publicado puede aparecer en el sitio publico.
    CONSTRAINT ck_scenarios_publico CHECK (NOT is_public OR status = 'publicado'),
    -- Un mismo analista no puede tener dos escenarios con el mismo nombre.
    CONSTRAINT uq_scenarios_owner_name UNIQUE (owner_id, name)
);

DROP TRIGGER IF EXISTS tg_scenarios_updated_at ON scenarios;
CREATE TRIGGER tg_scenarios_updated_at
    BEFORE UPDATE ON scenarios
    FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at();

CREATE INDEX IF NOT EXISTS ix_scenarios_owner   ON scenarios (owner_id);
CREATE INDEX IF NOT EXISTS ix_scenarios_publicos ON scenarios (status) WHERE is_public;

-- -----------------------------------------------------------------------------
-- scenario_versions
-- -----------------------------------------------------------------------------
-- Una version es inmutable una vez creada: es lo que hace reproducible una
-- corrida. Si el analista cambia algo, se crea la version siguiente.
CREATE TABLE IF NOT EXISTS scenario_versions (
    id              BIGSERIAL    PRIMARY KEY,
    scenario_id     BIGINT       NOT NULL,
    version_number  INTEGER      NOT NULL DEFAULT 1,
    is_current      BOOLEAN      NOT NULL DEFAULT FALSE,
    xml_path        VARCHAR(255),
    xml_checksum    CHAR(64),
    population_size INTEGER      NOT NULL,
    horizon_days    SMALLINT     NOT NULL DEFAULT 365,
    notes           TEXT,
    created_by      BIGINT       NOT NULL,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),

    CONSTRAINT uq_scenario_versions_numero UNIQUE (scenario_id, version_number),
    CONSTRAINT fk_scenario_versions_scenario
        FOREIGN KEY (scenario_id) REFERENCES scenarios (id) ON DELETE CASCADE,
    CONSTRAINT fk_scenario_versions_author
        FOREIGN KEY (created_by)  REFERENCES users (id)     ON DELETE RESTRICT,
    CONSTRAINT ck_scenario_versions_numero CHECK (version_number >= 1),
    CONSTRAINT ck_scenario_versions_poblacion
        CHECK (population_size BETWEEN 1000 AND 5000000),
    CONSTRAINT ck_scenario_versions_horizonte
        CHECK (horizon_days BETWEEN 1 AND 1095),
    CONSTRAINT ck_scenario_versions_checksum
        CHECK (xml_checksum IS NULL OR xml_checksum ~ '^[0-9a-f]{64}$'),
    -- Si hay XML exportado tiene que haber huella, para poder demostrar que la
    -- corrida uso exactamente ese archivo.
    CONSTRAINT ck_scenario_versions_xml CHECK (
        (xml_path IS NULL AND xml_checksum IS NULL)
        OR (xml_path IS NOT NULL AND xml_checksum IS NOT NULL)
    )
);

-- Una sola version vigente por escenario. El indice parcial unico lo garantiza
-- sin bloquear las versiones historicas, que llevan is_current = FALSE.
CREATE UNIQUE INDEX IF NOT EXISTS uq_scenario_versions_vigente
    ON scenario_versions (scenario_id) WHERE is_current;

CREATE INDEX IF NOT EXISTS ix_scenario_versions_scenario
    ON scenario_versions (scenario_id, version_number DESC);

-- -----------------------------------------------------------------------------
-- scenario_interventions
-- -----------------------------------------------------------------------------
-- Calendario de intervenciones de una version: es el contenido que el motor
-- traduce a reglas por dia de simulacion.
CREATE TABLE IF NOT EXISTS scenario_interventions (
    id                   BIGSERIAL    PRIMARY KEY,
    scenario_version_id  BIGINT       NOT NULL,
    intervention_type_id SMALLINT     NOT NULL,
    target_region_id     INTEGER,
    start_day            SMALLINT     NOT NULL,
    end_day              SMALLINT,
    coverage             NUMERIC(4,3),
    compliance           NUMERIC(4,3),
    params               JSONB        NOT NULL DEFAULT '{}'::jsonb,
    order_index          SMALLINT     NOT NULL DEFAULT 0,

    CONSTRAINT fk_scenario_interventions_version
        FOREIGN KEY (scenario_version_id)  REFERENCES scenario_versions (id)  ON DELETE CASCADE,
    CONSTRAINT fk_scenario_interventions_type
        FOREIGN KEY (intervention_type_id) REFERENCES intervention_types (id) ON DELETE RESTRICT,
    CONSTRAINT fk_scenario_interventions_region
        FOREIGN KEY (target_region_id)     REFERENCES regions (id)            ON DELETE RESTRICT,
    CONSTRAINT ck_scenario_interventions_inicio CHECK (start_day >= 0),
    CONSTRAINT ck_scenario_interventions_rango  CHECK (end_day IS NULL OR end_day >= start_day),
    CONSTRAINT ck_scenario_interventions_cobertura
        CHECK (coverage   IS NULL OR coverage   BETWEEN 0 AND 1),
    CONSTRAINT ck_scenario_interventions_cumplimiento
        CHECK (compliance IS NULL OR compliance BETWEEN 0 AND 1),
    CONSTRAINT ck_scenario_interventions_params
        CHECK (jsonb_typeof(params) = 'object'),
    -- Dos intervenciones del mismo tipo que empiezan el mismo dia en la misma
    -- zona son casi siempre un error de captura del editor de escritorio.
    -- NULLS NOT DISTINCT hace que la regla aplique tambien cuando la zona es
    -- nula, es decir cuando la intervencion cubre toda la region del escenario.
    -- Requiere PostgreSQL 15 o superior.
    CONSTRAINT uq_scenario_interventions_unica
        UNIQUE NULLS NOT DISTINCT
        (scenario_version_id, intervention_type_id, start_day, target_region_id)
);

CREATE INDEX IF NOT EXISTS ix_scenario_interventions_version
    ON scenario_interventions (scenario_version_id, start_day);

INSERT INTO schema_migrations (version, description)
VALUES ('006', 'Escenarios, versionado e intervenciones programadas')
ON CONFLICT (version) DO NOTHING;

COMMIT;
-- =============================================================================
-- 007_simulacion.sql
-- Dominio: simulacion.  Servicio propietario: simulation-service.
-- Tablas: simulation_batches, simulation_runs.
--
-- Aqui viven solo los metadatos. Las series diarias van a MongoDB y las
-- salidas voluminosas a Cloud Storage; esta base guarda unicamente el
-- identificador del documento y la ruta del artefacto.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- simulation_batches
-- -----------------------------------------------------------------------------
-- Un lote son entre 30 y 50 replicas de la misma version con semillas
-- distintas. El lote, no la corrida, es la unidad que se compara en la
-- frontera de eficiencia: una sola corrida de un modelo estocastico no
-- significa nada.
CREATE TABLE IF NOT EXISTS simulation_batches (
    id                  BIGSERIAL   PRIMARY KEY,
    scenario_version_id BIGINT      NOT NULL,
    requested_by        BIGINT      NOT NULL,
    replicas            SMALLINT    NOT NULL DEFAULT 30,
    engine              VARCHAR(20) NOT NULL DEFAULT 'numba',
    status              VARCHAR(20) NOT NULL DEFAULT 'encolado',
    summary_doc_id      VARCHAR(64),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at         TIMESTAMPTZ,

    CONSTRAINT fk_simulation_batches_version
        FOREIGN KEY (scenario_version_id) REFERENCES scenario_versions (id) ON DELETE RESTRICT,
    CONSTRAINT fk_simulation_batches_user
        FOREIGN KEY (requested_by)        REFERENCES users (id)             ON DELETE RESTRICT,
    -- Menos de 30 replicas no permite reportar mediana con banda de
    -- incertidumbre; mas de 200 satura la cola sin ganancia estadistica.
    CONSTRAINT ck_simulation_batches_replicas CHECK (replicas BETWEEN 30 AND 200),
    CONSTRAINT ck_simulation_batches_engine   CHECK (engine IN ('numba', 'cuda')),
    CONSTRAINT ck_simulation_batches_status   CHECK (status IN
        ('encolado', 'ejecutando', 'completado', 'fallido', 'cancelado')),
    CONSTRAINT ck_simulation_batches_fin CHECK (
        finished_at IS NULL OR finished_at >= created_at
    ),
    -- Un lote terminado tiene fecha de termino, y solo uno completado puede
    -- tener resumen agregado.
    CONSTRAINT ck_simulation_batches_terminal CHECK (
        (status IN ('completado', 'fallido', 'cancelado')) = (finished_at IS NOT NULL)
    ),
    CONSTRAINT ck_simulation_batches_resumen CHECK (
        summary_doc_id IS NULL OR status = 'completado'
    )
);

CREATE INDEX IF NOT EXISTS ix_simulation_batches_version
    ON simulation_batches (scenario_version_id);
CREATE INDEX IF NOT EXISTS ix_simulation_batches_user
    ON simulation_batches (requested_by, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_simulation_batches_activos
    ON simulation_batches (status) WHERE status IN ('encolado', 'ejecutando');

-- -----------------------------------------------------------------------------
-- simulation_runs
-- -----------------------------------------------------------------------------
-- id es el job_id que se devuelve al cliente en POST /api/v1/simulations.
-- El progreso en vivo se lleva en Redis (job:{id}:progress); la columna
-- progress guarda el valor consolidado para cuando Redis se reinicie.
CREATE TABLE IF NOT EXISTS simulation_runs (
    id                  BIGSERIAL    PRIMARY KEY,
    batch_id            BIGINT,
    scenario_version_id BIGINT       NOT NULL,
    seed                BIGINT       NOT NULL,
    replica_index       SMALLINT,
    status              VARCHAR(20)  NOT NULL DEFAULT 'encolado',
    progress            SMALLINT     NOT NULL DEFAULT 0,
    engine_version      VARCHAR(30),
    queued_at           TIMESTAMPTZ  NOT NULL DEFAULT now(),
    started_at          TIMESTAMPTZ,
    finished_at         TIMESTAMPTZ,
    result_doc_id       VARCHAR(64),
    artifacts_path      VARCHAR(255),
    error_message       TEXT,

    CONSTRAINT fk_simulation_runs_batch
        FOREIGN KEY (batch_id)            REFERENCES simulation_batches (id) ON DELETE CASCADE,
    CONSTRAINT fk_simulation_runs_version
        FOREIGN KEY (scenario_version_id) REFERENCES scenario_versions (id)  ON DELETE RESTRICT,
    CONSTRAINT ck_simulation_runs_status CHECK (status IN
        ('encolado', 'ejecutando', 'completado', 'fallido', 'cancelado')),
    CONSTRAINT ck_simulation_runs_progress CHECK (progress BETWEEN 0 AND 100),
    CONSTRAINT ck_simulation_runs_seed     CHECK (seed >= 0),
    CONSTRAINT ck_simulation_runs_replica  CHECK (replica_index IS NULL OR replica_index >= 0),
    -- Coherencia del ciclo de vida encolado -> ejecutando -> terminal.
    CONSTRAINT ck_simulation_runs_inicio CHECK (
        (status = 'encolado') = (started_at IS NULL)
    ),
    CONSTRAINT ck_simulation_runs_fin CHECK (
        (status IN ('completado', 'fallido', 'cancelado')) = (finished_at IS NOT NULL)
    ),
    CONSTRAINT ck_simulation_runs_tiempos CHECK (
        (started_at  IS NULL OR started_at  >= queued_at)
        AND (finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at)
    ),
    -- Una corrida fallida explica por que; una completada apunta a su
    -- documento de resultados en MongoDB.
    CONSTRAINT ck_simulation_runs_error CHECK (
        (status = 'fallido') = (error_message IS NOT NULL)
    ),
    CONSTRAINT ck_simulation_runs_resultado CHECK (
        result_doc_id IS NULL OR status = 'completado'
    ),
    -- Dentro de un lote, ni la semilla ni el numero de replica se repiten.
    CONSTRAINT uq_simulation_runs_replica UNIQUE (batch_id, replica_index),
    CONSTRAINT uq_simulation_runs_semilla UNIQUE (batch_id, seed)
);

-- El worker del motor pregunta por trabajos pendientes; el tablero pregunta
-- por las corridas de un lote.
CREATE INDEX IF NOT EXISTS ix_simulation_runs_pendientes
    ON simulation_runs (queued_at) WHERE status = 'encolado';
CREATE INDEX IF NOT EXISTS ix_simulation_runs_batch   ON simulation_runs (batch_id);
CREATE INDEX IF NOT EXISTS ix_simulation_runs_version ON simulation_runs (scenario_version_id);
CREATE INDEX IF NOT EXISTS ix_simulation_runs_status  ON simulation_runs (status);

INSERT INTO schema_migrations (version, description)
VALUES ('007', 'Simulacion: lotes y corridas')
ON CONFLICT (version) DO NOTHING;

COMMIT;
-- ===========================================================================
-- 008_comentarios.sql
-- Documentacion embebida en la base de datos.
--
-- Generado a partir del diccionario de datos: no editar a mano. Si cambia una
-- descripcion, cambiarla en el diccionario y volver a generar este archivo.
--
-- Consultar desde psql con \d+ nombre_tabla, o desde SQL con:
--   SELECT c.column_name, col_description(c.table_name::regclass, c.ordinal_position)
--   FROM information_schema.columns c WHERE c.table_name = 'cases';
-- ===========================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- users  (Seguridad y usuarios · auth-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE users IS 'Cuentas de acceso a la plataforma. Unica fuente de identidad para los tres clientes.';
COMMENT ON COLUMN users.id IS 'Identificador interno de la cuenta. [llave primaria]';
COMMENT ON COLUMN users.username IS 'Nombre de acceso. Unico, sin distincion de mayusculas.';
COMMENT ON COLUMN users.email IS 'Correo institucional. Se usa para recuperacion de contrasena.';
COMMENT ON COLUMN users.password_hash IS 'Hash con algoritmo de costo alto (bcrypt o argon2). Nunca la contrasena.';
COMMENT ON COLUMN users.full_name IS 'Nombre completo mostrado en la interfaz y en la bitacora.';
COMMENT ON COLUMN users.is_active IS 'Baja logica. Un usuario inactivo no puede autenticarse pero conserva su historial.';
COMMENT ON COLUMN users.failed_attempts IS 'Intentos fallidos consecutivos. Se reinicia al iniciar sesion con exito.';
COMMENT ON COLUMN users.last_login_at IS 'Ultimo inicio de sesion exitoso, en cualquier cliente.';
COMMENT ON COLUMN users.created_at IS 'Fecha de alta de la cuenta.';
COMMENT ON COLUMN users.updated_at IS 'Ultima modificacion del registro.';

-- ---------------------------------------------------------------------------
-- roles  (Seguridad y usuarios · auth-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE roles IS 'Catalogo de perfiles: administrador, epidemiologo, analista, capturista.';
COMMENT ON COLUMN roles.id IS 'Identificador del rol. [llave primaria]';
COMMENT ON COLUMN roles.code IS 'Clave estable usada en el codigo y en el JWT. Ejemplo: EPIDEMIOLOGO.';
COMMENT ON COLUMN roles.name IS 'Nombre visible del rol.';
COMMENT ON COLUMN roles.description IS 'Responsabilidades del perfil.';
COMMENT ON COLUMN roles.is_system IS 'Los roles de sistema no se pueden borrar desde la interfaz.';
COMMENT ON COLUMN roles.created_at IS 'Fecha de alta.';

-- ---------------------------------------------------------------------------
-- permissions  (Seguridad y usuarios · auth-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE permissions IS 'Permisos atomicos por recurso y accion. Base de la matriz de permisos.';
COMMENT ON COLUMN permissions.id IS 'Identificador del permiso. [llave primaria]';
COMMENT ON COLUMN permissions.code IS 'Clave compuesta recurso.accion. Ejemplo: scenarios.publish.';
COMMENT ON COLUMN permissions.resource IS 'Recurso protegido: scenarios, cases, users, simulations.';
COMMENT ON COLUMN permissions.action IS 'Accion: read, create, update, delete, publish, run.';
COMMENT ON COLUMN permissions.description IS 'Que habilita el permiso en terminos de negocio.';

-- ---------------------------------------------------------------------------
-- user_roles  (Seguridad y usuarios · auth-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE user_roles IS 'Asignacion de roles a usuarios. Un usuario puede tener varios roles.';
COMMENT ON COLUMN user_roles.user_id IS 'Usuario al que se asigna el rol. Referencia a users.id. [llave primaria]';
COMMENT ON COLUMN user_roles.role_id IS 'Rol asignado. Referencia a roles.id. [llave primaria]';
COMMENT ON COLUMN user_roles.assigned_by IS 'Administrador que hizo la asignacion. Referencia a users.id. [llave foranea]';
COMMENT ON COLUMN user_roles.assigned_at IS 'Momento de la asignacion.';

-- ---------------------------------------------------------------------------
-- role_permissions  (Seguridad y usuarios · auth-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE role_permissions IS 'Permisos concedidos a cada rol. Es la matriz de permisos del primer parcial.';
COMMENT ON COLUMN role_permissions.role_id IS 'Rol que recibe el permiso. Referencia a roles.id. [llave primaria]';
COMMENT ON COLUMN role_permissions.permission_id IS 'Permiso concedido. Referencia a permissions.id. [llave primaria]';

-- ---------------------------------------------------------------------------
-- password_resets  (Seguridad y usuarios · auth-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE password_resets IS 'Solicitudes de recuperacion de contrasena. Requisito explicito de la materia.';
COMMENT ON COLUMN password_resets.id IS 'Identificador de la solicitud. [llave primaria]';
COMMENT ON COLUMN password_resets.user_id IS 'Usuario que solicito el restablecimiento. Referencia a users.id. [llave foranea]';
COMMENT ON COLUMN password_resets.token_hash IS 'Hash del token enviado por correo. El token en claro nunca se guarda.';
COMMENT ON COLUMN password_resets.expires_at IS 'Vencimiento del token, tipicamente una hora.';
COMMENT ON COLUMN password_resets.used_at IS 'Momento de uso. Un token usado no se puede reutilizar.';
COMMENT ON COLUMN password_resets.requested_ip IS 'Direccion desde la que se pidio, para deteccion de abuso.';
COMMENT ON COLUMN password_resets.created_at IS 'Fecha de la solicitud.';

-- ---------------------------------------------------------------------------
-- devices  (Seguridad y usuarios · auth-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE devices IS 'Dispositivos moviles registrados. Permite revocar un telefono perdido sin tocar la cuenta.';
COMMENT ON COLUMN devices.id IS 'Identificador interno del dispositivo. [llave primaria]';
COMMENT ON COLUMN devices.user_id IS 'Duenio del dispositivo. Referencia a users.id. [llave foranea]';
COMMENT ON COLUMN devices.device_uid IS 'Identificador seguro generado por la app Android. Requisito de la materia.';
COMMENT ON COLUMN devices.platform IS 'Plataforma del cliente.';
COMMENT ON COLUMN devices.model IS 'Modelo del equipo, util para depurar fallas de camara o GPS.';
COMMENT ON COLUMN devices.app_version IS 'Version instalada de la app, para diagnosticar incompatibilidades.';
COMMENT ON COLUMN devices.push_token IS 'Token de notificaciones push. Cambia con reinstalaciones.';
COMMENT ON COLUMN devices.is_revoked IS 'Un dispositivo revocado no puede sincronizar aunque tenga JWT valido.';
COMMENT ON COLUMN devices.last_seen_at IS 'Ultima sincronizacion registrada.';
COMMENT ON COLUMN devices.created_at IS 'Fecha de registro del dispositivo.';

-- ---------------------------------------------------------------------------
-- audit_log  (Sistema y auditoria · sistema web / todos)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE audit_log IS 'Bitacora de auditoria: quien hizo que, cuando y desde donde. Solo insercion.';
COMMENT ON COLUMN audit_log.id IS 'Identificador del asiento. [llave primaria]';
COMMENT ON COLUMN audit_log.user_id IS 'Autor de la accion. Nulo en procesos automaticos. Referencia a users.id. [llave foranea]';
COMMENT ON COLUMN audit_log.action IS 'Operacion: LOGIN, CREATE, UPDATE, DELETE, PUBLISH, RUN.';
COMMENT ON COLUMN audit_log.entity_type IS 'Tabla o recurso afectado.';
COMMENT ON COLUMN audit_log.entity_id IS 'Identificador del registro afectado, como texto para admitir cualquier tipo.';
COMMENT ON COLUMN audit_log.correlation_id IS 'X-Correlation-ID de la peticion. Permite rastrear la operacion entre servicios.';
COMMENT ON COLUMN audit_log.ip_address IS 'Origen de la peticion.';
COMMENT ON COLUMN audit_log.user_agent IS 'Cliente que origino la accion: navegador, Android o escritorio.';
COMMENT ON COLUMN audit_log.data_before IS 'Estado previo del registro. Nulo en altas.';
COMMENT ON COLUMN audit_log.data_after IS 'Estado posterior. Nulo en bajas.';
COMMENT ON COLUMN audit_log.occurred_at IS 'Momento del evento. Indice para consultas por rango de fechas.';

-- ---------------------------------------------------------------------------
-- notifications  (Sistema y auditoria · sistema web / todos)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE notifications IS 'Avisos al usuario: corrida terminada, umbral rebasado, asignacion de zona.';
COMMENT ON COLUMN notifications.id IS 'Identificador del aviso. [llave primaria]';
COMMENT ON COLUMN notifications.user_id IS 'Destinatario. Referencia a users.id. [llave foranea]';
COMMENT ON COLUMN notifications.type IS 'Tipo: RUN_FINISHED, THRESHOLD_EXCEEDED, ASSIGNMENT.';
COMMENT ON COLUMN notifications.title IS 'Titulo corto mostrado en la campana del portal y en el push.';
COMMENT ON COLUMN notifications.body IS 'Cuerpo del mensaje.';
COMMENT ON COLUMN notifications.payload IS 'Datos para navegar al recurso: run_id, scenario_id, region_id.';
COMMENT ON COLUMN notifications.read_at IS 'Momento de lectura. Nulo mientras no se lee.';
COMMENT ON COLUMN notifications.created_at IS 'Fecha de emision.';

-- ---------------------------------------------------------------------------
-- system_settings  (Sistema y auditoria · sistema web / todos)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE system_settings IS 'Configuracion del sistema editable sin desplegar codigo.';
COMMENT ON COLUMN system_settings.key IS 'Clave del parametro. Ejemplo: max_replicas_por_lote. [llave primaria]';
COMMENT ON COLUMN system_settings.value IS 'Valor. JSONB para admitir numeros, textos, listas y objetos.';
COMMENT ON COLUMN system_settings.description IS 'Que controla el parametro y que rango es seguro.';
COMMENT ON COLUMN system_settings.updated_by IS 'Ultimo administrador que lo cambio. Referencia a users.id. [llave foranea]';
COMMENT ON COLUMN system_settings.updated_at IS 'Fecha del ultimo cambio.';

-- ---------------------------------------------------------------------------
-- diseases  (Catalogos · catalog-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE diseases IS 'Catalogo de enfermedades con sus parametros epidemiologicos base.';
COMMENT ON COLUMN diseases.id IS 'Identificador de la enfermedad. [llave primaria]';
COMMENT ON COLUMN diseases.code IS 'Clave estable. Ejemplo: COVID19_ORIGINAL.';
COMMENT ON COLUMN diseases.name IS 'Nombre de la enfermedad o variante.';
COMMENT ON COLUMN diseases.description IS 'Contexto y fuente de los parametros.';
COMMENT ON COLUMN diseases.default_params IS 'Parametros base: incubacion, duracion infecciosa, letalidad por grupo de edad.';
COMMENT ON COLUMN diseases.is_active IS 'Baja logica del catalogo.';
COMMENT ON COLUMN diseases.created_at IS 'Fecha de alta.';

-- ---------------------------------------------------------------------------
-- regions  (Catalogos · catalog-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE regions IS 'Jerarquia geografica del area metropolitana. Autorreferencial: estado, municipio, AGEB.';
COMMENT ON COLUMN regions.id IS 'Identificador interno de la zona. [llave primaria]';
COMMENT ON COLUMN regions.code IS 'Clave oficial INEGI. Ejemplo: 19039-0123.';
COMMENT ON COLUMN regions.name IS 'Nombre de la zona.';
COMMENT ON COLUMN regions.level IS 'Nivel jerarquico: estado, municipio o ageb.';
COMMENT ON COLUMN regions.parent_region_id IS 'Zona superior. Nulo solo en la raiz. Referencia a regions.id. [llave foranea]';
COMMENT ON COLUMN regions.population IS 'Poblacion censal. Insumo del generador de poblacion sintetica.';
COMMENT ON COLUMN regions.centroid_lat IS 'Latitud del centroide, para el mapa de incidencia.';
COMMENT ON COLUMN regions.centroid_lon IS 'Longitud del centroide.';
COMMENT ON COLUMN regions.created_at IS 'Fecha de carga.';

-- ---------------------------------------------------------------------------
-- intervention_types  (Catalogos · catalog-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE intervention_types IS 'Catalogo de intervenciones modelables y como se traducen al motor.';
COMMENT ON COLUMN intervention_types.id IS 'Identificador del tipo de intervencion. [llave primaria]';
COMMENT ON COLUMN intervention_types.code IS 'Clave estable. Ejemplo: CIERRE_ESCUELAS.';
COMMENT ON COLUMN intervention_types.name IS 'Nombre visible.';
COMMENT ON COLUMN intervention_types.target_layer IS 'Capa de contacto afectada: hogar, escuela, trabajo, comunidad o todas.';
COMMENT ON COLUMN intervention_types.primitive IS 'Primitiva del motor: edge_modifier o node_attr. Define como compila el XML.';
COMMENT ON COLUMN intervention_types.param_schema IS 'Esquema de los parametros admitidos. Valida el escenario antes de encolar.';
COMMENT ON COLUMN intervention_types.description IS 'Efecto de la intervencion en el modelo.';
COMMENT ON COLUMN intervention_types.is_active IS 'Baja logica del catalogo.';

-- ---------------------------------------------------------------------------
-- cases  (Vigilancia de campo · surveillance-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE cases IS 'Casos capturados en campo desde la app movil. Alimentan la recalibracion del modelo.';
COMMENT ON COLUMN cases.id IS 'Identificador del caso en el servidor. [llave primaria]';
COMMENT ON COLUMN cases.local_uuid IS 'Identificador generado en el dispositivo. Evita duplicados si un envio se repite.';
COMMENT ON COLUMN cases.device_id IS 'Dispositivo que capturo el caso. Referencia a devices.id. [llave foranea]';
COMMENT ON COLUMN cases.reported_by IS 'Brigadista que reporto. Referencia a users.id. [llave foranea]';
COMMENT ON COLUMN cases.disease_id IS 'Enfermedad reportada. Referencia a diseases.id. [llave foranea]';
COMMENT ON COLUMN cases.region_id IS 'Zona de residencia del caso. Referencia a regions.id. [llave foranea]';
COMMENT ON COLUMN cases.vaccine_lot_id IS 'Lote aplicado, si aplica. Referencia a vaccine_lots.id. [llave foranea]';
COMMENT ON COLUMN cases.age IS 'Edad en anios. Determina el riesgo de curso grave.';
COMMENT ON COLUMN cases.sex IS 'Sexo registrado: M, F u O.';
COMMENT ON COLUMN cases.onset_date IS 'Fecha de inicio de sintomas. Es la fecha epidemiologicamente relevante.';
COMMENT ON COLUMN cases.report_date IS 'Fecha de captura. La diferencia con onset_date estima el rezago de notificacion.';
COMMENT ON COLUMN cases.latitude IS 'Latitud capturada por GPS.';
COMMENT ON COLUMN cases.longitude IS 'Longitud capturada por GPS.';
COMMENT ON COLUMN cases.test_result IS 'Resultado de prueba: positivo, negativo, pendiente o sin prueba.';
COMMENT ON COLUMN cases.severity IS 'Gravedad: asintomatico, leve, grave o fallecido.';
COMMENT ON COLUMN cases.status IS 'Estado de validacion: pendiente, validado, duplicado o descartado.';
COMMENT ON COLUMN cases.created_at IS 'Momento de captura en el dispositivo.';
COMMENT ON COLUMN cases.synced_at IS 'Momento de llegada al servidor. Puede ser mucho posterior por el modo sin conexion.';

-- ---------------------------------------------------------------------------
-- case_attachments  (Vigilancia de campo · surveillance-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE case_attachments IS 'Referencias a evidencias fotograficas. El archivo vive en Cloud Storage, nunca en la base.';
COMMENT ON COLUMN case_attachments.id IS 'Identificador del adjunto. [llave primaria]';
COMMENT ON COLUMN case_attachments.case_id IS 'Caso al que pertenece la evidencia. Referencia a cases.id. [llave foranea]';
COMMENT ON COLUMN case_attachments.storage_path IS 'Ruta en el bucket: /evidence/{case_id}/archivo.';
COMMENT ON COLUMN case_attachments.mime_type IS 'Tipo de contenido validado en el servidor, no confiando en la extension.';
COMMENT ON COLUMN case_attachments.size_bytes IS 'Tamanio del archivo, para control de cuota.';
COMMENT ON COLUMN case_attachments.sha256 IS 'Huella del contenido. Detecta duplicados y corrupcion.';
COMMENT ON COLUMN case_attachments.privacy IS 'Nivel de privacidad. Los privados requieren URL firmada.';
COMMENT ON COLUMN case_attachments.uploaded_by IS 'Usuario que subio el archivo. Referencia a users.id. [llave foranea]';
COMMENT ON COLUMN case_attachments.uploaded_at IS 'Fecha de subida.';

-- ---------------------------------------------------------------------------
-- vaccine_lots  (Vigilancia de campo · surveillance-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE vaccine_lots IS 'Lotes de vacuna escaneados por QR desde la app movil.';
COMMENT ON COLUMN vaccine_lots.id IS 'Identificador del lote. [llave primaria]';
COMMENT ON COLUMN vaccine_lots.lot_code IS 'Codigo impreso en el lote, leido por QR o codigo de barras.';
COMMENT ON COLUMN vaccine_lots.manufacturer IS 'Fabricante.';
COMMENT ON COLUMN vaccine_lots.disease_id IS 'Enfermedad que previene. Referencia a diseases.id. [llave foranea]';
COMMENT ON COLUMN vaccine_lots.region_id IS 'Zona donde esta asignado el lote. Referencia a regions.id. [llave foranea]';
COMMENT ON COLUMN vaccine_lots.doses_total IS 'Dosis totales del lote.';
COMMENT ON COLUMN vaccine_lots.doses_used IS 'Dosis aplicadas. Nunca debe superar doses_total.';
COMMENT ON COLUMN vaccine_lots.expires_on IS 'Fecha de caducidad.';
COMMENT ON COLUMN vaccine_lots.scanned_by IS 'Usuario que registro el lote. Referencia a users.id. [llave foranea]';
COMMENT ON COLUMN vaccine_lots.scanned_at IS 'Momento del escaneo.';

-- ---------------------------------------------------------------------------
-- scenarios  (Escenarios · scenario-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE scenarios IS 'Escenario de politica publica. El contenido pesado vive en sus versiones.';
COMMENT ON COLUMN scenarios.id IS 'Identificador del escenario. [llave primaria]';
COMMENT ON COLUMN scenarios.name IS 'Nombre del escenario. Ejemplo: Cierre de escuelas semana 3.';
COMMENT ON COLUMN scenarios.description IS 'Pregunta de politica publica que busca responder.';
COMMENT ON COLUMN scenarios.disease_id IS 'Enfermedad simulada. Referencia a diseases.id. [llave foranea]';
COMMENT ON COLUMN scenarios.region_id IS 'Ambito geografico. Referencia a regions.id. [llave foranea]';
COMMENT ON COLUMN scenarios.owner_id IS 'Analista propietario. Referencia a users.id. [llave foranea]';
COMMENT ON COLUMN scenarios.status IS 'Estado: borrador, publicado o archivado.';
COMMENT ON COLUMN scenarios.is_public IS 'Si es visible en el sitio publico sin autenticacion.';
COMMENT ON COLUMN scenarios.created_at IS 'Fecha de creacion.';
COMMENT ON COLUMN scenarios.updated_at IS 'Ultima modificacion.';

-- ---------------------------------------------------------------------------
-- scenario_versions  (Escenarios · scenario-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE scenario_versions IS 'Versionado inmutable. Una corrida siempre apunta a una version, nunca al escenario.';
COMMENT ON COLUMN scenario_versions.id IS 'Identificador de la version. [llave primaria]';
COMMENT ON COLUMN scenario_versions.scenario_id IS 'Escenario al que pertenece. Unico junto con version_number. [llave foranea]';
COMMENT ON COLUMN scenario_versions.version_number IS 'Numero consecutivo dentro del escenario.';
COMMENT ON COLUMN scenario_versions.is_current IS 'Marca la version vigente. Solo una por escenario.';
COMMENT ON COLUMN scenario_versions.xml_path IS 'Ruta del XML exportado en el bucket: /scenarios/{id}/export.xml.';
COMMENT ON COLUMN scenario_versions.xml_checksum IS 'SHA-256 del XML. Garantiza que la corrida uso exactamente ese archivo.';
COMMENT ON COLUMN scenario_versions.population_size IS 'Numero de agentes de la poblacion sintetica.';
COMMENT ON COLUMN scenario_versions.horizon_days IS 'Dias simulados.';
COMMENT ON COLUMN scenario_versions.notes IS 'Que cambio respecto de la version anterior.';
COMMENT ON COLUMN scenario_versions.created_by IS 'Autor de la version. Referencia a users.id. [llave foranea]';
COMMENT ON COLUMN scenario_versions.created_at IS 'Fecha de congelamiento de la version.';

-- ---------------------------------------------------------------------------
-- scenario_interventions  (Escenarios · scenario-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE scenario_interventions IS 'Calendario de intervenciones de una version. Es el corazon del escenario.';
COMMENT ON COLUMN scenario_interventions.id IS 'Identificador de la intervencion programada. [llave primaria]';
COMMENT ON COLUMN scenario_interventions.scenario_version_id IS 'Version a la que pertenece. Referencia a scenario_versions.id. [llave foranea]';
COMMENT ON COLUMN scenario_interventions.intervention_type_id IS 'Tipo de intervencion. Referencia a intervention_types.id. [llave foranea]';
COMMENT ON COLUMN scenario_interventions.target_region_id IS 'Zona donde aplica. Nulo significa toda la region del escenario. [llave foranea]';
COMMENT ON COLUMN scenario_interventions.start_day IS 'Dia de simulacion en que se activa, contado desde el dia cero.';
COMMENT ON COLUMN scenario_interventions.end_day IS 'Dia en que se retira. Nulo significa hasta el fin del horizonte.';
COMMENT ON COLUMN scenario_interventions.coverage IS 'Fraccion de la poblacion objetivo alcanzada, de 0 a 1.';
COMMENT ON COLUMN scenario_interventions.compliance IS 'Nivel de cumplimiento esperado, de 0 a 1. Modula el efecto real.';
COMMENT ON COLUMN scenario_interventions.params IS 'Parametros propios del tipo: eficacia, criterio de prioridad, porcentaje de aforo.';
COMMENT ON COLUMN scenario_interventions.order_index IS 'Orden de aplicacion cuando dos intervenciones tocan la misma capa el mismo dia.';

-- ---------------------------------------------------------------------------
-- simulation_batches  (Simulacion · simulation-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE simulation_batches IS 'Lote de replicas de una misma version. Es la unidad que se compara en la frontera.';
COMMENT ON COLUMN simulation_batches.id IS 'Identificador del lote. [llave primaria]';
COMMENT ON COLUMN simulation_batches.scenario_version_id IS 'Version simulada. Referencia a scenario_versions.id. [llave foranea]';
COMMENT ON COLUMN simulation_batches.requested_by IS 'Usuario que lanzo el lote. Referencia a users.id. [llave foranea]';
COMMENT ON COLUMN simulation_batches.replicas IS 'Numero de corridas con semillas distintas. Entre 30 y 50.';
COMMENT ON COLUMN simulation_batches.engine IS 'Implementacion usada: numba o cuda.';
COMMENT ON COLUMN simulation_batches.status IS 'Estado agregado: encolado, ejecutando, completado, fallido o cancelado.';
COMMENT ON COLUMN simulation_batches.summary_doc_id IS 'Documento en MongoDB run_summaries con mediana y banda de incertidumbre.';
COMMENT ON COLUMN simulation_batches.created_at IS 'Fecha de encolado del lote.';
COMMENT ON COLUMN simulation_batches.finished_at IS 'Momento en que termino la ultima replica.';

-- ---------------------------------------------------------------------------
-- simulation_runs  (Simulacion · simulation-service)
-- ---------------------------------------------------------------------------
COMMENT ON TABLE simulation_runs IS 'Metadatos de una corrida individual. Los resultados voluminosos viven en MongoDB y GCS.';
COMMENT ON COLUMN simulation_runs.id IS 'Identificador de la corrida. Es el job_id devuelto al cliente. [llave primaria]';
COMMENT ON COLUMN simulation_runs.batch_id IS 'Lote al que pertenece. Nulo en corridas sueltas. Referencia a simulation_batches.id. [llave foranea]';
COMMENT ON COLUMN simulation_runs.scenario_version_id IS 'Version simulada. Se guarda tambien aqui para consultar sin unir el lote. [llave foranea]';
COMMENT ON COLUMN simulation_runs.seed IS 'Semilla del generador aleatorio. Hace la corrida reproducible.';
COMMENT ON COLUMN simulation_runs.replica_index IS 'Numero de replica dentro del lote.';
COMMENT ON COLUMN simulation_runs.status IS 'Ciclo de vida: encolado, ejecutando, completado, fallido o cancelado.';
COMMENT ON COLUMN simulation_runs.progress IS 'Porcentaje de avance. Se espeja en Redis durante la ejecucion.';
COMMENT ON COLUMN simulation_runs.engine_version IS 'Version del motor. Permite detectar resultados no comparables entre si.';
COMMENT ON COLUMN simulation_runs.queued_at IS 'Momento de entrada a la cola.';
COMMENT ON COLUMN simulation_runs.started_at IS 'Momento en que un worker tomo el trabajo.';
COMMENT ON COLUMN simulation_runs.finished_at IS 'Momento de termino, exitoso o no.';
COMMENT ON COLUMN simulation_runs.result_doc_id IS 'Documento en MongoDB run_results con las series diarias completas.';
COMMENT ON COLUMN simulation_runs.artifacts_path IS 'Ruta en el bucket con las salidas voluminosas: /runs/{run_id}/artifacts/.';
COMMENT ON COLUMN simulation_runs.error_message IS 'Causa de la falla cuando el estado es fallido.';

INSERT INTO schema_migrations (version, description)
VALUES ('008', 'Comentarios de tablas y columnas')
ON CONFLICT (version) DO NOTHING;

COMMIT;
-- =============================================================================
-- 009_roles_bd.sql
-- Roles de PostgreSQL por microservicio.
--
-- Los siete servicios comparten una sola instancia de PostgreSQL. Sin
-- separacion de privilegios, cualquier servicio puede escribir en cualquier
-- tabla y el limite de responsabilidad queda solo en la disciplina del equipo.
-- Aqui se hace obligatorio: cada servicio lee casi todo, pero escribe
-- unicamente en las tablas de su dominio.
--
-- IMPORTANTE
-- Las contrasenas de abajo son marcadores para desarrollo local. En Google
-- Compute Engine se generan aparte y se inyectan desde Secret Manager como
-- variables de entorno. Nunca deben quedar en el repositorio.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- Creacion de roles (idempotente)
-- -----------------------------------------------------------------------------
DO $$
DECLARE
    r TEXT;
BEGIN
    FOREACH r IN ARRAY ARRAY[
        'app_auth', 'app_catalog', 'app_scenario', 'app_simulation',
        'app_surveillance', 'app_analytics', 'app_monitoring', 'app_web'
    ]
    LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L', r, 'cambiar_en_despliegue');
        END IF;
    END LOOP;
END;
$$;

-- -----------------------------------------------------------------------------
-- Lectura general
-- -----------------------------------------------------------------------------
-- Todos pueden leer todo: los servicios necesitan resolver catalogos y validar
-- referencias. La separacion real esta en la escritura.
GRANT USAGE ON SCHEMA public TO
    app_auth, app_catalog, app_scenario, app_simulation,
    app_surveillance, app_analytics, app_monitoring, app_web;

GRANT SELECT ON ALL TABLES IN SCHEMA public TO
    app_auth, app_catalog, app_scenario, app_simulation,
    app_surveillance, app_analytics, app_monitoring, app_web;

-- -----------------------------------------------------------------------------
-- Escritura por dominio
-- -----------------------------------------------------------------------------
GRANT INSERT, UPDATE, DELETE ON
    users, roles, permissions, user_roles, role_permissions,
    password_resets, devices
    TO app_auth;

GRANT INSERT, UPDATE, DELETE ON
    diseases, regions, intervention_types
    TO app_catalog;

GRANT INSERT, UPDATE, DELETE ON
    scenarios, scenario_versions, scenario_interventions
    TO app_scenario;

GRANT INSERT, UPDATE, DELETE ON
    simulation_batches, simulation_runs
    TO app_simulation;

GRANT INSERT, UPDATE, DELETE ON
    cases, case_attachments, vaccine_lots
    TO app_surveillance;

GRANT INSERT, UPDATE, DELETE ON
    notifications, system_settings
    TO app_web;

-- analytics y monitoring son de solo lectura sobre PostgreSQL: sus escrituras
-- van a MongoDB. No reciben ningun permiso de escritura aqui.

-- -----------------------------------------------------------------------------
-- Bitacora: todos escriben, nadie modifica
-- -----------------------------------------------------------------------------
GRANT INSERT ON audit_log TO
    app_auth, app_catalog, app_scenario, app_simulation,
    app_surveillance, app_analytics, app_monitoring, app_web;

-- Notificaciones: varios servicios avisan al usuario, pero solo el sistema web
-- las marca como leidas.
GRANT INSERT ON notifications TO app_simulation, app_surveillance, app_analytics;

-- -----------------------------------------------------------------------------
-- Secuencias
-- -----------------------------------------------------------------------------
-- Sin USAGE sobre la secuencia, un INSERT en una tabla con BIGSERIAL falla.
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO
    app_auth, app_catalog, app_scenario, app_simulation,
    app_surveillance, app_analytics, app_monitoring, app_web;

-- -----------------------------------------------------------------------------
-- Tablas futuras
-- -----------------------------------------------------------------------------
-- Para que una migracion posterior no deje a los servicios sin acceso.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES TO
        app_auth, app_catalog, app_scenario, app_simulation,
        app_surveillance, app_analytics, app_monitoring, app_web;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO
        app_auth, app_catalog, app_scenario, app_simulation,
        app_surveillance, app_analytics, app_monitoring, app_web;

INSERT INTO schema_migrations (version, description)
VALUES ('009', 'Roles de base de datos por microservicio')
ON CONFLICT (version) DO NOTHING;

COMMIT;
-- =============================================================================
-- 010_datos_iniciales.sql
-- Carga inicial: roles, permisos, matriz de permisos y catalogos base.
--
-- Es el requisito de "carga inicial de datos" y "datos de prueba" del primer
-- parcial. Todo aqui es idempotente: se puede volver a correr sin duplicar.
--
-- Este archivo NO incluye casos ni escenarios de ejemplo. Esos van en un
-- archivo aparte de datos de demostracion, para poder cargar la base limpia
-- en produccion sin arrastrar datos ficticios.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- Roles
-- -----------------------------------------------------------------------------
INSERT INTO roles (code, name, description, is_system) VALUES
    ('ADMINISTRADOR', 'Administrador',
     'Administra usuarios, roles, catalogos y configuracion del sistema.', TRUE),
    ('EPIDEMIOLOGO', 'Epidemiologo',
     'Define parametros de enfermedad, valida casos de campo y publica escenarios.', TRUE),
    ('ANALISTA', 'Analista',
     'Construye escenarios, lanza corridas y compara resultados en la frontera.', TRUE),
    ('CAPTURISTA', 'Capturista de campo',
     'Registra casos y evidencias desde la aplicacion movil.', TRUE)
ON CONFLICT (code) DO NOTHING;

-- -----------------------------------------------------------------------------
-- Permisos
-- -----------------------------------------------------------------------------
INSERT INTO permissions (code, resource, action, description) VALUES
    ('users.read',          'users',       'read',    'Consultar usuarios.'),
    ('users.create',        'users',       'create',  'Dar de alta usuarios.'),
    ('users.update',        'users',       'update',  'Editar usuarios y asignar roles.'),
    ('users.delete',        'users',       'delete',  'Dar de baja usuarios.'),
    ('catalogs.read',       'catalogs',    'read',    'Consultar catalogos.'),
    ('catalogs.create',     'catalogs',    'create',  'Agregar entradas de catalogo.'),
    ('catalogs.update',     'catalogs',    'update',  'Editar entradas de catalogo.'),
    ('scenarios.read',      'scenarios',   'read',    'Consultar escenarios.'),
    ('scenarios.create',    'scenarios',   'create',  'Crear escenarios y versiones.'),
    ('scenarios.update',    'scenarios',   'update',  'Editar escenarios propios.'),
    ('scenarios.delete',    'scenarios',   'delete',  'Eliminar escenarios propios.'),
    ('scenarios.publish',   'scenarios',   'publish', 'Publicar un escenario al sitio publico.'),
    ('scenarios.export',    'scenarios',   'export',  'Exportar el XML de un escenario.'),
    ('simulations.read',    'simulations', 'read',    'Consultar estado y resultados de corridas.'),
    ('simulations.run',     'simulations', 'run',     'Encolar corridas y lotes.'),
    ('simulations.delete',  'simulations', 'delete',  'Cancelar o eliminar corridas.'),
    ('cases.read',          'cases',       'read',    'Consultar casos de campo.'),
    ('cases.create',        'cases',       'create',  'Registrar casos desde la app movil.'),
    ('cases.update',        'cases',       'update',  'Corregir casos capturados.'),
    ('cases.approve',       'cases',       'approve', 'Validar o descartar casos capturados.'),
    ('reports.read',        'reports',     'read',    'Consultar reportes y tableros.'),
    ('reports.export',      'reports',     'export',  'Descargar reportes.'),
    ('audit.read',          'audit',       'read',    'Consultar la bitacora de auditoria.'),
    ('settings.read',       'settings',    'read',    'Consultar la configuracion del sistema.'),
    ('settings.update',     'settings',    'update',  'Modificar la configuracion del sistema.')
ON CONFLICT (code) DO NOTHING;

-- -----------------------------------------------------------------------------
-- Matriz de permisos
-- -----------------------------------------------------------------------------
-- Administrador: todo.
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r CROSS JOIN permissions p
WHERE r.code = 'ADMINISTRADOR'
ON CONFLICT DO NOTHING;

-- Epidemiologo: catalogos, validacion de casos y publicacion de escenarios.
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r JOIN permissions p ON p.code IN (
    'catalogs.read', 'catalogs.create', 'catalogs.update',
    'scenarios.read', 'scenarios.publish', 'scenarios.export',
    'simulations.read',
    'cases.read', 'cases.update', 'cases.approve',
    'reports.read', 'reports.export',
    'audit.read', 'settings.read'
)
WHERE r.code = 'EPIDEMIOLOGO'
ON CONFLICT DO NOTHING;

-- Analista: construye y corre escenarios, pero no publica ni toca catalogos.
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r JOIN permissions p ON p.code IN (
    'catalogs.read',
    'scenarios.read', 'scenarios.create', 'scenarios.update',
    'scenarios.delete', 'scenarios.export',
    'simulations.read', 'simulations.run', 'simulations.delete',
    'cases.read',
    'reports.read', 'reports.export'
)
WHERE r.code = 'ANALISTA'
ON CONFLICT DO NOTHING;

-- Capturista: solo captura de campo. No ve escenarios ni auditoria.
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r JOIN permissions p ON p.code IN (
    'catalogs.read', 'cases.read', 'cases.create', 'cases.update'
)
WHERE r.code = 'CAPTURISTA'
ON CONFLICT DO NOTHING;

-- -----------------------------------------------------------------------------
-- Enfermedades
-- -----------------------------------------------------------------------------
-- Los parametros son valores iniciales de literatura, NO calibrados. La
-- calibracion contra la ola historica los sustituye; hasta entonces sirven
-- solo para que el motor arranque.
INSERT INTO diseases (code, name, description, default_params) VALUES
    ('SARS_COV_2_ANCESTRAL', 'SARS-CoV-2 (linaje ancestral)',
     'Parametros iniciales de literatura para la primera ola. Pendiente de calibracion.',
     '{"incubacion_dias": {"dist": "lognormal", "media": 5.1, "desv": 1.5},
       "infeccioso_dias": {"dist": "lognormal", "media": 8.0, "desv": 2.0},
       "prob_asintomatico": 0.35,
       "transmisibilidad_base": 0.045,
       "letalidad_por_edad": {"0-19": 0.00002, "20-39": 0.0002,
                              "40-59": 0.003, "60-79": 0.03, "80+": 0.10}}'::jsonb),
    ('INFLUENZA_ESTACIONAL', 'Influenza estacional A(H1N1)',
     'Perfil de referencia para contrastar con un patogeno de menor letalidad.',
     '{"incubacion_dias": {"dist": "lognormal", "media": 2.0, "desv": 0.8},
       "infeccioso_dias": {"dist": "lognormal", "media": 5.0, "desv": 1.5},
       "prob_asintomatico": 0.30,
       "transmisibilidad_base": 0.030,
       "letalidad_por_edad": {"0-19": 0.00001, "20-39": 0.00005,
                              "40-59": 0.0003, "60-79": 0.002, "80+": 0.008}}'::jsonb),
    ('PATOGENO_X', 'Patogeno hipotetico X',
     'Escenario de preparacion: patogeno nuevo con parametros definidos por el usuario.',
     '{}'::jsonb)
ON CONFLICT (code) DO NOTHING;

-- -----------------------------------------------------------------------------
-- Regiones
-- -----------------------------------------------------------------------------
-- Estado y los municipios del area metropolitana de Monterrey, con claves
-- INEGI. Las AGEB se cargan aparte desde el marco geoestadistico, porque son
-- miles y no tiene sentido escribirlas a mano.
INSERT INTO regions (code, name, level, parent_region_id, population, centroid_lat, centroid_lon)
VALUES ('19', 'Nuevo Leon', 'estado', NULL, 5784442, 25.592200, -99.996100)
ON CONFLICT (code) DO NOTHING;

INSERT INTO regions (code, name, level, parent_region_id, population, centroid_lat, centroid_lon)
SELECT v.code, v.name, 'municipio', e.id, v.pob, v.lat, v.lon
FROM (VALUES
    ('19039', 'Monterrey',          1142994, 25.686600, -100.316100),
    ('19019', 'San Pedro Garza Garcia', 132169, 25.657900, -100.402200),
    ('19026', 'Guadalupe',           643143, 25.676800, -100.259700),
    ('19006', 'Apodaca',             656464, 25.781900, -100.188600),
    ('19021', 'General Escobedo',    481157, 25.795400, -100.318100),
    ('19046', 'San Nicolas de los Garza', 412199, 25.741700, -100.302800),
    ('19048', 'Santa Catarina',      306322, 25.673100, -100.458300),
    ('19031', 'Juarez',              466465, 25.646600, -100.096100),
    ('19018', 'Garcia',              412199, 25.813300, -100.585600),
    ('19049', 'Santiago',             45988, 25.424700, -100.147200)
) AS v(code, name, pob, lat, lon)
CROSS JOIN (SELECT id FROM regions WHERE code = '19') e
ON CONFLICT (code) DO NOTHING;

-- -----------------------------------------------------------------------------
-- Tipos de intervencion
-- -----------------------------------------------------------------------------
INSERT INTO intervention_types (code, name, target_layer, primitive, description, param_schema) VALUES
    ('CIERRE_ESCUELAS', 'Cierre de escuelas', 'escuela', 'edge_modifier',
     'Desactiva la capa escuela a partir del dia indicado.',
     '{"type": "object", "properties": {
         "reduccion": {"type": "number", "minimum": 0, "maximum": 1, "default": 1.0}}}'::jsonb),

    ('REDUCCION_AFORO', 'Reduccion de aforo', 'comunidad', 'edge_modifier',
     'Reduce el numero de contactos de la capa comunidad en el porcentaje indicado.',
     '{"type": "object", "required": ["reduccion"], "properties": {
         "reduccion": {"type": "number", "minimum": 0, "maximum": 1}}}'::jsonb),

    ('CUBREBOCAS', 'Uso de cubrebocas', 'todas', 'edge_modifier',
     'Reduce la probabilidad de transmision en todas las capas de contacto.',
     '{"type": "object", "required": ["eficacia"], "properties": {
         "eficacia": {"type": "number", "minimum": 0, "maximum": 1}}}'::jsonb),

    ('CIERRE_TRABAJO', 'Cierre de centros de trabajo', 'trabajo', 'edge_modifier',
     'Desactiva o atenua la capa trabajo para los sectores indicados.',
     '{"type": "object", "properties": {
         "reduccion": {"type": "number", "minimum": 0, "maximum": 1, "default": 1.0},
         "sectores": {"type": "array", "items": {"type": "string"}}}}'::jsonb),

    ('VACUNACION', 'Campania de vacunacion', 'todas', 'node_attr',
     'Reduce la susceptibilidad de los agentes seleccionados, con eficacia parcial y criterio de prioridad.',
     '{"type": "object", "required": ["eficacia", "dosis_diarias"], "properties": {
         "eficacia": {"type": "number", "minimum": 0, "maximum": 1},
         "dosis_diarias": {"type": "integer", "minimum": 1},
         "prioridad": {"type": "string", "enum": ["edad_desc", "zona", "ocupacion", "aleatorio"]},
         "edad_minima": {"type": "integer", "minimum": 0, "maximum": 120}}}'::jsonb),

    ('TESTEO_AISLAMIENTO', 'Testeo y aislamiento', 'todas', 'node_attr',
     'Detecta una fraccion de los infecciosos y corta sus contactos fuera del hogar.',
     '{"type": "object", "required": ["deteccion", "retraso_dias"], "properties": {
         "deteccion": {"type": "number", "minimum": 0, "maximum": 1},
         "retraso_dias": {"type": "integer", "minimum": 0},
         "dias_aislamiento": {"type": "integer", "minimum": 1, "default": 10}}}'::jsonb)
ON CONFLICT (code) DO NOTHING;

-- -----------------------------------------------------------------------------
-- Configuracion del sistema
-- -----------------------------------------------------------------------------
INSERT INTO system_settings (key, value, description) VALUES
    ('replicas_por_defecto', '30'::jsonb,
     'Replicas de un lote cuando el cliente no especifica. Minimo estadistico aceptable.'),
    ('max_replicas_por_lote', '200'::jsonb,
     'Tope de replicas por lote, para no saturar la cola.'),
    ('umbral_saturacion_hospitalaria', '0.85'::jsonb,
     'Ocupacion a partir de la cual se emite notificacion de umbral rebasado.'),
    ('dias_retencion_evidencias', '1825'::jsonb,
     'Dias que se conservan las evidencias fotograficas en Cloud Storage.'),
    ('motor_por_defecto', '"numba"'::jsonb,
     'Implementacion usada cuando no hay VM con GPU encendida.')
ON CONFLICT (key) DO NOTHING;

-- -----------------------------------------------------------------------------
-- Usuario administrador inicial
-- -----------------------------------------------------------------------------
-- El hash es un marcador. Generar el real antes de levantar la base con:
--   python -c "import bcrypt;print(bcrypt.hashpw(b'TU_PASS',bcrypt.gensalt(12)).decode())"
-- y sustituirlo aqui, o crear la cuenta desde un comando de administracion.
-- Una cuenta con hash invalido no puede autenticarse: es intencional, para que
-- nadie olvide cambiarla.
INSERT INTO users (username, email, password_hash, full_name, is_active)
VALUES ('admin', 'admin@ejemplo.local',
        'REEMPLAZAR_ANTES_DE_DESPLEGAR', 'Administrador del sistema', TRUE)
ON CONFLICT (username) DO NOTHING;

INSERT INTO user_roles (user_id, role_id)
SELECT u.id, r.id
FROM users u CROSS JOIN roles r
WHERE u.username = 'admin' AND r.code = 'ADMINISTRADOR'
ON CONFLICT DO NOTHING;

INSERT INTO schema_migrations (version, description)
VALUES ('010', 'Carga inicial: roles, permisos, catalogos y configuracion')
ON CONFLICT (version) DO NOTHING;

COMMIT;
-- =============================================================================
-- 011_fix_audit_log_delete.sql
-- Dominio: sistema.  Corrige una contradiccion entre 001_base.sql y 003_sistema.sql.
--
-- PROBLEMA
-- 003_sistema.sql declara audit_log.user_id como:
--     FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL
-- es decir: la intencion original es que la bitacora SOBREVIVA al borrado de
-- un usuario, quedando el evento sin dueno.
--
-- Pero la misma migracion le pone a audit_log el trigger tg_audit_log_inmutable
-- (fn_solo_insercion, de 001_base.sql), que rechaza CUALQUIER update.
--
-- Las dos reglas se contradicen: al borrar un usuario, Postgres ejecuta el
-- SET NULL, el trigger lo rechaza y el DELETE completo revienta con
-- "restrict_violation". Resultado: ningun usuario que haya generado un solo
-- evento (basta con iniciar sesion una vez) se puede eliminar.
--
-- QUE HACE
-- Afina fn_solo_insercion para que permita EXACTAMENTE un caso: que la llave
-- foranea ponga user_id en NULL sin tocar ningun otro campo del renglon.
-- Todo lo demas se sigue rechazando igual que antes:
--     - cualquier DELETE sobre la bitacora
--     - cualquier UPDATE que cambie accion, entidad, fechas, IP, payloads...
--     - pasar user_id de un usuario a otro
-- Se cumple la intencion original de las DOS reglas sin debilitar la
-- inmutabilidad del contenido.
--
-- La funcion sigue siendo generica (no menciona columnas por nombre), asi que
-- puede usarse en otras tablas de solo insercion mas adelante.
--
-- ALCANCE: reemplaza una funcion. No altera tablas, columnas ni datos. Es
-- idempotente y no requiere recrear el trigger (tg_audit_log_inmutable apunta
-- a la funcion por nombre, y aqui se usa CREATE OR REPLACE).
-- =============================================================================

BEGIN;

CREATE OR REPLACE FUNCTION fn_solo_insercion()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    j_old JSONB;
    j_new JSONB;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        j_old := to_jsonb(OLD);
        j_new := to_jsonb(NEW);

        -- Unica excepcion permitida: la FK ON DELETE SET NULL desasociando el
        -- renglon de un usuario que se esta borrando. Se exige que user_id
        -- pase de un valor a NULL y que TODO lo demas quede identico.
        IF  j_old ? 'user_id'
        AND j_old->>'user_id' IS NOT NULL
        AND j_new->>'user_id' IS NULL
        AND (j_new - 'user_id') = (j_old - 'user_id')
        THEN
            RETURN NEW;
        END IF;
    END IF;

    RAISE EXCEPTION 'La tabla % es de solo insercion: no admite % ',
        TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$;

COMMENT ON FUNCTION fn_solo_insercion() IS
    'Trigger BEFORE UPDATE OR DELETE: bloquea toda modificacion de la fila. '
    'Unica excepcion: permite que una FK ON DELETE SET NULL ponga user_id en '
    'NULL sin alterar ningun otro campo (ver 011_fix_audit_log_delete.sql).';

INSERT INTO schema_migrations (version, description)
VALUES ('011', 'Bitacora: permite el SET NULL de user_id al borrar un usuario')
ON CONFLICT (version) DO NOTHING;

COMMIT;
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
-- =============================================================================
-- 013_escenarios_aprobacion.sql
-- Dominio: escenarios.  Servicio propietario: scenario-service.
--
-- Agrega a scenario_versions lo que le falta para el flujo que pide el
-- planteamiento del proyecto:
--
--     ANALISTA crea  ->  BORRADOR  ->  EN REVISION  ->  EPIDEMIOLOGO
--                                                        /        \
--                                                    APROBADO   RECHAZADO
--
-- Decision de diseno: el flujo de revision vive en la VERSION, no en el
-- escenario. scenarios.status ('borrador'/'publicado'/'archivado') se queda
-- como esta: describe el ciclo de publicacion del escenario completo. Lo que
-- se revisa y se aprueba es una version concreta e inmutable, que es tambien
-- lo unico que se puede simular de forma reproducible. Consecuencia buscada:
-- al crear la version siguiente de un escenario aprobado, esa version nueva
-- nace en 'borrador' y hay que volver a aprobarla.
--
-- Tambien agrega initial_infected, que el motor necesita y no existia en 006.
--
-- Es idempotente: columnas con IF NOT EXISTS y restricciones con
-- DROP CONSTRAINT IF EXISTS antes del ADD.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- Columnas nuevas
-- -----------------------------------------------------------------------------
ALTER TABLE scenario_versions
    ADD COLUMN IF NOT EXISTS initial_infected INTEGER     NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS status           VARCHAR(20) NOT NULL DEFAULT 'borrador',
    ADD COLUMN IF NOT EXISTS submitted_at     TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS reviewed_by      BIGINT,
    ADD COLUMN IF NOT EXISTS reviewed_at      TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS review_comment   TEXT;

-- -----------------------------------------------------------------------------
-- Reglas de negocio
-- -----------------------------------------------------------------------------
ALTER TABLE scenario_versions
    DROP CONSTRAINT IF EXISTS fk_scenario_versions_reviewer,
    ADD  CONSTRAINT fk_scenario_versions_reviewer
        FOREIGN KEY (reviewed_by) REFERENCES users (id) ON DELETE RESTRICT,

    DROP CONSTRAINT IF EXISTS ck_scenario_versions_status,
    ADD  CONSTRAINT ck_scenario_versions_status CHECK (status IN
        ('borrador', 'en_revision', 'aprobado', 'rechazado')),

    -- No se puede arrancar una epidemia con cero infectados, ni con mas
    -- infectados que habitantes.
    DROP CONSTRAINT IF EXISTS ck_scenario_versions_iniciales,
    ADD  CONSTRAINT ck_scenario_versions_iniciales
        CHECK (initial_infected BETWEEN 1 AND population_size),

    -- Un estado distinto de borrador implica que alguien la envio a revision.
    DROP CONSTRAINT IF EXISTS ck_scenario_versions_envio,
    ADD  CONSTRAINT ck_scenario_versions_envio
        CHECK (status = 'borrador' OR submitted_at IS NOT NULL),

    -- Coherencia del dictamen: una version resuelta sabe quien la resolvio y
    -- cuando; una que sigue en tramite no trae dictamen. Rechazar exige
    -- motivo, para que el analista sepa que corregir.
    DROP CONSTRAINT IF EXISTS ck_scenario_versions_revision,
    ADD  CONSTRAINT ck_scenario_versions_revision CHECK (
        CASE status
            WHEN 'borrador'    THEN reviewed_by IS NULL     AND reviewed_at IS NULL
            WHEN 'en_revision' THEN reviewed_by IS NULL     AND reviewed_at IS NULL
            WHEN 'aprobado'    THEN reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL
            WHEN 'rechazado'   THEN reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL
                                    AND review_comment IS NOT NULL
        END
    ),

    -- Separacion de responsabilidades: quien construye el escenario no es
    -- quien lo autoriza. La aplicacion ademas exige el rol EPIDEMIOLOGO, pero
    -- esta regla vive en la base para que ninguna via (script, psql, un
    -- servicio futuro) pueda saltarsela.
    DROP CONSTRAINT IF EXISTS ck_scenario_versions_no_autoaprobacion,
    ADD  CONSTRAINT ck_scenario_versions_no_autoaprobacion
        CHECK (reviewed_by IS NULL OR reviewed_by <> created_by);

-- Bandeja del epidemiologo: las versiones que esperan dictamen.
CREATE INDEX IF NOT EXISTS ix_scenario_versions_pendientes
    ON scenario_versions (submitted_at) WHERE status = 'en_revision';

CREATE INDEX IF NOT EXISTS ix_scenario_versions_revisor
    ON scenario_versions (reviewed_by);

-- -----------------------------------------------------------------------------
-- Documentacion embebida (mismo criterio que 008_comentarios.sql)
-- -----------------------------------------------------------------------------
COMMENT ON COLUMN scenario_versions.initial_infected IS
    'Infectados al dia 0 de la simulacion. Entre 1 y la poblacion de la version.';
COMMENT ON COLUMN scenario_versions.status IS
    'Flujo de revision de ESTA version: borrador -> en_revision -> aprobado | rechazado. Solo una version aprobada se puede simular.';
COMMENT ON COLUMN scenario_versions.submitted_at IS
    'Cuando el analista la envio a revision.';
COMMENT ON COLUMN scenario_versions.reviewed_by IS
    'Epidemiologo que aprobo o rechazo. Nunca puede ser el mismo que created_by.';
COMMENT ON COLUMN scenario_versions.reviewed_at IS
    'Fecha del dictamen.';
COMMENT ON COLUMN scenario_versions.review_comment IS
    'Motivo del dictamen. Obligatorio cuando se rechaza.';

INSERT INTO schema_migrations (version, description)
VALUES ('013', 'Escenarios: flujo de aprobacion por version e infectados iniciales')
ON CONFLICT (version) DO NOTHING;

COMMIT;
-- =============================================================================
-- 014_simulacion_resultados.sql
-- Dominio: simulacion.  Servicio propietario: simulation-service.
--
-- 007_simulacion.sql modelo la simulacion pensando en el motor definitivo
-- (numba/cuda, lotes de 30+ replicas) y en guardar las series en MongoDB.
-- Para el monolito de este avance eso no aplica todavia:
--
--   (1) el motor es python-ref (motor/, ENGINE_VERSION = 'python-ref-0.1'),
--   (2) se ejecuta una corrida a la vez, no lotes de replicas,
--   (3) NO hay MongoDB: los resultados se guardan aqui, en PostgreSQL.
--
-- Esta migracion ajusta esos tres puntos, agrega el usuario que pidio cada
-- corrida y lleva a la base la regla "solo se simula una version aprobada".
--
-- Tambien agrega a intervention_types el costo unitario que necesita la
-- frontera de Pareto (motor/pareto.py). Se agregan las columnas y la unidad
-- de cada tipo, pero NO un costo: inventar cifras economicas es justo lo que
-- el proyecto no debe hacer. Los captura el equipo con su fuente.
--
-- Es idempotente.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- simulation_batches: admitir el motor de referencia y corridas sueltas
-- -----------------------------------------------------------------------------
-- El limite de 30 replicas nacio de un motor estocastico donde una sola
-- corrida no significa nada. Sigue siendo cierto para el motor definitivo,
-- pero python-ref es reproducible por semilla y en esta etapa se ejecuta una
-- corrida por escenario, asi que el piso baja a 1.
ALTER TABLE simulation_batches
    DROP CONSTRAINT IF EXISTS ck_simulation_batches_engine,
    ADD  CONSTRAINT ck_simulation_batches_engine
        CHECK (engine IN ('python-ref', 'numba', 'cuda')),

    DROP CONSTRAINT IF EXISTS ck_simulation_batches_replicas,
    ADD  CONSTRAINT ck_simulation_batches_replicas
        CHECK (replicas BETWEEN 1 AND 200);

ALTER TABLE simulation_batches ALTER COLUMN engine SET DEFAULT 'python-ref';

-- -----------------------------------------------------------------------------
-- simulation_runs: quien pidio la corrida
-- -----------------------------------------------------------------------------
-- Hasta ahora el usuario solo vivia en el lote. Una corrida suelta no tenia
-- dueno, y la reproducibilidad exige saber quien la lanzo.
ALTER TABLE simulation_runs
    ADD COLUMN IF NOT EXISTS requested_by BIGINT;

UPDATE simulation_runs r
SET    requested_by = b.requested_by
FROM   simulation_batches b
WHERE  b.id = r.batch_id AND r.requested_by IS NULL;

DO $$
DECLARE
    huerfanas INTEGER;
BEGIN
    SELECT count(*) INTO huerfanas FROM simulation_runs WHERE requested_by IS NULL;
    IF huerfanas = 0 THEN
        ALTER TABLE simulation_runs ALTER COLUMN requested_by SET NOT NULL;
    ELSE
        -- No se tumba la migracion por datos viejos: se avisa y se deja
        -- opcional hasta que alguien les asigne dueno.
        RAISE NOTICE '014: % corridas sin usuario. requested_by queda opcional; '
                     'asignalas y luego corre: ALTER TABLE simulation_runs '
                     'ALTER COLUMN requested_by SET NOT NULL;', huerfanas;
    END IF;
END
$$;

ALTER TABLE simulation_runs
    DROP CONSTRAINT IF EXISTS fk_simulation_runs_user,
    ADD  CONSTRAINT fk_simulation_runs_user
        FOREIGN KEY (requested_by) REFERENCES users (id) ON DELETE RESTRICT;

CREATE INDEX IF NOT EXISTS ix_simulation_runs_user
    ON simulation_runs (requested_by, queued_at DESC);

-- -----------------------------------------------------------------------------
-- Regla: solo se simula una version APROBADA
-- -----------------------------------------------------------------------------
-- El planteamiento del proyecto separa quien construye el escenario de quien
-- lo autoriza. Si la regla vive solo en Flask, cualquier script que inserte
-- directo en simulation_runs se la salta. Aqui no.
CREATE OR REPLACE FUNCTION fn_version_aprobada()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_status VARCHAR(20);
BEGIN
    SELECT status INTO v_status
    FROM scenario_versions
    WHERE id = NEW.scenario_version_id;

    IF v_status IS DISTINCT FROM 'aprobado' THEN
        RAISE EXCEPTION
            'La version de escenario % no esta aprobada (estado: %); no se puede simular.',
            NEW.scenario_version_id, COALESCE(v_status, 'inexistente')
            USING ERRCODE = 'restrict_violation';
    END IF;

    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION fn_version_aprobada() IS
    'Trigger BEFORE INSERT: rechaza corridas y lotes sobre versiones de escenario que no esten aprobadas.';

DROP TRIGGER IF EXISTS tg_simulation_runs_version_aprobada ON simulation_runs;
CREATE TRIGGER tg_simulation_runs_version_aprobada
    BEFORE INSERT ON simulation_runs
    FOR EACH ROW EXECUTE FUNCTION fn_version_aprobada();

DROP TRIGGER IF EXISTS tg_simulation_batches_version_aprobada ON simulation_batches;
CREATE TRIGGER tg_simulation_batches_version_aprobada
    BEFORE INSERT ON simulation_batches
    FOR EACH ROW EXECUTE FUNCTION fn_version_aprobada();

-- -----------------------------------------------------------------------------
-- simulation_results: los resultados que iban a MongoDB
-- -----------------------------------------------------------------------------
-- Una fila por corrida. resumen y serie son exactamente lo que devuelve
-- motor.simular(): el resumen de indicadores y la serie diaria completa.
-- Las columnas generadas sacan del JSON los indicadores que la pantalla de
-- comparacion necesita ordenar y graficar, sin tener que abrir el documento.
CREATE TABLE IF NOT EXISTS simulation_results (
    run_id            BIGINT      PRIMARY KEY,
    engine_version    VARCHAR(30) NOT NULL,
    scenario_checksum CHAR(64),
    resumen           JSONB       NOT NULL,
    serie             JSONB       NOT NULL,
    trazabilidad      JSONB       NOT NULL DEFAULT '[]'::jsonb,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    casos_acumulados   INTEGER      GENERATED ALWAYS AS ((resumen->>'casos_acumulados')::integer)   STORED,
    hospitalizaciones  INTEGER      GENERATED ALWAYS AS ((resumen->>'hospitalizaciones')::integer)  STORED,
    fallecimientos     INTEGER      GENERATED ALWAYS AS ((resumen->>'fallecimientos')::integer)     STORED,
    pico_casos_activos INTEGER      GENERATED ALWAYS AS ((resumen->>'pico_casos_activos')::integer) STORED,
    dia_pico           SMALLINT     GENERATED ALWAYS AS ((resumen->>'dia_pico')::smallint)          STORED,
    tasa_ataque        NUMERIC(8,6) GENERATED ALWAYS AS ((resumen->>'tasa_ataque')::numeric)        STORED,

    CONSTRAINT fk_simulation_results_run
        FOREIGN KEY (run_id) REFERENCES simulation_runs (id) ON DELETE CASCADE,
    CONSTRAINT ck_simulation_results_resumen CHECK (jsonb_typeof(resumen) = 'object'),
    CONSTRAINT ck_simulation_results_serie   CHECK (jsonb_typeof(serie)   = 'array'),
    CONSTRAINT ck_simulation_results_traza   CHECK (jsonb_typeof(trazabilidad) = 'array'),
    -- La huella del escenario permite demostrar que dos corridas simularon
    -- exactamente la misma entrada (motor.huella_escenario()).
    CONSTRAINT ck_simulation_results_checksum
        CHECK (scenario_checksum IS NULL OR scenario_checksum ~ '^[0-9a-f]{64}$')
);

COMMENT ON TABLE simulation_results IS
    'Resultado de una corrida: indicadores resumen y serie diaria. Sustituye al documento de MongoDB mientras el sistema sea monolitico.';
COMMENT ON COLUMN simulation_results.resumen IS
    'Objeto con casos_acumulados, pico, dia_pico, hospitalizaciones, fallecimientos, tasa_ataque y desglose por grupo de edad.';
COMMENT ON COLUMN simulation_results.serie IS
    'Arreglo con un objeto por dia: S, E, I, R, H, D, V, casos activos y nuevos casos.';
COMMENT ON COLUMN simulation_results.trazabilidad IS
    'Parametros usados, con su fuente o su marca de supuesto, tal como los reporto el motor.';
COMMENT ON COLUMN simulation_results.scenario_checksum IS
    'SHA-256 de la entrada canonica del motor. Misma huella + misma semilla + mismo engine_version => mismo resultado.';

-- -----------------------------------------------------------------------------
-- intervention_types: costo unitario para la frontera de Pareto
-- -----------------------------------------------------------------------------
ALTER TABLE intervention_types
    ADD COLUMN IF NOT EXISTS unit_cost          NUMERIC(12,2),
    ADD COLUMN IF NOT EXISTS cost_unit          VARCHAR(30),
    ADD COLUMN IF NOT EXISTS cost_source        TEXT,
    ADD COLUMN IF NOT EXISTS cost_is_assumption BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE intervention_types
    DROP CONSTRAINT IF EXISTS ck_intervention_types_cost_unit,
    ADD  CONSTRAINT ck_intervention_types_cost_unit
        CHECK (cost_unit IS NULL OR cost_unit IN ('por_habitante_dia', 'por_dosis')),

    -- Misma regla que para los parametros de enfermedad: un costo se guarda
    -- con su fuente, o marcado explicitamente como supuesto. Nunca "a secas".
    DROP CONSTRAINT IF EXISTS ck_intervention_types_cost,
    ADD  CONSTRAINT ck_intervention_types_cost CHECK (
        unit_cost IS NULL
        OR (unit_cost >= 0
            AND cost_unit IS NOT NULL
            AND (cost_is_assumption OR cost_source IS NOT NULL))
    );

-- La unidad si se puede declarar sin inventar nada: se desprende de como
-- actua cada intervencion. El importe queda en NULL a proposito.
UPDATE intervention_types SET cost_unit = 'por_dosis'
WHERE  code = 'VACUNACION' AND cost_unit IS NULL;

UPDATE intervention_types SET cost_unit = 'por_habitante_dia'
WHERE  code <> 'VACUNACION' AND cost_unit IS NULL;

COMMENT ON COLUMN intervention_types.unit_cost IS
    'Costo unitario de aplicar la intervencion. NULL = sin capturar: la comparacion de costos no se puede calcular hasta que se defina.';
COMMENT ON COLUMN intervention_types.cost_unit IS
    'Unidad del costo: por_habitante_dia (intervenciones sobre capas de contacto y testeo) o por_dosis (vacunacion).';
COMMENT ON COLUMN intervention_types.cost_source IS
    'De donde salio la cifra. Obligatoria si el costo no esta marcado como supuesto.';
COMMENT ON COLUMN intervention_types.cost_is_assumption IS
    'TRUE si la cifra es un supuesto del equipo y no un dato con respaldo.';

INSERT INTO schema_migrations (version, description)
VALUES ('014', 'Simulacion: motor de referencia, resultados en PostgreSQL y costos de intervencion')
ON CONFLICT (version) DO NOTHING;

COMMIT;
