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
