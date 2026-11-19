"""
API del visor catastral (FastAPI + Psycopg + PostgreSQL/PostGIS).

Arranque (desde la raiz del repositorio):
    uvicorn backend.app.main:app --port 8000
Endpoints principales: ver README.md, seccion "Funcionalidades y endpoints".
"""
import psycopg
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import db, sql
from .config import FRONTEND
from .geojson import feature_collection

app = FastAPI(title="VECTORIAL - Visor catastral SIG Web", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])


@app.exception_handler(psycopg.OperationalError)
def sin_base_de_datos(request, exc):
    """Si PostgreSQL no responde, el visor recibe un mensaje claro y no un error 500 generico."""
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=503, content={"detail": "No hay conexión con PostgreSQL. Verifique que el servicio esté encendido y que .env tenga la conexión correcta."})


@app.on_event("shutdown")
def al_cerrar():
    db.cerrar()


# ---------------------------------------------------------------------
# Estado de la conexion (evidencia de que los datos salen de PostGIS)
# ---------------------------------------------------------------------
@app.get("/api/salud")
def salud():
    """Version de PostgreSQL y PostGIS y numero de filas de cada tabla."""
    info = db.una_fila(sql.SALUD)
    tablas = {f["tabla"]: f["filas"] for f in db.consultar(sql.CONTEO_TABLAS)}
    return {"estado": "ok", **info, "tablas": tablas}


# ---------------------------------------------------------------------
# F1. Visualizacion geografica
# ---------------------------------------------------------------------
@app.get("/api/municipios")
def municipios():
    """Capa de municipios (poligonos) con conteos por tabla relacionada."""
    return feature_collection(db.consultar(sql.MUNICIPIOS))


def _tolerancia(zoom):
    """Tolerancia de simplificacion en metros segun el nivel de zoom (sin simplificar desde el 17)."""
    if zoom >= 17:
        return 0
    return round(156543.03 / (2 ** zoom) * 0.6, 2)


@app.get("/api/capas/{capa}")
def capa(
    capa: str,
    minx: float = Query(..., ge=-80, le=-66, description="longitud oeste"),
    miny: float = Query(..., ge=-5, le=14, description="latitud sur"),
    maxx: float = Query(..., ge=-80, le=-66, description="longitud este"),
    maxy: float = Query(..., ge=-5, le=14, description="latitud norte"),
    zoom: int = Query(14, ge=0, le=22),
    municipio: str | None = Query(None, pattern=r"^\d{5}$"),
    limite: int = Query(3000, ge=1, le=6000),
):
    """Elementos de una capa catastral dentro de la ventana del mapa (bbox en grados)."""
    if capa not in sql.CAPAS:
        raise HTTPException(404, f"Capa desconocida. Opciones: {', '.join(sql.CAPAS)}")
    if minx >= maxx or miny >= maxy:
        raise HTTPException(422, "La ventana es invalida: minx < maxx y miny < maxy.")
    filas = db.consultar(sql.sql_capa(capa), {"minx": minx, "miny": miny, "maxx": maxx, "maxy": maxy,
                                              "tol": _tolerancia(zoom), "municipio": municipio, "limite": limite})
    return feature_collection(filas, {"capa": capa, "total": len(filas), "limite": limite, "truncado": len(filas) >= limite})


# ---------------------------------------------------------------------
# F2. Consulta de atributos
# ---------------------------------------------------------------------
@app.get("/api/buscar")
def buscar(
    q: str = Query(..., min_length=2, max_length=60),
    tipo: str = Query("todo", pattern="^(todo|terreno|vereda|via|direccion)$"),
    limite: int = Query(10, ge=1, le=30),
):
    """Busca terrenos por codigo, veredas por nombre, vias y direcciones por texto."""
    q = q.strip()
    contiene = f"%{q}%"
    resultados = []
    if tipo in ("todo", "terreno") and q.isdigit():
        resultados += db.consultar(sql.BUSCAR_TERRENO, {"patron": f"{q}%", "limite": limite})
    if tipo in ("todo", "vereda"):
        resultados += db.consultar(sql.BUSCAR_VEREDA, {"contiene": contiene, "q": q, "limite": limite})
    if tipo in ("todo", "via"):
        resultados += db.consultar(sql.BUSCAR_VIA, {"contiene": contiene, "q": q, "limite": limite})
    if tipo in ("todo", "direccion"):
        resultados += db.consultar(sql.BUSCAR_DIRECCION, {"contiene": contiene, "q": q, "limite": limite})
    return {"consulta": q, "total": len(resultados), "resultados": resultados}


@app.get("/api/terrenos/en-punto")
def terreno_en_punto(lat: float = Query(..., ge=-5, le=14), lng: float = Query(..., ge=-80, le=-66)):
    """F3: terreno que contiene el punto indicado (ST_Intersects en EPSG:9377)."""
    fila = db.una_fila(sql.TERRENO_EN_PUNTO, {"lat": lat, "lng": lng})
    if not fila:
        raise HTTPException(404, "No hay ningún terreno catastral en ese punto.")
    return ficha(fila["codigo"])


@app.get("/api/terrenos/{codigo}")
def ficha(codigo: str):
    """F2: ficha del terreno con su manzana/vereda, sus construcciones y sus direcciones."""
    if not codigo.isdigit() or len(codigo) > 30:
        raise HTTPException(422, "El código del terreno debe ser numérico (máximo 30 dígitos).")
    t = db.una_fila(sql.FICHA_TERRENO, {"codigo": codigo})
    if not t:
        raise HTTPException(404, "No existe un terreno con ese código.")
    construcciones = db.consultar(sql.CONSTRUCCIONES_DE_TERRENO, {"codigo": codigo})
    direcciones = [f["texto"] for f in db.consultar(sql.DIRECCIONES_DE_TERRENO, {"codigo": codigo}) if f["texto"]]
    terreno = feature_collection([t])["features"][0]
    return {
        "terreno": terreno,
        "construcciones": feature_collection(construcciones),
        "direcciones": direcciones,
    }


# ---------------------------------------------------------------------
# F3. Consulta espacial por distancia
# ---------------------------------------------------------------------
@app.get("/api/cercanos")
def cercanos(
    lat: float = Query(..., ge=-5, le=14),
    lng: float = Query(..., ge=-80, le=-66),
    radio: float = Query(150, gt=0, le=2000, description="radio en metros"),
    capa: str = Query("construcciones", pattern="^(terrenos|construcciones|vias)$"),
    limite: int = Query(100, ge=1, le=500),
):
    """Elementos a menos de `radio` metros del punto (ST_DWithin sobre EPSG:9377, unidad = metro)."""
    filas = db.consultar(sql.sql_cercanos(capa), {"lat": lat, "lng": lng, "radio": radio, "limite": limite})
    total = filas[0]["total_en_radio"] if filas else 0   # total real, aunque se devuelvan solo `limite`
    for fila in filas:
        del fila["total_en_radio"]
    return feature_collection(filas, {"capa": capa, "radio_m": radio, "total": total, "devueltos": len(filas)})


# ---------------------------------------------------------------------
# F4. Estadisticas por municipio y ocupacion de manzanas
# ---------------------------------------------------------------------
@app.get("/api/estadisticas/{codigo}")
def estadisticas(codigo: str):
    """Resumen catastral de un municipio calculado con agregaciones sobre varias tablas."""
    if not (codigo.isdigit() and len(codigo) == 5):
        raise HTTPException(422, "El código del municipio tiene 5 dígitos (por ejemplo 63130).")
    resumen = db.una_fila(sql.ESTADISTICAS_MUNICIPIO, {"codigo": codigo})
    if not resumen:
        raise HTTPException(404, "Municipio no encontrado.")
    return {
        "resumen": resumen,
        "construcciones_por_tipo": db.consultar(sql.CONSTRUCCIONES_POR_TIPO, {"codigo": codigo}),
        "construcciones_por_pisos": db.consultar(sql.CONSTRUCCIONES_POR_PISOS, {"codigo": codigo}),
        "manzanas_mas_ocupadas": db.consultar(sql.TOP_MANZANAS_OCUPACION, {"codigo": codigo}),
    }


# El visor (HTML/CSS/JS) se sirve desde la misma API: se monta al final para no tapar /api
app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
