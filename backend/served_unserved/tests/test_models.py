from datetime import date

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.models import ProtectedError

from bdc.models import Release
from geography.models import Block, State
from geography.tests.helpers import boundary_fields
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
    ({"code": "54009"}, "served_unserved_rollup_code_in_state"),
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


def make_status(
    release: Release, block: Block, flags: str = "111", h3_res8: str = "882a91ae3bfffff"
) -> ServedStatus:
    return ServedStatus.objects.create(
        release=release,
        location_id=1000338835,
        block=block,
        h3_res8=h3_res8,
        any_100_20=flags[0] == "1",
        wired_100_20=flags[1] == "1",
        terrestrial_100_20=flags[2] == "1",
    )


def make_rollup(release: Release, state: State, **changes: object) -> Rollup:
    return Rollup.objects.create(release=release, state=state, **{**VALID_ROLLUP, **changes})


@pytest.mark.parametrize("flags", ACCEPTED)
def test_consistent_flags_are_accepted(release: Release, block: Block, flags: str) -> None:
    make_status(release, block, flags)

    assert ServedStatus.objects.count() == 1


@pytest.mark.parametrize("flags", REJECTED)
def test_inconsistent_flags_are_rejected(release: Release, block: Block, flags: str) -> None:
    with pytest.raises(IntegrityError, match="_implies_"), transaction.atomic():
        make_status(release, block, flags)


def test_location_appears_once_per_release(
    release: Release, block: Block, served_status: ServedStatus
) -> None:
    with (
        pytest.raises(IntegrityError, match="served_unserved_unique_location_per_release"),
        transaction.atomic(),
    ):
        make_status(release, block)


def test_location_can_be_placed_differently_in_two_releases(
    block: Block, served_status: ServedStatus
) -> None:
    other_block = Block.objects.create(
        geoid="390490001101001",
        name="Block 1001",
        block_group=block.block_group,
        county_subdivision=block.county_subdivision,
        population_2020=0,
        housing_units_2020=0,
        urban_rural="R",
        **boundary_fields(),
    )
    other = Release.objects.create(
        filing_period="J26", as_of=date(2026, 6, 30), processed_on=date(2026, 9, 29)
    )

    make_status(other, other_block, h3_res8="882a91ae35fffff")

    placements = ServedStatus.objects.filter(location_id=1000338835).values_list(
        "release__filing_period", "block_id", "h3_res8"
    )
    assert sorted(placements) == [
        ("D25", "390490001101000", "882a91ae3bfffff"),
        ("J26", "390490001101001", "882a91ae35fffff"),
    ]


@pytest.mark.parametrize("h3_res8", ["882A91AE3BFFFFF", "882a91ae3bffff"])
def test_invalid_h3_cell_is_rejected(release: Release, block: Block, h3_res8: str) -> None:
    with (
        pytest.raises(IntegrityError, match="served_unserved_h3_res8_format"),
        transaction.atomic(),
    ):
        make_status(release, block, h3_res8=h3_res8)


def test_status_in_a_missing_block_is_rejected(release: Release) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        ServedStatus.objects.create(
            release=release,
            location_id=1000338835,
            block_id="390490001101999",
            h3_res8="882a91ae3bfffff",
            any_100_20=True,
            wired_100_20=True,
            terrestrial_100_20=True,
        )
        connection.check_constraints()


def test_deleting_a_release_deletes_its_statuses(
    release: Release, served_status: ServedStatus
) -> None:
    release.delete()

    assert ServedStatus.objects.count() == 0


def test_block_with_a_status_cannot_be_deleted(block: Block, served_status: ServedStatus) -> None:
    with pytest.raises(ProtectedError):
        block.delete()


def test_valid_rollup_is_accepted(release: Release, state: State) -> None:
    make_rollup(release, state)

    assert Rollup.objects.count() == 1


@pytest.mark.parametrize(("changes", "constraint"), REJECTED_ROLLUPS)
def test_invalid_rollups_are_rejected(
    release: Release, state: State, changes: dict[str, object], constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=constraint), transaction.atomic():
        make_rollup(release, state, **changes)


@pytest.mark.parametrize(("level", "code"), VALID_CODES)
def test_each_level_accepts_its_codes(
    release: Release, state: State, level: str, code: str
) -> None:
    make_rollup(release, state, level=level, code=code)

    rollup = Rollup.objects.get()
    assert (rollup.level, rollup.code) == (level, code)


def test_area_appears_once_per_state_in_a_release(
    release: Release, state: State, rollup: Rollup
) -> None:
    with (
        pytest.raises(IntegrityError, match="served_unserved_rollup_unique_area_per_state"),
        transaction.atomic(),
    ):
        make_rollup(release, state)


def test_area_can_appear_in_two_releases(release: Release, state: State, rollup: Rollup) -> None:
    other = Release.objects.create(
        filing_period="J26", as_of=date(2026, 6, 30), processed_on=date(2026, 9, 29)
    )

    make_rollup(other, state)

    assert Rollup.objects.filter(code="39049").count() == 2


def test_h3_cell_has_a_row_per_state(release: Release, state: State, wv_state: State) -> None:
    for each in (state, wv_state):
        make_rollup(release, each, level="h3_res8", code="882a91ae3bfffff")

    assert Rollup.objects.filter(code="882a91ae3bfffff").count() == 2


def test_state_with_rollups_cannot_be_deleted(state: State, rollup: Rollup) -> None:
    with pytest.raises(ProtectedError):
        state.delete()


def test_deleting_a_release_deletes_its_rollups(release: Release, rollup: Rollup) -> None:
    release.delete()

    assert Rollup.objects.count() == 0


def test_rollup_str(rollup: Rollup) -> None:
    assert str(rollup) == "County 39049 in December 2025 (processed 2026-09-29)"


def test_h3_rollup_str(release: Release, state: State) -> None:
    rollup = make_rollup(release, state, level="h3_res8", code="882a91ae3bfffff")

    assert str(rollup) == (
        "H3 resolution-8 cell 882a91ae3bfffff in December 2025 (processed 2026-09-29)"
    )


def test_place_rollup_str(release: Release, state: State) -> None:
    rollup = make_rollup(release, state, level="place", code="3918000")

    assert str(rollup) == "Place 3918000 in December 2025 (processed 2026-09-29)"
