from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from etl.management.commands.load_served_unserved import Command
from etl.tests.helpers import J25_STEM, j25_csv, make_data_dir
from served_unserved.models import ServedStatus


@pytest.mark.django_db
def test_command_loads_and_reports(tmp_path: Path) -> None:
    out = StringIO()

    call_command("load_served_unserved", data_dir=make_data_dir(tmp_path), stdout=out)

    assert "census blocks: 49 rows" in out.getvalue()
    assert "Loaded December 2025 (processed 2026-09-29): 31 locations in" in out.getvalue()
    assert ServedStatus.objects.count() == 31


@pytest.mark.django_db
def test_command_reports_load_errors(tmp_path: Path) -> None:
    with pytest.raises(CommandError, match="does not exist"):
        call_command("load_served_unserved", data_dir=tmp_path / "nope")


@pytest.mark.django_db
def test_command_loads_a_named_file_and_replaces_it(tmp_path: Path) -> None:
    data_dir = make_data_dir(tmp_path)
    make_data_dir(tmp_path, csv=j25_csv(), fcc_stem=J25_STEM)
    j25 = Path(f"{J25_STEM}.zip")
    out = StringIO()

    call_command("load_served_unserved", data_dir=data_dir, fcc_file=j25, stdout=out)
    call_command("load_served_unserved", data_dir=data_dir, fcc_file=j25, replace=True, stdout=out)

    assert "Deleted June 2025 (processed 2026-10-01) in" in out.getvalue()
    assert "Loaded June 2025 (processed 2026-10-01): 30 locations in" in out.getvalue()
    assert ServedStatus.objects.count() == 30


@pytest.mark.django_db
def test_command_refuses_a_loaded_release(tmp_path: Path) -> None:
    data_dir = make_data_dir(tmp_path)
    call_command("load_served_unserved", data_dir=data_dir, stdout=StringIO())

    with pytest.raises(CommandError, match="is already loaded; use --replace to load it again"):
        call_command("load_served_unserved", data_dir=data_dir, stdout=StringIO())


def test_default_options() -> None:
    parser = Command().create_parser("manage.py", "load_served_unserved")

    options = parser.parse_args([])

    assert options.data_dir == Path("/data/raw")
    assert options.fcc_file is None
    assert options.replace is False
