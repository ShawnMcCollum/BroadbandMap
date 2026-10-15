"""The migration that moves each location's block and cell onto its statuses (ADR 0012)."""

from collections.abc import Iterator
from datetime import date

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.state import StateApps

from bdc.models import Release
from geography.models import Block
from geography.tests.helpers import boundary_fields
from served_unserved.models import ServedStatus

pytestmark = pytest.mark.django_db(transaction=True)

# The last migrations with bdc.Location, and the ones that remove it
BEFORE = [("bdc", "0001_initial"), ("served_unserved", "0004_rollup_place_levels")]
AFTER = [("bdc", "0002_delete_location"), ("served_unserved", "0005_placement_per_release")]


def migrate(targets: list[tuple[str, str]]) -> StateApps:
    """Migrate the test database to ``targets`` and return the models as they were there."""
    executor = MigrationExecutor(connection)
    executor.migrate(targets)
    executor.loader.build_graph()
    return executor.loader.project_state(targets).apps


@pytest.fixture
def at_latest(transactional_db: None) -> Iterator[None]:
    """Migrate the test database back to the latest migrations after the test."""
    yield
    migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())


@pytest.fixture
def other_block(block: Block) -> Block:
    return Block.objects.create(
        geoid="390490001101001",
        name="Block 1001",
        block_group=block.block_group,
        county_subdivision=block.county_subdivision,
        population_2020=0,
        housing_units_2020=0,
        urban_rural="R",
        **boundary_fields(),
    )


@pytest.mark.usefixtures("at_latest")
def test_moves_each_location_s_placement_onto_its_statuses(
    block: Block, other_block: Block, release: Release
) -> None:
    old = migrate(BEFORE)
    location = old.get_model("bdc", "Location")
    status = old.get_model("served_unserved", "ServedStatus")
    location.objects.create(location_id=1, block_id=block.pk, h3_res8="882a91ae3bfffff")
    location.objects.create(location_id=2, block_id=other_block.pk, h3_res8="882a91ae35fffff")
    for location_id, flags in ((1, (True, True, True)), (2, (True, False, False))):
        status.objects.create(
            release_id=release.pk,
            location_id=location_id,
            any_100_20=flags[0],
            wired_100_20=flags[1],
            terrestrial_100_20=flags[2],
        )

    migrate(AFTER)

    rows = ServedStatus.objects.order_by("location_id").values_list(
        "release_id",
        "location_id",
        "block_id",
        "h3_res8",
        "any_100_20",
        "wired_100_20",
        "terrestrial_100_20",
    )
    assert list(rows) == [
        (release.pk, 1, "390490001101000", "882a91ae3bfffff", True, True, True),
        (release.pk, 2, "390490001101001", "882a91ae35fffff", True, False, False),
    ]
    assert "bdc_location" not in connection.introspection.table_names()


@pytest.mark.usefixtures("at_latest")
def test_undoing_restores_each_location_as_placed_in_its_latest_release(
    block: Block, other_block: Block, release: Release
) -> None:
    # Processed after December 2025, but describing June 2025
    june = Release.objects.create(
        filing_period="J25", as_of=date(2025, 6, 30), processed_on=date(2026, 10, 1)
    )
    for status_release, location_id, status_block, cell in (
        (june, 1, other_block, "882a91ae35fffff"),
        (release, 1, block, "882a91ae3bfffff"),
        (june, 2, other_block, "882a91ae35fffff"),
    ):
        ServedStatus.objects.create(
            release=status_release,
            location_id=location_id,
            block=status_block,
            h3_res8=cell,
            any_100_20=True,
            wired_100_20=False,
            terrestrial_100_20=False,
        )

    old = migrate(BEFORE)

    location = old.get_model("bdc", "Location")
    status = old.get_model("served_unserved", "ServedStatus")
    placements = location.objects.order_by("location_id").values_list(
        "location_id", "block_id", "h3_res8"
    )
    assert list(placements) == [
        (1, "390490001101000", "882a91ae3bfffff"),
        (2, "390490001101001", "882a91ae35fffff"),
    ]
    assert status.objects.count() == 3
