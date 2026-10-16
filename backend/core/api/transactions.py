"""Keep release resolution, coverage, and serialized rows in one read snapshot."""

from collections.abc import Iterator
from contextlib import contextmanager

from django.db import connection, transaction


@contextmanager
def read_snapshot() -> Iterator[None]:
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        yield
