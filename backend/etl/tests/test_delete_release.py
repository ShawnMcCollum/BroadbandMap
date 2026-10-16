import re
from datetime import date
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from pytest import MonkeyPatch

from bdc.models import Release
from core.tests.helpers import exclusive_locks, table_stats
from etl.load import LOADER_MODELS, load_served_unserved
from etl.management.commands.delete_release import Command
from etl.tests.helpers import J25_STEM, j25_csv, make_data_dir
from served_unserved.models import Rollup, ServedStatus

pytestmark = pytest.mark.django_db

DECEMBER = ("--as-of", "2025-12-31", "--processed-on", "2026-09-29")
JUNE = ("--as-of", "2025-06-30", "--processed-on", "2026-10-01")


def load_both(tmp_path: Path) -> None:
    """Load the fixture files' two releases: December 2025, then June 2025."""
    load_served_unserved(make_data_dir(tmp_path))
    load_served_unserved(make_data_dir(tmp_path / "j25", csv=j25_csv(), fcc_stem=J25_STEM))


def snapshot(release: Release) -> tuple[list[tuple[object, ...]], list[tuple[object, ...]]]:
    """A release's status and rollup rows, row ids included."""
    statuses = ServedStatus.objects.filter(release=release).order_by("id").values_list()
    rollups = Rollup.objects.filter(release=release).order_by("id").values_list()
    return list(statuses), list(rollups)


def test_deletes_one_release_and_leaves_the_other(tmp_path: Path) -> None:
    load_both(tmp_path)
    december = Release.objects.get(filing_period="D25")
    before = snapshot(december)
    out = StringIO()

    call_command("delete_release", *JUNE, "--no-input", stdout=out)

    assert [str(release) for release in Release.objects.all()] == [
        "December 2025 (processed 2026-09-29)"
    ]
    assert snapshot(december) == before
    assert (ServedStatus.objects.count(), Rollup.objects.count()) == (31, 18)
    assert re.fullmatch(
        r"Deleted June 2025 \(processed 2026-10-01\): 30 statuses and 16 rollups in \d+ s\.\n",
        out.getvalue(),
    )


def test_unknown_release_is_refused(tmp_path: Path) -> None:
    load_served_unserved(make_data_dir(tmp_path))
    december = Release.objects.get()
    before = snapshot(december)

    with pytest.raises(
        CommandError,
        match=re.escape(
            "no release is loaded as of 2025-06-30, processed 2026-10-01; "
            "loaded releases: --as-of 2025-12-31 --processed-on 2026-09-29"
        ),
    ):
        call_command("delete_release", *JUNE, "--no-input")

    assert snapshot(december) == before


def test_asks_before_deleting(served_status: ServedStatus, monkeypatch: MonkeyPatch) -> None:
    prompts: list[str] = []

    def answer_yes(prompt: str) -> str:
        prompts.append(prompt)
        return "yes"

    monkeypatch.setattr("builtins.input", answer_yes)
    out = StringIO()

    call_command("delete_release", *DECEMBER, stdout=out)

    assert prompts == [
        "Delete December 2025 (processed 2026-09-29), with its statuses and rollups? "
        "Type 'yes' to continue, or 'no' to cancel: "
    ]
    assert out.getvalue().startswith("Deleted December 2025 (processed 2026-09-29): ")
    assert (Release.objects.count(), ServedStatus.objects.count()) == (0, 0)


@pytest.mark.parametrize("answer", ["no", "", "y", "YES"])
def test_any_answer_but_yes_cancels(
    served_status: ServedStatus, monkeypatch: MonkeyPatch, answer: str
) -> None:
    monkeypatch.setattr("builtins.input", lambda prompt: answer)
    out = StringIO()

    call_command("delete_release", *DECEMBER, stdout=out)

    assert out.getvalue() == "Deletion cancelled.\n"
    assert (Release.objects.count(), ServedStatus.objects.count()) == (1, 1)


def test_no_answer_is_an_error(served_status: ServedStatus, monkeypatch: MonkeyPatch) -> None:
    def no_answer(prompt: str) -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", no_answer)

    with pytest.raises(
        CommandError,
        match=re.escape(
            "no answer to the confirmation question; use --no-input to delete without asking"
        ),
    ):
        call_command("delete_release", *DECEMBER)

    assert (Release.objects.count(), ServedStatus.objects.count()) == (1, 1)


def test_release_deleted_while_asking(
    served_status: ServedStatus, monkeypatch: MonkeyPatch
) -> None:
    def delete_then_answer(prompt: str) -> str:
        Release.objects.all().delete()
        return "yes"

    monkeypatch.setattr("builtins.input", delete_then_answer)

    with pytest.raises(
        CommandError, match=re.escape("December 2025 (processed 2026-09-29) is no longer loaded")
    ):
        call_command("delete_release", *DECEMBER)


def test_release_replaced_while_asking_is_deleted_by_its_dates(
    served_status: ServedStatus, monkeypatch: MonkeyPatch
) -> None:
    def replace_then_answer(prompt: str) -> str:
        old = Release.objects.get()
        old.delete()
        Release.objects.create(filing_period="D25", as_of=old.as_of, processed_on=old.processed_on)
        return "yes"

    monkeypatch.setattr("builtins.input", replace_then_answer)
    out = StringIO()

    call_command("delete_release", *DECEMBER, stdout=out)

    assert Release.objects.count() == 0
    assert out.getvalue().startswith(
        "Deleted December 2025 (processed 2026-09-29): 0 statuses and 0 rollups in"
    )


def test_takes_no_lock_that_blocks_readers(tmp_path: Path) -> None:
    load_both(tmp_path)

    call_command("delete_release", *JUNE, "--no-input", stdout=StringIO())

    # Every lock is held until the test's transaction ends, so this sees the loads' and the
    # deletion's. The loads take none (test_no_load_takes_a_lock_that_blocks_readers).
    assert exclusive_locks() == []


@pytest.mark.django_db(transaction=True)
def test_vacuums_and_analyzes_the_changed_tables(tmp_path: Path) -> None:
    load_both(tmp_path)
    before = table_stats(LOADER_MODELS)
    out = StringIO()

    call_command("delete_release", *JUNE, "--no-input", stdout=out)

    after = table_stats(LOADER_MODELS)
    deleted, vacuumed = out.getvalue().splitlines()
    assert deleted.startswith(
        "Deleted June 2025 (processed 2026-10-01): 30 statuses and 16 rollups in"
    )
    assert re.fullmatch(r"Vacuumed and analyzed 3 tables in \d+ s", vacuumed)
    changed = {"served_unserved_servedstatus", "served_unserved_rollup", "bdc_release"}
    for model in LOADER_MODELS:
        table = model._meta.db_table
        if table in changed:
            assert after[table].vacuum_count == before[table].vacuum_count + 1, table
            assert after[table].analyzed_after_vacuum(), table
        else:
            assert after[table].vacuum_count == before[table].vacuum_count, table


def test_both_dates_are_required(served_status: ServedStatus) -> None:
    with pytest.raises(CommandError, match="the following arguments are required: --processed-on"):
        call_command("delete_release", "--as-of", "2025-12-31", "--no-input")

    assert Release.objects.count() == 1


def test_dates_are_iso_dates(served_status: ServedStatus) -> None:
    with pytest.raises(
        CommandError,
        match=re.escape("argument --as-of: 'December 2025' is not a date in the form YYYY-MM-DD"),
    ):
        call_command("delete_release", "--as-of", "December 2025", "--processed-on", "2026-09-29")

    assert Release.objects.count() == 1


def test_default_options() -> None:
    parser = Command().create_parser("manage.py", "delete_release")

    options = parser.parse_args(list(JUNE))

    assert (options.as_of, options.processed_on) == (date(2025, 6, 30), date(2026, 10, 1))
    assert options.interactive is True
