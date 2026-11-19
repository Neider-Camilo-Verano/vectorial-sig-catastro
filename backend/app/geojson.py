"""Construccion de las respuestas GeoJSON a partir de las filas que devuelve PostGIS."""
import json


def feature_collection(filas, extra=None):
    """Cada fila trae la columna 'geojson' (texto producido por ST_AsGeoJSON); el resto son atributos."""
    features = []
    for fila in filas:
        propiedades = {k: _plano(v) for k, v in fila.items() if k != "geojson"}
        geometria = json.loads(fila["geojson"]) if fila.get("geojson") else None
        features.append({"type": "Feature", "geometry": geometria, "properties": propiedades})
    resultado = {"type": "FeatureCollection", "features": features}
    if extra:
        resultado["metadatos"] = extra
    return resultado


def _plano(valor):
    """Convierte Decimal y fechas a tipos que JSON entienda."""
    from decimal import Decimal
    if isinstance(valor, Decimal):
        return float(valor)
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    return valor
