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
