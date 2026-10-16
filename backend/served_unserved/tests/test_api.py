"""Summary contracts, state contributions, and missing-data semantics."""

from datetime import date
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from bdc.models import Release
from geography.models import Block, County, State
from geography.tests.helpers import boundary_fields
from served_unserved.models import Rollup, ServedStatus

pytestmark = pytest.mark.django_db(transaction=True)
URL = "/api/v1/served-unserved/rollups/"
CELL = "882a91ae3bfffff"


@pytest.mark.parametrize(
    ("level", "code"),
    [
        ("county", "39049"),
        ("tract", "39049000110"),
        ("block_group", "390490001101"),
        ("block", "390490001101000"),
        ("h3_res8", CELL),
        ("place", "3918000"),
        ("county_subdivision", "3904918000"),
    ],
)
@pytest.mark.parametrize(
    ("flag", "served", "not_served"),
    [
        ("any", 8, 2),
        ("wired", 4, 6),
        ("terrestrial", 6, 4),
    ],
)
def test_summary_all_levels_and_flags(
    release: Release,
    block: Block,
    served_status: ServedStatus,
    level: str,
    code: str,
    flag: str,
    served: int,
    not_served: int,
) -> None:
    Rollup.objects.create(
        release=release,
        state_id="39",
        level=level,
        code=code,
        locations=10,
        any_100_20=8,
        wired_100_20=4,
        terrestrial_100_20=6,
    )
    response = APIClient().get(URL, {"level": level, "code": code, "flag": flag})
    assert response.status_code == 200
    data = response.json()
    assert data["results"] == [
        {
            "code": code,
            "locations": 10,
            "any_100_20": 8,
            "wired_100_20": 4,
            "terrestrial_100_20": 6,
            "served": served,
            "not_served": not_served,
        }
    ]
    assert data["summary_coverage"] == "observed"
    assert data["release"]["as_of"] == "2025-12-31"
    assert data["release"]["states"][0]["code"] == "39"
    assert data["threshold"] == {"download_mbps": 100, "upload_mbps": 20}
    assert data["boundary_vintage"] == (None if level == "h3_res8" else 2020)
    assert response["Cache-Control"] == "no-store"


def test_border_cell_sums_before_pagination(
    release: Release, state: State, wv_block: Block, served_status: ServedStatus
) -> None:
    Rollup.objects.create(
        release=release,
        state=state,
        level="h3_res8",
        code=CELL,
        locations=10,
        any_100_20=8,
        wired_100_20=4,
        terrestrial_100_20=6,
    )
    Rollup.objects.create(
        release=release,
        state_id="54",
        level="h3_res8",
        code=CELL,
        locations=5,
        any_100_20=5,
        wired_100_20=2,
        terrestrial_100_20=3,
    )
    Rollup.objects.create(
        release=release,
        state=state,
        level="h3_res8",
        code="882a91ae39fffff",
        locations=2,
        any_100_20=2,
        wired_100_20=1,
        terrestrial_100_20=2,
    )
    client = APIClient()
    first = client.get(URL, {"level": "h3_res8", "page_size": "1"}).json()
    assert first["count"] == 2
    second = client.get(first["next"]).json()
    assert second["results"] == [
        {
            "code": CELL,
            "locations": 15,
            "any_100_20": 13,
            "wired_100_20": 6,
            "terrestrial_100_20": 9,
            "served": 6,
            "not_served": 9,
        }
    ]
    assert second["next"] is None
    assert second["previous"]
    filtered = client.get(URL, {"level": "h3_res8", "code": CELL, "state": "39"}).json()
    assert filtered["results"][0]["locations"] == 10
    assert filtered["results"][0]["served"] == 4
    links = parse_qs(urlsplit(first["next"]).query)
    assert links["as_of"] == ["2025-12-31"]
    assert links["processed_on"] == ["2026-09-29"]
    assert links["flag"] == ["wired"]


def test_missing_rollup_is_not_measured_zero(served_status: ServedStatus) -> None:
    response = APIClient().get(URL, {"level": "county", "code": "39049"})
    assert response.status_code == 503
    assert response.json()["code"] == "service_unavailable"
    collection = APIClient().get(URL, {"level": "county"}).json()
    assert collection["results"] == []
    assert collection["summary_coverage"] == "stored_rollups_only"


def test_no_observations_and_outside_release_coverage(
    served_status: ServedStatus, state: State, wv_block: Block
) -> None:
    County.objects.create(geoid="39001", state=state, name="Adams County", **boundary_fields())
    empty = APIClient().get(URL, {"level": "county", "code": "39001"})
    assert empty.status_code == 200
    assert empty.json()["results"] == []
    assert empty.json()["summary_coverage"] == "no_observations"
    outside = APIClient().get(URL, {"level": "county", "code": "54009"})
    assert outside.status_code == 200
    assert outside.json()["summary_coverage"] == "outside_release_coverage"


def test_known_h3_without_observations_in_selected_release(served_status: ServedStatus) -> None:
    Release.objects.create(
        filing_period="D26", as_of=date(2026, 12, 31), processed_on=date(2027, 9, 29)
    )
    response = APIClient().get(URL, {"level": "h3_res8", "code": CELL})
    assert response.status_code == 200
    assert response.json()["summary_coverage"] == "no_observations"


@pytest.mark.parametrize(
    "query",
    [
        "",
        "level=invalid",
        "level=county&code=3904",
        "level=county&code=abcde",
        "level=county&code=39049&state=54",
        "level=county&state=3",
        "level=county&flag=other",
        "level=county&as_of=2025-12-31",
        "level=county&processed_on=2026-09-29",
        "level=county&as_of=no&processed_on=2026-09-29",
        "level=county&as_of=2025-6-30&processed_on=2026-09-29",
        "level=county&as_of=2025-02-30&processed_on=2026-09-29",
        "level=county&flag=",
        "level=county&level=county",
        "level=county&flga=wired",
        "level=county&code=",
        "level=county&page=0",
        "level=county&page_size=1001",
        "level=county&page_size=1.5",
        "level=county&code=%2039049",
        "level=h3_res8&code=882A91AE3BFFFFF",
    ],
)
def test_invalid_queries(query: str) -> None:
    response = APIClient().get(URL + "?" + query)
    assert response.status_code == 400
    assert response["Content-Type"] == "application/problem+json"
    assert response.json()["code"] == "validation_error"


@pytest.mark.parametrize(
    "params",
    [
        {"level": "county"},
        {"level": "county", "state": "99"},
        {"level": "county", "code": "39999"},
        {"level": "h3_res8", "code": "882a91ae39fffff"},
        {"level": "county", "as_of": "2025-06-30", "processed_on": "2026-10-01"},
    ],
)
def test_unknown_release_state_or_area(params: dict[str, Any], county: County) -> None:
    if params != {"level": "county"}:
        Release.objects.create(filing_period="D25", as_of="2025-12-31", processed_on="2026-09-29")
    assert APIClient().get(URL, params).status_code == 404


def test_latest_order_explicit_dates_and_pinned_links(rollup: Rollup, state: State) -> None:
    old = Release.objects.create(
        filing_period="J25", as_of=date(2025, 6, 30), processed_on=date(2026, 10, 1)
    )
    Rollup.objects.create(
        release=old,
        state=state,
        level="county",
        code="39049",
        locations=20,
        any_100_20=15,
        wired_100_20=8,
        terrestrial_100_20=12,
    )
    assert APIClient().get(URL, {"level": "county"}).json()["results"][0]["served"] == 4
    selected = (
        APIClient()
        .get(URL, {"level": "county", "as_of": "2025-06-30", "processed_on": "2026-10-01"})
        .json()
    )
    assert selected["results"][0]["served"] == 8
    for code in ["39001", "39003"]:
        Rollup.objects.create(
            release=rollup.release,
            state=state,
            level="county",
            code=code,
            locations=1,
            any_100_20=1,
            wired_100_20=0,
            terrestrial_100_20=1,
        )
    first = APIClient().get(URL, {"level": "county", "page_size": "1", "state": "39"}).json()
    Release.objects.create(
        filing_period="D26", as_of=date(2026, 12, 31), processed_on=date(2027, 9, 29)
    )
    second = APIClient().get(first["next"]).json()
    assert second["release"]["as_of"] == "2025-12-31"
    assert second["results"][0]["code"] == "39003"
    assert APIClient().get(URL, {"level": "county", "page": "99"}).status_code == 404


@pytest.mark.parametrize("staff", [None, False, True])
def test_public_reads_and_no_writes(rollup: Rollup, staff: bool | None) -> None:
    client = APIClient()
    if staff is not None:
        client.force_authenticate(User.objects.create(username="reader", is_staff=staff))
    assert client.get(URL, {"level": "county"}).status_code == 200
    assert client.head(URL, {"level": "county"}).content == b""
    assert client.options(URL).status_code == 200
    for method in ["post", "put", "patch", "delete", "trace"]:
        response = getattr(client, method)(URL)
        assert response.status_code == 405
        assert response["Allow"] == "GET, HEAD, OPTIONS"


def test_summary_query_growth_is_bounded_and_excludes_polygons(
    rollup: Rollup, state: State
) -> None:
    client = APIClient()
    with CaptureQueriesContext(connection) as first:
        assert client.get(URL, {"level": "county"}).status_code == 200
    for i in range(10):
        Rollup.objects.create(
            release=rollup.release,
            state=state,
            level="county",
            code=f"390{i:02}",
            locations=1,
            any_100_20=1,
            wired_100_20=1,
            terrestrial_100_20=1,
        )
    with CaptureQueriesContext(connection) as many:
        assert client.get(URL, {"level": "county"}).status_code == 200
    assert len(many) == len(first)
    assert not any('"geom"' in query["sql"] for query in many)
    assert any("SUM(" in query["sql"] and "GROUP BY" in query["sql"] for query in many)


def test_identifiers_preserve_leading_zeros(release: Release) -> None:
    state = State.objects.create(geoid="01", abbreviation="AL", name="Alabama", **boundary_fields())
    County.objects.create(geoid="01001", state=state, name="Autauga County", **boundary_fields())
    Rollup.objects.create(
        release=release,
        state=state,
        level="county",
        code="01001",
        locations=10,
        any_100_20=8,
        wired_100_20=4,
        terrestrial_100_20=6,
    )
    response = APIClient().get(URL, {"level": "county", "state": "01", "code": "01001"})
    assert response.status_code == 200
    assert response.json()["results"][0]["code"] == "01001"
    assert response.json()["selection"]["state"] == "01"
