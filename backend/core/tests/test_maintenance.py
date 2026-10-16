import re

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from bdc.models import Release
from core.maintenance import vacuum_analyze
from core.tests.helpers import table_stats
from geography.models import State


@pytest.mark.django_db(transaction=True)
def test_vacuums_then_analyzes_each_table() -> None:
    before = table_stats((Release, State))
    messages: list[str] = []

    with CaptureQueriesContext(connection) as queries:
        vacuum_analyze((Release, State), messages.append)

    after = table_stats((Release, State))
    assert [query["sql"] for query in queries.captured_queries] == [
        'VACUUM (ANALYZE, TRUNCATE false) "bdc_release", "geography_state"'
    ]
    for table in ("bdc_release", "geography_state"):
        assert after[table].vacuum_count == before[table].vacuum_count + 1
        assert after[table].analyzed_after_vacuum()
    assert len(messages) == 1
    assert re.fullmatch(r"Vacuumed and analyzed 2 tables in \d+ s", messages[0])


@pytest.mark.django_db(transaction=True)
def test_reports_a_single_table() -> None:
    messages: list[str] = []

    vacuum_analyze((Release,), messages.append)

    assert len(messages) == 1
    assert re.fullmatch(r"Vacuumed and analyzed 1 table in \d+ s", messages[0])


@pytest.mark.django_db
def test_does_nothing_inside_a_transaction() -> None:
    messages: list[str] = []

    with CaptureQueriesContext(connection) as queries:
        vacuum_analyze((Release, State), messages.append)

    assert queries.captured_queries == []
    assert messages == []
