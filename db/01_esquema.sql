-- =====================================================================
--  GEODATABASE CATASTRAL - VECTORIAL SIG Web
--  PostgreSQL 16 + PostGIS 3.4   |   SRID 9377 (MAGNA-SIRGAS / Origen Nacional)
--  Fuente: Base catastral vectorial IGAC / DANE (geodatabase departamental
--  "XX.gdb", capas U_* urbanas y R_* rurales).
--  Se crea la estructura vacia; los datos se cargan con scripts/cargar_gdb.py
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- El EPSG:9377 no viene registrado en todas las instalaciones de PostGIS;
-- sin el, ST_Transform hacia 4326 falla. Se agrega solo si falta.
INSERT INTO spatial_ref_sys (srid, auth_name, auth_srid, srtext, proj4text)
SELECT 9377, 'EPSG', 9377,
       'PROJCRS["MAGNA-SIRGAS / Origen-Nacional",BASEGEOGCRS["MAGNA-SIRGAS",DATUM["Marco Geocentrico Nacional de Referencia",ELLIPSOID["GRS 1980",6378137,298.257222101,LENGTHUNIT["metre",1]]],PRIMEM["Greenwich",0,ANGLEUNIT["degree",0.0174532925199433]]],CONVERSION["Colombia Origen-Nacional",METHOD["Transverse Mercator",ID["EPSG",9807]],PARAMETER["Latitude of natural origin",4,ANGLEUNIT["degree",0.0174532925199433]],PARAMETER["Longitude of natural origin",-73,ANGLEUNIT["degree",0.0174532925199433]],PARAMETER["Scale factor at natural origin",0.9992,SCALEUNIT["unity",1]],PARAMETER["False easting",5000000,LENGTHUNIT["metre",1]],PARAMETER["False northing",2000000,LENGTHUNIT["metre",1]]],CS[Cartesian,2],AXIS["northing (N)",north,ORDER[1],LENGTHUNIT["metre",1]],AXIS["easting (E)",east,ORDER[2],LENGTHUNIT["metre",1]],ID["EPSG",9377]]',
       '+proj=tmerc +lat_0=4 +lon_0=-73 +k=0.9992 +x_0=5000000 +y_0=2000000 +ellps=GRS80 +units=m +no_defs'
WHERE NOT EXISTS (SELECT 1 FROM spatial_ref_sys WHERE srid = 9377);

DROP SCHEMA IF EXISTS catastro CASCADE;
CREATE SCHEMA catastro;

-- ---------------------------------------------------------------------
-- Division administrativa (codigos DIVIPOLA del DANE)
-- ---------------------------------------------------------------------
CREATE TABLE catastro.departamento (
    codigo  char(2) PRIMARY KEY,
    nombre  varchar(60) NOT NULL
);

CREATE TABLE catastro.municipio (
    codigo               char(5) PRIMARY KEY,
    departamento_codigo  char(2) NOT NULL REFERENCES catastro.departamento(codigo)
                         ON UPDATE CASCADE ON DELETE RESTRICT,
    nombre               varchar(80) NOT NULL,
    con_catastro         boolean NOT NULL DEFAULT false,   -- true si la GDB trae datos del municipio
    geom                 geometry(MultiPolygon, 9377)       -- se calcula con 02_post_carga.sql
);
CREATE INDEX municipio_geom_gix ON catastro.municipio USING GIST (geom);
CREATE INDEX municipio_dep_idx  ON catastro.municipio (departamento_codigo);

-- ---------------------------------------------------------------------
-- Unidades espaciales
-- ---------------------------------------------------------------------
CREATE TABLE catastro.perimetro_urbano (
    globalid          char(38) PRIMARY KEY,
    municipio_codigo  char(5) NOT NULL REFERENCES catastro.municipio(codigo)
                      ON UPDATE CASCADE ON DELETE RESTRICT,
    nombre_geografico varchar(120),
    tipo_avaluo       char(2),
    area_m2           numeric(16,2) GENERATED ALWAYS AS (ST_Area(geom)::numeric(16,2)) STORED,
    geom              geometry(MultiPolygon, 9377) NOT NULL
);
CREATE INDEX perimetro_geom_gix ON catastro.perimetro_urbano USING GIST (geom);
CREATE INDEX perimetro_mun_idx  ON catastro.perimetro_urbano (municipio_codigo);

CREATE TABLE catastro.vereda (
    codigo            char(17) PRIMARY KEY,
    municipio_codigo  char(5) NOT NULL REFERENCES catastro.municipio(codigo)
                      ON UPDATE CASCADE ON DELETE RESTRICT,
    nombre            varchar(120) NOT NULL,
    area_m2           numeric(16,2) GENERATED ALWAYS AS (ST_Area(geom)::numeric(16,2)) STORED,
    geom              geometry(MultiPolygon, 9377) NOT NULL
);
CREATE INDEX vereda_geom_gix   ON catastro.vereda USING GIST (geom);
CREATE INDEX vereda_mun_idx    ON catastro.vereda (municipio_codigo);
CREATE INDEX vereda_nombre_trg ON catastro.vereda USING GIN (nombre gin_trgm_ops);

CREATE TABLE catastro.manzana (
    codigo            char(17) PRIMARY KEY,
    municipio_codigo  char(5) NOT NULL REFERENCES catastro.municipio(codigo)
                      ON UPDATE CASCADE ON DELETE RESTRICT,
    barrio_codigo     varchar(17),
    area_m2           numeric(14,2) GENERATED ALWAYS AS (ST_Area(geom)::numeric(14,2)) STORED,
    geom              geometry(MultiPolygon, 9377) NOT NULL
);
CREATE INDEX manzana_geom_gix ON catastro.manzana USING GIST (geom);
CREATE INDEX manzana_mun_idx  ON catastro.manzana (municipio_codigo);

-- Terreno (predio): zona 'U' urbana o 'R' rural. Un terreno urbano pertenece a una
-- manzana y uno rural a una vereda. Si la fuente trae un codigo de manzana/vereda
-- generico (sin asignar) o inexistente, la clave foranea queda en NULL.
CREATE TABLE catastro.terreno (
    codigo            varchar(30) PRIMARY KEY,
    zona              char(1) NOT NULL CHECK (zona IN ('U','R')),
    municipio_codigo  char(5) NOT NULL REFERENCES catastro.municipio(codigo)
                      ON UPDATE CASCADE ON DELETE RESTRICT,
    manzana_codigo    char(17) REFERENCES catastro.manzana(codigo)
                      ON UPDATE CASCADE ON DELETE SET NULL,
    vereda_codigo     char(17) REFERENCES catastro.vereda(codigo)
                      ON UPDATE CASCADE ON DELETE SET NULL,
    num_subterraneos  smallint,
    area_m2           numeric(14,2) GENERATED ALWAYS AS (ST_Area(geom)::numeric(14,2)) STORED,
    geom              geometry(MultiPolygon, 9377) NOT NULL,
    CONSTRAINT chk_terreno_zona CHECK (
        (zona = 'U' AND vereda_codigo IS NULL) OR (zona = 'R' AND manzana_codigo IS NULL))
);
CREATE INDEX terreno_geom_gix ON catastro.terreno USING GIST (geom);
CREATE INDEX terreno_mun_idx  ON catastro.terreno (municipio_codigo);
CREATE INDEX terreno_mz_idx   ON catastro.terreno (manzana_codigo);
CREATE INDEX terreno_ver_idx  ON catastro.terreno (vereda_codigo);
CREATE INDEX terreno_cod_pref ON catastro.terreno (codigo varchar_pattern_ops);

CREATE TABLE catastro.tipo_construccion (
    id      smallserial PRIMARY KEY,
    nombre  varchar(30) NOT NULL UNIQUE
);
INSERT INTO catastro.tipo_construccion (nombre) VALUES ('CONVENCIONAL'), ('NO CONVENCIONAL'), ('SIN DATO');

CREATE TABLE catastro.construccion (
    globalid              char(38) PRIMARY KEY,
    codigo                varchar(30) NOT NULL,        -- repetido por cada construccion del terreno
    terreno_codigo        varchar(30) REFERENCES catastro.terreno(codigo)
                          ON UPDATE CASCADE ON DELETE SET NULL,
    municipio_codigo      char(5) NOT NULL REFERENCES catastro.municipio(codigo)
                          ON UPDATE CASCADE ON DELETE RESTRICT,
    zona                  char(1) NOT NULL CHECK (zona IN ('U','R')),
    tipo_construccion_id  smallint NOT NULL REFERENCES catastro.tipo_construccion(id)
                          ON UPDATE CASCADE ON DELETE RESTRICT,
    tipo_dominio          varchar(10),
    identificador         varchar(40),
    num_pisos             smallint CHECK (num_pisos IS NULL OR num_pisos BETWEEN 0 AND 100),
    num_sotanos           smallint,
    area_m2               numeric(14,2) GENERATED ALWAYS AS (ST_Area(geom)::numeric(14,2)) STORED,
    geom                  geometry(MultiPolygon, 9377) NOT NULL
);
CREATE INDEX construccion_geom_gix ON catastro.construccion USING GIST (geom);
CREATE INDEX construccion_ter_idx  ON catastro.construccion (terreno_codigo);
CREATE INDEX construccion_mun_idx  ON catastro.construccion (municipio_codigo);
CREATE INDEX construccion_tipo_idx ON catastro.construccion (tipo_construccion_id);

-- ---------------------------------------------------------------------
-- Nomenclatura
-- ---------------------------------------------------------------------
CREATE TABLE catastro.nomenclatura_vial (
    globalid          char(38) PRIMARY KEY,
    municipio_codigo  char(5) NOT NULL REFERENCES catastro.municipio(codigo)
                      ON UPDATE CASCADE ON DELETE RESTRICT,
    zona              char(1) NOT NULL CHECK (zona IN ('U','R')),
    texto             varchar(250),
    longitud_m        numeric(12,2) GENERATED ALWAYS AS (ST_Length(geom)::numeric(12,2)) STORED,
    geom              geometry(MultiLineString, 9377) NOT NULL
);
CREATE INDEX nomvial_geom_gix  ON catastro.nomenclatura_vial USING GIST (geom);
CREATE INDEX nomvial_mun_idx   ON catastro.nomenclatura_vial (municipio_codigo);
CREATE INDEX nomvial_texto_trg ON catastro.nomenclatura_vial USING GIN (texto gin_trgm_ops);

CREATE TABLE catastro.nomenclatura_domiciliaria (
    globalid          char(38) PRIMARY KEY,
    municipio_codigo  char(5) NOT NULL REFERENCES catastro.municipio(codigo)
                      ON UPDATE CASCADE ON DELETE RESTRICT,
    zona              char(1) NOT NULL CHECK (zona IN ('U','R')),
    terreno_codigo    varchar(30) REFERENCES catastro.terreno(codigo)
                      ON UPDATE CASCADE ON DELETE SET NULL,
    texto             varchar(250),
    geom              geometry(MultiLineString, 9377) NOT NULL
);
CREATE INDEX nomdom_geom_gix  ON catastro.nomenclatura_domiciliaria USING GIST (geom);
CREATE INDEX nomdom_mun_idx   ON catastro.nomenclatura_domiciliaria (municipio_codigo);
CREATE INDEX nomdom_ter_idx   ON catastro.nomenclatura_domiciliaria (terreno_codigo);
CREATE INDEX nomdom_texto_trg ON catastro.nomenclatura_domiciliaria USING GIN (texto gin_trgm_ops);
