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
