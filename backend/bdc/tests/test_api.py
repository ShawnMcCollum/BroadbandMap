"""Release discovery is ordered by data period and discloses actual state coverage."""

from datetime import date

import pytest
from rest_framework.test import APIClient

from bdc.models import Release
from geography.models import Block
from served_unserved.models import ServedStatus

pytestmark = pytest.mark.django_db(transaction=True)
URL = "/api/v1/releases/"


def test_empty_catalog() -> None:
    response = APIClient().get(URL)
    assert response.status_code == 200
    assert response.json() == {"count": 0, "next": None, "previous": None, "results": []}
    assert response["Cache-Control"] == "no-store"
    assert APIClient().get(URL, {"page": 2}).status_code == 404


def test_catalog_orders_period_then_version_and_reports_per_release_states(
    served_status: ServedStatus,
    wv_block: Block,
) -> None:
    old = Release.objects.create(
        filing_period="J25", as_of=date(2025, 6, 30), processed_on=date(2026, 10, 1)
    )
    newer_version = Release.objects.create(
        filing_period="D25", as_of=date(2025, 12, 31), processed_on=date(2026, 9, 30)
    )
    ServedStatus.objects.create(
        release=old,
        block=wv_block,
        location_id=2,
        h3_res8="882a91ae3bfffff",
        any_100_20=True,
        wired_100_20=False,
        terrestrial_100_20=True,
    )
    response = APIClient().get(URL)
    data = response.json()
    assert [r["processed_on"] for r in data["results"]] == [
        "2026-09-30",
        "2026-09-29",
        "2026-10-01",
    ]
    assert data["results"][0] == {
        "filing_period": "D25",
        "as_of": "2025-12-31",
        "processed_on": "2026-09-30",
        "states": [],
    }
    assert data["results"][1]["states"] == [
        {"code": "39", "name": "Ohio", "abbreviation": "OH"},
    ]
    assert data["results"][2]["states"][0]["code"] == "54"
    assert newer_version.pk != served_status.release_id
    page = APIClient().get(URL, {"page_size": 1}).json()
    assert page["count"] == 3
    assert "page=2" in page["next"]
    assert APIClient().get(page["next"]).json()["results"] == [data["results"][1]]


@pytest.mark.parametrize(
    "query",
    [
        "page=0",
        "page=-1",
        "page=x",
        "page_size=0",
        "page_size=101",
        "page_size=1.5",
        "page_size=",
        "page=1&page=1",
        "unknown=x",
    ],
)
def test_catalog_rejects_invalid_queries(query: str) -> None:
    response = APIClient().get(URL + "?" + query)
    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
