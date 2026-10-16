import re
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime

from django.db import connection, models, transaction

from core.write_lock import take_write_lock

# A load that another connection runs in the write-lock tests
LOAD_RUNNING = "load of June 2025 (processed 2026-10-01)"
# What a writer refused the lock is told while that load runs
REFUSED_BY_LOAD = re.compile(
    r"another writer is running: load of June 2025 \(processed 2026-10-01\), process \d+, "
    r"since \d{4}-\d\d-\d\d \d\d:\d\d:\d\d UTC; try again once it has finished"
)

# PostgreSQL's statistics on manual vacuums and analyzes of each table. A vacuum or analyze
# reports them as it finishes, so a query in a later transaction sees them.
TABLE_STATS = """
SELECT relname, vacuum_count, last_vacuum, last_analyze
FROM pg_stat_user_tables
WHERE relname = ANY(%s)
"""

# Relations this connection holds ACCESS EXCLUSIVE locks on. A read takes an ACCESS SHARE lock,
# which no other lock mode blocks.
EXCLUSIVE_LOCKS = """
SELECT DISTINCT c.relname
FROM pg_locks AS l
JOIN pg_class AS c ON c.oid = l.relation
WHERE l.pid = pg_backend_pid() AND l.mode = 'AccessExclusiveLock'
ORDER BY 1
"""


@dataclass(frozen=True)
class TableStats:
    vacuum_count: int
    last_vacuum: datetime | None
    last_analyze: datetime | None

    def analyzed_after_vacuum(self) -> bool:
        """Whether the table was analyzed after its last manual vacuum."""
        return (
            self.last_vacuum is not None
            and self.last_analyze is not None
            and self.last_analyze >= self.last_vacuum
        )


def table_stats(tables: Sequence[type[models.Model]]) -> dict[str, TableStats]:
    """Each table's manual vacuum and analyze statistics, by table name."""
    names = [model._meta.db_table for model in tables]
    with connection.cursor() as cursor:
        cursor.execute(TABLE_STATS, [names])
        return {name: TableStats(*stats) for name, *stats in cursor.fetchall()}


def exclusive_locks() -> list[str]:
    """The relations this connection holds ACCESS EXCLUSIVE locks on, which block readers.

    A lock is held until the transaction that took it ends, so inside a test's transaction this
    lists every such lock the test has taken.
    """
    with connection.cursor() as cursor:
        cursor.execute(EXCLUSIVE_LOCKS)
        return [name for (name,) in cursor.fetchall()]


def backend_pid() -> int:
    """The process id of this connection's PostgreSQL backend."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_backend_pid()")
        (pid,) = cursor.fetchone()
    return int(pid)


def application_name() -> str:
    """This connection's application_name."""
    with connection.cursor() as cursor:
        cursor.execute("SHOW application_name")
        (name,) = cursor.fetchone()
    return str(name)


@contextmanager
def lock_held_elsewhere(operation: str) -> Iterator[None]:
    """Hold the write lock, labelled ``operation``, on another connection while the block runs.

    The other connection is a thread's own. Its transaction writes nothing, and it is closed
    before the block's exit returns.
    """
    holding = threading.Event()
    finish = threading.Event()
    failures: list[BaseException] = []

    def hold() -> None:
        try:
            with transaction.atomic():
                take_write_lock(operation)
                holding.set()
                finish.wait(timeout=30)
        except BaseException as error:
            failures.append(error)
        finally:
            holding.set()
            connection.close()

    thread = threading.Thread(target=hold)
    thread.start()
    holding.wait(timeout=30)
    try:
        if failures:
            raise failures[0]
        yield
    finally:
        finish.set()
        thread.join(timeout=30)
