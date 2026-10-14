import json
from datetime import date
from pathlib import Path

import pytest
from django.db import transaction
from pytest import MonkeyPatch

from bdc.models import Location, Release
from etl.errors import LoadError, ReconciliationError
from etl.load import LOADER_MODELS, LoadResult, load_served_unserved
from etl.reconcile import Counts, database_counts
from etl.tests.helpers import MALFORMED, edit_csv, make_data_dir
from etl.tiger import LEVELS
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
from served_unserved.models import ServedStatus

pytestmark = pytest.mark.django_db

FIXTURE_COUNTS = {
    "State": 1,
    "County": 1,
    "Tract": 1,
    "BlockGroup": 2,
    "Block": 49,
    "Place": 1,
    "CountySubdivision": 2,
    "Location": 31,
    "ServedStatus": 31,
    "Release": 1,
}
EMPTY_COUNTS = dict.fromkeys(FIXTURE_COUNTS, 0)


def table_counts() -> dict[str, int]:
    return {model.__name__: model._default_manager.count() for model in LOADER_MODELS}


def load(tmp_path: Path, csv: str | None = None) -> LoadResult:
    return load_served_unserved(make_data_dir(tmp_path, csv=csv))


def test_loads_the_fixture_files(tmp_path: Path) -> None:
    load(tmp_path)

    assert table_counts() == FIXTURE_COUNTS


def test_result_reports_matching_counts(tmp_path: Path) -> None:
    result = load(tmp_path)

    assert result.source == result.database
    assert result.source.rows == {
        "state": 1,
        "county": 1,
        "tract": 1,
        "block_group": 2,
        "block": 49,
        "place": 1,
        "county_subdivision": 2,
        "location": 31,
        "served_status": 31,
    }
    assert result.source.flag_combinations == {"0,0,0": 1, "1,0,0": 10, "1,0,1": 10, "1,1,1": 10}
    assert result.source.locations_per_county == {"39055": 31}
    assert json.dumps(result.as_dict())


def test_boundary_rows_match_the_source(tmp_path: Path) -> None:
    load(tmp_path)

    def check(
        model: type[Boundary],
        geoid: str,
        name: str,
        land: int,
        water: int,
        point: tuple[float, float] | None = None,
    ) -> None:
        row = model._default_manager.get(pk=geoid)
        assert row.name == name
        assert row.land_area_m2 == land
        assert row.water_area_m2 == water
        if point is not None:
            assert row.internal_point.coords == pytest.approx(point, abs=1e-9)

    check(State, "39", "Ohio", 105823700104, 10274656132, (-82.7119975, 40.4149297))
    assert State.objects.get(pk="39").abbreviation == "OH"

    check(County, "39055", "Geauga County", 1036773963, 20701156, (-81.1735054, 41.4993217))
    assert County.objects.get(pk="39055").state_id == "39"

    check(Tract, "39055312000", "Census Tract 3120", 64870101, 1795504, (-81.1492389, 41.3809158))
    assert Tract.objects.get(pk="39055312000").county_id == "39055"

    check(BlockGroup, "390553120001", "Block Group 1", 32351710, 72308)
    check(BlockGroup, "390553120002", "Block Group 2", 32518391, 1723196)
    assert set(BlockGroup.objects.values_list("tract_id", flat=True)) == {"39055312000"}

    check(Block, "390553120001004", "Block 1004", 3018165, 7228, (-81.1349002, 41.4175788))
    block = Block.objects.get(pk="390553120001004")
    assert block.block_group_id == "390553120001"
    assert block.population_2020 == 177
    assert block.housing_units_2020 == 54
    assert block.urban_rural == "R"
    assert Block.objects.filter(block_group_id="390553120001").count() == 24
    assert Block.objects.filter(block_group_id="390553120002").count() == 25

    check(Place, "3959934", "Parkman CDP", 1848558, 10918, (-81.0550121, 41.3722060))
    assert Place.objects.get(pk="3959934").state_id == "39"

    check(
        CountySubdivision,
        "3905549714",
        "Middlefield township",
        58075834,
        539675,
        (-81.0393955, 41.4679065),
    )
    assert CountySubdivision.objects.get(pk="3905577574").name == "Troy township"
    assert set(CountySubdivision.objects.values_list("county_id", flat=True)) == {"39055"}


def test_geometries_are_wgs84_multipolygons(tmp_path: Path) -> None:
    load(tmp_path)

    for level in LEVELS:
        for row in level.model._default_manager.all():
            assert row.geom.srid == 4326
            assert row.geom.geom_type == "MultiPolygon"
            assert row.internal_point.srid == 4326
    assert County.objects.get().geom.num_geom == 1
    assert CountySubdivision.objects.get(pk="3905549714").geom.num_geom == 7
    assert CountySubdivision.objects.get(pk="3905577574").geom.num_geom == 1


def test_location_and_status_rows(tmp_path: Path) -> None:
    load(tmp_path)

    location = Location.objects.get(pk=1004026994)
    assert location.block_id == "390553120001004"
    assert location.h3_res8 == "882ab14f59fffff"

    flags = {
        status.location_id: (status.any_100_20, status.wired_100_20, status.terrestrial_100_20)
        for status in ServedStatus.objects.all()
    }
    assert flags[1004026994] == (False, False, False)
    assert flags[1003988971] == (True, True, True)
    assert flags[1003989144] == (True, False, True)
    assert flags[1003988997] == (True, False, False)
    assert ServedStatus.objects.exclude(release=Release.objects.get()).count() == 0


def test_release_comes_from_the_file_name(tmp_path: Path) -> None:
    result = load(tmp_path)

    release = Release.objects.get()
    assert release.filing_period == "D25"
    assert release.as_of == date(2025, 12, 31)
    assert release.processed_on == date(2026, 9, 29)
    assert result.release_id == release.pk


def test_loading_twice_leaves_the_same_rows(tmp_path: Path) -> None:
    first = load(tmp_path)
    second = load(tmp_path)

    assert table_counts() == FIXTURE_COUNTS
    assert Release.objects.count() == 1
    assert second.database == first.database


def test_failed_load_leaves_the_database_unchanged(tmp_path: Path) -> None:
    load(tmp_path / "good")
    release_pk = Release.objects.get().pk

    with pytest.raises(LoadError):
        load(tmp_path / "bad", csv=edit_csv(7, "wired_dl100_ul20", "2"))

    assert table_counts() == FIXTURE_COUNTS
    assert Release.objects.get().pk == release_pk


def test_rejected_tiger_file_rolls_back(tmp_path: Path) -> None:
    bad_tract = MALFORMED / "bad_geoid" / "tl_2020_39_tract.zip"
    data_dir = make_data_dir(tmp_path, tiger={"tl_2020_39_tract": bad_tract})

    with pytest.raises(LoadError):
        load_served_unserved(data_dir)

    assert State.objects.count() == 0
    assert County.objects.count() == 0


def test_duplicate_location_id(tmp_path: Path) -> None:
    with pytest.raises(LoadError, match="bdc_location: duplicate key value"):
        load(tmp_path, csv=edit_csv(3, "location_id", "1003988971"))

    assert table_counts() == EMPTY_COUNTS


def test_reconciliation_mismatch_rolls_back(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    def short_by_one(release: Release) -> Counts:
        counts = database_counts(release)
        counts.rows["location"] -= 1
        return counts

    monkeypatch.setattr("etl.load.database_counts", short_by_one)

    with pytest.raises(ReconciliationError, match=r"rows\[location\]: source 31, database 30"):
        load(tmp_path)

    assert table_counts() == EMPTY_COUNTS


def test_progress_reports_each_table(tmp_path: Path) -> None:
    messages: list[str] = []

    load_served_unserved(make_data_dir(tmp_path), progress=messages.append)

    assert any(message.startswith("census blocks: 49 rows") for message in messages)
    assert any(message.startswith("served statuses: 31 rows") for message in messages)
    assert "Reconciling counts" in messages


def test_refuses_to_run_inside_another_transaction(tmp_path: Path) -> None:
    data_dir = make_data_dir(tmp_path)

    with transaction.atomic(), pytest.raises(RuntimeError, match="durable"):
        load_served_unserved(data_dir)
