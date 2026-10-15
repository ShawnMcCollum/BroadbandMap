from datetime import date

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from bdc.models import Location, Release
from served_unserved.models import Rollup, ServedStatus

# Flags are written (any, wired, terrestrial). Wired implies terrestrial, which
# implies any.
ACCEPTED = ["000", "100", "101", "111"]
REJECTED = ["001", "010", "011", "110"]

VALID_ROLLUP = {
    "level": "county",
    "code": "39049",
    "locations": 10,
    "any_100_20": 8,
    "terrestrial_100_20": 6,
    "wired_100_20": 4,
}
# (changes to VALID_ROLLUP, name of the constraint that rejects the result)
REJECTED_ROLLUPS = [
    ({"code": "3904"}, "served_unserved_rollup_code_fits_level"),
    ({"code": "390490"}, "served_unserved_rollup_code_fits_level"),
    ({"code": "3904a"}, "served_unserved_rollup_code_fits_level"),
    ({"level": "tract", "code": "39049"}, "served_unserved_rollup_code_fits_level"),
    ({"level": "block_group", "code": "39049000110"}, "served_unserved_rollup_code_fits_level"),
    ({"level": "block", "code": "39049000110100"}, "served_unserved_rollup_code_fits_level"),
    ({"level": "block", "code": "882a91ae3bfffff"}, "served_unserved_rollup_code_fits_level"),
    ({"level": "h3_res8", "code": "882A91AE3BFFFFF"}, "served_unserved_rollup_code_fits_level"),
    ({"level": "h3_res8", "code": "882a91ae3bffff"}, "served_unserved_rollup_code_fits_level"),
    ({"level": "state", "code": "39"}, "served_unserved_rollup_code_fits_level"),
    ({"level": "place", "code": "391800"}, "served_unserved_rollup_code_fits_level"),
    (
        {"level": "county_subdivision", "code": "390491800"},
        "served_unserved_rollup_code_fits_level",
    ),
    (
        {"locations": 0, "any_100_20": 0, "terrestrial_100_20": 0, "wired_100_20": 0},
        "served_unserved_rollup_has_locations",
    ),
    ({"any_100_20": 11}, "served_unserved_rollup_any_within_locations"),
    ({"terrestrial_100_20": 9}, "served_unserved_rollup_terrestrial_within_any"),
    ({"wired_100_20": 7}, "served_unserved_rollup_wired_within_terrestrial"),
    ({"wired_100_20": -1}, "served_unserved_rollup_wired_100_20_check"),
]
# (level, a code of that level's form)
VALID_CODES = [
    ("county", "39049"),
    ("tract", "39049000110"),
    ("block_group", "390490001101"),
    ("block", "390490001101000"),
    ("h3_res8", "882a91ae3bfffff"),
    ("place", "3918000"),
    ("county_subdivision", "3904918000"),
]


def make_status(release: Release, location: Location, flags: str = "111") -> ServedStatus:
    return ServedStatus.objects.create(
        release=release,
        location=location,
        any_100_20=flags[0] == "1",
        wired_100_20=flags[1] == "1",
        terrestrial_100_20=flags[2] == "1",
    )


def make_rollup(release: Release, **changes: object) -> Rollup:
    return Rollup.objects.create(release=release, **{**VALID_ROLLUP, **changes})


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


def test_valid_rollup_is_accepted(release: Release) -> None:
    make_rollup(release)

    assert Rollup.objects.count() == 1


@pytest.mark.parametrize(("changes", "constraint"), REJECTED_ROLLUPS)
def test_invalid_rollups_are_rejected(
    release: Release, changes: dict[str, object], constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=constraint), transaction.atomic():
        make_rollup(release, **changes)


@pytest.mark.parametrize(("level", "code"), VALID_CODES)
def test_each_level_accepts_its_codes(release: Release, level: str, code: str) -> None:
    make_rollup(release, level=level, code=code)

    rollup = Rollup.objects.get()
    assert (rollup.level, rollup.code) == (level, code)


def test_area_appears_once_per_release(release: Release, rollup: Rollup) -> None:
    with (
        pytest.raises(IntegrityError, match="served_unserved_rollup_unique_area_per_release"),
        transaction.atomic(),
    ):
        make_rollup(release)


def test_area_can_appear_in_two_releases(release: Release, rollup: Rollup) -> None:
    other = Release.objects.create(
        filing_period="J26", as_of=date(2026, 6, 30), processed_on=date(2026, 9, 29)
    )

    make_rollup(other)

    assert Rollup.objects.filter(code="39049").count() == 2


def test_deleting_a_release_deletes_its_rollups(release: Release, rollup: Rollup) -> None:
    release.delete()

    assert Rollup.objects.count() == 0


def test_rollup_str(rollup: Rollup) -> None:
    assert str(rollup) == "County 39049 in December 2025 (processed 2026-09-29)"


def test_h3_rollup_str(release: Release) -> None:
    rollup = make_rollup(release, level="h3_res8", code="882a91ae3bfffff")

    assert str(rollup) == (
        "H3 resolution-8 cell 882a91ae3bfffff in December 2025 (processed 2026-09-29)"
    )


def test_place_rollup_str(release: Release) -> None:
    rollup = make_rollup(release, level="place", code="3918000")

    assert str(rollup) == "Place 3918000 in December 2025 (processed 2026-09-29)"
