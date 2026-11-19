"""Conexion con PostgreSQL mediante Psycopg 3 y un pool de conexiones."""
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import DATABASE_URL

_pool = None


def pool():
    """Crea el pool la primera vez que se necesita."""
    global _pool
    if _pool is None:
        if not DATABASE_URL:
            raise RuntimeError("Falta DATABASE_URL: copie .env.example a .env y complete la conexion.")
        _pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=8, kwargs={"row_factory": dict_row}, open=True)
    return _pool


def cerrar():
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def consultar(sql, parametros=None):
    """Ejecuta una consulta con parametros (%s o %(nombre)s) y devuelve una lista de diccionarios.
    Los valores del usuario NUNCA se concatenan en el SQL: Psycopg los envia aparte."""
    with pool().connection() as con:
        return con.execute(sql, parametros).fetchall()


def una_fila(sql, parametros=None):
    filas = consultar(sql, parametros)
    return filas[0] if filas else None
