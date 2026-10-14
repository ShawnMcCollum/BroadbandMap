from pathlib import Path

import pytest

from etl.errors import LoadError
from etl.fcc import LocationRow, read_locations
from etl.files import find_fcc_file
from etl.tests.helpers import FIXTURES, edit_csv, fixture_csv, make_data_dir
from etl.tests.sources import dbf_records

BLOCK_FILE = "tl_2020_39_tabblock20.zip"
BLOCKS = {
    record["GEOID20"]
    for record in dbf_records(FIXTURES / "tiger2020" / BLOCK_FILE, "tl_2020_39_tabblock20.dbf")
}


def read(root: Path, csv: str | bytes) -> list[LocationRow]:
    fcc = find_fcc_file(make_data_dir(root, csv=csv))
    return list(read_locations(fcc, BLOCKS, BLOCK_FILE))


def without_column(text: str, index: int) -> str:
    """The CSV with one column removed from every line."""
    lines = (
        ",".join(f for i, f in enumerate(line.split(",")) if i != index)
        for line in text.splitlines()
    )
    return "\n".join(lines) + "\n"


def with_short_line(text: str, line: int) -> str:
    """The CSV with the last field removed from one line."""
    lines = text.splitlines()
    lines[line - 1] = lines[line - 1].rsplit(",", 1)[0]
    return "\n".join(lines) + "\n"


def test_reads_every_row(tmp_path: Path) -> None:
    rows = read(tmp_path, fixture_csv())

    assert len(rows) == 31
    assert rows[0] == LocationRow(
        1003988971, "390553120002014", "882ab14f33fffff", True, True, True
    )
    assert rows[-1] == LocationRow(
        1004026994, "390553120001004", "882ab14f59fffff", False, False, False
    )
    assert rows[21].flags == "1,0,1"


@pytest.mark.parametrize(
    ("csv", "message"),
    [
        pytest.param(
            fixture_csv().replace("h3_res8_id", "h3", 1),
            "expected columns location_id,block_geoid,h3_res8_id,",
            id="renamed-header",
        ),
        pytest.param(without_column(fixture_csv(), 2), "expected columns", id="missing-column"),
        pytest.param(
            with_short_line(fixture_csv(), 4),
            "line 4: expected 6 fields, found 5",
            id="short-line",
        ),
        pytest.param(
            edit_csv(2, "location_id", "abc"),
            "line 2: location_id 'abc' is not a positive integer",
            id="location-id-text",
        ),
        pytest.param(
            edit_csv(2, "location_id", "0"),
            "line 2: location_id '0' is not a positive integer",
            id="location-id-zero",
        ),
        pytest.param(
            edit_csv(5, "block_geoid", "39055312000201"),
            "line 5: block_geoid '39055312000201' is not a 15-digit GEOID in state 39",
            id="geoid-too-short",
        ),
        pytest.param(
            edit_csv(5, "block_geoid", "180553120002014"),
            "line 5: block_geoid '180553120002014' is not a 15-digit GEOID in state 39",
            id="geoid-other-state",
        ),
        pytest.param(
            edit_csv(3, "block_geoid", "390553120009999"),
            "line 3: block_geoid '390553120009999' is not in tl_2020_39_tabblock20.zip",
            id="geoid-unknown-block",
        ),
        pytest.param(
            edit_csv(6, "h3_res8_id", "882AB14F33FFFFF"),
            "line 6: h3_res8_id '882AB14F33FFFFF' is not 15 lowercase hex characters",
            id="h3-uppercase",
        ),
        pytest.param(
            edit_csv(7, "wired_dl100_ul20", "2"),
            "line 7: wired_dl100_ul20 must be 0 or 1, found '2'",
            id="flag-two",
        ),
        pytest.param(
            edit_csv(8, "any_dl100_ul20", ""),
            "line 8: any_dl100_ul20 must be 0 or 1, found ''",
            id="flag-empty",
        ),
        pytest.param(
            edit_csv(2, "terrestrial_dl100_ul20", "0"),
            "line 2: flags are not nested",
            id="flags-not-nested",
        ),
        pytest.param(fixture_csv().splitlines()[0] + "\n", "no data rows", id="header-only"),
    ],
)
def test_rejects_malformed_rows(tmp_path: Path, csv: str, message: str) -> None:
    with pytest.raises(LoadError, match=message):
        read(tmp_path, csv)


def test_rejects_text_that_is_not_utf8(tmp_path: Path) -> None:
    with pytest.raises(LoadError, match="not UTF-8 text"):
        read(tmp_path, b"\xff\xfe\x00")
