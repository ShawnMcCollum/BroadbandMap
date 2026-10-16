"""One lock for every writer of the loaded tables, so that no two run at once (ADR 0015).

A data load, a release's deletion and a rollup rebuild each take it first in their transaction,
and PostgreSQL releases it when the transaction commits or rolls back. It is an advisory lock:
it locks no table, so no reader waits for it (ADR 0013).
"""

from typing import NamedTuple

from django.db import connection

# The eight bytes "bbmwrite" read as one big-endian integer. pg_locks shows the lock as an
# advisory lock with classid 1650617719, objid 1919513701 and objsubid 1.
WRITE_LOCK_KEY = int.from_bytes(b"bbmwrite", "big")

# The process that holds the write lock in this database: its pid, its application_name, and
# when its transaction started, in UTC.
HOLDER = """
SELECT activity.pid,
       activity.application_name,
       to_char(activity.xact_start AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')
FROM pg_locks AS lock
JOIN pg_stat_activity AS activity ON activity.pid = lock.pid
WHERE lock.locktype = 'advisory'
  AND lock.granted
  AND lock.database = (SELECT oid FROM pg_database WHERE datname = current_database())
  AND lock.objsubid = 1
  AND (lock.classid::bigint << 32 | lock.objid::bigint) = %s
"""


class WriteLockHeld(Exception):
    """Another writer of the loaded tables holds the write lock. Nothing was changed."""


class Holder(NamedTuple):
    """The process that holds the write lock."""

    pid: int
    # Its application_name, which a writer sets to what it is doing
    operation: str
    # When its transaction started, as YYYY-MM-DD HH:MM:SS in UTC
    since: str


def write_lock_holder() -> Holder | None:
    """The process that holds the write lock in this database, or None."""
    with connection.cursor() as cursor:
        # A transaction otherwise keeps the pg_stat_activity it read first.
        cursor.execute("SELECT pg_stat_clear_snapshot()")
        cursor.execute(HOLDER, [WRITE_LOCK_KEY])
        row = cursor.fetchone()
    return None if row is None else Holder(*row)


def refusal(holder: Holder | None) -> str:
    """Why a writer cannot start while ``holder`` holds the write lock."""
    if holder is None:
        return "another writer held the write lock and has just finished; try again"
    details = [holder.operation] if holder.operation else []
    details += [f"process {holder.pid}", f"since {holder.since} UTC"]
    return f"another writer is running: {', '.join(details)}; try again once it has finished"


def take_write_lock(operation: str) -> None:
    """Take the write lock until the current transaction ends, or raise WriteLockHeld at once.

    ``operation`` says what this writer does, in at most 63 characters, e.g. "load of state 39 into
    June 2025 (processed 2026-10-01)". It is this connection's application_name until the
    transaction ends, so that a writer refused the lock can name it.

    Raises RuntimeError outside a transaction, where the lock would be released at once.
    """
    if not connection.in_atomic_block:
        raise RuntimeError(
            "take_write_lock() must be called inside transaction.atomic(): "
            "the lock is held until the transaction ends"
        )
    with connection.cursor() as cursor:
        # The label first, so that a connection seen holding the lock is already labelled.
        cursor.execute("SELECT set_config('application_name', %s, true)", [operation])
        cursor.execute("SELECT pg_try_advisory_xact_lock(%s)", [WRITE_LOCK_KEY])
        (taken,) = cursor.fetchone()
    if not taken:
        raise WriteLockHeld(refusal(write_lock_holder()))
