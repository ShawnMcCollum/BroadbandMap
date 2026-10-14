from datetime import date

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from bdc.models import Location, Release
from served_unserved.models import ServedStatus

# Flags are written (any, wired, terrestrial). Wired implies terrestrial, which
# implies any.
ACCEPTED = ["000", "100", "101", "111"]
REJECTED = ["001", "010", "011", "110"]


def make_status(release: Release, location: Location, flags: str = "111") -> ServedStatus:
    return ServedStatus.objects.create(
        release=release,
        location=location,
        any_100_20=flags[0] == "1",
        wired_100_20=flags[1] == "1",
        terrestrial_100_20=flags[2] == "1",
    )


@pytest.mark.parametrize("flags", ACCEPTED)
def test_consistent_flags_are_accepted(release: Release, location: Location, flags: str) -> None:
    make_status(release, location, flags)

    assert ServedStatus.objects.count() == 1


@pytest.mark.parametrize("flags", REJECTED)
def test_inconsistent_flags_are_rejected(release: Release, location: Location, flags: str) -> None:
    with pytest.raises(IntegrityError, match="_implies_"), transaction.atomic():
        make_status(release, location, flags)


def test_location_appears_once_per_release(
    release: Release, location: Location, served_status: ServedStatus
) -> None:
    with (
        pytest.raises(IntegrityError, match="served_unserved_unique_location_per_release"),
        transaction.atomic(),
    ):
        make_status(release, location)


def test_location_can_appear_in_two_releases(
    release: Release, location: Location, served_status: ServedStatus
) -> None:
    other = Release.objects.create(
        filing_period="J26", as_of=date(2026, 6, 30), processed_on=date(2026, 9, 29)
    )

    make_status(other, location)

    assert ServedStatus.objects.filter(location=location).count() == 2


def test_deleting_a_release_deletes_its_statuses(
    release: Release, served_status: ServedStatus
) -> None:
    release.delete()

    assert ServedStatus.objects.count() == 0


def test_location_with_statuses_cannot_be_deleted(
    location: Location, served_status: ServedStatus
) -> None:
    with pytest.raises(ProtectedError):
        location.delete()
