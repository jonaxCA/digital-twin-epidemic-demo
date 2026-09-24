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
