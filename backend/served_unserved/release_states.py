"""Which states a release holds, and removing one state from a release (ADR 0017).

A release is national, and each data load adds one state's statuses to it. A state is in a release
when the release has a status in one of the state's blocks, whose GEOIDs start with its FIPS code.
"""

from bdc.models import Release
from geography.models import State
from served_unserved.models import Rollup, ServedStatus


def holds_state(release: Release, state_fips: str) -> bool:
    """Whether the release has a status in the state: one lookup in servedstatus_release_block."""
    statuses = ServedStatus.objects.filter(release=release, block__geoid__startswith=state_fips)
    return statuses.exists()


def states_in_release(release: Release) -> list[State]:
    """The loaded states the release has statuses in, in GEOID order, without their geometry."""
    states = State.objects.only("geoid", "name", "abbreviation")
    return [state for state in states if holds_state(release, state.geoid)]


def delete_state(release: Release, state_fips: str) -> tuple[int, int]:
    """Delete the release's statuses and rollups in the state; return how many of each.

    The release itself, and its rows in other states, are kept.
    """
    statuses, _ = ServedStatus.objects.filter(
        release=release, block__geoid__startswith=state_fips
    ).delete()
    rollups, _ = Rollup.objects.filter(release=release, state_id=state_fips).delete()
    return statuses, rollups
