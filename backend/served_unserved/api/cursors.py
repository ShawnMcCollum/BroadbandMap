"""Signed, selection-bound keyset cursors; no transaction survives an HTTP request."""

from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import urlencode

from django.core import signing
from django.db.models import F, QuerySet
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request

from bdc.models import Release
from core.api.problems import DatasetChanged
from served_unserved.models import ServedStatus
from served_unserved.queries import location_order

SALT = "served_unserved.locations.v1"
SELECTION_KEYS = ("level", "code", "state", "flag", "status", "page_size")


def selection_context(params: dict[str, Any]) -> dict[str, Any]:
    return {name: params.get(name) for name in SELECTION_KEYS}


def invalid_cursor() -> ValidationError:
    return ValidationError({"cursor": "Invalid cursor or changed query context."})


@dataclass(frozen=True)
class LocationCursor:
    release_id: int
    generation: int
    position: int
    reverse: bool


def decode_cursor(params: dict[str, Any]) -> LocationCursor | None:
    """Pin an omitted release to the signed dates, before resolving latest.

    Explicit dates must agree. This also works if a caller keeps the cursor but
    omits the dates from a generated link after a newer release is loaded.
    """
    if "cursor" not in params:
        return None
    try:
        payload = signing.loads(params["cursor"], salt=SALT)
        if not isinstance(payload, dict) or payload.get("v") != 1:
            raise ValueError
        if payload["selection"] != selection_context(params):
            raise ValueError
        for name in ("release_id", "generation", "position"):
            if type(payload[name]) is not int or not -(2**63) <= payload[name] < 2**63:
                raise ValueError
        if payload["release_id"] < 1 or payload["generation"] < 1:
            raise ValueError
        if type(payload["reverse"]) is not bool:
            raise ValueError
        dates = {name: date.fromisoformat(payload[name]) for name in ("as_of", "processed_on")}
        if "as_of" in params and any(params[name] != value for name, value in dates.items()):
            raise ValueError
    except (signing.BadSignature, ValueError, KeyError, TypeError):
        raise invalid_cursor() from None
    params.update(dates)
    return LocationCursor(
        payload["release_id"], payload["generation"], payload["position"], payload["reverse"]
    )


def require_generation(release: Release | None, cursor: LocationCursor) -> Release:
    if (
        release is None
        or release.pk != cursor.release_id
        or release.data_generation != cursor.generation
    ):
        raise DatasetChanged()
    return release


def location_page(
    request: Request,
    rows: QuerySet[ServedStatus],
    release: Release,
    params: dict[str, Any],
    cursor: LocationCursor | None,
) -> dict[str, Any]:
    """Seek by the unique FCC ID and fetch at most page_size + 1 rows.

    The opposite link uses a bounded existence probe, never a filtered COUNT or
    an offset. Backward queries reverse the seek and restore ascending output.
    """
    reverse = cursor is not None and cursor.reverse
    selected = rows
    if cursor is not None:
        selected = selected.filter(
            **{"location_id__lt" if reverse else "location_id__gt": cursor.position}
        )
    page_size = params["page_size"]
    results = list(
        selected.order_by(location_order(reverse=reverse)).values(
            "location_id",
            "h3_res8",
            "any_100_20",
            "wired_100_20",
            "terrestrial_100_20",
            block_geoid=F("block_id"),
        )[: page_size + 1]
    )
    more = len(results) > page_size
    results = results[:page_size]
    if reverse:
        results.reverse()

    def link(position: int, *, backwards: bool) -> str:
        token = signing.dumps(
            {
                "v": 1,
                "selection": selection_context(params),
                "as_of": release.as_of.isoformat(),
                "processed_on": release.processed_on.isoformat(),
                "release_id": release.pk,
                "generation": release.data_generation,
                "position": position,
                "reverse": backwards,
            },
            salt=SALT,
            compress=True,
        )
        query = {
            **selection_context(params),
            "as_of": release.as_of,
            "processed_on": release.processed_on,
            "cursor": token,
        }
        return request.build_absolute_uri(
            request.path
            + "?"
            + urlencode({key: value for key, value in query.items() if value is not None})
        )

    next_link = previous_link = None
    if results:
        first, last = results[0]["location_id"], results[-1]["location_id"]
        has_previous = (
            more if reverse else cursor is not None and rows.filter(location_id__lt=first).exists()
        )
        has_next = rows.filter(location_id__gt=last).exists() if reverse else more
        if has_previous:
            previous_link = link(first, backwards=True)
        if has_next:
            next_link = link(last, backwards=False)
    return {"next": next_link, "previous": previous_link, "results": results}
