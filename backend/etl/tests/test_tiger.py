from pathlib import Path

import pytest
from django.contrib.gis.geos import GEOSGeometry, Point

from etl.errors import LoadError
from etl.tests.helpers import FIXTURES, MALFORMED
from etl.tiger import LEVELS, Level, Row, read_level

BY_LABEL = {level.label: level for level in LEVELS}
TIGER = FIXTURES / "tiger2020"


def read(
    label: str,
    *,
    path: Path | None = None,
    state_fips: str = "39",
    parents: set[str] | None = None,
    geoids: set[str] | None = None,
) -> list[Row]:
    level: Level = BY_LABEL[label]
    path = path or TIGER / f"{level.file_name(state_fips)}.zip"
    return list(read_level(level, path, state_fips, parents, set() if geoids is None else geoids))


def row_for(rows: list[Row], geoid: str) -> Row:
    (row,) = (row for row in rows if row["geoid"] == geoid)
    return row


def test_state_file_is_filtered_to_the_state() -> None:
    geoids: set[str] = set()

    rows = read("state", geoids=geoids)

    assert len(rows) == 1
    assert rows[0]["geoid"] == "39"
    assert rows[0]["name"] == "Ohio"
    assert rows[0]["abbreviation"] == "OH"
    assert geoids == {"39"}


def test_county_row() -> None:
    rows = read("county", parents={"39"})

    assert len(rows) == 1
    assert rows[0]["geoid"] == "39055"
    assert rows[0]["name"] == "Geauga County"
    assert rows[0]["state_id"] == "39"
    assert rows[0]["land_area_m2"] == 1036773963
    assert rows[0]["water_area_m2"] == 20701156


def test_geometry_is_reprojected_and_promoted() -> None:
    (row,) = read("county", parents={"39"})

    geom = GEOSGeometry(str(row["geom"]))
    point = GEOSGeometry(str(row["internal_point"]))

    assert geom.srid == 4326
    assert geom.geom_type == "MultiPolygon"
    assert geom.num_geom == 1
    assert isinstance(point, Point)
    assert point.srid == 4326
    assert point.coords == pytest.approx((-81.1735054, 41.4993217), abs=1e-9)


def test_multipolygon_keeps_its_parts() -> None:
    rows = read("county_subdivision", parents={"39055"})

    geom = GEOSGeometry(str(row_for(rows, "3905549714")["geom"]))

    assert geom.srid == 4326
    assert geom.geom_type == "MultiPolygon"
    assert geom.num_geom == 7


def test_block_row() -> None:
    rows = read("block", parents={"390553120001", "390553120002"})

    row = row_for(rows, "390553120001004")

    assert len(rows) == 49
    assert row["name"] == "Block 1004"
    assert row["block_group_id"] == "390553120001"
    assert row["population_2020"] == 177
    assert row["housing_units_2020"] == 54
    assert row["urban_rural"] == "R"


def test_missing_field() -> None:
    path = MALFORMED / "missing_namelsad" / "tl_2020_39_tract.zip"

    with pytest.raises(LoadError, match=r"tl_2020_39_tract\.zip: missing fields: NAMELSAD"):
        read("tract", path=path, parents={"39055"})


def test_bad_geoid() -> None:
    path = MALFORMED / "bad_geoid" / "tl_2020_39_tract.zip"

    with pytest.raises(LoadError, match="feature 0: GEOID '3905531200' is not 11 digits"):
        read("tract", path=path, parents={"39055"})


def test_parent_not_loaded() -> None:
    with pytest.raises(LoadError, match="feature 0: county 39055 was not loaded"):
        read("tract", parents={"39001"})


def test_no_features_for_state() -> None:
    with pytest.raises(LoadError, match="no features for state 99"):
        read("state", state_fips="99", path=TIGER / "tl_2020_us_state.zip")
