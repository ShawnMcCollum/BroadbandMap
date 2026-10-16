"""Resolve stable public dates and materialize geometry-free release coverage."""

from typing import Any

from rest_framework.exceptions import NotFound

from bdc.models import Release
from served_unserved.release_states import states_in_release


def resolve_release(params: dict[str, Any]) -> Release:
    releases = Release.objects.all()
    if "as_of" in params:
        releases = releases.filter(as_of=params["as_of"], processed_on=params["processed_on"])
    release = releases.first()
    if release is None:
        raise NotFound()
    return release


def release_metadata(release: Release) -> dict[str, Any]:
    return {
        "filing_period": release.filing_period,
        "as_of": release.as_of,
        "processed_on": release.processed_on,
        "states": [
            {"code": state.geoid, "name": state.name, "abbreviation": state.abbreviation}
            for state in states_in_release(release)
        ],
    }
