"""
Todas las consultas SQL/PostGIS de la aplicacion, en un solo lugar.

Convenciones:
  * Los datos estan en EPSG:9377 (MAGNA-SIRGAS Origen Nacional, metros).
  * El navegador trabaja en EPSG:4326 (grados). Los puntos y cajas que llegan en
    grados se transforman a 9377 con ST_Transform ANTES de compararlos con las
    geometrias, para que los indices GiST se usen y las distancias salgan en metros.
  * Las geometrias que se devuelven se transforman a 4326 con ST_Transform
    (Leaflet exige longitud/latitud) y se redondean a 6 decimales (~0,1 m).
  * Los valores que vienen del usuario llegan como parametros (%(nombre)s).
"""

# Capas que el visor puede pedir por ventana: nombre -> (tabla, columnas de atributos)
CAPAS = {
    "perimetros": ("catastro.perimetro_urbano", "t.globalid AS id, t.nombre_geografico AS nombre, t.municipio_codigo, t.area_m2"),
    "veredas": ("catastro.vereda", "t.codigo AS id, t.nombre, t.municipio_codigo, t.area_m2"),
    "manzanas": (
        "catastro.manzana",
        "t.codigo AS id, t.municipio_codigo, t.area_m2, o.n_terrenos, o.n_construcciones, o.indice_ocupacion",
    ),
    "terrenos": ("catastro.terreno", "t.codigo AS id, t.zona, t.municipio_codigo, t.manzana_codigo, t.vereda_codigo, t.area_m2"),
    "construcciones": (
        "catastro.construccion",
        "t.globalid AS id, t.codigo, t.terreno_codigo, t.zona, tc.nombre AS tipo, t.num_pisos, t.area_m2",
    ),
    "vias": ("catastro.nomenclatura_vial", "t.globalid AS id, t.texto AS nombre, t.zona, t.longitud_m"),
}

# JOIN adicional que necesita cada capa (fijo, no depende del usuario)
JOIN_CAPA = {
    "manzanas": "LEFT JOIN catastro.mv_ocupacion_manzana o ON o.manzana_codigo = t.codigo",
    "construcciones": "JOIN catastro.tipo_construccion tc ON tc.id = t.tipo_construccion_id",
}


def sql_capa(capa):
    """F1: elementos de una capa que caen dentro de la ventana del mapa."""
    tabla, columnas = CAPAS[capa]
    return f"""
    SELECT {columnas},
           ST_AsGeoJSON(
               ST_Transform(
                   CASE WHEN %(tol)s > 0 THEN ST_SimplifyPreserveTopology(t.geom, %(tol)s) ELSE t.geom END,
                   4326), 6) AS geojson
    FROM {tabla} t
    {JOIN_CAPA.get(capa, "")}
    WHERE t.geom && ST_Transform(ST_MakeEnvelope(%(minx)s, %(miny)s, %(maxx)s, %(maxy)s, 4326), 9377)
      AND (%(municipio)s::text IS NULL OR t.municipio_codigo = %(municipio)s)
    LIMIT %(limite)s
    """


# F1: municipios con conteos (capa de entrada del visor)
MUNICIPIOS = """
SELECT m.codigo, m.nombre, m.con_catastro,
       round((ST_Area(m.geom) / 1000000.0)::numeric, 1)                         AS area_km2,
       (SELECT count(*) FROM catastro.manzana x WHERE x.municipio_codigo = m.codigo)       AS n_manzanas,
       (SELECT count(*) FROM catastro.vereda x WHERE x.municipio_codigo = m.codigo)        AS n_veredas,
       (SELECT count(*) FROM catastro.terreno x WHERE x.municipio_codigo = m.codigo)       AS n_terrenos,
       (SELECT count(*) FROM catastro.construccion x WHERE x.municipio_codigo = m.codigo)  AS n_construcciones,
       ST_AsGeoJSON(ST_Transform(ST_SimplifyPreserveTopology(m.geom, 20), 4326), 6)        AS geojson
FROM catastro.municipio m
WHERE m.geom IS NOT NULL
ORDER BY m.nombre
"""

# F2: busqueda por atributos (texto o codigo)
BUSCAR_TERRENO = """
SELECT t.codigo AS id, 'terreno' AS tipo, t.codigo AS titulo,
       CASE t.zona WHEN 'U' THEN 'Terreno urbano' ELSE 'Terreno rural' END || ' - ' || m.nombre AS detalle,
       ST_Y(ST_Transform(ST_PointOnSurface(t.geom), 4326)) AS lat,
       ST_X(ST_Transform(ST_PointOnSurface(t.geom), 4326)) AS lng
FROM catastro.terreno t JOIN catastro.municipio m ON m.codigo = t.municipio_codigo
WHERE t.codigo LIKE %(patron)s
ORDER BY t.codigo
LIMIT %(limite)s
"""

BUSCAR_VEREDA = """
SELECT v.codigo AS id, 'vereda' AS tipo, v.nombre AS titulo, 'Vereda - ' || m.nombre AS detalle,
       ST_Y(ST_Transform(ST_PointOnSurface(v.geom), 4326)) AS lat,
       ST_X(ST_Transform(ST_PointOnSurface(v.geom), 4326)) AS lng
FROM catastro.vereda v JOIN catastro.municipio m ON m.codigo = v.municipio_codigo
WHERE v.nombre ILIKE %(contiene)s
ORDER BY similarity(v.nombre, %(q)s) DESC, v.nombre
LIMIT %(limite)s
"""

BUSCAR_VIA = """
SELECT min(v.globalid) AS id, 'via' AS tipo, v.texto AS titulo,
       'Via - ' || m.nombre AS detalle,
       ST_Y(ST_Transform(ST_PointOnSurface(ST_Collect(v.geom)), 4326)) AS lat,
       ST_X(ST_Transform(ST_PointOnSurface(ST_Collect(v.geom)), 4326)) AS lng
FROM catastro.nomenclatura_vial v JOIN catastro.municipio m ON m.codigo = v.municipio_codigo
WHERE v.texto ILIKE %(contiene)s
GROUP BY v.texto, m.nombre
ORDER BY similarity(v.texto, %(q)s) DESC, v.texto
LIMIT %(limite)s
"""

BUSCAR_DIRECCION = """
SELECT d.globalid AS id, 'direccion' AS tipo, d.texto AS titulo, 'Direccion - ' || m.nombre AS detalle,
       ST_Y(ST_Transform(ST_PointOnSurface(d.geom), 4326)) AS lat,
       ST_X(ST_Transform(ST_PointOnSurface(d.geom), 4326)) AS lng
FROM catastro.nomenclatura_domiciliaria d JOIN catastro.municipio m ON m.codigo = d.municipio_codigo
WHERE d.texto ILIKE %(contiene)s
ORDER BY similarity(d.texto, %(q)s) DESC, d.texto
LIMIT %(limite)s
"""

# F2: ficha de un terreno y sus relaciones (JOIN por claves foraneas)
FICHA_TERRENO = """
SELECT t.codigo, t.zona, t.area_m2, t.num_subterraneos,
       t.municipio_codigo, m.nombre AS municipio,
       t.manzana_codigo, v.codigo AS vereda_codigo, v.nombre AS vereda,
       (SELECT count(*) FROM catastro.construccion c WHERE c.terreno_codigo = t.codigo)                AS n_construcciones,
       (SELECT COALESCE(sum(c.area_m2), 0) FROM catastro.construccion c WHERE c.terreno_codigo = t.codigo) AS area_construida_m2,
       (SELECT COALESCE(max(c.num_pisos), 0) FROM catastro.construccion c WHERE c.terreno_codigo = t.codigo) AS max_pisos,
       ST_AsGeoJSON(ST_Transform(t.geom, 4326), 6) AS geojson
FROM catastro.terreno t
JOIN catastro.municipio m ON m.codigo = t.municipio_codigo
LEFT JOIN catastro.vereda v ON v.codigo = t.vereda_codigo
WHERE t.codigo = %(codigo)s
"""

CONSTRUCCIONES_DE_TERRENO = """
SELECT c.globalid AS id, c.identificador, tc.nombre AS tipo, c.tipo_dominio, c.num_pisos, c.area_m2,
       ST_AsGeoJSON(ST_Transform(c.geom, 4326), 6) AS geojson
FROM catastro.construccion c
JOIN catastro.tipo_construccion tc ON tc.id = c.tipo_construccion_id
WHERE c.terreno_codigo = %(codigo)s
ORDER BY c.area_m2 DESC
"""

DIRECCIONES_DE_TERRENO = """
SELECT d.texto FROM catastro.nomenclatura_domiciliaria d WHERE d.terreno_codigo = %(codigo)s ORDER BY d.texto
"""

# F3: consulta espacial 1 - terreno que contiene el punto (ST_Intersects con el punto en 9377)
TERRENO_EN_PUNTO = """
WITH p AS (SELECT ST_Transform(ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326), 9377) AS g)
SELECT t.codigo
FROM catastro.terreno t, p
WHERE ST_Intersects(t.geom, p.g)
ORDER BY t.zona, t.codigo
LIMIT 1
"""

# F3: consulta espacial 2 - elementos dentro de un radio en metros (ST_DWithin + ST_Distance)
def sql_cercanos(capa):
    tabla, columnas = CAPAS[capa]
    return f"""
    WITH p AS (SELECT ST_Transform(ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326), 9377) AS g)
    SELECT {columnas},
           round(ST_Distance(t.geom, p.g)::numeric, 1) AS distancia_m,
           count(*) OVER () AS total_en_radio,
           ST_AsGeoJSON(ST_Transform(t.geom, 4326), 6) AS geojson
    FROM {tabla} t
    {JOIN_CAPA.get(capa, "")}
    , p
    WHERE ST_DWithin(t.geom, p.g, %(radio)s)
    ORDER BY ST_Distance(t.geom, p.g)
    LIMIT %(limite)s
    """

# F4: estadisticas por municipio (agregaciones sobre varias tablas relacionadas)
ESTADISTICAS_MUNICIPIO = """
SELECT m.codigo, m.nombre,
       (SELECT count(*) FROM catastro.terreno t WHERE t.municipio_codigo = m.codigo AND t.zona = 'U') AS terrenos_urbanos,
       (SELECT count(*) FROM catastro.terreno t WHERE t.municipio_codigo = m.codigo AND t.zona = 'R') AS terrenos_rurales,
       (SELECT round(COALESCE(sum(t.area_m2), 0) / 10000.0, 1) FROM catastro.terreno t WHERE t.municipio_codigo = m.codigo AND t.zona = 'U') AS area_urbana_ha,
       (SELECT round(COALESCE(sum(t.area_m2), 0) / 10000.0, 1) FROM catastro.terreno t WHERE t.municipio_codigo = m.codigo AND t.zona = 'R') AS area_rural_ha,
       (SELECT count(*) FROM catastro.construccion c WHERE c.municipio_codigo = m.codigo) AS construcciones,
       (SELECT round(COALESCE(avg(c.num_pisos), 0), 2) FROM catastro.construccion c WHERE c.municipio_codigo = m.codigo AND c.num_pisos > 0) AS pisos_promedio,
       (SELECT round(COALESCE(avg(o.indice_ocupacion), 0), 3)
          FROM catastro.mv_ocupacion_manzana o JOIN catastro.manzana mz ON mz.codigo = o.manzana_codigo
         WHERE mz.municipio_codigo = m.codigo) AS ocupacion_media_manzana
FROM catastro.municipio m
WHERE m.codigo = %(codigo)s
"""

CONSTRUCCIONES_POR_TIPO = """
SELECT tc.nombre AS tipo, count(*) AS cantidad
FROM catastro.construccion c JOIN catastro.tipo_construccion tc ON tc.id = c.tipo_construccion_id
WHERE c.municipio_codigo = %(codigo)s
GROUP BY tc.nombre ORDER BY cantidad DESC
"""

CONSTRUCCIONES_POR_PISOS = """
SELECT CASE WHEN c.num_pisos IS NULL OR c.num_pisos = 0 THEN 'Sin dato'
            WHEN c.num_pisos >= 5 THEN '5 o más' ELSE c.num_pisos::text END AS pisos,
       count(*) AS cantidad
FROM catastro.construccion c
WHERE c.municipio_codigo = %(codigo)s
GROUP BY 1 ORDER BY 1
"""

TOP_MANZANAS_OCUPACION = """
SELECT mz.codigo, o.n_terrenos, o.n_construcciones, o.indice_ocupacion
FROM catastro.mv_ocupacion_manzana o JOIN catastro.manzana mz ON mz.codigo = o.manzana_codigo
WHERE mz.municipio_codigo = %(codigo)s AND o.n_terrenos >= 5
ORDER BY o.indice_ocupacion DESC
LIMIT 5
"""

# Estado de la conexion (evidencia de que la fuente es PostgreSQL/PostGIS)
SALUD = """
SELECT current_database() AS base, version() AS postgresql, postgis_version() AS postgis
"""

CONTEO_TABLAS = """
SELECT 'municipio' AS tabla, count(*) AS filas FROM catastro.municipio
UNION ALL SELECT 'perimetro_urbano', count(*) FROM catastro.perimetro_urbano
UNION ALL SELECT 'vereda', count(*) FROM catastro.vereda
UNION ALL SELECT 'manzana', count(*) FROM catastro.manzana
UNION ALL SELECT 'terreno', count(*) FROM catastro.terreno
UNION ALL SELECT 'construccion', count(*) FROM catastro.construccion
UNION ALL SELECT 'nomenclatura_vial', count(*) FROM catastro.nomenclatura_vial
UNION ALL SELECT 'nomenclatura_domiciliaria', count(*) FROM catastro.nomenclatura_domiciliaria
"""
