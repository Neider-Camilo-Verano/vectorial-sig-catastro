-- =====================================================================
--  CONSULTAS DE VERIFICACION (se ejecutan DIRECTAMENTE en PostgreSQL)
--  Cada bloque equivale a un endpoint de la API: el resultado debe coincidir
--  con lo que muestra el visor. Ejecutar en pgAdmin o con:
--      psql -d catastro_quindio -f db/03_consultas_verificacion.sql
-- =====================================================================

-- 0. La fuente es PostgreSQL/PostGIS (equivale a GET /api/salud)
SELECT current_database() AS base, postgis_version() AS postgis;
SELECT f_table_name AS tabla, type AS tipo_geometria, srid
FROM geometry_columns WHERE f_table_schema = 'catastro' ORDER BY 1;

-- 1. F1 - Terrenos por municipio (equivale a GET /api/municipios, campo n_terrenos)
SELECT m.codigo, m.nombre, count(t.codigo) AS n_terrenos
FROM catastro.municipio m
LEFT JOIN catastro.terreno t ON t.municipio_codigo = m.codigo
WHERE m.con_catastro
GROUP BY m.codigo, m.nombre
ORDER BY m.nombre;

-- 1.1 F1 - Terrenos dentro de una ventana (equivale a GET /api/capas/terrenos?minx=-75.6425&miny=4.5285&maxx=-75.6410&maxy=4.5300)
--     La caja llega en grados (4326) y se lleva a 9377 para aprovechar el indice GiST.
SELECT count(*) AS terrenos_en_ventana
FROM catastro.terreno
WHERE geom && ST_Transform(ST_MakeEnvelope(-75.6425, 4.5285, -75.6410, 4.5300, 4326), 9377);

-- 2. F2 - Ficha de un terreno (equivale a GET /api/terrenos/631300100000001430008000000000)
SELECT t.codigo, t.zona, t.area_m2, m.nombre AS municipio,
       count(c.globalid) AS n_construcciones,
       COALESCE(sum(c.area_m2), 0) AS area_construida_m2,
       COALESCE(max(c.num_pisos), 0) AS max_pisos
FROM catastro.terreno t
JOIN catastro.municipio m ON m.codigo = t.municipio_codigo
LEFT JOIN catastro.construccion c ON c.terreno_codigo = t.codigo
WHERE t.codigo = '631300100000001430008000000000'
GROUP BY t.codigo, t.zona, t.area_m2, m.nombre;

-- 2.1 F2 - Busqueda de vereda por nombre (equivale a GET /api/buscar?q=Pedregales)
SELECT v.codigo, v.nombre, m.nombre AS municipio
FROM catastro.vereda v JOIN catastro.municipio m ON m.codigo = v.municipio_codigo
WHERE v.nombre ILIKE '%Pedregales%';

-- 3. F3 - Terreno que contiene un punto (equivale a GET /api/terrenos/en-punto?lat=4.52896&lng=-75.64182)
--    ST_Intersects: ambas geometrias deben estar en el mismo SRID; el punto se transforma de 4326 a 9377.
SELECT codigo
FROM catastro.terreno
WHERE ST_Intersects(geom, ST_Transform(ST_SetSRID(ST_MakePoint(-75.64182, 4.52896), 4326), 9377))
ORDER BY zona, codigo
LIMIT 1;

-- 3.1 F3 - Construcciones a menos de 100 m de ese punto (equivale a GET /api/cercanos?lat=4.52896&lng=-75.64182&radio=100&capa=construcciones)
--     ST_DWithin sobre EPSG:9377 (unidades en metros). Si se usara 4326 el radio estaria en grados.
WITH p AS (SELECT ST_Transform(ST_SetSRID(ST_MakePoint(-75.64182, 4.52896), 4326), 9377) AS g)
SELECT count(*) AS construcciones_en_100_m,
       round(min(ST_Distance(c.geom, p.g))::numeric, 1) AS mas_cercana_m
FROM catastro.construccion c, p
WHERE ST_DWithin(c.geom, p.g, 100);

-- 4. F4 - Resumen de Calarca (equivale a GET /api/estadisticas/63130)
SELECT count(*) FILTER (WHERE zona = 'U') AS terrenos_urbanos,
       count(*) FILTER (WHERE zona = 'R') AS terrenos_rurales,
       round(sum(area_m2) FILTER (WHERE zona = 'U') / 10000.0, 1) AS area_urbana_ha
FROM catastro.terreno WHERE municipio_codigo = '63130';

SELECT tc.nombre AS tipo, count(*) AS cantidad
FROM catastro.construccion c JOIN catastro.tipo_construccion tc ON tc.id = c.tipo_construccion_id
WHERE c.municipio_codigo = '63130'
GROUP BY tc.nombre ORDER BY cantidad DESC;

-- 4.1 F4 - Manzanas mas ocupadas de Calarca (con al menos 5 terrenos)
SELECT mz.codigo, o.n_terrenos, o.indice_ocupacion
FROM catastro.mv_ocupacion_manzana o JOIN catastro.manzana mz ON mz.codigo = o.manzana_codigo
WHERE mz.municipio_codigo = '63130' AND o.n_terrenos >= 5
ORDER BY o.indice_ocupacion DESC LIMIT 5;

-- 5. Plan de ejecucion: el indice espacial GiST se usa en la busqueda por ventana
EXPLAIN (ANALYZE, BUFFERS)
SELECT count(*) FROM catastro.terreno
WHERE geom && ST_Transform(ST_MakeEnvelope(-75.6425, 4.5285, -75.6410, 4.5300, 4326), 9377);

-- 6. Integridad: no deben existir registros huerfanos ni geometrias invalidas
SELECT 'manzana sin municipio' AS control, count(*) AS problemas
FROM catastro.manzana m WHERE NOT EXISTS (SELECT 1 FROM catastro.municipio x WHERE x.codigo = m.municipio_codigo)
UNION ALL SELECT 'terreno con manzana inexistente', count(*)
FROM catastro.terreno t WHERE t.manzana_codigo IS NOT NULL AND NOT EXISTS (SELECT 1 FROM catastro.manzana x WHERE x.codigo = t.manzana_codigo)
UNION ALL SELECT 'construccion con terreno inexistente', count(*)
FROM catastro.construccion c WHERE c.terreno_codigo IS NOT NULL AND NOT EXISTS (SELECT 1 FROM catastro.terreno x WHERE x.codigo = c.terreno_codigo)
UNION ALL SELECT 'geometrias invalidas (terreno, construccion, manzana)', count(*)
FROM (SELECT geom FROM catastro.terreno UNION ALL SELECT geom FROM catastro.construccion UNION ALL SELECT geom FROM catastro.manzana) g
WHERE NOT ST_IsValid(g.geom);
