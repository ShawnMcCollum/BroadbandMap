"""Lay out the test fixtures like the real data directory, and edit the fixture CSV."""

import shutil
import zipfile
from collections.abc import Mapping
from pathlib import Path

from django.db import connection

from etl.load import LOADER_MODELS

FIXTURES = Path(__file__).parent / "fixtures"
MALFORMED = FIXTURES / "malformed"
FCC_STEM = "bdc_39_fixed_broadband_served_unserved_D25_29sep2026"
# A second release: June 2025, processed after December 2025, as the FCC did
J25_STEM = "bdc_39_fixed_broadband_served_unserved_J25_01oct2026"

# The fixture CSV's rollups: (level, code, locations, any, wired, terrestrial), sorted. The
# fixture blocks lie in Troy township and in no place.
FIXTURE_ROLLUPS = [
    ("block", "390553120001004", 1, 0, 0, 0),
    ("block", "390553120001013", 5, 5, 0, 5),
    ("block", "390553120002011", 8, 8, 5, 6),
    ("block", "390553120002014", 7, 7, 5, 6),
    ("block", "390553120002016", 3, 3, 0, 3),
    ("block", "390553120002019", 7, 7, 0, 0),
    ("block_group", "390553120001", 6, 5, 0, 5),
    ("block_group", "390553120002", 25, 25, 10, 15),
    ("county", "39055", 31, 30, 10, 20),
    ("county_subdivision", "3905577574", 31, 30, 10, 20),
    ("h3_res8", "882ab14c07fffff", 7, 7, 0, 0),
    ("h3_res8", "882ab14c65fffff", 1, 1, 0, 1),
    ("h3_res8", "882ab14e23fffff", 1, 1, 0, 1),
    ("h3_res8", "882ab14e27fffff", 7, 7, 0, 7),
    ("h3_res8", "882ab14f31fffff", 1, 1, 0, 1),
    ("h3_res8", "882ab14f33fffff", 13, 13, 10, 10),
    ("h3_res8", "882ab14f59fffff", 1, 0, 0, 0),
    ("tract", "39055312000", 31, 30, 10, 20),
]

# The rollups of j25_csv(): the fixture CSV without its last row, location 1004026994, the only
# location in block 390553120001004 and cell 882ab14f59fffff, and served by nothing
J25_ROLLUPS = [
    ("block", "390553120001013", 5, 5, 0, 5),
    ("block", "390553120002011", 8, 8, 5, 6),
    ("block", "390553120002014", 7, 7, 5, 6),
    ("block", "390553120002016", 3, 3, 0, 3),
    ("block", "390553120002019", 7, 7, 0, 0),
    ("block_group", "390553120001", 5, 5, 0, 5),
    ("block_group", "390553120002", 25, 25, 10, 15),
    ("county", "39055", 30, 30, 10, 20),
    ("county_subdivision", "3905577574", 30, 30, 10, 20),
    ("h3_res8", "882ab14c07fffff", 7, 7, 0, 0),
    ("h3_res8", "882ab14c65fffff", 1, 1, 0, 1),
    ("h3_res8", "882ab14e23fffff", 1, 1, 0, 1),
    ("h3_res8", "882ab14e27fffff", 7, 7, 0, 7),
    ("h3_res8", "882ab14f31fffff", 1, 1, 0, 1),
    ("h3_res8", "882ab14f33fffff", 13, 13, 10, 10),
    ("tract", "39055312000", 30, 30, 10, 20),
]

# West Virginia's file of the release FCC_STEM names. Its locations are made up, in real blocks of
# the West Virginia fixtures; the last one shares cell 882ab14f33fffff with 13 Ohio fixture
# locations, as a location across a state line would.
WV_STEM = "bdc_54_fixed_broadband_served_unserved_D25_29sep2026"

# The West Virginia CSV's rollups, sorted as FIXTURE_ROLLUPS. Blocks 540090311031011 and
# 540090311032016 are in Weirton city; 540090311032004 is not.
WV_ROLLUPS = [
    ("block", "540090311031011", 3, 3, 2, 3),
    ("block", "540090311032004", 1, 1, 0, 1),
    ("block", "540090311032016", 2, 1, 0, 0),
    ("block_group", "540090311031", 3, 3, 2, 3),
    ("block_group", "540090311032", 3, 2, 0, 1),
    ("county", "54009", 6, 5, 2, 4),
    ("county_subdivision", "5400993552", 6, 5, 2, 4),
    ("h3_res8", "882a8a6c13fffff", 3, 3, 2, 3),
    ("h3_res8", "882a8a6c17fffff", 2, 1, 0, 0),
    ("h3_res8", "882ab14f33fffff", 1, 1, 0, 1),
    ("place", "5485156", 5, 4, 2, 3),
    ("tract", "54009031103", 6, 5, 2, 4),
]


def fixture_csv() -> str:
    """The fixture CSV's text."""
    return (FIXTURES / "served_unserved.csv").read_text(encoding="utf-8")


def wv_csv() -> str:
    """West Virginia's CSV, of the same release as the Ohio fixture."""
    return (FIXTURES / "served_unserved_54.csv").read_text(encoding="utf-8")


def j25_csv() -> str:
    """The fixture CSV without its last row, as a second release's file."""
    return "\n".join(fixture_csv().splitlines()[:-1]) + "\n"


def edit_csv(line: int, column: str, value: str) -> str:
    """The fixture CSV with one field changed. Line 1 is the header."""
    lines = fixture_csv().splitlines()
    index = lines[0].split(",").index(column)
    fields = lines[line - 1].split(",")
    fields[index] = value
    lines[line - 1] = ",".join(fields)
    return "\n".join(lines) + "\n"


def make_data_dir(
    root: Path,
    *,
    csv: str | bytes | None = None,
    fcc_stem: str = FCC_STEM,
    tiger: Mapping[str, Path] | None = None,
) -> Path:
    """Lay out root/raw like /data/raw from the fixtures and return it.

    csv replaces the fixture CSV inside the FCC zip; tiger maps a TIGER file
    name (e.g. "tl_2020_39_tract") to a replacement zip.
    """
    raw = root / "raw"
    tiger_dir = raw / "tiger2020"
    tiger_dir.mkdir(parents=True, exist_ok=True)
    for path in (FIXTURES / "tiger2020").glob("*.zip"):
        shutil.copy(path, tiger_dir / path.name)
    for name, replacement in (tiger or {}).items():
        shutil.copy(replacement, tiger_dir / f"{name}.zip")
    with zipfile.ZipFile(raw / f"{fcc_stem}.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{fcc_stem}.csv", fixture_csv() if csv is None else csv)
    return raw


def clear_tables() -> None:
    """Empty every table the loader owns, in one statement."""
    quote = connection.ops.quote_name
    tables = ", ".join(quote(model._meta.db_table) for model in LOADER_MODELS)
    with connection.cursor() as cursor:
        cursor.execute(f"TRUNCATE {tables}")
