"""GeoJSON uses the standard JSON encoder with its registered media type."""

from rest_framework.renderers import JSONRenderer


class GeoJSONRenderer(JSONRenderer):
    media_type = "application/geo+json"
    format = "geojson"
