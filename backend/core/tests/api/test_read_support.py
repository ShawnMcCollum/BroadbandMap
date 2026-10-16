"""Shared pagination validation and request-scoped, read-only snapshot isolation."""

import pytest
from django.db import InternalError, connection
from rest_framework.test import APIClient

from bdc.models import Release
from core.api.transactions import read_snapshot
from geography.models import County
from served_unserved.models import Rollup

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


@pytest.mark.parametrize(
    ("url", "params"),
    [
        ("/api/v1/releases/", {}),
        ("/api/v1/served-unserved/rollups/", {"level": "county"}),
        ("/api/v1/geographies/county/", {"state": "39"}),
    ],
)
@pytest.mark.parametrize("field", ["page", "page_size"])
@pytest.mark.parametrize("value", ["1.0", "10.00", "1e1", " 1 "])
def test_pagination_rejects_noninteger_notation(
    url: str,
    params: dict[str, str],
    field: str,
    value: str,
) -> None:
    response = APIClient().get(url, {**params, field: value})
    assert response.status_code == 400
    assert response["Content-Type"] == "application/problem+json"
    assert response.json()["code"] == "validation_error"
    assert response.json()["errors"] == [
        {
            "pointer": f"/{field}",
            "code": "invalid",
            "message": "A valid integer is required.",
        }
    ]


@pytest.mark.parametrize(
    ("url", "params", "cap"),
    [
        ("/api/v1/releases/", {}, 100),
        ("/api/v1/served-unserved/rollups/", {"level": "county"}, 1000),
        ("/api/v1/geographies/county/", {"state": "39"}, 100),
    ],
)
def test_pagination_accepts_integers_and_preserves_bounds(
    rollup: Rollup,
    county: County,
    url: str,
    params: dict[str, str],
    cap: int,
) -> None:
    client = APIClient()
    assert client.get(url, {**params, "page": "1", "page_size": str(cap)}).status_code == 200
    assert client.get(url, {**params, "page": "01", "page_size": "01"}).status_code == 200
    for field in ["page", "page_size"]:
        for value in ["0", "-1"]:
            response = client.get(url, {**params, field: value})
            assert response.status_code == 400
            assert response.json()["errors"][0]["pointer"] == f"/{field}"
            assert response.json()["errors"][0]["code"] == "min_value"
    response = client.get(url, {**params, "page_size": str(cap + 1)})
    assert response.status_code == 400
    assert response.json()["errors"][0]["code"] == "max_value"
