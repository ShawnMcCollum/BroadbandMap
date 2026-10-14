"""Read the FCC Served/Unserved CSV into validated location rows."""

import csv
import io
import re
import zipfile
from collections.abc import Iterator, Sequence
from collections.abc import Set as AbstractSet
from typing import NamedTuple

from etl.errors import LoadError
from etl.files import FccFile

HEADER = (
    "location_id",
    "block_geoid",
    "h3_res8_id",
    "any_dl100_ul20",
    "wired_dl100_ul20",
    "terrestrial_dl100_ul20",
)
LOCATION_ID = re.compile(r"[1-9][0-9]{0,18}")
BLOCK_GEOID = re.compile(r"[0-9]{15}")
H3_CELL = re.compile(r"[0-9a-f]{15}")
MAX_BIGINT = 2**63 - 1


class LocationRow(NamedTuple):
    location_id: int
    block_geoid: str
    h3_res8: str
    any_100_20: bool
    wired_100_20: bool
    terrestrial_100_20: bool

    @property
    def flags(self) -> str:
        """The flags as "any,wired,terrestrial", e.g. "1,0,1"."""
        return f"{self.any_100_20:d},{self.wired_100_20:d},{self.terrestrial_100_20:d}"


def read_locations(
    fcc: FccFile, block_geoids: AbstractSet[str], block_file: str
) -> Iterator[LocationRow]:
    """Yield every row of the FCC CSV, stopping with a LoadError at the first bad one."""
    name = fcc.path.name
    with zipfile.ZipFile(fcc.path) as archive, archive.open(fcc.csv_name) as raw:
        reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8", newline=""))
        try:
            header = next(reader, None)
            if header != list(HEADER):
                raise LoadError(
                    f"{name}: expected columns {','.join(HEADER)}; found {','.join(header or [])}"
                )
            rows = 0
            for fields in reader:
                try:
                    row = parse_row(fields, fcc.state_fips, block_geoids, block_file)
                except ValueError as error:
                    raise LoadError(f"{name}: line {reader.line_num}: {error}") from error
                rows += 1
                yield row
        except UnicodeDecodeError as error:
            raise LoadError(f"{name}: not UTF-8 text") from error
        except csv.Error as error:
            raise LoadError(f"{name}: line {reader.line_num}: {error}") from error
        if not rows:
            raise LoadError(f"{name}: no data rows")


def parse_row(
    fields: Sequence[str], state_fips: str, block_geoids: AbstractSet[str], block_file: str
) -> LocationRow:
    """Check one CSV row and convert it. Raise ValueError describing the first problem."""
    if len(fields) != len(HEADER):
        raise ValueError(f"expected {len(HEADER)} fields, found {len(fields)}")
    location_id, block_geoid, h3_res8, *flag_values = fields

    if not LOCATION_ID.fullmatch(location_id) or int(location_id) > MAX_BIGINT:
        raise ValueError(f"location_id {location_id!r} is not a positive integer")
    if not BLOCK_GEOID.fullmatch(block_geoid) or not block_geoid.startswith(state_fips):
        raise ValueError(
            f"block_geoid {block_geoid!r} is not a 15-digit GEOID in state {state_fips}"
        )
    if block_geoid not in block_geoids:
        raise ValueError(f"block_geoid {block_geoid!r} is not in {block_file}")
    if not H3_CELL.fullmatch(h3_res8):
        raise ValueError(f"h3_res8_id {h3_res8!r} is not 15 lowercase hex characters")
    for column, value in zip(HEADER[3:], flag_values, strict=True):
        if value not in ("0", "1"):
            raise ValueError(f"{column} must be 0 or 1, found {value!r}")

    any_100_20, wired_100_20, terrestrial_100_20 = (value == "1" for value in flag_values)
    if (wired_100_20 and not terrestrial_100_20) or (terrestrial_100_20 and not any_100_20):
        raise ValueError(
            "flags are not nested (wired implies terrestrial implies any): "
            f"any={any_100_20:d} wired={wired_100_20:d} terrestrial={terrestrial_100_20:d}"
        )
    return LocationRow(
        int(location_id), block_geoid, h3_res8, any_100_20, wired_100_20, terrestrial_100_20
    )
