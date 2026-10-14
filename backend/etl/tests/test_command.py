from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from bdc.models import Location
from etl.management.commands.load_served_unserved import Command
from etl.tests.helpers import make_data_dir


@pytest.mark.django_db
def test_command_loads_and_reports(tmp_path: Path) -> None:
    out = StringIO()

    call_command("load_served_unserved", data_dir=make_data_dir(tmp_path), stdout=out)

    assert "census blocks: 49 rows" in out.getvalue()
    assert "Loaded December 2025 (processed 2026-09-29): 31 locations in" in out.getvalue()
    assert Location.objects.count() == 31


@pytest.mark.django_db
def test_command_reports_load_errors(tmp_path: Path) -> None:
    with pytest.raises(CommandError, match="does not exist"):
        call_command("load_served_unserved", data_dir=tmp_path / "nope")


def test_default_data_dir() -> None:
    parser = Command().create_parser("manage.py", "load_served_unserved")

    assert parser.parse_args([]).data_dir == Path("/data/raw")
