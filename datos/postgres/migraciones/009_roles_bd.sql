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
