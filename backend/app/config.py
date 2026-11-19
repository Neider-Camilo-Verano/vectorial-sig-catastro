"""Configuracion: la conexion a PostgreSQL se lee del archivo .env (que NO se sube a GitHub)."""
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent


def cargar_env():
    archivo = RAIZ / ".env"
    if archivo.exists():
        for linea in archivo.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if linea and not linea.startswith("#") and "=" in linea:
                clave, valor = linea.split("=", 1)
                os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


cargar_env()

DATABASE_URL = os.environ.get("DATABASE_URL", "")
FRONTEND = RAIZ / "frontend"
