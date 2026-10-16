import json
import re
import shutil
import time
from collections.abc import Iterator
from collections.abc import Set as AbstractSet
from datetime import date
from pathlib import Path

import pytest
from django.contrib.gis.geos import MultiPolygon, Polygon
from django.db import connection, transaction
from django.db.models import F, ForeignObjectRel
from pytest import MonkeyPatch

from bdc.models import Release
from core.tests.helpers import (
    LOAD_RUNNING,
    REFUSED_BY_LOAD,
    backend_pid,
    exclusive_locks,
    lock_held_elsewhere,
)
from core.write_lock import Holder, WriteLockHeld, write_lock_holder
from etl.errors import LoadError, ReconciliationError
from etl.fcc import LocationRow, read_locations
from etl.files import FccFile
from etl.load import LOADER_MODELS, LoadResult, load_served_unserved, loaded_release
from etl.reconcile import Counts, database_counts
from etl.tests.helpers import (
    FCC_STEM,
    FIXTURE_ROLLUPS,
    J25_ROLLUPS,
    J25_STEM,
    MALFORMED,
    WV_ROLLUPS,
    WV_STEM,
    edit_csv,
    j25_csv,
    make_data_dir,
    wv_csv,
)
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
from served_unserved.models import Rollup, ServedStatus
from served_unserved.rollups import COUNT_FIELDS, build_rollups, statuses_in

pytestmark = pytest.mark.django_db

FIXTURE_COUNTS = {
    "State": 1,
    "County": 1,
    "Tract": 1,
    "BlockGroup": 2,
    "Block": 49,
    "Place": 1,
    "CountySubdivision": 2,
    "Rollup": 18,
    "ServedStatus": 31,
    "Release": 1,
}
EMPTY_COUNTS = dict.fromkeys(FIXTURE_COUNTS, 0)
# Ohio's and West Virginia's fixture files, loaded into one release
BOTH_COUNTS = {
    "State": 2,
    "County": 2,
    "Tract": 2,
    "BlockGroup": 4,
    "Block": 126,
    "Place": 2,
    "CountySubdivision": 3,
    "Rollup": 30,
    "ServedStatus": 37,
    "Release": 1,
}
WV_SOURCE_ROWS = {
    "state": 1,
    "county": 1,
    "tract": 1,
    "block_group": 2,
    "block": 77,
    "place": 1,
    "county_subdivision": 1,
    "served_status": 6,
}


def table_counts() -> dict[str, int]:
    return {model.__name__: model._default_manager.count() for model in LOADER_MODELS}


def load(tmp_path: Path, csv: str | None = None, *, replace: bool = False) -> LoadResult:
    return load_served_unserved(make_data_dir(tmp_path, csv=csv), replace=replace)


def load_j25(tmp_path: Path) -> LoadResult:
    """Load the second release, June 2025, from its own data directory."""
    return load_served_unserved(make_data_dir(tmp_path / "j25", csv=j25_csv(), fcc_stem=J25_STEM))


def load_wv(tmp_path: Path, *, replace: bool = False) -> LoadResult:
    """Load West Virginia's file of the December 2025 release, from its own data directory."""
    data_dir = make_data_dir(tmp_path / "wv", csv=wv_csv(), fcc_stem=WV_STEM)
    return load_served_unserved(data_dir, replace=replace)


def rollups(release: Release) -> list[tuple[object, ...]]:
    return sorted(
        Rollup.objects.filter(release=release).values_list("level", "code", *COUNT_FIELDS)
    )


def state_rollups(release: Release, state_fips: str) -> list[tuple[object, ...]]:
    return sorted(
        Rollup.objects.filter(release=release, state_id=state_fips).values_list(
            "level", "code", *COUNT_FIELDS
        )
    )


def snapshot(release: Release) -> tuple[list[tuple[object, ...]], list[tuple[object, ...]]]:
    """A release's status and rollup rows, row ids included."""
    statuses = ServedStatus.objects.filter(release=release).order_by("id").values_list()
    rollup_rows = Rollup.objects.filter(release=release).order_by("id").values_list()
    return list(statuses), list(rollup_rows)


def state_snapshot(
    release: Release, state_fips: str
) -> tuple[list[tuple[object, ...]], list[tuple[object, ...]]]:
    """A state's status and rollup rows in a release, row ids included."""
    statuses = ServedStatus.objects.filter(release=release, block__geoid__startswith=state_fips)
    rollup_rows = Rollup.objects.filter(release=release, state_id=state_fips)
    return list(statuses.order_by("id").values_list()), list(
        rollup_rows.order_by("id").values_list()
    )


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
        "served_status": 31,
    }
    assert result.source.flag_combinations == {"0,0,0": 1, "1,0,0": 10, "1,0,1": 10, "1,1,1": 10}
    assert result.source.locations_per_county == {"39055": 31}
    assert result.source.county_rollups == {
        "39055:locations": 31,
        "39055:any_100_20": 30,
        "39055:wired_100_20": 10,
        "39055:terrestrial_100_20": 20,
    }
    assert result.source.rollup_totals == {
        f"{level}:{name}": value
        for level in (
            "county",
            "tract",
            "block_group",
            "block",
            "h3_res8",
            "place",
            "county_subdivision",
        )
        for name, value in (
            ("locations", 31),
            ("any_100_20", 30),
            ("wired_100_20", 10),
            ("terrestrial_100_20", 20),
        )
    }
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


def test_status_rows(tmp_path: Path) -> None:
    load(tmp_path)

    status = ServedStatus.objects.get(location_id=1004026994)
    assert status.block_id == "390553120001004"
    assert status.h3_res8 == "882ab14f59fffff"

    flags = {
        status.location_id: (status.any_100_20, status.wired_100_20, status.terrestrial_100_20)
        for status in ServedStatus.objects.all()
    }
    assert flags[1004026994] == (False, False, False)
    assert flags[1003988971] == (True, True, True)
    assert flags[1003989144] == (True, False, True)
    assert flags[1003988997] == (True, False, False)
    assert ServedStatus.objects.exclude(release=Release.objects.get()).count() == 0


def test_reads_the_fcc_file_once(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    opened: list[str] = []

    def counted(
        fcc: FccFile, block_geoids: AbstractSet[str], block_file: str
    ) -> Iterator[LocationRow]:
        opened.append(fcc.path.name)
        return read_locations(fcc, block_geoids, block_file)

    monkeypatch.setattr("etl.load.read_locations", counted)

    load(tmp_path)

    assert opened == [f"{FCC_STEM}.zip"]


def test_builds_the_rollups(tmp_path: Path) -> None:
    load(tmp_path)

    release_pk = Release.objects.get().pk
    assert set(Rollup.objects.values_list("release_id", flat=True)) == {release_pk}
    rows = sorted(Rollup.objects.values_list("level", "code", *COUNT_FIELDS))
    assert rows == FIXTURE_ROLLUPS


def test_assigns_each_block_its_county_subdivision(tmp_path: Path) -> None:
    load(tmp_path)

    assert Block.objects.filter(county_subdivision_id="3905577574").count() == 49
    assert Block.objects.exclude(place=None).count() == 0


def test_release_comes_from_the_file_name(tmp_path: Path) -> None:
    result = load(tmp_path)

    release = Release.objects.get()
    assert release.filing_period == "D25"
    assert release.as_of == date(2025, 12, 31)
    assert release.processed_on == date(2026, 9, 29)
    assert (result.as_of, result.processed_on) == (release.as_of, release.processed_on)
    assert result.as_dict()["as_of"] == "2025-12-31"
    assert result.as_dict()["processed_on"] == "2026-09-29"
    assert result.state_fips == "39"
    assert result.as_dict()["state_fips"] == "39"


def test_second_release_is_added_beside_the_first(tmp_path: Path) -> None:
    load(tmp_path)
    december = Release.objects.get()
    before = snapshot(december)

    result = load_j25(tmp_path)

    assert [str(release) for release in Release.objects.all()] == [
        "December 2025 (processed 2026-09-29)",
        "June 2025 (processed 2026-10-01)",
    ]
    assert snapshot(december) == before
    june = Release.objects.get(filing_period="J25")
    assert rollups(june) == J25_ROLLUPS
    assert table_counts() == FIXTURE_COUNTS | {"Release": 2, "ServedStatus": 61, "Rollup": 34}
    assert (result.as_of, result.processed_on) == (date(2025, 6, 30), date(2026, 10, 1))
    assert result.source == result.database
    assert result.source.rows == {"served_status": 30}


def test_second_release_needs_no_tiger_files(tmp_path: Path) -> None:
    load(tmp_path)
    data_dir = make_data_dir(tmp_path / "j25", csv=j25_csv(), fcc_stem=J25_STEM)
    shutil.rmtree(data_dir / "tiger2020")

    load_served_unserved(data_dir)

    assert Release.objects.count() == 2


def test_releases_load_in_any_order(tmp_path: Path) -> None:
    load_j25(tmp_path)
    load(tmp_path)

    december, june = Release.objects.all()
    assert (december.filing_period, june.filing_period) == ("D25", "J25")
    assert rollups(december) == FIXTURE_ROLLUPS
    assert rollups(june) == J25_ROLLUPS


def test_fcc_file_chooses_among_several(tmp_path: Path) -> None:
    data_dir = make_data_dir(tmp_path)
    make_data_dir(tmp_path, csv=j25_csv(), fcc_stem=J25_STEM)

    load_served_unserved(data_dir, fcc_file=Path(f"{J25_STEM}.zip"))
    load_served_unserved(data_dir, fcc_file=data_dir / f"{FCC_STEM}.zip")

    assert list(Release.objects.values_list("filing_period", flat=True)) == ["D25", "J25"]


def test_loaded_state_is_refused(tmp_path: Path) -> None:
    load(tmp_path)
    before = snapshot(Release.objects.get())

    with pytest.raises(
        LoadError,
        match=re.escape(
            "Ohio is already loaded in December 2025 (processed 2026-09-29); "
            "use --replace to load it again"
        ),
    ):
        load(tmp_path)

    assert snapshot(Release.objects.get()) == before


def test_replace_loads_the_release_again(tmp_path: Path) -> None:
    first = load(tmp_path)
    release_pk = Release.objects.get().pk

    second = load(tmp_path, replace=True)

    assert Release.objects.get().pk == release_pk
    assert table_counts() == FIXTURE_COUNTS
    assert second.source == second.database
    assert second.database.rows == {"served_status": 31}
    for name in ("flag_combinations", "locations_per_county", "county_rollups", "rollup_totals"):
        assert getattr(second.database, name) == getattr(first.database, name), name


def test_replace_leaves_other_releases_alone(tmp_path: Path) -> None:
    load(tmp_path)
    load_j25(tmp_path)
    june = Release.objects.get(filing_period="J25")
    before = snapshot(june)

    load(tmp_path, replace=True)

    assert snapshot(june) == before
    assert rollups(Release.objects.get(filing_period="D25")) == FIXTURE_ROLLUPS


def test_failed_replace_leaves_the_database_unchanged(tmp_path: Path) -> None:
    load(tmp_path / "good")
    release = Release.objects.get()
    before = snapshot(release)

    with pytest.raises(LoadError, match="wired_dl100_ul20 must be 0 or 1"):
        load(tmp_path / "bad", csv=edit_csv(7, "wired_dl100_ul20", "2"), replace=True)

    assert table_counts() == FIXTURE_COUNTS
    assert snapshot(release) == before


def test_blocks_without_a_county_subdivision_are_refused(tmp_path: Path) -> None:
    load(tmp_path)
    Block.objects.filter(pk="390553120001004").update(county_subdivision=None)

    with pytest.raises(
        LoadError,
        match=re.escape("census blocks without a county subdivision: 390553120001004;"),
    ):
        load_j25(tmp_path)

    assert Release.objects.count() == 1


def test_no_load_takes_a_lock_that_blocks_readers(tmp_path: Path) -> None:
    # Locks are held until the transaction ends, so the last message inside it sees them all.
    held: list[list[str]] = []

    def record(message: str) -> None:
        if message == "Reconciling counts":
            held.append(exclusive_locks())

    data_dir = make_data_dir(tmp_path)
    load_served_unserved(data_dir, progress=record)
    j25_dir = make_data_dir(tmp_path / "j25", csv=j25_csv(), fcc_stem=J25_STEM)
    load_served_unserved(j25_dir, progress=record)
    load_served_unserved(data_dir, progress=record, replace=True)
    wv_dir = make_data_dir(tmp_path / "wv", csv=wv_csv(), fcc_stem=WV_STEM)
    load_served_unserved(wv_dir, progress=record)
    load_served_unserved(wv_dir, progress=record, replace=True)

    assert held == [[], [], [], [], []]


def test_takes_the_write_lock_before_reading_the_database(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    holders: list[Holder | None] = []

    def record(fcc: FccFile) -> tuple[Release | None, bool]:
        holders.append(write_lock_holder())
        return loaded_release(fcc)

    monkeypatch.setattr("etl.load.loaded_release", record)

    load(tmp_path)

    assert len(holders) == 1
    assert holders[0] is not None
    assert (holders[0].pid, holders[0].operation) == (
        backend_pid(),
        "load of state 39 into December 2025 (processed 2026-09-29)",
    )


def test_refused_while_another_writer_runs(tmp_path: Path) -> None:
    data_dir = make_data_dir(tmp_path)
    messages: list[str] = []

    with lock_held_elsewhere(LOAD_RUNNING):
        began = time.monotonic()
        with pytest.raises(WriteLockHeld) as refused:
            load_served_unserved(data_dir, progress=messages.append)
        elapsed = time.monotonic() - began

    assert REFUSED_BY_LOAD.fullmatch(str(refused.value))
    assert elapsed < 1
    assert messages == []
    assert table_counts() == EMPTY_COUNTS


def test_only_loader_tables_refer_to_loader_tables() -> None:
    # Deleting a release, or emptying the loaded tables, then reaches no other data.
    owned = set(LOADER_MODELS)
    for model in LOADER_MODELS:
        for relation in model._meta.get_fields(include_hidden=True):
            if isinstance(relation, ForeignObjectRel):
                referrer = relation.field.model
                assert referrer in owned, (
                    f"{referrer.__name__}.{relation.field.name} refers to {model.__name__}"
                )


# The B-tree indexes of each table data loads write, each read by a query that ADR 0021 names.
# An index that a field adds by default, such as a new foreign key's, fails this test until a
# decision says which query reads it.
LOADER_INDEXES = {
    "bdc_release": {"bdc_release_pkey", "bdc_release_unique_version"},
    "geography_state": {
        "geography_state_pkey",
        "geography_state_geoid_7116cb60_like",
        "geography_state_unique_abbreviation",
    },
    "geography_county": {"geography_county_pkey", "geography_county_geoid_bfda5a9e_like"},
    "geography_tract": {"geography_tract_pkey", "geography_tract_geoid_43c47ff5_like"},
    "geography_blockgroup": {
        "geography_blockgroup_pkey",
        "geography_blockgroup_geoid_79f527d7_like",
    },
    "geography_block": {
        "geography_block_pkey",
        "geography_block_geoid_97074710_like",
        "block_place",
        "block_county_subdivision",
    },
    "geography_place": {"geography_place_pkey", "geography_place_geoid_c4067e4d_like"},
    "geography_countysubdivision": {
        "geography_countysubdivision_pkey",
        "geography_countysubdivision_geoid_6482151a_like",
    },
    "served_unserved_servedstatus": {
        "served_unserved_servedstatus_pkey",
        "served_unserved_unique_location_per_release",
        "servedstatus_release_block",
        "servedstatus_release_h3",
    },
    "served_unserved_rollup": {
        "served_unserved_rollup_pkey",
        "served_unserved_rollup_unique_area_per_state",
        "rollup_release_state_level",
    },
}

BTREE_INDEXES = """
SELECT indexname FROM pg_indexes
WHERE schemaname = 'public' AND tablename = %s AND indexdef LIKE '%% USING btree %%'
"""


def test_loader_tables_have_only_the_indexes_queries_use() -> None:
    found: dict[str, set[str]] = {}
    with connection.cursor() as cursor:
        for model in LOADER_MODELS:
            table = model._meta.db_table
            cursor.execute(BTREE_INDEXES, [table])
            found[table] = {name for (name,) in cursor.fetchall()}

    assert found == LOADER_INDEXES


def test_rejected_tiger_file_rolls_back(tmp_path: Path) -> None:
    bad_tract = MALFORMED / "bad_geoid" / "tl_2020_39_tract.zip"
    data_dir = make_data_dir(tmp_path, tiger={"tl_2020_39_tract": bad_tract})

    with pytest.raises(LoadError):
        load_served_unserved(data_dir)

    assert State.objects.count() == 0
    assert County.objects.count() == 0


def test_block_outside_every_county_subdivision_rolls_back(tmp_path: Path) -> None:
    middlefield_only = MALFORMED / "no_county_subdivision" / "tl_2020_39_cousub.zip"
    data_dir = make_data_dir(tmp_path, tiger={"tl_2020_39_cousub": middlefield_only})

    with pytest.raises(
        LoadError,
        match=re.escape(
            "census blocks in no county subdivision: "
            "390553120001000, 390553120001001, 390553120001002, 390553120001003, "
            "390553120001004"
        ),
    ):
        load_served_unserved(data_dir)

    assert table_counts() == EMPTY_COUNTS


def test_duplicate_location_id(tmp_path: Path) -> None:
    with pytest.raises(LoadError, match="served_unserved_servedstatus: duplicate key value"):
        load(tmp_path, csv=edit_csv(3, "location_id", "1003988971"))

    assert table_counts() == EMPTY_COUNTS


def test_reconciliation_mismatch_rolls_back(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    def short_by_one(release: Release, state_fips: str, *, boundaries: bool = False) -> Counts:
        counts = database_counts(release, state_fips, boundaries=boundaries)
        counts.rows["served_status"] -= 1
        return counts

    monkeypatch.setattr("etl.load.database_counts", short_by_one)

    with pytest.raises(ReconciliationError, match=r"rows\[served_status\]: source 31, database 30"):
        load(tmp_path)

    assert table_counts() == EMPTY_COUNTS


def test_rollup_mismatch_rolls_back(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    def short_by_one(release: Release, state_fips: str, level: str) -> int:
        count = build_rollups(release, state_fips, level)
        if level == "county":
            Rollup.objects.filter(release=release, level=level).update(
                wired_100_20=F("wired_100_20") - 1
            )
        return count

    monkeypatch.setattr("etl.load.build_rollups", short_by_one)

    with pytest.raises(
        ReconciliationError, match=r"county_rollups\[39055:wired_100_20\]: source 10, database 9"
    ):
        load(tmp_path)

    assert table_counts() == EMPTY_COUNTS


def test_rollup_totals_mismatch_rolls_back(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    def drop_a_cell(release: Release, state_fips: str, level: str) -> int:
        count = build_rollups(release, state_fips, level)
        if level == "h3_res8":
            Rollup.objects.filter(release=release, level=level, code="882ab14f59fffff").delete()
        return count

    monkeypatch.setattr("etl.load.build_rollups", drop_a_cell)

    with pytest.raises(
        ReconciliationError, match=r"rollup_totals\[h3_res8:locations\]: source 31, database 30"
    ):
        load(tmp_path)

    assert table_counts() == EMPTY_COUNTS


def test_progress_reports_each_table(tmp_path: Path) -> None:
    messages: list[str] = []

    load_served_unserved(make_data_dir(tmp_path), progress=messages.append)

    assert any(message.startswith("census blocks: 49 rows") for message in messages)
    assert any(message.startswith("served statuses: 31 rows") for message in messages)
    assert any(
        message.startswith("block assignment: 0 of 49 blocks in a place") for message in messages
    )
    assert "Analyzing blocks and statuses" in messages
    for level, rows in (
        ("county", 1),
        ("tract", 1),
        ("block_group", 2),
        ("block", 6),
        ("h3_res8", 7),
        ("place", 0),
        ("county_subdivision", 1),
    ):
        assert any(message.startswith(f"rollups by {level}: {rows} rows") for message in messages)
    assert "Reconciling counts" in messages


def test_progress_when_the_boundaries_are_loaded(tmp_path: Path) -> None:
    load(tmp_path)
    messages: list[str] = []

    load_served_unserved(make_data_dir(tmp_path), progress=messages.append, replace=True)

    assert any(
        message.startswith("Deleted Ohio from December 2025 (processed 2026-09-29) in ")
        for message in messages
    )
    assert "Census boundaries for Ohio are already loaded" in messages
    assert not any(message.startswith("census blocks:") for message in messages)
    assert not any(message.startswith("block assignment:") for message in messages)
    assert any(message.startswith("served statuses: 31 rows") for message in messages)
    assert "Analyzing statuses" in messages


def test_second_state_joins_the_release(tmp_path: Path) -> None:
    load(tmp_path)
    release = Release.objects.get()
    ohio = state_snapshot(release, "39")

    result = load_wv(tmp_path)

    assert Release.objects.get().pk == release.pk
    assert state_snapshot(release, "39") == ohio
    assert state_rollups(release, "54") == WV_ROLLUPS
    assert table_counts() == BOTH_COUNTS
    assert result.state_fips == "54"
    assert result.source == result.database
    assert result.source.rows == WV_SOURCE_ROWS


def test_states_load_in_either_order(tmp_path: Path) -> None:
    load_wv(tmp_path)

    load(tmp_path)

    release = Release.objects.get()
    assert state_rollups(release, "39") == FIXTURE_ROLLUPS
    assert state_rollups(release, "54") == WV_ROLLUPS
    assert table_counts() == BOTH_COUNTS


def test_cell_on_the_state_line_has_a_row_per_state(tmp_path: Path) -> None:
    load(tmp_path)
    load_wv(tmp_path)

    release = Release.objects.get()
    cell = Rollup.objects.filter(release=release, level="h3_res8", code="882ab14f33fffff")
    assert list(cell.order_by("state").values_list("state_id", *COUNT_FIELDS)) == [
        ("39", 13, 13, 10, 10),
        ("54", 1, 1, 0, 1),
    ]
    assert statuses_in(release, "h3_res8", "882ab14f33fffff").count() == 14


def test_loaded_second_state_is_refused(tmp_path: Path) -> None:
    load(tmp_path)
    load_wv(tmp_path)
    release = Release.objects.get()
    before = snapshot(release)

    with pytest.raises(
        LoadError,
        match=re.escape(
            "West Virginia is already loaded in December 2025 (processed 2026-09-29); "
            "use --replace to load it again"
        ),
    ):
        load_wv(tmp_path)

    assert snapshot(release) == before


def test_replacing_a_state_leaves_the_other_alone(tmp_path: Path) -> None:
    load(tmp_path)
    load_wv(tmp_path)
    release = Release.objects.get()
    ohio = state_snapshot(release, "39")

    result = load_wv(tmp_path, replace=True)

    assert Release.objects.get().pk == release.pk
    assert state_snapshot(release, "39") == ohio
    assert state_rollups(release, "54") == WV_ROLLUPS
    assert table_counts() == BOTH_COUNTS
    assert result.source == result.database


def test_second_state_assigns_only_its_blocks(tmp_path: Path) -> None:
    load(tmp_path)
    # Middlefield township: a reassignment of Ohio's blocks would show.
    Block.objects.filter(pk="390553120001004").update(county_subdivision_id="3905549714")

    load_wv(tmp_path)

    assert Block.objects.get(pk="390553120001004").county_subdivision_id == "3905549714"
    west_virginia = Block.objects.filter(geoid__startswith="54")
    assert west_virginia.filter(county_subdivision_id="5400993552").count() == 77
    assert west_virginia.exclude(place=None).count() == 64


def test_second_state_checks_only_its_geometries(tmp_path: Path) -> None:
    load(tmp_path)
    bow_tie = Polygon(((-81.2, 41.4), (-81.1, 41.5), (-81.1, 41.4), (-81.2, 41.5), (-81.2, 41.4)))
    Tract.objects.filter(pk="39055312000").update(geom=MultiPolygon(bow_tie, srid=4326))

    load_wv(tmp_path)

    assert ServedStatus.objects.filter(block__geoid__startswith="54").count() == 6


def test_progress_for_a_second_state(tmp_path: Path) -> None:
    load(tmp_path)
    messages: list[str] = []

    data_dir = make_data_dir(tmp_path / "wv", csv=wv_csv(), fcc_stem=WV_STEM)
    load_served_unserved(data_dir, progress=messages.append)

    assert any(message.startswith("census blocks: 77 rows") for message in messages)
    assert any(
        message.startswith("block assignment: 64 of 77 blocks in a place") for message in messages
    )
    assert any(message.startswith("served statuses: 6 rows") for message in messages)
    assert "Analyzing blocks and statuses" in messages


def test_refuses_to_run_inside_another_transaction(tmp_path: Path) -> None:
    data_dir = make_data_dir(tmp_path)

    with transaction.atomic(), pytest.raises(RuntimeError, match="durable"):
        load_served_unserved(data_dir)
