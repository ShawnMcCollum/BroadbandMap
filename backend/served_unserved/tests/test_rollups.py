import re
from datetime import date

import pytest
from django.db.models import Count, Q, QuerySet

from bdc.models import Location, Release
from geography.models import Block, BlockGroup, County, State, Tract
from geography.tests.helpers import boundary_fields
from served_unserved.models import Rollup, ServedStatus
from served_unserved.rollups import COUNT_FIELDS, build_rollups, statuses_in

H3 = "882a91ae3bfffff"

# (location_id, block GEOID, flags as any/wired/terrestrial). Franklin County (39049) has
# three locations in two tracts, and Delaware County (39041) has two. Adams County (39001)
# has none.
STATUSES = [
    (1001, "390490001101000", "111"),
    (1002, "390490001101000", "101"),
    (1003, "390490002001000", "000"),
    (1004, "390410001001000", "100"),
    (1005, "390410001001000", "111"),
]
# (level, code, locations, any, wired, terrestrial)
EXPECTED = [
    ("county", "39041", 2, 2, 1, 1),
    ("county", "39049", 3, 2, 1, 2),
]


def add_block(state: State, geoid: str) -> Block:
    """Create the block, and its county, tract and block group unless they exist."""
    county, _ = County.objects.get_or_create(
        geoid=geoid[:5],
        defaults={"name": f"County {geoid[:5]}", "state": state, **boundary_fields()},
    )
    tract, _ = Tract.objects.get_or_create(
        geoid=geoid[:11],
        defaults={"name": f"Tract {geoid[:11]}", "county": county, **boundary_fields()},
    )
    block_group, _ = BlockGroup.objects.get_or_create(
        geoid=geoid[:12],
        defaults={"name": f"Block Group {geoid[:12]}", "tract": tract, **boundary_fields()},
    )
    return Block.objects.create(
        geoid=geoid,
        name=f"Block {geoid}",
        block_group=block_group,
        population_2020=0,
        housing_units_2020=0,
        urban_rural="R",
        **boundary_fields(),
    )


def add_status(release: Release, location_id: int, block: Block, flags: str) -> ServedStatus:
    location, _ = Location.objects.get_or_create(
        location_id=location_id, defaults={"block": block, "h3_res8": H3}
    )
    return ServedStatus.objects.create(
        release=release,
        location=location,
        any_100_20=flags[0] == "1",
        wired_100_20=flags[1] == "1",
        terrestrial_100_20=flags[2] == "1",
    )


def rollup_rows(release: Release) -> list[tuple[object, ...]]:
    return list(
        Rollup.objects.filter(release=release)
        .order_by("level", "code")
        .values_list("level", "code", *COUNT_FIELDS)
    )


def counted(statuses: QuerySet[ServedStatus]) -> tuple[int, int, int, int]:
    totals = statuses.order_by().aggregate(
        n=Count("pk"),
        a=Count("pk", filter=Q(any_100_20=True)),
        w=Count("pk", filter=Q(wired_100_20=True)),
        t=Count("pk", filter=Q(terrestrial_100_20=True)),
    )
    return totals["n"], totals["a"], totals["w"], totals["t"]


@pytest.fixture
def release_with_statuses(state: State, release: Release) -> Release:
    blocks = {geoid: add_block(state, geoid) for geoid in sorted({row[1] for row in STATUSES})}
    County.objects.create(geoid="39001", name="Adams County", state=state, **boundary_fields())
    for location_id, geoid, flags in STATUSES:
        add_status(release, location_id, blocks[geoid], flags)
    return release


@pytest.fixture
def other_release(db: None) -> Release:
    return Release.objects.create(
        filing_period="J26", as_of=date(2026, 6, 30), processed_on=date(2026, 9, 29)
    )


def test_builds_one_row_per_county_with_locations(release_with_statuses: Release) -> None:
    assert build_rollups(release_with_statuses) == 2

    assert rollup_rows(release_with_statuses) == EXPECTED


def test_counts_only_the_given_release(
    release_with_statuses: Release, other_release: Release
) -> None:
    add_status(other_release, 1003, Block.objects.get(pk="390490002001000"), "111")

    assert build_rollups(release_with_statuses) == 2
    assert build_rollups(other_release) == 1

    assert rollup_rows(other_release) == [("county", "39049", 1, 1, 1, 1)]
    assert rollup_rows(release_with_statuses) == EXPECTED


def test_rebuilding_replaces_the_rows(release_with_statuses: Release) -> None:
    build_rollups(release_with_statuses)
    ServedStatus.objects.filter(location_id=1003).update(
        any_100_20=True, wired_100_20=True, terrestrial_100_20=True
    )

    assert build_rollups(release_with_statuses) == 2

    assert rollup_rows(release_with_statuses) == [
        ("county", "39041", 2, 2, 1, 1),
        ("county", "39049", 3, 3, 2, 3),
    ]


def test_release_without_statuses_has_no_rollups(
    release_with_statuses: Release, other_release: Release
) -> None:
    assert build_rollups(other_release) == 0

    assert rollup_rows(other_release) == []


def test_statuses_in_selects_what_each_rollup_counts(release_with_statuses: Release) -> None:
    build_rollups(release_with_statuses)

    for rollup in Rollup.objects.filter(release=release_with_statuses):
        statuses = statuses_in(release_with_statuses, rollup.level, rollup.code)
        assert counted(statuses) == (
            rollup.locations,
            rollup.any_100_20,
            rollup.wired_100_20,
            rollup.terrestrial_100_20,
        )
    franklin = statuses_in(release_with_statuses, "county", "39049")
    assert set(franklin.values_list("location_id", flat=True)) == {1001, 1002, 1003}


def test_statuses_in_is_limited_to_the_release(
    release_with_statuses: Release, other_release: Release
) -> None:
    add_status(other_release, 1003, Block.objects.get(pk="390490002001000"), "111")

    statuses = statuses_in(other_release, "county", "39049")

    assert set(statuses.values_list("location_id", flat=True)) == {1003}


@pytest.mark.parametrize(
    ("level", "code", "message"),
    [
        ("tract", "39049000110", "no rollups at level 'tract'"),
        ("county", "3904", "county code '3904' is not 5 digits"),
        ("county", "390490", "county code '390490' is not 5 digits"),
        ("county", "3904a", "county code '3904a' is not 5 digits"),
        ("county", "39049\n", "county code '39049\\n' is not 5 digits"),
    ],
)
def test_statuses_in_rejects_bad_keys(
    release: Release, level: str, code: str, message: str
) -> None:
    with pytest.raises(ValueError, match=re.escape(message)):
        statuses_in(release, level, code)
