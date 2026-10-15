import re

import pytest
from django.contrib.gis.geos import Point

from etl.assign import assign_blocks
from etl.errors import LoadError
from geography.models import Block, BlockGroup, County, CountySubdivision, Place, State
from geography.tests.helpers import boundary_fields, square

FIRST = "390490001101000"
SECOND = "390490001101001"
THIRD = "390490001101002"


def add_place(state: State, geoid: str, lon: float, lat: float, size: float) -> Place:
    return Place.objects.create(
        **{**boundary_fields(), "geom": square(lon, lat, size)},
        geoid=geoid,
        name=f"Place {geoid}",
        state=state,
    )


def add_county_subdivision(
    county: County, geoid: str, lon: float, lat: float, size: float
) -> CountySubdivision:
    return CountySubdivision.objects.create(
        **{**boundary_fields(), "geom": square(lon, lat, size)},
        geoid=geoid,
        name=f"County subdivision {geoid}",
        county=county,
    )


def add_block(block_group: BlockGroup, geoid: str, lon: float, lat: float) -> Block:
    return Block.objects.create(
        **{**boundary_fields(), "internal_point": Point(lon, lat, srid=4326)},
        geoid=geoid,
        name=f"Block {geoid[-4:]}",
        block_group=block_group,
        population_2020=0,
        housing_units_2020=0,
        urban_rural="R",
    )


def areas() -> dict[str, tuple[str | None, str | None]]:
    """Every block's (place, county subdivision)."""
    return {
        geoid: (place_id, county_subdivision_id)
        for geoid, place_id, county_subdivision_id in Block.objects.values_list(
            "geoid", "place_id", "county_subdivision_id"
        )
    }


@pytest.fixture
def layout(state: State, county: County, block_group: BlockGroup) -> None:
    """Columbus city (a place and a county subdivision), Clinton township and three blocks.

    The first block is in the place and in Columbus city's county subdivision, the second only
    in that county subdivision, the third only in Clinton township. No point lies on an edge.
    """
    add_place(state, "3918000", -83.0, 40.0, 0.02)
    add_county_subdivision(county, "3904918000", -83.0, 40.0, 0.04)
    add_county_subdivision(county, "3904916112", -82.95, 40.0, 0.04)
    add_block(block_group, FIRST, -82.985, 40.01)
    add_block(block_group, SECOND, -82.97, 40.03)
    add_block(block_group, THIRD, -82.93, 40.01)


ASSIGNED = {
    FIRST: ("3918000", "3904918000"),
    SECOND: (None, "3904918000"),
    THIRD: (None, "3904916112"),
}


def test_assigns_the_areas_that_hold_each_internal_point(layout: None) -> None:
    assert assign_blocks() == 1

    assert areas() == ASSIGNED


def test_reassigning_replaces_earlier_areas(layout: None) -> None:
    Block.objects.filter(pk=SECOND).update(place_id="3918000")
    Block.objects.filter(pk=THIRD).update(county_subdivision_id="3904918000")

    assign_blocks()

    assert areas() == ASSIGNED


def test_block_in_no_county_subdivision_fails(layout: None, block_group: BlockGroup) -> None:
    add_block(block_group, "390490001101003", -82.5, 40.5)

    with pytest.raises(
        LoadError, match=re.escape("census blocks in no county subdivision: 390490001101003")
    ):
        assign_blocks()


def test_county_subdivision_of_another_county_is_not_matched(
    layout: None, state: State, block_group: BlockGroup
) -> None:
    delaware = County.objects.create(
        geoid="39041", name="Delaware County", state=state, **boundary_fields()
    )
    add_county_subdivision(delaware, "3904158618", -82.6, 40.4, 0.2)
    add_block(block_group, "390490001101003", -82.5, 40.5)

    with pytest.raises(
        LoadError, match=re.escape("census blocks in no county subdivision: 390490001101003")
    ):
        assign_blocks()


def test_point_in_two_places_fails(layout: None, state: State) -> None:
    add_place(state, "3983342", -82.99, 40.0, 0.02)

    with pytest.raises(
        LoadError,
        match=re.escape(
            "census blocks whose internal point lies in more than one area: "
            f"{FIRST} (places 3918000, 3983342)"
        ),
    ):
        assign_blocks()

    assert areas() == {FIRST: (None, None), SECOND: (None, None), THIRD: (None, None)}


def test_point_in_two_county_subdivisions_fails(layout: None, county: County) -> None:
    add_county_subdivision(county, "3904971787", -83.0, 40.0, 0.04)

    with pytest.raises(
        LoadError,
        match=re.escape(
            f"{FIRST} (county subdivisions 3904918000, 3904971787), "
            f"{SECOND} (county subdivisions 3904918000, 3904971787)"
        ),
    ):
        assign_blocks()
