"""
Genera la evidencia de integracion: llama a la API (HTTP) y ejecuta, aparte, la
misma consulta SQL directamente en PostgreSQL, y compara los resultados.

Requisitos: el servidor encendido (iniciar.bat) y DATABASE_URL en .env.
    python scripts/verificar_api_vs_sql.py
El informe se guarda en docs/evidencias/verificacion.txt
"""
import json
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

import psycopg

RAIZ = Path(__file__).resolve().parent.parent
for linea in (RAIZ / ".env").read_text(encoding="utf-8").splitlines() if (RAIZ / ".env").exists() else []:
    if "=" in linea and not linea.startswith("#"):
        k, v = linea.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())
URL_BD = os.environ.get("DATABASE_URL")
API = os.environ.get("API_URL", "http://127.0.0.1:8000")
if not URL_BD:
    sys.exit("Falta DATABASE_URL en .env")

LAT, LNG = 4.52896, -75.64182          # punto de prueba en Calarca
BOX = (-75.6425, 4.5285, -75.6410, 4.5300)
informe = []
fallos = 0


def api(ruta):
    with urllib.request.urlopen(API + ruta, timeout=30) as r:
        return json.load(r)


def sql(consulta, *params):
    with psycopg.connect(URL_BD) as con:
        return con.execute(consulta, params or None).fetchall()


def comparar(titulo, endpoint, consulta, valor_api, valor_sql):
    global fallos
    igual = valor_api == valor_sql
    fallos += not igual
    informe.append(f"[{'COINCIDE' if igual else 'DIFERENTE'}] {titulo}\n"
                   f"   HTTP : GET {endpoint}\n   SQL  : {' '.join(consulta.split())}\n"
                   f"   API devuelve : {valor_api}\n   SQL devuelve : {valor_sql}\n")


informe.append(f"Verificacion API vs SQL - {datetime.now():%Y-%m-%d %H:%M}\n" + "=" * 70 + "\n")
s = api("/api/salud")
informe.append(f"Base: {s['base']}\n{s['postgresql']}\nPostGIS {s['postgis']}\n")

c = "SELECT count(*) FROM catastro.terreno"
comparar("Terrenos en la base", "/api/salud", c, s["tablas"]["terreno"], sql(c)[0][0])

c = "SELECT count(*) FROM catastro.terreno WHERE municipio_codigo = '63130'"
m = {f["properties"]["codigo"]: f["properties"] for f in api("/api/municipios")["features"]}
comparar("F1 terrenos de Calarca (capa de municipios)", "/api/municipios", c, m["63130"]["n_terrenos"], sql(c)[0][0])

c = ("SELECT count(*) FROM catastro.terreno WHERE geom && "
     "ST_Transform(ST_MakeEnvelope(%s,%s,%s,%s,4326),9377)")
r = api("/api/capas/terrenos?minx=%s&miny=%s&maxx=%s&maxy=%s&zoom=17&limite=6000" % BOX)
comparar("F1 terrenos dentro de la ventana", "/api/capas/terrenos?minx=..&zoom=17", c, len(r["features"]), sql(c, *BOX)[0][0])

c = "SELECT count(*) FROM catastro.construccion WHERE terreno_codigo = '631300100000001430008000000000'"
f = api("/api/terrenos/631300100000001430008000000000")
comparar("F2 construcciones del terreno 631300100000001430008000000000", "/api/terrenos/6313001000000014300080000000000", c,
         f["terreno"]["properties"]["n_construcciones"], sql(c)[0][0])

c = "SELECT count(*) FROM catastro.vereda WHERE nombre ILIKE '%Pedregales%'"
b = api("/api/buscar?q=Pedregales&tipo=vereda")
comparar("F2 veredas llamadas Pedregales", "/api/buscar?q=Pedregales&tipo=vereda", c, b["total"], sql(c)[0][0])

c = ("SELECT codigo FROM catastro.terreno WHERE ST_Intersects(geom, "
     "ST_Transform(ST_SetSRID(ST_MakePoint(%s,%s),4326),9377)) ORDER BY zona, codigo LIMIT 1")
r = api(f"/api/terrenos/en-punto?lat={LAT}&lng={LNG}")
comparar("F3 terreno que contiene el punto (ST_Intersects)", f"/api/terrenos/en-punto?lat={LAT}&lng={LNG}", c,
         r["terreno"]["properties"]["codigo"], sql(c, LNG, LAT)[0][0])

c = ("SELECT count(*) FROM catastro.construccion WHERE ST_DWithin(geom, "
     "ST_Transform(ST_SetSRID(ST_MakePoint(%s,%s),4326),9377), 100)")
r = api(f"/api/cercanos?lat={LAT}&lng={LNG}&radio=100&capa=construcciones")
comparar("F3 construcciones a menos de 100 m (ST_DWithin, metros)", f"/api/cercanos?lat={LAT}&lng={LNG}&radio=100&capa=construcciones", c,
         r["metadatos"]["total"], sql(c, LNG, LAT)[0][0])

c = "SELECT count(*) FROM catastro.construccion WHERE municipio_codigo = '63130'"
e = api("/api/estadisticas/63130")
comparar("F4 construcciones de Calarca (estadisticas)", "/api/estadisticas/63130", c, e["resumen"]["construcciones"], sql(c)[0][0])

informe.append("=" * 70 + f"\nResultado: {len(informe) - 2 - fallos} coinciden, {fallos} difieren")
texto = "\n".join(informe)
print(texto)
(RAIZ / "docs" / "evidencias").mkdir(parents=True, exist_ok=True)
(RAIZ / "docs" / "evidencias" / "verificacion.txt").write_text(texto, encoding="utf-8")
sys.exit(1 if fallos else 0)
