from datetime import date

import pytest

from bdc.models import Release
from geography.models import Block, BlockGroup, County, CountySubdivision, Place, State, Tract
from geography.tests.helpers import boundary_fields
from served_unserved.models import Rollup, ServedStatus


@pytest.fixture
def state(db: None) -> State:
    return State.objects.create(geoid="39", name="Ohio", abbreviation="OH", **boundary_fields())


@pytest.fixture
def county(state: State) -> County:
    return County.objects.create(
        geoid="39049", name="Franklin County", state=state, **boundary_fields()
    )


@pytest.fixture
def tract(county: County) -> Tract:
    return Tract.objects.create(
        geoid="39049000110", name="Census Tract 1.10", county=county, **boundary_fields()
    )


@pytest.fixture
def block_group(tract: Tract) -> BlockGroup:
    return BlockGroup.objects.create(
        geoid="390490001101", name="Block Group 1", tract=tract, **boundary_fields()
    )


@pytest.fixture
def place(state: State) -> Place:
    return Place.objects.create(
        geoid="3918000", name="Columbus city", state=state, **boundary_fields()
    )


@pytest.fixture
def county_subdivision(county: County) -> CountySubdivision:
    return CountySubdivision.objects.create(
        geoid="3904918000", name="Columbus city", county=county, **boundary_fields()
    )


@pytest.fixture
def block(block_group: BlockGroup, place: Place, county_subdivision: CountySubdivision) -> Block:
    return Block.objects.create(
        geoid="390490001101000",
        name="Block 1000",
        block_group=block_group,
        place=place,
        county_subdivision=county_subdivision,
        population_2020=25,
        housing_units_2020=10,
        urban_rural="U",
        **boundary_fields(),
    )


@pytest.fixture
def release(db: None) -> Release:
    return Release.objects.create(
        filing_period="D25", as_of=date(2025, 12, 31), processed_on=date(2026, 9, 29)
    )


@pytest.fixture
def served_status(release: Release, block: Block) -> ServedStatus:
    return ServedStatus.objects.create(
        release=release,
        location_id=1000338835,
        block=block,
        h3_res8="882a91ae3bfffff",
        any_100_20=True,
        wired_100_20=True,
        terrestrial_100_20=True,
    )


@pytest.fixture
def rollup(release: Release, state: State) -> Rollup:
    return Rollup.objects.create(
        release=release,
        state=state,
        level="county",
        code="39049",
        locations=10,
        any_100_20=8,
        wired_100_20=4,
        terrestrial_100_20=6,
    )


@pytest.fixture
def wv_state(db: None) -> State:
    return State.objects.create(
        geoid="54", name="West Virginia", abbreviation="WV", **boundary_fields()
    )


@pytest.fixture
def wv_block(wv_state: State) -> Block:
    """A West Virginia block in Weirton city and Weirton district, with its parent areas."""
    county = County.objects.create(
        geoid="54009", name="Brooke County", state=wv_state, **boundary_fields()
    )
    tract = Tract.objects.create(
        geoid="54009031103", name="Census Tract 311.03", county=county, **boundary_fields()
    )
    block_group = BlockGroup.objects.create(
        geoid="540090311031", name="Block Group 1", tract=tract, **boundary_fields()
    )
    place = Place.objects.create(
        geoid="5485156", name="Weirton city", state=wv_state, **boundary_fields()
    )
    county_subdivision = CountySubdivision.objects.create(
        geoid="5400993552", name="Weirton district", county=county, **boundary_fields()
    )
    return Block.objects.create(
        geoid="540090311031011",
        name="Block 1011",
        block_group=block_group,
        place=place,
        county_subdivision=county_subdivision,
        population_2020=100,
        housing_units_2020=57,
        urban_rural="U",
        **boundary_fields(),
    )
