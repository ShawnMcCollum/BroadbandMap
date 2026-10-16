from typing import Any

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from geography.models import (
    Block,
    BlockGroup,
    Boundary,
    County,
    CountySubdivision,
    Place,
    State,
    Tract,
)
from geography.tests.helpers import boundary_fields, square

BOUNDARIES: list[tuple[type[Boundary], int]] = [
    (State, 2),
    (County, 5),
    (Tract, 11),
    (BlockGroup, 12),
    (Block, 15),
    (Place, 7),
    (CountySubdivision, 10),
]


@pytest.fixture
def required_fields(
    state: State, county: County, tract: Tract, block_group: BlockGroup
) -> dict[type[Boundary], dict[str, Any]]:
    """The fields each boundary model needs besides the shared ones."""
    return {
        State: {"abbreviation": "XX"},
        County: {"state": state},
        Tract: {"county": county},
        BlockGroup: {"tract": tract},
        Block: {
            "block_group": block_group,
            "population_2020": 0,
            "housing_units_2020": 0,
            "urban_rural": "R",
        },
        Place: {"state": state},
        CountySubdivision: {"county": county},
    }


def create_boundary(
    model: type[Boundary], geoid: str, required_fields: dict[type[Boundary], dict[str, Any]]
) -> Boundary:
    fields = {"geoid": geoid, "name": "Test", **boundary_fields(), **required_fields[model]}
    return model._default_manager.create(**fields)


@pytest.mark.parametrize(("model", "length"), BOUNDARIES)
def test_geoid_one_digit_short_is_rejected(
    model: type[Boundary],
    length: int,
    required_fields: dict[type[Boundary], dict[str, Any]],
) -> None:
    constraint = f"geography_{model._meta.model_name}_geoid_format"

    with pytest.raises(IntegrityError, match=constraint), transaction.atomic():
        create_boundary(model, "1" * (length - 1), required_fields)


@pytest.mark.parametrize(("model", "length"), BOUNDARIES)
def test_geoid_with_a_letter_is_rejected(
    model: type[Boundary],
    length: int,
    required_fields: dict[type[Boundary], dict[str, Any]],
) -> None:
    constraint = f"geography_{model._meta.model_name}_geoid_format"

    with pytest.raises(IntegrityError, match=constraint), transaction.atomic():
        create_boundary(model, "1" * (length - 1) + "A", required_fields)


def test_block_belongs_to_a_state_through_its_parents(block: Block, state: State) -> None:
    assert block.block_group.tract.county.state == state


def test_parents_list_their_children(
    state: State, county: County, tract: Tract, block_group: BlockGroup, block: Block
) -> None:
    assert list(state.counties.all()) == [county]
    assert list(county.tracts.all()) == [tract]
    assert list(tract.block_groups.all()) == [block_group]
    assert list(block_group.blocks.all()) == [block]


def test_county_with_a_tract_cannot_be_deleted(county: County, tract: Tract) -> None:
    with pytest.raises(ProtectedError):
        county.delete()


def test_geometry_in_nad83_is_stored_as_wgs84(state: State) -> None:
    geom = square(-83.0, 40.0)
    geom.srid = 4269
    state.geom = geom
    state.save()

    stored = State.objects.get(pk=state.pk)

    assert stored.geom.srid == 4326


def test_str_shows_name_and_geoid(county: County) -> None:
    assert str(county) == "Franklin County (39049)"


def test_block_records_its_place_and_county_subdivision(
    block: Block, place: Place, county_subdivision: CountySubdivision
) -> None:
    assert block.place == place
    assert block.county_subdivision == county_subdivision
    assert list(place.blocks.all()) == [block]
    assert list(county_subdivision.blocks.all()) == [block]


def test_block_without_a_place_or_county_subdivision_is_accepted(block_group: BlockGroup) -> None:
    Block.objects.create(
        geoid="390490001101001",
        name="Block 1001",
        block_group=block_group,
        population_2020=0,
        housing_units_2020=0,
        urban_rural="R",
        **boundary_fields(),
    )

    assert Block.objects.get(pk="390490001101001").place is None


def test_county_subdivision_in_another_county_is_rejected(block: Block, state: State) -> None:
    delaware = County.objects.create(
        geoid="39041", name="Delaware County", state=state, **boundary_fields()
    )
    orange = CountySubdivision.objects.create(
        geoid="3904158618", name="Orange township", county=delaware, **boundary_fields()
    )
    block.county_subdivision = orange

    with (
        pytest.raises(IntegrityError, match="geography_block_county_subdivision_in_county"),
        transaction.atomic(),
    ):
        block.save()


def test_two_states_cannot_share_an_abbreviation(state: State) -> None:
    with (
        pytest.raises(IntegrityError, match="geography_state_unique_abbreviation"),
        transaction.atomic(),
    ):
        State.objects.create(
            geoid="54", name="West Virginia", abbreviation=state.abbreviation, **boundary_fields()
        )


def test_area_with_blocks_cannot_be_deleted(
    place: Place, county_subdivision: CountySubdivision, block: Block
) -> None:
    with pytest.raises(ProtectedError):
        place.delete()
    with pytest.raises(ProtectedError):
        county_subdivision.delete()
