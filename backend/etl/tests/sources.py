"""Read the source files without the loader, to compute expected values for the full-data tests.

These readers use only the standard library and import nothing from etl or
GDAL, so they share no code, and no mistakes, with the loader.
"""

import csv
import io
import struct
import zipfile
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

# label -> (file name without .zip, whether the file covers every state)
BOUNDARY_FILES = {
    "state": ("tl_2020_us_state", True),
    "county": ("tl_2020_us_county", True),
    "tract": ("tl_2020_{state}_tract", False),
    "block_group": ("tl_2020_{state}_bg", False),
    "block": ("tl_2020_{state}_tabblock20", False),
    "place": ("tl_2020_{state}_place", False),
    "county_subdivision": ("tl_2020_{state}_cousub", False),
}


def dbf_records(zip_path: Path, member: str) -> Iterator[dict[str, str]]:
    """Read the records of a dBASE table inside a zip, as stripped strings."""
    with zipfile.ZipFile(zip_path) as archive:
        data = archive.read(member)
    count, header_length, record_length = struct.unpack("<4xIHH", data[:12])

    fields: list[tuple[str, int]] = []
    offset = 32
    while data[offset] != 0x0D:
        descriptor = data[offset : offset + 32]
        fields.append((descriptor[:11].split(b"\x00")[0].decode("ascii"), descriptor[16]))
        offset += 32

    for index in range(count):
        start = header_length + index * record_length
        record = data[start : start + record_length]
        if record[:1] == b"*":
            continue
        position = 1
        values: dict[str, str] = {}
        for name, length in fields:
            values[name] = record[position : position + length].decode("utf-8").strip()
            position += length
        yield values


def boundary_counts(tiger_dir: Path, state_fips: str = "39") -> dict[str, int]:
    """Count the records of each boundary level that belong to the state."""
    counts: dict[str, int] = {}
    for label, (stem, nationwide) in BOUNDARY_FILES.items():
        name = stem.format(state=state_fips)
        records = dbf_records(tiger_dir / f"{name}.zip", f"{name}.dbf")
        counts[label] = sum(
            1 for record in records if not nationwide or record["STATEFP"] == state_fips
        )
    return counts


class FccSummary(NamedTuple):
    rows: int
    flag_combinations: Counter[str]
    locations_per_county: Counter[str]


def fcc_summary(zip_path: Path) -> FccSummary:
    """Count the rows, flag combinations and locations per county in the FCC zip's one CSV."""
    rows = 0
    flag_combinations: Counter[str] = Counter()
    locations_per_county: Counter[str] = Counter()
    with zipfile.ZipFile(zip_path) as archive:
        (member,) = archive.namelist()
        with archive.open(member) as raw:
            for row in csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8", newline="")):
                rows += 1
                flags = ",".join(
                    row[column]
                    for column in ("any_dl100_ul20", "wired_dl100_ul20", "terrestrial_dl100_ul20")
                )
                flag_combinations[flags] += 1
                locations_per_county[row["block_geoid"][:5]] += 1
    return FccSummary(rows, flag_combinations, locations_per_county)
