"""
Pruebas de la API contra la base PostgreSQL/PostGIS real (sin simulaciones).
Cada respuesta HTTP se contrasta con una consulta SQL independiente.

    python tests/test_api.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg
from fastapi.testclient import TestClient

from backend.app.config import DATABASE_URL
from backend.app.main import app

ok = fallos = 0


def prueba(nombre, condicion, detalle=""):
    global ok, fallos
    if condicion:
        ok += 1
        print(f"OK     {nombre}")
    else:
        fallos += 1
        print(f"FALLO  {nombre}  {detalle}")


def sql(consulta, *params):
    with psycopg.connect(DATABASE_URL) as con:
        return con.execute(consulta, params).fetchall()


with TestClient(app) as c:
    # --- conexion y evidencia de PostGIS -----------------------------
    r = c.get("/api/salud").json()
    prueba("salud: responde PostgreSQL y PostGIS", "PostgreSQL" in r["postgresql"] and r["postgis"].startswith("3"))
    prueba("salud: conteos de tablas = SQL directo",
           r["tablas"]["terreno"] == sql("SELECT count(*) FROM catastro.terreno")[0][0]
           and r["tablas"]["construccion"] == sql("SELECT count(*) FROM catastro.construccion")[0][0])

    # --- F1 municipios ----------------------------------------------
    r = c.get("/api/municipios").json()
    prueba("F1 municipios: FeatureCollection de poligonos", r["type"] == "FeatureCollection" and r["features"][0]["geometry"]["type"] in ("Polygon", "MultiPolygon"))
    esperado = dict(sql("SELECT municipio_codigo, count(*) FROM catastro.terreno GROUP BY 1"))
    prueba("F1 municipios: n_terrenos de cada municipio = SQL",
           all(f["properties"]["n_terrenos"] == esperado[f["properties"]["codigo"]] for f in r["features"]))
    lng, lat = r["features"][0]["geometry"]["coordinates"][0][0][:2] if r["features"][0]["geometry"]["type"] == "Polygon" else r["features"][0]["geometry"]["coordinates"][0][0][0][:2]
    prueba("F1 municipios: coordenadas en grados (Quindio)", -76 < lng < -75 and 4 < lat < 5, (lng, lat))

    # --- F1 capas por ventana ---------------------------------------
    box = dict(minx=-75.700, miny=4.455, maxx=-75.690, maxy=4.465, zoom=17)
    for capa in ["manzanas", "terrenos", "construcciones", "vias", "veredas", "perimetros"]:
        r = c.get(f"/api/capas/{capa}", params=box)
        prueba(f"F1 capa {capa}: 200 y GeoJSON", r.status_code == 200 and r.json()["type"] == "FeatureCollection", r.text[:100])
    r = c.get("/api/capas/terrenos", params=box).json()
    n_sql = sql("""SELECT count(*) FROM catastro.terreno
                   WHERE geom && ST_Transform(ST_MakeEnvelope(%s,%s,%s,%s,4326),9377)""", box["minx"], box["miny"], box["maxx"], box["maxy"])[0][0]
    prueba(f"F1 terrenos en ventana ({len(r['features'])}) = SQL ({n_sql})", len(r["features"]) == n_sql and n_sql > 0)
    r = c.get("/api/capas/terrenos", params={**box, "limite": 5}).json()
    prueba("F1 limite respetado y marcado como truncado", len(r["features"]) == 5 and r["metadatos"]["truncado"])
    prueba("F1 capa inexistente -> 404", c.get("/api/capas/inventada", params=box).status_code == 404)
    prueba("F1 ventana invertida -> 422", c.get("/api/capas/terrenos", params={**box, "minx": -75.6}).status_code == 422)
    prueba("F1 coordenada fuera de Colombia -> 422", c.get("/api/capas/terrenos", params={**box, "minx": 10}).status_code == 422)
    prueba("F1 municipio mal formado -> 422", c.get("/api/capas/terrenos", params={**box, "municipio": "abc"}).status_code == 422)

    # --- F2 busqueda y ficha ----------------------------------------
    r = c.get("/api/buscar", params={"q": "Pedregales"}).json()
    n = sql("SELECT count(*) FROM catastro.vereda WHERE nombre ILIKE %s", "%Pedregales%")[0][0]
    veredas = [x for x in r["resultados"] if x["tipo"] == "vereda"]
    prueba(f"F2 buscar vereda 'Pedregales' ({len(veredas)}) = SQL ({n})", len(veredas) == n and n > 0)
    prueba("F2 resultados traen lat/lng", all(-5 < x["lat"] < 14 and -80 < x["lng"] < -66 for x in r["resultados"]))
    r = c.get("/api/buscar", params={"q": "63130010000000"}).json()
    prueba("F2 buscar terreno por prefijo de codigo", any(x["tipo"] == "terreno" for x in r["resultados"]))
    r = c.get("/api/buscar", params={"q": "CARRERA 1"}).json()
    prueba("F2 buscar via por texto", any(x["tipo"] == "via" for x in r["resultados"]))
    inyeccion = "'; DROP TABLE catastro.terreno; --"
    r = c.get("/api/buscar", params={"q": inyeccion})
    prueba("Seguridad: texto con SQL se trata como dato (200, sin resultados)", r.status_code == 200 and r.json()["total"] == 0)
    prueba("Seguridad: la tabla terreno sigue existiendo", sql("SELECT count(*) FROM catastro.terreno")[0][0] > 0)
    prueba("F2 consulta muy corta -> 422", c.get("/api/buscar", params={"q": "a"}).status_code == 422)

    cod = sql("SELECT codigo FROM catastro.terreno t WHERE (SELECT count(*) FROM catastro.construccion c WHERE c.terreno_codigo=t.codigo)>=2 AND zona='U' ORDER BY codigo LIMIT 1")[0][0]
    r = c.get(f"/api/terrenos/{cod}").json()
    n_sql = sql("SELECT count(*), COALESCE(sum(area_m2),0) FROM catastro.construccion WHERE terreno_codigo=%s", cod)[0]
    prueba("F2 ficha: n construcciones = SQL", r["terreno"]["properties"]["n_construcciones"] == n_sql[0] == len(r["construcciones"]["features"]))
    prueba("F2 ficha: area construida = SQL", abs(r["terreno"]["properties"]["area_construida_m2"] - float(n_sql[1])) < 0.01)
    prueba("F2 ficha: municipio y geometria presentes", r["terreno"]["properties"]["municipio"] and r["terreno"]["geometry"]["type"] in ("Polygon", "MultiPolygon"))
    prueba("F2 ficha inexistente -> 404", c.get("/api/terrenos/123").status_code == 404)
    prueba("F2 codigo no numerico -> 422", c.get("/api/terrenos/abc").status_code == 422)

    # --- F3 consultas espaciales ------------------------------------
    centro = c.get(f"/api/terrenos/{cod}").json()["terreno"]["geometry"]["coordinates"]
    while isinstance(centro[0], list):
        centro = centro[0]
    lng, lat = centro[0], centro[1]
    r = c.get("/api/terrenos/en-punto", params={"lat": lat, "lng": lng})
    prueba("F3 terreno en punto: 200", r.status_code == 200, r.text[:100])
    esperado = sql("""SELECT codigo FROM catastro.terreno
                      WHERE ST_Intersects(geom, ST_Transform(ST_SetSRID(ST_MakePoint(%s,%s),4326),9377))
                      ORDER BY zona, codigo LIMIT 1""", lng, lat)[0][0]
    prueba("F3 terreno en punto = SQL independiente", r.json()["terreno"]["properties"]["codigo"] == esperado)
    prueba("F3 punto sin terreno (fuera del Quindio) -> 404", c.get("/api/terrenos/en-punto", params={"lat": 4.0, "lng": -70.0}).status_code == 404)

    for capa in ["terrenos", "construcciones", "vias"]:
        r = c.get("/api/cercanos", params={"lat": lat, "lng": lng, "radio": 120, "capa": capa}).json()
        tabla = {"terrenos": "terreno", "construcciones": "construccion", "vias": "nomenclatura_vial"}[capa]
        n_sql = sql(f"""SELECT count(*) FROM catastro.{tabla}
                        WHERE ST_DWithin(geom, ST_Transform(ST_SetSRID(ST_MakePoint(%s,%s),4326),9377), 120)""", lng, lat)[0][0]
        prueba(f"F3 cercanos {capa} a 120 m (total {r['metadatos']['total']}, devueltos {len(r['features'])}) = SQL ({n_sql})", r["metadatos"]["total"] == n_sql and len(r["features"]) == min(n_sql, 100) and n_sql > 0)
        d = [f["properties"]["distancia_m"] for f in r["features"]]
        prueba(f"F3 cercanos {capa}: ordenados por distancia y <= radio", d == sorted(d) and all(x <= 120 for x in d))
    prueba("F3 radio excesivo -> 422", c.get("/api/cercanos", params={"lat": lat, "lng": lng, "radio": 99999}).status_code == 422)
    prueba("F3 capa invalida -> 422", c.get("/api/cercanos", params={"lat": lat, "lng": lng, "capa": "x"}).status_code == 422)

    # --- F4 estadisticas ---------------------------------------------
    r = c.get("/api/estadisticas/63130").json()
    esp = sql("SELECT count(*) FILTER (WHERE zona='U'), count(*) FILTER (WHERE zona='R') FROM catastro.terreno WHERE municipio_codigo='63130'")[0]
    prueba("F4 terrenos urbanos/rurales de Calarca = SQL", (r["resumen"]["terrenos_urbanos"], r["resumen"]["terrenos_rurales"]) == esp)
    prueba("F4 construcciones por tipo suman el total",
           sum(x["cantidad"] for x in r["construcciones_por_tipo"]) == r["resumen"]["construcciones"])
    prueba("F4 manzanas mas ocupadas: 5 filas ordenadas",
           len(r["manzanas_mas_ocupadas"]) == 5 and [float(x["indice_ocupacion"]) for x in r["manzanas_mas_ocupadas"]] == sorted((float(x["indice_ocupacion"]) for x in r["manzanas_mas_ocupadas"]), reverse=True))
    prueba("F4 municipio inexistente -> 404", c.get("/api/estadisticas/99999").status_code == 404)
    prueba("F4 codigo mal formado -> 422", c.get("/api/estadisticas/12").status_code == 422)
    x, y = sql("SELECT ST_X(ST_Transform(ST_Centroid(geom),4326)), ST_Y(ST_Transform(ST_Centroid(geom),4326)) FROM catastro.manzana WHERE municipio_codigo='63130' LIMIT 1")[0]
    r = c.get("/api/capas/manzanas", params={"minx": x - 0.002, "miny": y - 0.002, "maxx": x + 0.002, "maxy": y + 0.002, "zoom": 17}).json()
    prueba("F4 manzanas traen indice_ocupacion", len(r["features"]) > 0 and all("indice_ocupacion" in f["properties"] for f in r["features"]))

print(f"\n{ok} correctas, {fallos} fallidas")
sys.exit(1 if fallos else 0)
