# ruff: noqa: RUF012 -- DRF view configuration uses class-level lists.
"""Public release catalog."""

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from bdc.api.queries import release_metadata
from bdc.api.serializers import ReleasePage
from bdc.models import Release
from core.api.pagination import PageQuery, page_bounds, page_metadata
from core.api.schema import problem_responses
from core.api.transactions import read_snapshot


class Releases(APIView):
    authentication_classes: list[type] = []
    permission_classes = [AllowAny]
    http_method_names = ["get", "head", "options"]

    @extend_schema(
        operation_id="releases_list",
        description="Loaded releases ordered by descending data period, then processing date. "
        "Each release discloses its actual states; dates do not imply nationwide coverage.",
        parameters=[PageQuery],
        responses={200: ReleasePage, **problem_responses(400, 404, 405, 406, 500)},
        auth=[],
    )
    def get(self, request: Request) -> Response:
        query = PageQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        with read_snapshot():
            releases = Release.objects.all()
            count = releases.count()
            start, end = page_bounds(count, params)
            payload = {
                **page_metadata(request, count, params),
                "results": [release_metadata(release) for release in releases[start:end]],
            }
            return Response(ReleasePage(payload).data, headers={"Cache-Control": "no-store"})
