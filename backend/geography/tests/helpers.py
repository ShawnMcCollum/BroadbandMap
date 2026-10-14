from typing import Any

from django.contrib.gis.geos import MultiPolygon, Point, Polygon


def square(lon: float, lat: float, size: float = 0.01) -> MultiPolygon:
    """A one-square MultiPolygon in WGS84 with its lower-left corner at (lon, lat)."""
    return MultiPolygon(Polygon.from_bbox((lon, lat, lon + size, lat + size)), srid=4326)


def boundary_fields() -> dict[str, Any]:
    """The fields every boundary model shares, with fixed test values."""
    return {
        "land_area_m2": 1000,
        "water_area_m2": 0,
        "internal_point": Point(-83.0, 40.0, srid=4326),
        "geom": square(-83.0, 40.0),
    }
