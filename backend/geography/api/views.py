# ruff: noqa: RUF012 -- DRF view configuration uses class-level lists.
"""County polygons with independent feature and payload limits."""

import json
from typing import Any

from django.db.models import Sum
from django.db.models.functions import Length
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import ErrorDetail, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api.pagination import page_bounds, page_metadata
from core.api.schema import problem_responses
from core.api.transactions import read_snapshot
from geography.api.queries import county_geometries, require_state
from geography.api.renderers import GeoJSONRenderer
from geography.api.serializers import CountyCollection, CountyQuery

MAX_GEOMETRY_BYTES = 5 * 1024 * 1024


def check_payload_size(size: int) -> None:
    if size > MAX_GEOMETRY_BYTES:
        raise ValidationError(
            {
                "page_size": [
                    ErrorDetail(
                        "Geometry response is too large; request fewer features.",
                        code="geometry_payload_too_large",
                    )
                ]
            }
        )


class Counties(APIView):
    authentication_classes: list[type] = []
    permission_classes = [AllowAny]
    http_method_names = ["get", "head", "options"]
    renderer_classes = [GeoJSONRenderer]

    @extend_schema(
        operation_id="county_geojson_list",
        description="RFC 7946 county MultiPolygons in WGS84, ordered by GEOID. Feature IDs "
        "match summary codes. Boundaries do not assert release coverage. Maximum 100 features "
        "and 5 MiB per response; request fewer features if the byte limit is exceeded.",
        parameters=[CountyQuery],
        responses={
            (200, "application/geo+json"): CountyCollection,
            **problem_responses(400, 404, 405, 406, 500),
        },
        auth=[],
    )
    def get(self, request: Request) -> Response:
        query = CountyQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        with read_snapshot():
            require_state(params["state"])
            counties = county_geometries(params["state"])
            count = counties.count()
            start, end = page_bounds(count, params)
            page = counties.values("geoid", "name", "geojson")[start:end]
            # GeoJSON geometry contains only ASCII, so character length equals bytes.
            # Aggregate in PostgreSQL before transferring any potentially large polygon.
            check_payload_size(page.aggregate(size=Sum(Length("geojson")))["size"] or 0)
            features: list[dict[str, Any]] = [
                {
                    "type": "Feature",
                    "id": row["geoid"],
                    "properties": {"code": row["geoid"], "name": row["name"]},
                    "geometry": json.loads(row["geojson"]),
                }
                for row in page
            ]
            payload = {
                **page_metadata(request, count, params),
                "type": "FeatureCollection",
                "features": features,
                "state": params["state"],
                "boundary_vintage": 2020,
            }
            data = CountyCollection(payload).data
            # Do not allow Accept's optional indent parameter to bypass the byte cap.
            renderer_context = self.get_renderer_context()
            check_payload_size(
                len(GeoJSONRenderer().render(data, request.accepted_media_type, renderer_context))
            )
            return Response(data, headers={"Cache-Control": "no-store"})
