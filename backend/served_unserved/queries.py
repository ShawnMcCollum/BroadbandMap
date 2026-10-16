"""Stored summary reads; never reaggregate the source locations for counts."""

from typing import Any

from django.db.models import F, QuerySet, Sum
from django.db.models.expressions import OrderBy

from bdc.models import Release
from core.api.problems import ServiceUnavailable
from served_unserved.models import Rollup, RollupLevel, ServedStatus
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
    statuses = location_rows(release, params)
    if statuses.exists():
        raise ServiceUnavailable()
    area_state = params.get("state")
    if params["level"] != RollupLevel.H3_RES8:
        area_state = params["code"][:2]
    if area_state is not None and area_state not in state_codes:
        return "outside_release_coverage"
    return "no_observations"


def location_rows(release: Release, params: dict[str, Any]) -> QuerySet[ServedStatus]:
    """Use the rollups' membership rules, including assigned place/subdivision keys."""
    rows = statuses_in(release, params["level"], params["code"])
    if "state" in params:
        rows = rows.filter(block__geoid__startswith=params["state"])
    return rows


def location_coverage(params: dict[str, Any], state_codes: set[str], observed: bool) -> str:
    if observed:
        return "observed"
    state = params.get("state")
    if params["level"] != RollupLevel.H3_RES8:
        state = params["code"][:2]
    if state is not None and state not in state_codes:
        return "outside_release_coverage"
    return "no_observations"


def location_order(*, reverse: bool = False) -> OrderBy:
    """Sort geographically filtered candidates, preserving numeric FCC ID order.

    Ordering directly by the indexed ID let PostgreSQL assume the first matches
    were nearby: Ohio county/place first pages scanned millions of unrelated IDs.
    The exact bigint identity expression prevents that ordered-index shortcut;
    geographic indexes filter candidates before a bounded top-N sort instead.
    Range predicates still use the original ID. See ADR 0019 and its profiling.
    """
    expression = F("location_id") + 0
    return expression.desc() if reverse else expression.asc()
