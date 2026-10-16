import re
import time
from datetime import date
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from pytest import MonkeyPatch

from bdc.models import Release
from core.tests.helpers import (
    LOAD_RUNNING,
    REFUSED_BY_LOAD,
    backend_pid,
    exclusive_locks,
    lock_held_elsewhere,
    table_stats,
)
from core.write_lock import Holder, write_lock_holder
from etl.load import LOADER_MODELS, load_served_unserved
from etl.management.commands.delete_release import Command
from etl.tests.helpers import J25_STEM, WV_STEM, j25_csv, make_data_dir, wv_csv
from geography.models import Block, State
from served_unserved.models import Rollup, ServedStatus
from served_unserved.release_states import states_in_release

pytestmark = pytest.mark.django_db

DECEMBER = ("--as-of", "2025-12-31", "--processed-on", "2026-09-29")
JUNE = ("--as-of", "2025-06-30", "--processed-on", "2026-10-01")


def load_both(tmp_path: Path) -> None:
    """Load the fixture files' two releases: December 2025, then June 2025."""
    load_served_unserved(make_data_dir(tmp_path))
    load_served_unserved(make_data_dir(tmp_path / "j25", csv=j25_csv(), fcc_stem=J25_STEM))


def load_two_states(tmp_path: Path) -> None:
    """Load Ohio and West Virginia into December 2025, then Ohio into June 2025."""
    load_served_unserved(make_data_dir(tmp_path))
    load_served_unserved(make_data_dir(tmp_path / "wv", csv=wv_csv(), fcc_stem=WV_STEM))
    load_served_unserved(make_data_dir(tmp_path / "j25", csv=j25_csv(), fcc_stem=J25_STEM))


def state_snapshot(
    release: Release, state_fips: str
) -> tuple[list[tuple[object, ...]], list[tuple[object, ...]]]:
    """A release's status and rollup rows in one state, row ids included."""
    statuses = ServedStatus.objects.filter(release=release, block__geoid__startswith=state_fips)
    rollups = Rollup.objects.filter(release=release, state_id=state_fips)
    return (
        list(statuses.order_by("id").values_list()),
        list(rollups.order_by("id").values_list()),
    )


def add_wv_status(release: Release, block: Block) -> ServedStatus:
    """A West Virginia status, location 2001, served by any technology only."""
    return ServedStatus.objects.create(
        release=release,
        location_id=2001,
        block=block,
        h3_res8="882a8a6c13fffff",
        any_100_20=True,
        wired_100_20=False,
        terrestrial_100_20=False,
    )


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


def test_deletes_every_state_of_the_release(tmp_path: Path) -> None:
    load_served_unserved(make_data_dir(tmp_path))
    load_served_unserved(make_data_dir(tmp_path / "wv", csv=wv_csv(), fcc_stem=WV_STEM))
    out = StringIO()

    call_command("delete_release", *DECEMBER, "--no-input", stdout=out)

    assert re.fullmatch(
        r"Deleted December 2025 \(processed 2026-09-29\): 37 statuses and 30 rollups in \d+ s\.\n",
        out.getvalue(),
    )
    assert Release.objects.count() == 0
    assert Rollup.objects.count() == 0
    assert Block.objects.count() == 126


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


def test_refused_while_another_writer_runs(served_status: ServedStatus, rollup: Rollup) -> None:
    # Made by fixtures, not by a load: this test's transaction would keep a load's write lock.
    before = snapshot(served_status.release)

    with lock_held_elsewhere(LOAD_RUNNING):
        began = time.monotonic()
        with pytest.raises(CommandError) as refused:
            call_command("delete_release", *DECEMBER, "--no-input")
        elapsed = time.monotonic() - began

    assert REFUSED_BY_LOAD.fullmatch(str(refused.value))
    assert elapsed < 1
    assert snapshot(served_status.release) == before


def test_takes_the_write_lock_after_the_answer(
    served_status: ServedStatus, monkeypatch: MonkeyPatch
) -> None:
    holders: list[Holder | None] = []

    def answer_yes(prompt: str) -> str:
        holders.append(write_lock_holder())
        return "yes"

    monkeypatch.setattr("builtins.input", answer_yes)

    call_command("delete_release", *DECEMBER, stdout=StringIO())

    holder = write_lock_holder()
    assert holders == [None]
    assert holder is not None
    assert (holder.pid, holder.operation) == (
        backend_pid(),
        "deletion of December 2025 (processed 2026-09-29)",
    )


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


def test_deletes_one_state_and_leaves_the_others(tmp_path: Path) -> None:
    load_two_states(tmp_path)
    december = Release.objects.get(filing_period="D25")
    june = Release.objects.get(filing_period="J25")
    ohio_before = state_snapshot(december, "39")
    june_before = snapshot(june)
    out = StringIO()

    call_command("delete_release", *DECEMBER, "--state", "54", "--no-input", stdout=out)

    assert re.fullmatch(
        r"Deleted West Virginia from December 2025 \(processed 2026-09-29\): "
        r"6 statuses and 12 rollups in \d+ s\.\n",
        out.getvalue(),
    )
    assert state_snapshot(december, "39") == ohio_before
    # The cell West Virginia shared with Ohio keeps Ohio's row.
    shared = Rollup.objects.get(
        release=december, state_id="39", level="h3_res8", code="882ab14f33fffff"
    )
    assert shared.locations == 13
    assert snapshot(june) == june_before
    assert state_snapshot(december, "54") == ([], [])
    assert Release.objects.get(filing_period="D25").pk == december.pk
    assert [state.geoid for state in states_in_release(december)] == ["39"]
    assert Block.objects.count() == 126


def test_deleting_the_last_state_deletes_the_release(tmp_path: Path) -> None:
    load_both(tmp_path)
    december = Release.objects.get(filing_period="D25")
    before = snapshot(december)
    out = StringIO()

    call_command("delete_release", *JUNE, "--state", "39", "--no-input", stdout=out)

    assert re.fullmatch(
        r"Deleted Ohio from June 2025 \(processed 2026-10-01\): 30 statuses and 16 rollups "
        r"in \d+ s\. It was the release's only state, so the release was deleted too\.\n",
        out.getvalue(),
    )
    assert [str(release) for release in Release.objects.all()] == [
        "December 2025 (processed 2026-09-29)"
    ]
    assert snapshot(december) == before
    assert (ServedStatus.objects.count(), Rollup.objects.count()) == (31, 18)


def test_state_the_release_does_not_hold_is_refused_before_asking(
    served_status: ServedStatus, wv_state: State, monkeypatch: MonkeyPatch
) -> None:
    prompts: list[str] = []

    def answer_yes(prompt: str) -> str:
        prompts.append(prompt)
        return "yes"

    monkeypatch.setattr("builtins.input", answer_yes)
    before = snapshot(served_status.release)

    with pytest.raises(CommandError) as refused:
        call_command("delete_release", *DECEMBER, "--state", "54")

    assert str(refused.value) == (
        "West Virginia is not loaded in December 2025 (processed 2026-09-29); "
        "states it holds: --state 39 (Ohio)"
    )
    assert prompts == []
    assert snapshot(served_status.release) == before


def test_state_without_boundaries_is_refused(served_status: ServedStatus, wv_block: Block) -> None:
    add_wv_status(served_status.release, wv_block)

    with pytest.raises(CommandError) as refused:
        call_command("delete_release", *DECEMBER, "--state", "06", "--no-input")

    assert str(refused.value) == (
        "state 06 is not loaded in December 2025 (processed 2026-09-29); "
        "states it holds: --state 39 (Ohio), --state 54 (West Virginia)"
    )
    assert ServedStatus.objects.count() == 2


def test_release_without_statuses_lists_no_states(release: Release, state: State) -> None:
    with pytest.raises(CommandError) as refused:
        call_command("delete_release", *DECEMBER, "--state", "39", "--no-input")

    assert str(refused.value) == "Ohio is not loaded in December 2025 (processed 2026-09-29)"
    assert Release.objects.count() == 1


@pytest.mark.parametrize("value", ["5", "054", "WV"])
def test_state_is_a_two_digit_fips_code(served_status: ServedStatus, value: str) -> None:
    with pytest.raises(
        CommandError,
        match=re.escape(f"argument --state: {value!r} is not a two-digit state FIPS code, e.g. 39"),
    ):
        call_command("delete_release", *DECEMBER, "--state", value, "--no-input")

    assert ServedStatus.objects.count() == 1


def test_asks_before_deleting_a_state(
    served_status: ServedStatus, wv_block: Block, monkeypatch: MonkeyPatch
) -> None:
    add_wv_status(served_status.release, wv_block)
    prompts: list[str] = []

    def answer_yes(prompt: str) -> str:
        prompts.append(prompt)
        return "yes"

    monkeypatch.setattr("builtins.input", answer_yes)
    out = StringIO()

    call_command("delete_release", *DECEMBER, "--state", "54", stdout=out)

    assert prompts == [
        "Delete West Virginia from December 2025 (processed 2026-09-29), "
        "with its statuses and rollups there? "
        "Type 'yes' to continue, or 'no' to cancel: "
    ]
    assert out.getvalue().startswith(
        "Deleted West Virginia from December 2025 (processed 2026-09-29): "
    )
    assert list(ServedStatus.objects.values_list("location_id", flat=True)) == [1000338835]


def test_asks_before_deleting_the_last_state(
    served_status: ServedStatus, monkeypatch: MonkeyPatch
) -> None:
    prompts: list[str] = []

    def answer_no(prompt: str) -> str:
        prompts.append(prompt)
        return "no"

    monkeypatch.setattr("builtins.input", answer_no)
    out = StringIO()

    call_command("delete_release", *DECEMBER, "--state", "39", stdout=out)

    assert prompts == [
        "Delete Ohio from December 2025 (processed 2026-09-29), "
        "with its statuses and rollups there? "
        "It is the release's only state, so the release is deleted too. "
        "Type 'yes' to continue, or 'no' to cancel: "
    ]
    assert out.getvalue() == "Deletion cancelled.\n"
    assert (Release.objects.count(), ServedStatus.objects.count()) == (1, 1)


def test_state_deleted_while_asking(
    served_status: ServedStatus, wv_block: Block, monkeypatch: MonkeyPatch
) -> None:
    wv = add_wv_status(served_status.release, wv_block)

    def delete_then_answer(prompt: str) -> str:
        wv.delete()
        return "yes"

    monkeypatch.setattr("builtins.input", delete_then_answer)

    with pytest.raises(
        CommandError,
        match=re.escape(
            "West Virginia is no longer loaded in December 2025 (processed 2026-09-29)"
        ),
    ):
        call_command("delete_release", *DECEMBER, "--state", "54")

    assert list(ServedStatus.objects.values_list("location_id", flat=True)) == [1000338835]
    assert Release.objects.count() == 1


def test_release_deleted_while_asking_about_a_state(
    served_status: ServedStatus, monkeypatch: MonkeyPatch
) -> None:
    def delete_then_answer(prompt: str) -> str:
        Release.objects.all().delete()
        return "yes"

    monkeypatch.setattr("builtins.input", delete_then_answer)

    with pytest.raises(
        CommandError, match=re.escape("December 2025 (processed 2026-09-29) is no longer loaded")
    ):
        call_command("delete_release", *DECEMBER, "--state", "39")


def test_last_state_is_decided_after_the_answer(
    served_status: ServedStatus, wv_block: Block, monkeypatch: MonkeyPatch
) -> None:
    wv = add_wv_status(served_status.release, wv_block)
    prompts: list[str] = []

    def delete_then_answer(prompt: str) -> str:
        prompts.append(prompt)
        wv.delete()
        return "yes"

    monkeypatch.setattr("builtins.input", delete_then_answer)
    out = StringIO()

    call_command("delete_release", *DECEMBER, "--state", "39", stdout=out)

    assert "only state" not in prompts[0]
    assert re.fullmatch(
        r"Deleted Ohio from December 2025 \(processed 2026-09-29\): 1 statuses and 0 rollups "
        r"in \d+ s\. It was the release's only state, so the release was deleted too\.\n",
        out.getvalue(),
    )
    assert Release.objects.count() == 0


def test_deleting_a_state_takes_no_lock_that_blocks_readers(tmp_path: Path) -> None:
    load_two_states(tmp_path)

    call_command("delete_release", *DECEMBER, "--state", "54", "--no-input", stdout=StringIO())
    call_command("delete_release", *JUNE, "--state", "39", "--no-input", stdout=StringIO())

    # Every lock is held until the test's transaction ends, so this sees the loads' and the
    # deletions'. The loads take none (test_no_load_takes_a_lock_that_blocks_readers).
    assert exclusive_locks() == []


def test_deleting_a_state_is_refused_while_another_writer_runs(
    served_status: ServedStatus, rollup: Rollup
) -> None:
    # Made by fixtures, not by a load: this test's transaction would keep a load's write lock.
    before = snapshot(served_status.release)

    with lock_held_elsewhere(LOAD_RUNNING):
        began = time.monotonic()
        with pytest.raises(CommandError) as refused:
            call_command("delete_release", *DECEMBER, "--state", "39", "--no-input")
        elapsed = time.monotonic() - began

    assert REFUSED_BY_LOAD.fullmatch(str(refused.value))
    assert elapsed < 1
    assert snapshot(served_status.release) == before


def test_deleting_a_state_takes_the_write_lock_after_the_answer(
    served_status: ServedStatus, wv_block: Block, monkeypatch: MonkeyPatch
) -> None:
    add_wv_status(served_status.release, wv_block)
    holders: list[Holder | None] = []

    def answer_yes(prompt: str) -> str:
        holders.append(write_lock_holder())
        return "yes"

    monkeypatch.setattr("builtins.input", answer_yes)

    call_command("delete_release", *DECEMBER, "--state", "54", stdout=StringIO())

    holder = write_lock_holder()
    assert holders == [None]
    assert holder is not None
    assert (holder.pid, holder.operation) == (
        backend_pid(),
        "deletion of state 54 from December 2025 (processed 2026-09-29)",
    )


@pytest.mark.django_db(transaction=True)
def test_vacuums_and_analyzes_the_tables_a_state_deletion_changed(tmp_path: Path) -> None:
    load_served_unserved(make_data_dir(tmp_path))
    load_served_unserved(make_data_dir(tmp_path / "wv", csv=wv_csv(), fcc_stem=WV_STEM))
    before = table_stats(LOADER_MODELS)

    # Deleting West Virginia keeps the release.
    out = StringIO()
    call_command("delete_release", *DECEMBER, "--state", "54", "--no-input", stdout=out)
    middle = table_stats(LOADER_MODELS)

    deleted, vacuumed = out.getvalue().splitlines()
    assert deleted.startswith(
        "Deleted West Virginia from December 2025 (processed 2026-09-29): "
        "6 statuses and 12 rollups in"
    )
    assert re.fullmatch(r"Vacuumed and analyzed 2 tables in \d+ s", vacuumed)
    changed = {"served_unserved_servedstatus", "served_unserved_rollup"}
    for model in LOADER_MODELS:
        table = model._meta.db_table
        if table in changed:
            assert middle[table].vacuum_count == before[table].vacuum_count + 1, table
            assert middle[table].analyzed_after_vacuum(), table
        else:
            assert middle[table].vacuum_count == before[table].vacuum_count, table

    # Deleting Ohio, the release's last state, deletes the release too.
    out = StringIO()
    call_command("delete_release", *DECEMBER, "--state", "39", "--no-input", stdout=out)
    after = table_stats(LOADER_MODELS)

    deleted, vacuumed = out.getvalue().splitlines()
    assert deleted.startswith(
        "Deleted Ohio from December 2025 (processed 2026-09-29): 31 statuses and 18 rollups in"
    )
    assert deleted.endswith("It was the release's only state, so the release was deleted too.")
    assert re.fullmatch(r"Vacuumed and analyzed 3 tables in \d+ s", vacuumed)
    changed = {"served_unserved_servedstatus", "served_unserved_rollup", "bdc_release"}
    for model in LOADER_MODELS:
        table = model._meta.db_table
        if table in changed:
            assert after[table].vacuum_count == middle[table].vacuum_count + 1, table
            assert after[table].analyzed_after_vacuum(), table
        else:
            assert after[table].vacuum_count == middle[table].vacuum_count, table


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
    assert options.state is None
