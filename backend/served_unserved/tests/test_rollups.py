import re
from datetime import date

import pytest
from django.db.models import Count, Q, QuerySet, Sum

from bdc.models import Release
from geography.models import Block, BlockGroup, County, CountySubdivision, Place, State, Tract
from geography.tests.helpers import boundary_fields
from served_unserved.models import AREA_KEYS, Rollup, RollupLevel, ServedStatus
from served_unserved.rollups import COUNT_FIELDS, build_rollups, statuses_in

# H3 cells. A and C each lie in one county; B holds a Franklin and a Delaware location.
CELL_A = "882a91ae3bfffff"
CELL_B = "882a91ae35fffff"
CELL_C = "882a91ae1dfffff"

# (location_id, block GEOID, H3 cell, flags as any/wired/terrestrial). Franklin County (39049)
# has three locations: two in tract 39049000110, in different block groups, and one in tract
# 39049000200. Delaware County (39041) has two, in two blocks of one block group. Adams County
# (39001) has none.
STATUSES = [
    (1001, "390490001101000", CELL_A, "111"),
    (1002, "390490001102000", CELL_A, "101"),
    (1003, "390490002001000", CELL_B, "000"),
    (1004, "390410001001000", CELL_B, "100"),
    (1005, "390410001001001", CELL_C, "111"),
]
# Block GEOID -> (place, county subdivision). Columbus city (3918000) crosses into Delaware
# County. Blocks 390490001102000 and 390410001001001 are in no place.
BLOCK_AREAS = {
    "390410001001000": ("3918000", "3904158618"),
    "390410001001001": (None, "3904158618"),
    "390490001101000": ("3918000", "3904918000"),
    "390490001102000": (None, "3904916112"),
    "390490002001000": ("3918000", "3904918000"),
}
# (level, code, locations, any, wired, terrestrial), sorted
EXPECTED = [
    ("block", "390410001001000", 1, 1, 0, 0),
    ("block", "390410001001001", 1, 1, 1, 1),
    ("block", "390490001101000", 1, 1, 1, 1),
    ("block", "390490001102000", 1, 1, 0, 1),
    ("block", "390490002001000", 1, 0, 0, 0),
    ("block_group", "390410001001", 2, 2, 1, 1),
    ("block_group", "390490001101", 1, 1, 1, 1),
    ("block_group", "390490001102", 1, 1, 0, 1),
    ("block_group", "390490002001", 1, 0, 0, 0),
    ("county", "39041", 2, 2, 1, 1),
    ("county", "39049", 3, 2, 1, 2),
    ("county_subdivision", "3904158618", 2, 2, 1, 1),
    ("county_subdivision", "3904916112", 1, 1, 0, 1),
    ("county_subdivision", "3904918000", 2, 1, 1, 1),
    ("h3_res8", CELL_C, 1, 1, 1, 1),
    ("h3_res8", CELL_B, 2, 1, 0, 0),
    ("h3_res8", CELL_A, 2, 2, 1, 2),
    ("place", "3918000", 3, 2, 1, 1),
    ("tract", "39041000100", 2, 2, 1, 1),
    ("tract", "39049000110", 2, 2, 1, 2),
    ("tract", "39049000200", 1, 0, 0, 0),
]
# (level, code) -> location IDs that statuses_in selects
SELECTED = {
    ("county", "39049"): {1001, 1002, 1003},
    ("tract", "39049000110"): {1001, 1002},
    ("block_group", "390490001101"): {1001},
    ("block", "390410001001001"): {1005},
    ("h3_res8", CELL_B): {1003, 1004},
    ("place", "3918000"): {1001, 1003, 1004},
    ("county_subdivision", "3904918000"): {1001, 1003},
}

# (level, code) -> location IDs that statuses_in selects in other_release, where location 1003
# lies in block 390410001001001 and cell C (test_each_release_keeps_its_own_placement)
MOVED = {
    ("county", "39049"): set(),
    ("county", "39041"): {1003},
    ("tract", "39049000200"): set(),
    ("tract", "39041000100"): {1003},
    ("block_group", "390410001001"): {1003},
    ("block", "390490002001000"): set(),
    ("block", "390410001001001"): {1003},
    ("h3_res8", CELL_B): set(),
    ("h3_res8", CELL_C): {1003},
    ("place", "3918000"): set(),
    ("county_subdivision", "3904918000"): set(),
    ("county_subdivision", "3904158618"): {1003},
}


def add_block(state: State, geoid: str, place: str | None, county_subdivision: str) -> Block:
    """Create the block, and its county, tract, block group and areas unless they exist."""
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
    place_row = None
    if place is not None:
        place_row, _ = Place.objects.get_or_create(
            geoid=place,
            defaults={"name": f"Place {place}", "state": state, **boundary_fields()},
        )
    subdivision, _ = CountySubdivision.objects.get_or_create(
        geoid=county_subdivision,
        defaults={
            "name": f"County subdivision {county_subdivision}",
            "county": county,
            **boundary_fields(),
        },
    )
    return Block.objects.create(
        geoid=geoid,
        name=f"Block {geoid}",
        block_group=block_group,
        place=place_row,
        county_subdivision=subdivision,
        population_2020=0,
        housing_units_2020=0,
        urban_rural="R",
        **boundary_fields(),
    )


def add_status(
    release: Release, location_id: int, block: Block, cell: str, flags: str
) -> ServedStatus:
    return ServedStatus.objects.create(
        release=release,
        location_id=location_id,
        block=block,
        h3_res8=cell,
        any_100_20=flags[0] == "1",
        wired_100_20=flags[1] == "1",
        terrestrial_100_20=flags[2] == "1",
    )


def add_wv_status(
    release: Release,
    block: Block,
    location_id: int = 2001,
    cell: str = CELL_A,
    flags: str = "100",
) -> ServedStatus:
    return add_status(release, location_id, block, cell, flags)


def build_all(release: Release) -> int:
    return sum(build_rollups(release, "39", level) for level in RollupLevel)


def rollup_rows(release: Release) -> list[tuple[object, ...]]:
    return sorted(
        Rollup.objects.filter(release=release).values_list("level", "code", *COUNT_FIELDS)
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
    blocks = {geoid: add_block(state, geoid, *BLOCK_AREAS[geoid]) for geoid in sorted(BLOCK_AREAS)}
    County.objects.create(geoid="39001", name="Adams County", state=state, **boundary_fields())
    for location_id, geoid, cell, flags in STATUSES:
        add_status(release, location_id, blocks[geoid], cell, flags)
    return release


@pytest.fixture
def other_release(db: None) -> Release:
    return Release.objects.create(
        filing_period="J26", as_of=date(2026, 6, 30), processed_on=date(2026, 9, 29)
    )


def test_area_keys_cover_every_level() -> None:
    assert set(AREA_KEYS) == set(RollupLevel)


def test_builds_one_row_per_area_with_locations(release_with_statuses: Release) -> None:
    assert build_all(release_with_statuses) == 21

    assert rollup_rows(release_with_statuses) == EXPECTED
    assert not Rollup.objects.filter(code="39001").exists()


def test_builds_only_the_given_state(release_with_statuses: Release, wv_block: Block) -> None:
    add_wv_status(release_with_statuses, wv_block)

    assert build_all(release_with_statuses) == 21

    assert rollup_rows(release_with_statuses) == EXPECTED
    assert not Rollup.objects.filter(state_id="54").exists()


def test_cell_on_a_state_line_has_a_row_per_state(
    release_with_statuses: Release, wv_block: Block
) -> None:
    add_wv_status(release_with_statuses, wv_block)

    build_all(release_with_statuses)
    for level in RollupLevel:
        build_rollups(release_with_statuses, "54", level)

    cell = Rollup.objects.filter(release=release_with_statuses, level="h3_res8", code=CELL_A)
    assert list(cell.order_by("state").values_list("state_id", *COUNT_FIELDS)) == [
        ("39", 2, 2, 1, 2),
        ("54", 1, 1, 0, 0),
    ]
    statuses = statuses_in(release_with_statuses, "h3_res8", CELL_A)
    assert set(statuses.values_list("location_id", flat=True)) == {1001, 1002, 2001}


def test_rebuilding_one_state_leaves_the_other(
    release_with_statuses: Release, wv_block: Block
) -> None:
    add_wv_status(release_with_statuses, wv_block)
    for level in RollupLevel:
        build_rollups(release_with_statuses, "54", level)
    before = list(Rollup.objects.filter(state_id="54").order_by("id").values_list())

    build_all(release_with_statuses)
    build_all(release_with_statuses)

    assert list(Rollup.objects.filter(state_id="54").order_by("id").values_list()) == before


def test_builds_one_level_at_a_time(release_with_statuses: Release) -> None:
    tracts = [row for row in EXPECTED if row[0] == "tract"]
    counties = [row for row in EXPECTED if row[0] == "county"]

    assert build_rollups(release_with_statuses, "39", "tract") == 3
    assert rollup_rows(release_with_statuses) == tracts

    assert build_rollups(release_with_statuses, "39", "county") == 2
    assert rollup_rows(release_with_statuses) == counties + tracts


def test_counts_only_the_given_release(
    release_with_statuses: Release, other_release: Release
) -> None:
    add_status(other_release, 1003, Block.objects.get(pk="390490002001000"), CELL_B, "111")

    assert build_all(release_with_statuses) == 21
    assert build_all(other_release) == 7

    assert rollup_rows(other_release) == [
        ("block", "390490002001000", 1, 1, 1, 1),
        ("block_group", "390490002001", 1, 1, 1, 1),
        ("county", "39049", 1, 1, 1, 1),
        ("county_subdivision", "3904918000", 1, 1, 1, 1),
        ("h3_res8", CELL_B, 1, 1, 1, 1),
        ("place", "3918000", 1, 1, 1, 1),
        ("tract", "39049000200", 1, 1, 1, 1),
    ]
    assert rollup_rows(release_with_statuses) == EXPECTED


def test_rebuilding_replaces_the_rows(release_with_statuses: Release) -> None:
    build_all(release_with_statuses)
    ServedStatus.objects.filter(location_id=1003).update(
        any_100_20=True, wired_100_20=True, terrestrial_100_20=True
    )

    assert build_all(release_with_statuses) == 21

    changed = {
        ("block", "390490002001000"): (1, 1, 1, 1),
        ("block_group", "390490002001"): (1, 1, 1, 1),
        ("county", "39049"): (3, 3, 2, 3),
        ("county_subdivision", "3904918000"): (2, 2, 2, 2),
        ("h3_res8", CELL_B): (2, 2, 1, 1),
        ("place", "3918000"): (3, 3, 2, 2),
        ("tract", "39049000200"): (1, 1, 1, 1),
    }
    assert rollup_rows(release_with_statuses) == [
        (level, code, *changed.get((level, code), tuple(counts)))
        for level, code, *counts in EXPECTED
    ]


def test_each_release_keeps_its_own_placement(
    release_with_statuses: Release, other_release: Release
) -> None:
    build_all(release_with_statuses)
    # In the other release, location 1003 lies in a Delaware County block outside every place
    # and in cell C, not in a Franklin County block of Columbus city and in cell B.
    add_status(other_release, 1003, Block.objects.get(pk="390410001001001"), CELL_C, "111")

    assert build_all(other_release) == 6
    assert build_all(release_with_statuses) == 21

    assert rollup_rows(release_with_statuses) == EXPECTED
    assert rollup_rows(other_release) == [
        ("block", "390410001001001", 1, 1, 1, 1),
        ("block_group", "390410001001", 1, 1, 1, 1),
        ("county", "39041", 1, 1, 1, 1),
        ("county_subdivision", "3904158618", 1, 1, 1, 1),
        ("h3_res8", CELL_C, 1, 1, 1, 1),
        ("tract", "39041000100", 1, 1, 1, 1),
    ]
    for (level, code), location_ids in SELECTED.items():
        statuses = statuses_in(release_with_statuses, level, code)
        assert set(statuses.values_list("location_id", flat=True)) == location_ids
    for (level, code), location_ids in MOVED.items():
        statuses = statuses_in(other_release, level, code)
        assert set(statuses.values_list("location_id", flat=True)) == location_ids


def test_release_without_statuses_has_no_rollups(
    release_with_statuses: Release, other_release: Release
) -> None:
    assert build_all(other_release) == 0

    assert rollup_rows(other_release) == []


def test_build_rejects_a_level_without_rollups(release: Release) -> None:
    with pytest.raises(ValueError, match=re.escape("no rollups at level 'state'")):
        build_rollups(release, "39", "state")


def test_location_outside_every_place_adds_to_no_place_row(release_with_statuses: Release) -> None:
    build_all(release_with_statuses)

    sums = {
        level: Rollup.objects.filter(level=level).aggregate(Sum("locations"))["locations__sum"]
        for level in RollupLevel
    }
    assert sums == {level: 3 if level == RollupLevel.PLACE else 5 for level in RollupLevel}


def test_statuses_in_selects_what_each_rollup_counts(release_with_statuses: Release) -> None:
    build_all(release_with_statuses)

    for rollup in Rollup.objects.filter(release=release_with_statuses):
        statuses = statuses_in(release_with_statuses, rollup.level, rollup.code)
        assert counted(statuses) == (
            rollup.locations,
            rollup.any_100_20,
            rollup.wired_100_20,
            rollup.terrestrial_100_20,
        )
    for (level, code), location_ids in SELECTED.items():
        statuses = statuses_in(release_with_statuses, level, code)
        assert set(statuses.values_list("location_id", flat=True)) == location_ids


def test_statuses_in_is_limited_to_the_release(
    release_with_statuses: Release, other_release: Release
) -> None:
    add_status(other_release, 1003, Block.objects.get(pk="390490002001000"), CELL_B, "111")

    county = statuses_in(other_release, "county", "39049")
    cell = statuses_in(other_release, "h3_res8", CELL_B)
    place = statuses_in(other_release, "place", "3918000")

    assert set(county.values_list("location_id", flat=True)) == {1003}
    assert set(cell.values_list("location_id", flat=True)) == {1003}
    assert set(place.values_list("location_id", flat=True)) == {1003}


@pytest.mark.parametrize(
    ("level", "code", "message"),
    [
        ("state", "39", "no rollups at level 'state'"),
        ("county", "3904", "county code '3904' is not 5 digits"),
        ("county", "390490", "county code '390490' is not 5 digits"),
        ("county", "3904a", "county code '3904a' is not 5 digits"),
        ("county", "39049\n", "county code '39049\\n' is not 5 digits"),
        ("tract", "39049", "tract code '39049' is not 11 digits"),
        ("block_group", "39049000110", "block_group code '39049000110' is not 12 digits"),
        ("block", "882a91ae3bfffff", "block code '882a91ae3bfffff' is not 15 digits"),
        (
            "h3_res8",
            "882A91AE3BFFFFF",
            "h3_res8 code '882A91AE3BFFFFF' is not 15 lowercase hex characters",
        ),
        (
            "h3_res8",
            "882a91ae3bffff",
            "h3_res8 code '882a91ae3bffff' is not 15 lowercase hex characters",
        ),
        ("place", "391800", "place code '391800' is not 7 digits"),
        (
            "county_subdivision",
            "390491800",
            "county_subdivision code '390491800' is not 10 digits",
        ),
    ],
)
def test_statuses_in_rejects_bad_keys(
    release: Release, level: str, code: str, message: str
) -> None:
    with pytest.raises(ValueError, match=re.escape(message)):
        statuses_in(release, level, code)
