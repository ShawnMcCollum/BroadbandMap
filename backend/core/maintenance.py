"""Upkeep of tables after bulk writes: vacuum and analyze."""

import time
from collections.abc import Callable, Sequence

from django.db import connection, models


def vacuum_analyze(tables: Sequence[type[models.Model]], progress: Callable[[str], None]) -> None:
    """Vacuum and analyze the tables, once the writes to them have committed.

    The vacuum frees the space of deleted rows for reuse and marks pages whose rows are all
    visible; the analyze refreshes the planner's statistics. ``TRUNCATE false`` keeps the vacuum
    from cutting empty pages off the end of a table, which takes an ACCESS EXCLUSIVE lock that
    blocks readers (ADR 0014). Their space is reused by later writes instead.

    VACUUM cannot run inside a transaction block. Inside one, which only the test suite's
    transactions allow, nothing is done.
    """
    if connection.in_atomic_block:
        return
    began = time.monotonic()
    quote = connection.ops.quote_name
    names = ", ".join(quote(model._meta.db_table) for model in tables)
    with connection.cursor() as cursor:
        cursor.execute(f"VACUUM (ANALYZE, TRUNCATE false) {names}")
    count = f"{len(tables)} table" if len(tables) == 1 else f"{len(tables)} tables"
    progress(f"Vacuumed and analyzed {count} in {time.monotonic() - began:.0f} s")
