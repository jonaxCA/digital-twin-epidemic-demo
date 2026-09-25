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
    ('19021', 'General Escobedo',    481213, 25.795400, -100.318100),
    ('19046', 'San Nicolas de los Garza', 412199, 25.741700, -100.302800),
    ('19048', 'Santa Catarina',      306322, 25.673100, -100.458300),
    ('19031', 'Juarez',              471523, 25.646600, -100.096100),
    ('19018', 'Garcia',              397205, 25.813300, -100.585600),
    ('19049', 'Santiago',             46784, 25.424700, -100.147200)
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
