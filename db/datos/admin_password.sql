-- =============================================================================
-- admin_password.sql
-- Le pone contrasena REAL a la cuenta admin sembrada por 010_datos_iniciales.sql
-- (que trae el marcador invalido REEMPLAZAR_ANTES_DE_DESPLEGAR a proposito).
--
-- Se necesita para poder entrar con el rol ADMINISTRADOR y mostrar el CRUD de
-- usuarios en el entorno local.
--
-- ALCANCE: este archivo NO modifica el esquema. Solo hace UPDATE de una fila
-- (users.password_hash del admin) e inserta el rol si le faltara. Es seguro
-- correrlo sobre una base que ya esta en uso -- no toca casos, escenarios,
-- catalogos ni ninguna otra cuenta.
--
--   usuario:   admin
--   password:  Admin2026!
--
-- Es una contrasena de desarrollo local. Cambiala antes de exponer esto fuera
-- de la VM.
-- =============================================================================

BEGIN;

UPDATE users
SET password_hash = '$2b$12$SURuIT39lI7zbNTruNOBMu7C3YXltAT816pKLZREW8U6iTJvoJK7q'
WHERE username = 'admin';

-- Se asegura de que admin tenga el rol ADMINISTRADOR (010 ya lo asigna; esto
-- solo cubre el caso de una base donde se haya perdido).
INSERT INTO user_roles (user_id, role_id)
SELECT u.id, r.id
FROM users u CROSS JOIN roles r
WHERE u.username = 'admin' AND r.code = 'ADMINISTRADOR'
ON CONFLICT DO NOTHING;

COMMIT;
