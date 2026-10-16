"""Stored summary reads; never reaggregate the source locations for counts."""

from typing import Any

from django.db.models import QuerySet, Sum

from bdc.models import Release
from core.api.problems import ServiceUnavailable
from served_unserved.models import Rollup, RollupLevel
from served_unserved.rollups import COUNT_FIELDS, statuses_in


def summary_rows(release: Release, params: dict[str, Any]) -> QuerySet[Rollup, dict[str, Any]]:
    rows = Rollup.objects.filter(release=release, level=params["level"]).order_by()
    if "state" in params:
        rows = rows.filter(state_id=params["state"])
    if "code" in params:
        rows = rows.filter(code=params["code"])
    return (
        rows.values("code")
        .annotate(**{field: Sum(field) for field in COUNT_FIELDS})
        .order_by("code")
    )


def summary_coverage(
    release: Release, params: dict[str, Any], count: int, state_codes: set[str]
) -> str:
    if "code" not in params:
        return "stored_rollups_only"
    if count:
        return "observed"
    statuses = statuses_in(release, params["level"], params["code"])
    if "state" in params:
        statuses = statuses.filter(block_id__startswith=params["state"])
    if statuses.exists():
        raise ServiceUnavailable()
    area_state = params.get("state")
    if params["level"] != RollupLevel.H3_RES8:
        area_state = params["code"][:2]
    if area_state is not None and area_state not in state_codes:
        return "outside_release_coverage"
    return "no_observations"
