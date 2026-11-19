"""
Carga una geodatabase catastral departamental (IGAC / DANE, archivo 'XX.gdb')
en PostgreSQL/PostGIS, sobre el esquema creado por db/01_esquema.sql.

Uso:
    python scripts/cargar_gdb.py RUTA/63.gdb
    python scripts/cargar_gdb.py RUTA/05.gdb --departamento 05

La conexion se toma del archivo .env (variable DATABASE_URL) o del entorno.

Depuracion que aplica (esta documentada en el README):
  * Registros con el mismo CODIGO: se conserva el de FECHA_LOG mas reciente.
  * Geometrias invalidas: se reparan con make_valid y se fuerzan a 2D / Multi*.
  * Codigos de manzana o vereda genericos (terminan en 000000000000) o que no
    existen en su capa: la clave foranea queda en NULL.
  * Capas *_INFORMAL y U_BARRIO / U_SECTOR / R_SECTOR no se cargan.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import pyogrio
import psycopg
import shapely
from shapely.geometry import MultiLineString, MultiPolygon

SRID = 9377
RAIZ = Path(__file__).resolve().parent.parent


def cargar_env():
    """Lee .env sin depender de librerias extra."""
    archivo = RAIZ / ".env"
    if archivo.exists():
        for linea in archivo.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if linea and not linea.startswith("#") and "=" in linea:
                clave, valor = linea.split("=", 1)
                os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


def leer_capa(gdb, capa):
    df = pyogrio.read_dataframe(gdb, layer=capa)
    df.columns = [c.lower() for c in df.columns]
    return df


def a_multi(geom, tipo):
    """Repara, pasa a 2D y devuelve Multi{Polygon|LineString} (o None si no queda nada)."""
    if geom is None or geom.is_empty:
        return None
    geom = shapely.force_2d(geom)
    if not geom.is_valid:
        geom = shapely.make_valid(geom)
    partes = [p for p in shapely.get_parts(geom) if p.geom_type in (("Polygon",) if tipo == "poly" else ("LineString",))]
    # make_valid puede devolver una coleccion; se descartan las partes de otra dimension
    if not partes:
        return None
    return MultiPolygon(partes) if tipo == "poly" else MultiLineString(partes)


def ewkb(geom):
    return shapely.to_wkb(shapely.set_srid(geom, SRID), hex=True, include_srid=True)


def ultimo_por_codigo(df, columna="codigo"):
    """Entre registros con el mismo codigo se queda con el mas reciente."""
    df = df.sort_values("fecha_log", na_position="first")
    return df.drop_duplicates(subset=[columna], keep="last")


def codigo_municipio(df):
    return df["codigo_municipio"].astype(str).str.strip().str.zfill(5)


def limpiar(valor):
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto if texto and texto.lower() != "nan" else None


def copiar(cur, tabla, columnas, filas):
    n = 0
    with cur.copy(f"COPY {tabla} ({', '.join(columnas)}) FROM STDIN") as copy:
        for fila in filas:
            copy.write_row(fila)
            n += 1
    return n


def principal():
    cargar_env()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gdb", help="ruta de la carpeta .gdb")
    ap.add_argument("--departamento", help="codigo DANE del departamento (por defecto, el nombre de la carpeta)")
    ap.add_argument("--url", default=os.environ.get("DATABASE_URL"), help="cadena de conexion (por defecto DATABASE_URL)")
    args = ap.parse_args()
    if not args.url:
        sys.exit("Falta la conexion: define DATABASE_URL en .env (vea .env.example).")
    gdb = Path(args.gdb)
    if not gdb.exists():
        sys.exit(f"No existe {gdb}")
    dep = args.departamento or gdb.stem
    if len(dep) != 2 or not dep.isdigit():
        sys.exit("No pude deducir el departamento: use --departamento 63")

    t0 = time.time()
    divipola = json.loads((RAIZ / "datos" / "divipola.json").read_text(encoding="utf-8"))
    nombre_dep = divipola["departamentos"].get(dep)
    if not nombre_dep:
        sys.exit(f"Departamento {dep} no esta en datos/divipola.json")

    capas = {c for c, _ in pyogrio.list_layers(str(gdb))}
    print(f"Geodatabase {gdb.name}: {len(capas)} capas; departamento {dep} ({nombre_dep})")

    with psycopg.connect(args.url, autocommit=False) as con:
        cur = con.cursor()

        # --- division administrativa ---------------------------------
        cur.execute("INSERT INTO catastro.departamento (codigo, nombre) VALUES (%s, %s) ON CONFLICT DO NOTHING", (dep, nombre_dep))
        for m in divipola["municipios"]:
            if m["codigo"].startswith(dep):
                cur.execute(
                    "INSERT INTO catastro.municipio (codigo, departamento_codigo, nombre) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                    (m["codigo"], dep, m["nombre"]),
                )

        def municipios_con_datos(*dfs):
            usados = set()
            for d in dfs:
                usados |= set(codigo_municipio(d).unique())
            return usados

        # --- lectura y depuracion en memoria -------------------------
        print("Leyendo capas...")
        u_per = leer_capa(str(gdb), "U_PERIMETRO")
        r_ver = ultimo_por_codigo(leer_capa(str(gdb), "R_VEREDA"))
        u_man = ultimo_por_codigo(leer_capa(str(gdb), "U_MANZANA"))
        u_ter = ultimo_por_codigo(leer_capa(str(gdb), "U_TERRENO"))
        r_ter = ultimo_por_codigo(leer_capa(str(gdb), "R_TERRENO"))
        u_con = leer_capa(str(gdb), "U_CONSTRUCCION")
        r_con = leer_capa(str(gdb), "R_CONSTRUCCION")
        u_vial = leer_capa(str(gdb), "U_NOMENCLATURA_VIAL")
        r_vial = leer_capa(str(gdb), "R_NOMENCLATURA_VIAL")
        u_dom = leer_capa(str(gdb), "U_NOMENCLATURA_DOMICILIARIA")
        r_dom = leer_capa(str(gdb), "R_NOMENCLATURA_DOMICILIARIA")

        # municipios que realmente traen informacion
        con_datos = municipios_con_datos(u_per, r_ver, u_man, u_ter, r_ter)
        cur.execute("UPDATE catastro.municipio SET con_catastro = true WHERE codigo = ANY(%s)", (list(con_datos),))
        conocidos = {r[0] for r in cur.execute("SELECT codigo FROM catastro.municipio").fetchall()}
        desconocidos = con_datos - conocidos
        if desconocidos:
            sys.exit(f"Codigos de municipio sin catalogo DIVIPOLA: {sorted(desconocidos)}")

        # --- perimetros urbanos --------------------------------------
        filas = []
        for r in u_per.itertuples():
            g = a_multi(r.geometry, "poly")
            if g is not None:
                filas.append((str(r.globalid), str(r.codigo_municipio).zfill(5), limpiar(r.nombre_geografico), limpiar(r.tipo_avaluo), ewkb(g)))
        n = copiar(cur, "catastro.perimetro_urbano", ["globalid", "municipio_codigo", "nombre_geografico", "tipo_avaluo", "geom"], filas)
        print(f"  perimetro_urbano: {n}")

        # --- veredas -------------------------------------------------
        filas = []
        for r in r_ver.itertuples():
            g = a_multi(r.geometry, "poly")
            if g is not None:
                filas.append((r.codigo, str(r.codigo_municipio).zfill(5), limpiar(r.nombre) or "SIN NOMBRE", ewkb(g)))
        n = copiar(cur, "catastro.vereda", ["codigo", "municipio_codigo", "nombre", "geom"], filas)
        veredas = {f[0] for f in filas}
        print(f"  vereda: {n}")

        # --- manzanas ------------------------------------------------
        filas = []
        for r in u_man.itertuples():
            g = a_multi(r.geometry, "poly")
            if g is not None:
                filas.append((r.codigo, str(r.codigo_municipio).zfill(5), limpiar(r.barrio_codigo), ewkb(g)))
        n = copiar(cur, "catastro.manzana", ["codigo", "municipio_codigo", "barrio_codigo", "geom"], filas)
        manzanas = {f[0] for f in filas}
        print(f"  manzana: {n}")

        # --- terrenos (urbanos y rurales en una sola tabla) ---------
        candidatos = {}
        sin_manzana = sin_vereda = ceros = cruzados = 0
        for zona, df in (("U", u_ter), ("R", r_ter)):
            for r in df.itertuples():
                g = a_multi(r.geometry, "poly")
                if g is None:
                    continue
                if not r.codigo.strip("0"):          # codigo todo en ceros: registro sin identificar
                    ceros += 1
                    continue
                sub = None if r.numero_subterraneos != r.numero_subterraneos else int(r.numero_subterraneos)
                if zona == "U":
                    mz = r.manzana_codigo if r.manzana_codigo in manzanas else None
                    vd = None
                else:
                    mz = None
                    vd = r.vereda_codigo if r.vereda_codigo in veredas else None
                fila = (r.codigo, zona, str(r.codigo_municipio).zfill(5), mz, vd, sub, ewkb(g))
                previo = candidatos.get(r.codigo)
                if previo is not None:
                    cruzados += 1                      # mismo codigo en zona urbana y rural: gana el mas reciente
                    if previo[0] >= r.fecha_log:
                        continue
                candidatos[r.codigo] = (r.fecha_log, fila)
        filas = [f for _, f in candidatos.values()]
        sin_manzana = sum(1 for f in filas if f[1] == "U" and f[3] is None)
        sin_vereda = sum(1 for f in filas if f[1] == "R" and f[4] is None)
        n = copiar(cur, "catastro.terreno", ["codigo", "zona", "municipio_codigo", "manzana_codigo", "vereda_codigo", "num_subterraneos", "geom"], filas)
        terrenos = {f[0] for f in filas}
        print(f"  terreno: {n}  (sin manzana asignada: {sin_manzana}, sin vereda asignada: {sin_vereda}; descartados por codigo en ceros: {ceros}; codigos en ambas zonas: {cruzados})")

        # --- construcciones ------------------------------------------
        cur.execute("SELECT nombre, id FROM catastro.tipo_construccion")
        tipos = dict(cur.fetchall())
        filas = []
        vistos = set()
        repetidas = set()
        for zona, df in (("U", u_con), ("R", r_con)):
            for r in df.itertuples():
                g = a_multi(r.geometry, "poly")
                gid = str(r.globalid)
                if g is None or gid in vistos:
                    continue
                vistos.add(gid)
                huella = (r.codigo, limpiar(r.identificador), g.wkb)
                if huella in repetidas:                  # misma construccion registrada dos veces
                    continue
                repetidas.add(huella)
                tipo = tipos.get((limpiar(r.tipo_construccion) or "SIN DATO").upper(), tipos["SIN DATO"])
                pisos = None if r.numero_pisos != r.numero_pisos else int(r.numero_pisos)
                sot = None if r.numero_sotanos != r.numero_sotanos else int(r.numero_sotanos)
                if pisos is not None and not 0 <= pisos <= 100:
                    pisos = None
                tc = r.terreno_codigo if r.terreno_codigo in terrenos else None
                filas.append((gid, r.codigo, tc, str(r.codigo_municipio).zfill(5), zona, tipo,
                              limpiar(getattr(r, "tipo_dominio", None)), limpiar(r.identificador), pisos, sot, ewkb(g)))
        n = copiar(cur, "catastro.construccion",
                   ["globalid", "codigo", "terreno_codigo", "municipio_codigo", "zona", "tipo_construccion_id", "tipo_dominio", "identificador", "num_pisos", "num_sotanos", "geom"], filas)
        print(f"  construccion: {n}  (sin terreno asociado: {sum(1 for f in filas if f[2] is None)}; repetidas descartadas: {len(vistos) - len(filas)})")

        # --- nomenclatura vial ---------------------------------------
        filas = []
        for zona, df in (("U", u_vial), ("R", r_vial)):
            for r in df.itertuples():
                g = a_multi(r.geometry, "line")
                if g is not None:
                    filas.append((str(r.globalid), str(r.codigo_municipio).zfill(5), zona, limpiar(r.texto), ewkb(g)))
        n = copiar(cur, "catastro.nomenclatura_vial", ["globalid", "municipio_codigo", "zona", "texto", "geom"], filas)
        print(f"  nomenclatura_vial: {n}")

        # --- nomenclatura domiciliaria -------------------------------
        filas = []
        for zona, df in (("U", u_dom), ("R", r_dom)):
            for r in df.itertuples():
                g = a_multi(r.geometry, "line")
                if g is not None:
                    tc = r.terreno_codigo if r.terreno_codigo in terrenos else None
                    filas.append((str(r.globalid), str(r.codigo_municipio).zfill(5), zona, tc, limpiar(r.texto), ewkb(g)))
        n = copiar(cur, "catastro.nomenclatura_domiciliaria", ["globalid", "municipio_codigo", "zona", "terreno_codigo", "texto", "geom"], filas)
        print(f"  nomenclatura_domiciliaria: {n}")

        con.commit()
    print(f"Carga terminada en {time.time() - t0:.0f} s. Ejecute ahora db/02_post_carga.sql")


if __name__ == "__main__":
    principal()
