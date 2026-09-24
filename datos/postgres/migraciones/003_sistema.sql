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
