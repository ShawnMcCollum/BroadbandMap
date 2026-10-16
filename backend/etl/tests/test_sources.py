from pathlib import Path

from etl.tests.helpers import FCC_STEM, FIXTURE_ROLLUPS, FIXTURES, make_data_dir
from etl.tests.sources import AREA_CODES, add_up_by_area, boundary_counts, dbf_records, fcc_summary


def test_dbf_records_reads_a_tract() -> None:
    records = list(
        dbf_records(FIXTURES / "tiger2020" / "tl_2020_39_tract.zip", "tl_2020_39_tract.dbf")
    )

    assert len(records) == 1
    assert records[0]["GEOID"] == "39055312000"
    assert records[0]["NAMELSAD"] == "Census Tract 3120"
    assert records[0]["ALAND"] == "64870101"


def test_dbf_records_reads_every_block() -> None:
    blocks = FIXTURES / "tiger2020" / "tl_2020_39_tabblock20.zip"

    assert len(list(dbf_records(blocks, "tl_2020_39_tabblock20.dbf"))) == 49


def test_boundary_counts_keep_only_the_state() -> None:
    assert boundary_counts(FIXTURES / "tiger2020") == {
        "state": 1,
        "county": 1,
        "tract": 1,
        "block_group": 2,
        "block": 49,
        "place": 1,
        "county_subdivision": 2,
    }


def test_boundary_counts_of_the_second_state() -> None:
    assert boundary_counts(FIXTURES / "tiger2020", "54") == {
        "state": 1,
        "county": 1,
        "tract": 1,
        "block_group": 2,
        "block": 77,
        "place": 1,
        "county_subdivision": 1,
    }


def test_fcc_summary_counts_the_fixture_csv(tmp_path: Path) -> None:
    summary = fcc_summary(make_data_dir(tmp_path) / f"{FCC_STEM}.zip")

    assert summary.rows == 31
    assert summary.flag_combinations == {"0,0,0": 1, "1,0,0": 10, "1,0,1": 10, "1,1,1": 10}
    assert summary.locations_per_county == {"39055": 31}
    expected: dict[str, dict[str, tuple[int, int, int, int]]] = {}
    # The reader does not compute places or county subdivisions.
    for level, code, locations, any_, wired, terrestrial in FIXTURE_ROLLUPS:
        if level in AREA_CODES:
            expected.setdefault(level, {})[code] = (locations, any_, wired, terrestrial)
    assert summary.rollups == expected


def test_add_up_by_area() -> None:
    blocks = {"A": (1, 1, 0, 1), "B": (2, 1, 1, 1), "C": (3, 0, 0, 0)}

    assert add_up_by_area(blocks, {"A": "X", "B": "X", "C": None}) == {"X": (3, 2, 1, 2)}
