# ruff: noqa: RUF012 -- DRF view configuration uses class-level lists.
"""Read-only rollup orchestration."""

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from bdc.api.queries import release_metadata, resolve_release
from bdc.models import Release
from core.api.pagination import page_bounds, page_metadata
from core.api.schema import problem_responses
from core.api.transactions import read_snapshot
from geography.api.queries import require_area, require_state
from served_unserved.api.cursors import decode_cursor, location_page, require_generation
from served_unserved.api.serializers import LocationPage, LocationQuery, RollupPage, RollupQuery
from served_unserved.models import RollupLevel
from served_unserved.queries import location_coverage, location_rows, summary_coverage, summary_rows


class Rollups(APIView):
    authentication_classes: list[type] = []
    permission_classes = [AllowAny]
    http_method_names = ["get", "head", "options"]

    @extend_schema(
        operation_id="served_unserved_rollups_list",
        description="Stored 100/20 Mbps counts ordered by area code. H3 rows sum contributing "
        "states before pagination. Geometry is separate. Links pin resolved release dates, "
        "but separate pages are fresh reads and may change after replacement or rebuilding.",
        parameters=[RollupQuery],
        responses={200: RollupPage, **problem_responses(400, 404, 405, 406, 500, 503)},
        auth=[],
    )
    def get(self, request: Request) -> Response:
        query = RollupQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        with read_snapshot():
            release = resolve_release(params)
            if "state" in params:
                require_state(params["state"])
            if "code" in params:
                require_area(params["level"], params["code"])
            metadata = release_metadata(release)
            rows = summary_rows(release, params)
            count = rows.count()
            coverage = summary_coverage(
                release, params, count, {state["code"] for state in metadata["states"]}
            )
            start, end = page_bounds(count, params)
            results = list(rows[start:end])
            for row in results:
                row["served"] = row[params["flag"] + "_100_20"]
                row["not_served"] = row["locations"] - row["served"]
            links = {**params, "as_of": release.as_of, "processed_on": release.processed_on}
            payload = {
                **page_metadata(request, count, links),
                "results": results,
                "release": metadata,
                "selection": {
                    name: params.get(name) for name in ("level", "code", "state", "flag")
                },
                "threshold": {"download_mbps": 100, "upload_mbps": 20},
                "boundary_vintage": None if params["level"] == RollupLevel.H3_RES8 else 2020,
                "summary_coverage": coverage,
            }
            return Response(RollupPage(payload).data, headers={"Cache-Control": "no-store"})


class Locations(APIView):
    authentication_classes: list[type] = []
    permission_classes = [AllowAny]
    http_method_names = ["get", "head", "options"]

    @extend_schema(
        operation_id="served_unserved_locations_list",
        description="Locations in one area, ordered by ascending FCC location_id. "
        "Signed cursors pin release dates, selection, page size, and release-wide generation. "
        "A committed load, state deletion, or rollup rebuild requires restarting without a "
        "cursor (409 dataset_changed). No total count or point geometries are returned. "
        "area_coverage describes observations before the optional status filter.",
        parameters=[LocationQuery],
        responses={200: LocationPage, **problem_responses(400, 404, 405, 406, 409, 500)},
        auth=[],
    )
    def get(self, request: Request) -> Response:
        query = LocationQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        cursor = decode_cursor(params)
        with read_snapshot():
            if cursor is None:
                release = resolve_release(params)
            else:
                release = require_generation(
                    Release.objects.filter(
                        as_of=params["as_of"], processed_on=params["processed_on"]
                    ).first(),
                    cursor,
                )
            if "state" in params:
                require_state(params["state"])
            require_area(params["level"], params["code"])
            metadata = release_metadata(release)
            rows = location_rows(release, params)
            coverage = location_coverage(
                params, {state["code"] for state in metadata["states"]}, rows.exists()
            )
            if "status" in params:
                rows = rows.filter(**{params["flag"] + "_100_20": params["status"] == "served"})
            payload = {
                **location_page(request, rows, release, params, cursor),
                "release": metadata,
                "selection": {
                    name: params.get(name) for name in ("level", "code", "state", "flag", "status")
                },
                "threshold": {"download_mbps": 100, "upload_mbps": 20},
                "boundary_vintage": None if params["level"] == RollupLevel.H3_RES8 else 2020,
                "area_coverage": coverage,
            }
            return Response(LocationPage(payload).data, headers={"Cache-Control": "no-store"})
