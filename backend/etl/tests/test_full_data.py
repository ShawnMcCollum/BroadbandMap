"""Reconcile a load of the real files in /data/raw against independent readers.

Deselected by default; run it with ``pytest -m full_data``. It does two full
loads, so it takes about 18 minutes.
"""

from collections.abc import Iterator

import pytest
from django.db import connection, transaction
from django.db.models import Count, F, Q
from django.db.models.functions import Left
from pytest_django.plugin import DjangoDbBlocker

from bdc.models import Location, Release
from etl.files import DEFAULT_DATA_DIR, FCC_GLOB
from etl.load import LoadResult, clear_tables, load_served_unserved
from etl.tests import sources
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
from served_unserved.models import Rollup, RollupLevel, ServedStatus
from served_unserved.rollups import COUNT_FIELDS, statuses_in

RAW = DEFAULT_DATA_DIR
pytestmark = [
    pytest.mark.full_data,
    pytest.mark.django_db,
    pytest.mark.skipif(
        not (RAW / "tiger2020").is_dir() or not any(RAW.glob(FCC_GLOB)),
        reason="the real source files are not in /data/raw",
    ),
]

BOUNDARY_MODELS: dict[str, type[Boundary]] = {
    "state": State,
    "county": County,
    "tract": Tract,
    "block_group": BlockGroup,
    "block": Block,
    "place": Place,
    "county_subdivision": CountySubdivision,
}
# (model, foreign key column, length of the parent's GEOID)
PARENT_PREFIXES: list[tuple[type[Boundary], str, int]] = [
    (County, "state_id", 2),
    (Tract, "county_id", 5),
    (BlockGroup, "tract_id", 11),
    (Block, "block_group_id", 12),
    (Place, "state_id", 2),
    (CountySubdivision, "county_id", 5),
]
# The selection rule is checked for every area at the levels with up to 10,000 areas, and for
# every 100th area, in code order, at the block and H3 levels: all of them would take about
# 11 minutes.
SELECTION_STEPS = {"county": 1, "tract": 1, "block_group": 1, "block": 100, "h3_res8": 100}


@pytest.fixture(scope="module")
def expected_fcc() -> sources.FccSummary:
    return sources.fcc_summary(next(RAW.glob(FCC_GLOB)))


@pytest.fixture(scope="module")
def expected_boundaries() -> dict[str, int]:
    return sources.boundary_counts(RAW / "tiger2020")


@pytest.fixture(scope="module")
def loaded(django_db_setup: None, django_db_blocker: DjangoDbBlocker) -> Iterator[LoadResult]:
    """Load the real files once, committed to the test database, for every test here."""
    with django_db_blocker.unblock():
        yield load_served_unserved(RAW)
        # Leave the tables empty, so later test modules start from nothing.
        with transaction.atomic():
            clear_tables()


@pytest.mark.usefixtures("loaded")
def test_row_counts_match_the_source(
    expected_boundaries: dict[str, int], expected_fcc: sources.FccSummary
) -> None:
    for label, model in BOUNDARY_MODELS.items():
        assert model._default_manager.count() == expected_boundaries[label], label
    assert Location.objects.count() == expected_fcc.rows
    assert ServedStatus.objects.count() == expected_fcc.rows


@pytest.mark.usefixtures("loaded")
def test_flag_combinations_match_the_source(expected_fcc: sources.FccSummary) -> None:
    rows = (
        ServedStatus.objects.order_by()
        .values_list("any_100_20", "wired_100_20", "terrestrial_100_20")
        .annotate(n=Count("id"))
    )
    found = {f"{a:d},{w:d},{t:d}": n for a, w, t, n in rows}

    assert found == expected_fcc.flag_combinations


@pytest.mark.usefixtures("loaded")
def test_locations_per_county_match_the_source(expected_fcc: sources.FccSummary) -> None:
    rows = (
        Location.objects.order_by()
        .annotate(county=Left("block_id", 5))
        .values_list("county")
        .annotate(n=Count("location_id"))
    )

    assert dict(rows) == expected_fcc.locations_per_county


@pytest.mark.usefixtures("loaded")
def test_parent_ids_match_geoid_prefixes() -> None:
    for model, column, length in PARENT_PREFIXES:
        mismatches = (
            model._default_manager.annotate(prefix=Left("geoid", length))
            .exclude(prefix=F(column))
            .count()
        )
        assert mismatches == 0, model.__name__


@pytest.mark.usefixtures("loaded")
def test_geometries_are_valid_wgs84_multipolygons() -> None:
    quote = connection.ops.quote_name
    for label, model in BOUNDARY_MODELS.items():
        assert model._default_manager.filter(geom__isvalid=False).count() == 0, label

        # Table names come from model metadata, never from input.
        sql = (
            f"SELECT count(*) FROM {quote(model._meta.db_table)} "  # noqa: S608
            "WHERE ST_SRID(geom) <> 4326 OR ST_SRID(internal_point) <> 4326 "
            "OR GeometryType(geom) <> 'MULTIPOLYGON'"
        )
        with connection.cursor() as cursor:
            cursor.execute(sql)
            assert cursor.fetchone() == (0,), label


@pytest.mark.usefixtures("loaded")
def test_block_internal_points_lie_in_their_county() -> None:
    sql = (
        "SELECT count(*) FROM geography_block b "
        "JOIN geography_county c ON c.geoid = left(b.geoid, 5) "
        "WHERE NOT ST_Intersects(c.geom, b.internal_point)"
    )
    with connection.cursor() as cursor:
        cursor.execute(sql)
        assert cursor.fetchone() == (0,)


@pytest.mark.usefixtures("loaded")
@pytest.mark.parametrize("level", list(RollupLevel))
def test_rollups_match_the_source(level: str, expected_fcc: sources.FccSummary) -> None:
    rows = Rollup.objects.filter(level=level).values_list("code", *COUNT_FIELDS)
    found = {code: tuple(values) for code, *values in rows}

    assert found == expected_fcc.rollups[level]


@pytest.mark.parametrize("level", list(RollupLevel))
def test_each_key_selects_what_its_rollup_counts(loaded: LoadResult, level: str) -> None:
    release = Release.objects.get(pk=loaded.release_id)
    rollups = list(Rollup.objects.filter(release=release, level=level).order_by("code"))
    for rollup in rollups[:: SELECTION_STEPS[level]]:
        totals = (
            statuses_in(release, rollup.level, rollup.code)
            .order_by()
            .aggregate(
                n=Count("pk"),
                a=Count("pk", filter=Q(any_100_20=True)),
                w=Count("pk", filter=Q(wired_100_20=True)),
                t=Count("pk", filter=Q(terrestrial_100_20=True)),
            )
        )

        assert (totals["n"], totals["a"], totals["w"], totals["t"]) == (
            rollup.locations,
            rollup.any_100_20,
            rollup.wired_100_20,
            rollup.terrestrial_100_20,
        ), rollup.code


def test_loader_counts_agree(loaded: LoadResult, expected_fcc: sources.FccSummary) -> None:
    assert loaded.source == loaded.database
    assert loaded.source.rows["location"] == expected_fcc.rows


def test_loading_twice_leaves_the_same_counts(loaded: LoadResult) -> None:
    second = load_served_unserved(RAW)

    assert second.database.as_dict() == loaded.database.as_dict()
    assert Release.objects.count() == 1
