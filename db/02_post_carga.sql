-- =====================================================================
--  Despues de cargar la GDB: geometria de cada municipio y estadisticas
-- =====================================================================
-- El limite municipal se obtiene de los propios datos catastrales:
-- union de las veredas (zona rural) y de los perimetros urbanos, con un
-- cierre de 10 m para eliminar rendijas entre poligonos vecinos.
UPDATE catastro.municipio m
SET geom = (
    SELECT ST_Multi(ST_CollectionExtract(
               ST_MakeValid(ST_Buffer(ST_Buffer(ST_Union(g), 10), -10)), 3))
    FROM (
        SELECT geom AS g FROM catastro.vereda WHERE municipio_codigo = m.codigo
        UNION ALL
        SELECT geom FROM catastro.perimetro_urbano WHERE municipio_codigo = m.codigo
    ) t
)
WHERE m.con_catastro;

-- ANALYZE (y no VACUUM) para que el script tambien corra dentro de la transaccion de pgAdmin
ANALYZE;

-- Vista materializada para la funcionalidad F4 (ocupacion construida por manzana):
-- area construida de los terrenos de cada manzana / area de la manzana.
DROP MATERIALIZED VIEW IF EXISTS catastro.mv_ocupacion_manzana;
CREATE MATERIALIZED VIEW catastro.mv_ocupacion_manzana AS
SELECT mz.codigo                                   AS manzana_codigo,
       count(DISTINCT t.codigo)                    AS n_terrenos,
       count(c.globalid)                           AS n_construcciones,
       COALESCE(sum(c.area_m2), 0)                 AS area_construida_m2,
       round(LEAST(COALESCE(sum(c.area_m2), 0) / NULLIF(mz.area_m2, 0), 9.99), 4) AS indice_ocupacion
FROM catastro.manzana mz
LEFT JOIN catastro.terreno t       ON t.manzana_codigo = mz.codigo
LEFT JOIN catastro.construccion c  ON c.terreno_codigo = t.codigo
GROUP BY mz.codigo, mz.area_m2;
CREATE UNIQUE INDEX mv_ocupacion_pk ON catastro.mv_ocupacion_manzana (manzana_codigo);
ANALYZE catastro.mv_ocupacion_manzana;
