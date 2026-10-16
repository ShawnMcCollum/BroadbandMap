import re
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.tests.helpers import LOAD_RUNNING, REFUSED_BY_LOAD, lock_held_elsewhere, table_stats
from etl.load import LOADER_MODELS
from etl.management.commands.load_served_unserved import Command
from etl.tests.helpers import FCC_STEM, J25_STEM, WV_STEM, j25_csv, make_data_dir, wv_csv
from served_unserved.models import ServedStatus


@pytest.mark.django_db
def test_command_loads_and_reports(tmp_path: Path) -> None:
    out = StringIO()

    call_command("load_served_unserved", data_dir=make_data_dir(tmp_path), stdout=out)

    assert "census blocks: 49 rows" in out.getvalue()
    assert (
        "Loaded Ohio into December 2025 (processed 2026-09-29): 31 locations in" in out.getvalue()
    )
    assert ServedStatus.objects.count() == 31


@pytest.mark.django_db(transaction=True)
def test_command_vacuums_and_analyzes_the_loaded_tables(tmp_path: Path) -> None:
    before = table_stats(LOADER_MODELS)
    out = StringIO()

    call_command("load_served_unserved", data_dir=make_data_dir(tmp_path), stdout=out)

    after = table_stats(LOADER_MODELS)
    *_, loaded, vacuumed = out.getvalue().splitlines()
    assert loaded.startswith(
        "Loaded Ohio into December 2025 (processed 2026-09-29): 31 locations in"
    )
    assert re.fullmatch(r"Vacuumed and analyzed 10 tables in \d+ s", vacuumed)
    for model in LOADER_MODELS:
        table = model._meta.db_table
        assert after[table].vacuum_count == before[table].vacuum_count + 1, table
        assert after[table].analyzed_after_vacuum(), table


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

    assert "Deleted Ohio from June 2025 (processed 2026-10-01) in" in out.getvalue()
    assert "Loaded Ohio into June 2025 (processed 2026-10-01): 30 locations in" in out.getvalue()
    assert ServedStatus.objects.count() == 30


@pytest.mark.django_db
def test_command_refuses_a_loaded_release(tmp_path: Path) -> None:
    data_dir = make_data_dir(tmp_path)
    call_command("load_served_unserved", data_dir=data_dir, stdout=StringIO())

    with pytest.raises(
        CommandError,
        match=re.escape(
            "Ohio is already loaded in December 2025 (processed 2026-09-29); "
            "use --replace to load it again"
        ),
    ):
        call_command("load_served_unserved", data_dir=data_dir, stdout=StringIO())


@pytest.mark.django_db
def test_command_loads_a_second_state(tmp_path: Path) -> None:
    data_dir = make_data_dir(tmp_path)
    make_data_dir(tmp_path, csv=wv_csv(), fcc_stem=WV_STEM)
    out = StringIO()

    call_command(
        "load_served_unserved", data_dir=data_dir, fcc_file=Path(f"{FCC_STEM}.zip"), stdout=out
    )
    call_command(
        "load_served_unserved", data_dir=data_dir, fcc_file=Path(f"{WV_STEM}.zip"), stdout=out
    )

    assert (
        "Loaded West Virginia into December 2025 (processed 2026-09-29): 6 locations in"
        in out.getvalue()
    )
    assert ServedStatus.objects.count() == 37


@pytest.mark.django_db
def test_command_reports_the_running_writer(tmp_path: Path) -> None:
    data_dir = make_data_dir(tmp_path)

    with lock_held_elsewhere(LOAD_RUNNING), pytest.raises(CommandError) as refused:
        call_command("load_served_unserved", data_dir=data_dir, stdout=StringIO())

    assert REFUSED_BY_LOAD.fullmatch(str(refused.value))
    assert ServedStatus.objects.count() == 0


def test_default_options() -> None:
    parser = Command().create_parser("manage.py", "load_served_unserved")

    options = parser.parse_args([])

    assert options.data_dir == Path("/data/raw")
    assert options.fcc_file is None
    assert options.replace is False
