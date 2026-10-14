"""Lay out the test fixtures like the real data directory, and edit the fixture CSV."""

import shutil
import zipfile
from collections.abc import Mapping
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
MALFORMED = FIXTURES / "malformed"
FCC_STEM = "bdc_39_fixed_broadband_served_unserved_D25_29sep2026"


def fixture_csv() -> str:
    """The fixture CSV's text."""
    return (FIXTURES / "served_unserved.csv").read_text(encoding="utf-8")


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
