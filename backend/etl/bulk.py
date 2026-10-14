"""Write rows into a table with PostgreSQL COPY."""

from collections.abc import Iterable, Sequence

import psycopg
from django.db import connection, models

from etl.errors import LoadError


def copy_rows(
    model: type[models.Model], columns: Sequence[str], rows: Iterable[Sequence[object]]
) -> int:
    """Stream rows into the model's table with COPY and return how many were written.

    Geometries are hex EWKB strings. A database error becomes a LoadError; an
    exception raised while producing rows aborts the COPY and propagates unchanged.
    """
    table = model._meta.db_table
    quote = connection.ops.quote_name
    statement = f"COPY {quote(table)} ({', '.join(quote(c) for c in columns)}) FROM STDIN"
    count = 0
    try:
        with connection.cursor() as cursor, cursor.copy(statement) as copy:
            for row in rows:
                copy.write_row(row)
                count += 1
    except psycopg.Error as error:
        message = f"{table}: {error.diag.message_primary or error}"
        if error.diag.message_detail:
            message += f" ({error.diag.message_detail})"
        raise LoadError(message) from error
    return count
