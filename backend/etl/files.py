"""Find the source files in the data directory and check that they can be read."""

import re
import zipfile
import zlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from etl.errors import LoadError

DEFAULT_DATA_DIR = Path("/data/raw")
TIGER_DIR = "tiger2020"
FCC_GLOB = "bdc_*_fixed_broadband_served_unserved_*.zip"
FCC_NAME = re.compile(
    r"^bdc_(?P<state>[0-9]{2})_fixed_broadband_served_unserved_"
    r"(?P<period>[JD][0-9]{2})_(?P<processed>[0-9]{1,2}[a-z]{3}[0-9]{4})\.zip$"
)
SHAPEFILE_PARTS = (".shp", ".shx", ".dbf", ".prj", ".cpg")


@dataclass(frozen=True)
class FccFile:
    """The FCC Served/Unserved zip and the release described by its name."""

    path: Path
    state_fips: str
    filing_period: str
    as_of: date
    processed_on: date

    @property
    def csv_name(self) -> str:
        return self.path.stem + ".csv"


def find_fcc_file(data_dir: Path) -> FccFile:
    """Find the one FCC Served/Unserved zip in ``data_dir`` and read its name."""
    if not data_dir.is_dir():
        raise LoadError(f"data directory {data_dir} does not exist")
    matches = sorted(data_dir.glob(FCC_GLOB))
    if not matches:
        raise LoadError(f"no FCC Served/Unserved file ({FCC_GLOB}) in {data_dir}")
    if len(matches) > 1:
        names = ", ".join(match.name for match in matches)
        raise LoadError(
            f"found {len(matches)} FCC Served/Unserved files in {data_dir}; keep only one: {names}"
        )

    path = matches[0]
    parsed = FCC_NAME.match(path.name)
    if parsed is None:
        raise LoadError(
            f"{path.name}: expected a name like bdc_39_fixed_broadband_served_unserved_"
            "D25_29sep2026.zip"
        )

    period = parsed["period"]
    year = 2000 + int(period[1:])
    as_of = date(year, 12, 31) if period[0] == "D" else date(year, 6, 30)
    try:
        processed_on = datetime.strptime(parsed["processed"], "%d%b%Y").date()
    except ValueError as error:
        raise LoadError(f"{path.name}: {parsed['processed']!r} is not a date") from error
    return FccFile(
        path=path,
        state_fips=parsed["state"],
        filing_period=period,
        as_of=as_of,
        processed_on=processed_on,
    )


def tiger_path(data_dir: Path, file_name: str) -> Path:
    """Where the TIGER/Line zip called ``file_name`` (without ``.zip``) belongs."""
    return data_dir / TIGER_DIR / f"{file_name}.zip"


def check_files(fcc: FccFile, tiger_files: Iterable[Path]) -> None:
    """Check every source file, so a bad file fails in seconds instead of mid-load."""
    for path in tiger_files:
        check_zip(path, [path.stem + part for part in SHAPEFILE_PARTS])
    check_zip(fcc.path, [fcc.csv_name])


def check_zip(path: Path, members: Sequence[str]) -> None:
    """Raise LoadError unless ``path`` is an intact zip that holds every member."""
    if not path.is_file():
        raise LoadError(f"missing file {path}")
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            missing = [member for member in members if member not in names]
            if missing:
                raise LoadError(f"{path.name}: missing {', '.join(missing)}")
            bad_member = archive.testzip()
    except (zipfile.BadZipFile, EOFError, zlib.error) as error:
        raise LoadError(f"{path.name}: not a valid zip file") from error
    if bad_member is not None:
        raise LoadError(f"{path.name}: corrupt member {bad_member}")
