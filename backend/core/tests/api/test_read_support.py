"""Snapshot isolation is request-scoped and read-only."""

import pytest
from django.db import InternalError, connection

from bdc.models import Release
from core.api.transactions import read_snapshot

pytestmark = pytest.mark.django_db(transaction=True)


def test_read_snapshot_isolation_and_cleanup() -> None:
    with read_snapshot(), connection.cursor() as cursor:
        cursor.execute("SHOW transaction_isolation")
        assert cursor.fetchone() == ("repeatable read",)
        cursor.execute("SHOW transaction_read_only")
        assert cursor.fetchone() == ("on",)
    with connection.cursor() as cursor:
        cursor.execute("SHOW transaction_isolation")
        assert cursor.fetchone() == ("read committed",)
        cursor.execute("SHOW transaction_read_only")
        assert cursor.fetchone() == ("off",)


def test_snapshot_prevents_writes_and_rolls_back_on_error() -> None:
    with pytest.raises(InternalError), read_snapshot():
        Release.objects.create(filing_period="D25", as_of="2025-12-31", processed_on="2026-09-29")
    assert not connection.in_atomic_block
    assert not Release.objects.exists()
