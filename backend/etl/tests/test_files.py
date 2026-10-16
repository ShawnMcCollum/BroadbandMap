import shutil
import zipfile
from datetime import date
from pathlib import Path

import pytest

from etl.errors import LoadError
from etl.files import check_files, find_fcc_file, read_fcc_name, tiger_path
from etl.tests.helpers import FCC_STEM, J25_STEM, make_data_dir
from etl.tiger import LEVELS


def check_data_dir(data_dir: Path) -> None:
    """Run the same checks the loader runs before it opens a transaction."""
    tiger_files = [tiger_path(data_dir, level.file_name("39")) for level in LEVELS]
    check_files(find_fcc_file(data_dir), tiger_files)


def rewrite_zip(path: Path, drop: str) -> None:
    """Rewrite a zip without one of its members."""
    with zipfile.ZipFile(path) as source:
        kept = {name: source.read(name) for name in source.namelist() if name != drop}
    with zipfile.ZipFile(path, "w") as target:
        for name, data in kept.items():
            target.writestr(name, data)


def test_find_fcc_file_reads_the_release_from_its_name(tmp_path: Path) -> None:
    data_dir = make_data_dir(tmp_path)

    fcc = find_fcc_file(data_dir)

    assert fcc.path == data_dir / f"{FCC_STEM}.zip"
    assert fcc.state_fips == "39"
    assert fcc.filing_period == "D25"
    assert fcc.as_of == date(2025, 12, 31)
    assert fcc.processed_on == date(2026, 9, 29)
    assert fcc.csv_name == f"{FCC_STEM}.csv"


def test_june_release_is_as_of_june_30(tmp_path: Path) -> None:
    stem = "bdc_39_fixed_broadband_served_unserved_J26_15mar2027"

    fcc = find_fcc_file(make_data_dir(tmp_path, fcc_stem=stem))

    assert fcc.filing_period == "J26"
    assert fcc.as_of == date(2026, 6, 30)
    assert fcc.processed_on == date(2027, 3, 15)


def test_missing_data_dir(tmp_path: Path) -> None:
    with pytest.raises(LoadError, match="does not exist"):
        find_fcc_file(tmp_path / "nope")


def test_no_fcc_file(tmp_path: Path) -> None:
    data_dir = make_data_dir(tmp_path)
    (data_dir / f"{FCC_STEM}.zip").unlink()

    with pytest.raises(LoadError, match="no FCC Served/Unserved file"):
        find_fcc_file(data_dir)


def test_two_fcc_files(tmp_path: Path) -> None:
    data_dir = make_data_dir(tmp_path)
    older = "bdc_39_fixed_broadband_served_unserved_D24_01jan2025"
    shutil.copy(data_dir / f"{FCC_STEM}.zip", data_dir / f"{older}.zip")

    with pytest.raises(
        LoadError, match=r"found 2 FCC Served/Unserved files in .*; choose one with --fcc-file"
    ):
        find_fcc_file(data_dir)


def test_read_fcc_name_reads_the_named_file(tmp_path: Path) -> None:
    data_dir = make_data_dir(tmp_path)
    make_data_dir(tmp_path, fcc_stem=J25_STEM)

    fcc = read_fcc_name(data_dir / f"{J25_STEM}.zip")

    assert fcc.path == data_dir / f"{J25_STEM}.zip"
    assert fcc.filing_period == "J25"
    assert fcc.as_of == date(2025, 6, 30)
    assert fcc.processed_on == date(2026, 10, 1)


def test_read_fcc_name_of_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(LoadError, match=r"missing file .*nope\.zip"):
        read_fcc_name(tmp_path / "nope.zip")


def test_unrecognised_fcc_name(tmp_path: Path) -> None:
    stem = "bdc_39_fixed_broadband_served_unserved_X25_29sep2026"

    with pytest.raises(LoadError, match="expected a name like"):
        find_fcc_file(make_data_dir(tmp_path, fcc_stem=stem))


def test_missing_tiger_file(tmp_path: Path) -> None:
    data_dir = make_data_dir(tmp_path)
    (data_dir / "tiger2020" / "tl_2020_39_place.zip").unlink()

    with pytest.raises(LoadError, match=r"missing file .*tl_2020_39_place\.zip"):
        check_data_dir(data_dir)


def test_truncated_zip(tmp_path: Path) -> None:
    data_dir = make_data_dir(tmp_path)
    blocks = data_dir / "tiger2020" / "tl_2020_39_tabblock20.zip"
    content = blocks.read_bytes()
    blocks.write_bytes(content[: len(content) // 2])

    with pytest.raises(LoadError, match=r"tl_2020_39_tabblock20\.zip: not a valid zip file"):
        check_data_dir(data_dir)


def test_zip_without_dbf(tmp_path: Path) -> None:
    data_dir = make_data_dir(tmp_path)
    rewrite_zip(data_dir / "tiger2020" / "tl_2020_39_tract.zip", drop="tl_2020_39_tract.dbf")

    with pytest.raises(LoadError, match=r"tl_2020_39_tract\.zip: missing tl_2020_39_tract\.dbf"):
        check_data_dir(data_dir)


def test_fcc_zip_without_its_csv(tmp_path: Path) -> None:
    data_dir = make_data_dir(tmp_path)
    with zipfile.ZipFile(data_dir / f"{FCC_STEM}.zip", "w") as archive:
        archive.writestr("other.csv", "location_id\n")

    with pytest.raises(LoadError, match=f"missing {FCC_STEM}.csv"):
        check_data_dir(data_dir)
