import re
import time

import pytest
from django.db import transaction

from core.tests.helpers import (
    LOAD_RUNNING,
    REFUSED_BY_LOAD,
    application_name,
    backend_pid,
    exclusive_locks,
    lock_held_elsewhere,
)
from core.write_lock import (
    WRITE_LOCK_KEY,
    Holder,
    WriteLockHeld,
    refusal,
    take_write_lock,
    write_lock_holder,
)


def test_key_spells_bbmwrite() -> None:
    assert WRITE_LOCK_KEY == 7089349123222631525
    assert (WRITE_LOCK_KEY >> 32, WRITE_LOCK_KEY & 0xFFFFFFFF) == (1650617719, 1919513701)


@pytest.mark.django_db
def test_takes_the_lock_and_labels_the_connection() -> None:
    take_write_lock(LOAD_RUNNING)

    holder = write_lock_holder()
    assert holder is not None
    assert (holder.pid, holder.operation) == (backend_pid(), LOAD_RUNNING)
    assert re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", holder.since)
    # An advisory lock locks no table, so no reader waits for it.
    assert exclusive_locks() == []


@pytest.mark.django_db
def test_second_writer_is_refused_at_once() -> None:
    with lock_held_elsewhere(LOAD_RUNNING):
        began = time.monotonic()
        with pytest.raises(WriteLockHeld) as refused, transaction.atomic():
            take_write_lock("rollup rebuild of June 2025 (processed 2026-10-01)")
        elapsed = time.monotonic() - began

    assert REFUSED_BY_LOAD.fullmatch(str(refused.value))
    assert elapsed < 1
    # The refused writer's transaction rolled back, and its label with it.
    assert application_name() == ""


@pytest.mark.django_db
def test_holder_is_none_when_no_writer_runs() -> None:
    assert write_lock_holder() is None


@pytest.mark.django_db(transaction=True)
def test_lock_and_label_end_when_the_transaction_commits() -> None:
    with transaction.atomic():
        take_write_lock("deletion of June 2025 (processed 2026-10-01)")
        assert write_lock_holder() is not None

    assert write_lock_holder() is None
    assert application_name() == ""


@pytest.mark.django_db(transaction=True)
def test_lock_and_label_end_when_the_transaction_rolls_back() -> None:
    with pytest.raises(RuntimeError, match="the writer failed"), transaction.atomic():
        take_write_lock("deletion of June 2025 (processed 2026-10-01)")
        raise RuntimeError("the writer failed")

    assert write_lock_holder() is None
    assert application_name() == ""


@pytest.mark.django_db(transaction=True)
def test_lock_needs_a_transaction() -> None:
    with pytest.raises(RuntimeError, match=re.escape("must be called inside transaction.atomic()")):
        take_write_lock("deletion of June 2025 (processed 2026-10-01)")

    assert write_lock_holder() is None
    assert application_name() == ""


@pytest.mark.parametrize(
    ("holder", "message"),
    [
        (
            Holder(4321, "load of June 2025 (processed 2026-10-01)", "2026-10-16 03:36:57"),
            "another writer is running: load of June 2025 (processed 2026-10-01), process 4321, "
            "since 2026-10-16 03:36:57 UTC; try again once it has finished",
        ),
        (
            Holder(4321, "", "2026-10-16 03:36:57"),
            "another writer is running: process 4321, since 2026-10-16 03:36:57 UTC; "
            "try again once it has finished",
        ),
        (None, "another writer held the write lock and has just finished; try again"),
    ],
)
def test_refusal_names_the_holder(holder: Holder | None, message: str) -> None:
    assert refusal(holder) == message
