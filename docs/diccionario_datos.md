# Diccionario de datos

Esquema `catastro`. Todas las geometrías están en **EPSG:9377** (MAGNA-SIRGAS / Origen Nacional, unidad: metro). Generado a partir de la base real (`information_schema` y `geometry_columns`).


## `catastro.construccion`  (100.593 filas)

| Columna | Tipo | Clave | Descripción |
|---|---|---|---|
| globalid | char NOT NULL | PK | Identificador único de la fuente (GlobalID) |
| codigo | varchar NOT NULL |  | Código catastral del terreno de origen (se repite en cada construcción del terreno) |
| terreno_codigo | varchar | FK → terreno.codigo | FK → terreno (NULL si no existe en la capa) |
| municipio_codigo | char NOT NULL | FK → municipio.codigo | FK → municipio (DIVIPOLA 5 dígitos) |
| zona | char NOT NULL |  | U = urbana, R = rural |
| tipo_construccion_id | smallint NOT NULL | FK → tipo_construccion.id | FK → tipo_construccion |
| tipo_dominio | varchar |  | PRIVADO / COMUN |
| identificador | varchar |  | Identificador de la construcción dentro del terreno |
| num_pisos | smallint |  | Número de pisos (0–100) |
| num_sotanos | smallint |  | Número de sótanos |
| area_m2 | numeric |  | Área calculada con ST_Area (m²), columna generada |
| geom | geometry(MULTIPOLYGON, 9377) NOT NULL |  | Geometría en EPSG:9377 |

## `catastro.departamento`  (1 fila)

| Columna | Tipo | Clave | Descripción |
|---|---|---|---|
| codigo | char NOT NULL | PK | Código catastral / DIVIPOLA |
| nombre | varchar NOT NULL |  | Nombre |

## `catastro.manzana`  (3.772 filas)

| Columna | Tipo | Clave | Descripción |
|---|---|---|---|
| codigo | char NOT NULL | PK | Código catastral / DIVIPOLA |
| municipio_codigo | char NOT NULL | FK → municipio.codigo | FK → municipio (DIVIPOLA 5 dígitos) |
| barrio_codigo | varchar |  | Código de barrio de la fuente |
| area_m2 | numeric |  | Área calculada con ST_Area (m²), columna generada |
| geom | geometry(MULTIPOLYGON, 9377) NOT NULL |  | Geometría en EPSG:9377 |

## `catastro.municipio`  (12 filas)

| Columna | Tipo | Clave | Descripción |
|---|---|---|---|
| codigo | char NOT NULL | PK | Código catastral / DIVIPOLA |
| departamento_codigo | char NOT NULL | FK → departamento.codigo | FK → departamento |
| nombre | varchar NOT NULL |  | Nombre |
| con_catastro | bool NOT NULL |  | Verdadero si la GDB trae datos de ese municipio |
| geom | geometry(MULTIPOLYGON, 9377) |  | Geometría en EPSG:9377 |

## `catastro.nomenclatura_domiciliaria`  (80.661 filas)

| Columna | Tipo | Clave | Descripción |
|---|---|---|---|
| globalid | char NOT NULL | PK | Identificador único de la fuente (GlobalID) |
| municipio_codigo | char NOT NULL | FK → municipio.codigo | FK → municipio (DIVIPOLA 5 dígitos) |
| zona | char NOT NULL |  | U = urbana, R = rural |
| terreno_codigo | varchar | FK → terreno.codigo | FK → terreno (NULL si no existe en la capa) |
| texto | varchar |  | Texto de la nomenclatura |
| geom | geometry(MULTILINESTRING, 9377) NOT NULL |  | Geometría en EPSG:9377 |

## `catastro.nomenclatura_vial`  (2.192 filas)

| Columna | Tipo | Clave | Descripción |
|---|---|---|---|
| globalid | char NOT NULL | PK | Identificador único de la fuente (GlobalID) |
| municipio_codigo | char NOT NULL | FK → municipio.codigo | FK → municipio (DIVIPOLA 5 dígitos) |
| zona | char NOT NULL |  | U = urbana, R = rural |
| texto | varchar |  | Texto de la nomenclatura |
| longitud_m | numeric |  | Longitud con ST_Length (m), columna generada |
| geom | geometry(MULTILINESTRING, 9377) NOT NULL |  | Geometría en EPSG:9377 |

## `catastro.perimetro_urbano`  (14 filas)

| Columna | Tipo | Clave | Descripción |
|---|---|---|---|
| globalid | char NOT NULL | PK | Identificador único de la fuente (GlobalID) |
| municipio_codigo | char NOT NULL | FK → municipio.codigo | FK → municipio (DIVIPOLA 5 dígitos) |
| nombre_geografico | varchar |  | Nombre del perímetro urbano |
| tipo_avaluo | char |  | Tipo de avalúo de la fuente |
| area_m2 | numeric |  | Área calculada con ST_Area (m²), columna generada |
| geom | geometry(MULTIPOLYGON, 9377) NOT NULL |  | Geometría en EPSG:9377 |

## `catastro.terreno`  (77.918 filas)

| Columna | Tipo | Clave | Descripción |
|---|---|---|---|
| codigo | varchar NOT NULL | PK | Código catastral / DIVIPOLA |
| zona | char NOT NULL |  | U = urbana, R = rural |
| municipio_codigo | char NOT NULL | FK → municipio.codigo | FK → municipio (DIVIPOLA 5 dígitos) |
| manzana_codigo | char | FK → manzana.codigo | FK → manzana (NULL si la fuente no la asigna) |
| vereda_codigo | char | FK → vereda.codigo | FK → vereda (NULL si la fuente no la asigna) |
| num_subterraneos | smallint |  | Número de subterráneos |
| area_m2 | numeric |  | Área calculada con ST_Area (m²), columna generada |
| geom | geometry(MULTIPOLYGON, 9377) NOT NULL |  | Geometría en EPSG:9377 |

## `catastro.tipo_construccion`  (3 filas)

| Columna | Tipo | Clave | Descripción |
|---|---|---|---|
| id | smallint NOT NULL | PK | Identificador secuencial |
| nombre | varchar NOT NULL |  | Nombre |

## `catastro.vereda`  (126 filas)

| Columna | Tipo | Clave | Descripción |
|---|---|---|---|
| codigo | char NOT NULL | PK | Código catastral / DIVIPOLA |
| municipio_codigo | char NOT NULL | FK → municipio.codigo | FK → municipio (DIVIPOLA 5 dígitos) |
| nombre | varchar NOT NULL |  | Nombre de la vereda |
| area_m2 | numeric |  | Área calculada con ST_Area (m²), columna generada |
| geom | geometry(MULTIPOLYGON, 9377) NOT NULL |  | Geometría en EPSG:9377 |
