"""Location membership, bounded traversal, validation and generated contracts."""

import json
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from django.core import signing
from django.db import connection
from django.test.utils import CaptureQueriesContext
from openapi_schema_validator import OAS30Validator
from rest_framework.test import APIClient

from bdc.models import Release
from core.management.commands.check_api_schema import BASELINE_PATH
from core.tests.api.helpers import problem
from geography.models import Block, County, State
from geography.tests.helpers import boundary_fields
from served_unserved.api.cursors import SALT
from served_unserved.models import ServedStatus

pytestmark = pytest.mark.django_db(transaction=True)
URL = "/api/v1/served-unserved/locations/"
CELL = "882a91ae3bfffff"
PARAMS: dict[str, Any] = {"level": "county", "code": "39049"}


def add_status(
    release: Release, block: Block, location: int, flags: tuple[bool, bool, bool]
) -> None:
    ServedStatus.objects.create(
        release=release,
        block=block,
        location_id=location,
        h3_res8=CELL,
        any_100_20=flags[0],
        wired_100_20=flags[1],
        terrestrial_100_20=flags[2],
    )


@pytest.fixture
def locations(release: Release, block: Block, wv_block: Block) -> Release:
    # Deliberately insert out of order. WV shares the cell, but not the census areas.
    for location, flags in [
        (40, (True, True, True)),
        (10, (False, False, False)),
        (30, (True, False, True)),
        (20, (True, False, False)),
    ]:
        add_status(release, block, location, flags)
    add_status(release, wv_block, 50, (True, True, True))
    return release


@pytest.mark.parametrize(
    ("level", "code"),
    [
        ("county", "39049"),
        ("tract", "39049000110"),
        ("block_group", "390490001101"),
        ("block", "390490001101000"),
        ("place", "3918000"),
        ("county_subdivision", "3904918000"),
        ("h3_res8", CELL),
    ],
)
def test_membership_and_contract(locations: Release, level: str, code: str) -> None:
    response = APIClient().get(URL, {"level": level, "code": code})
    assert response.status_code == 200
    body = response.json()
    assert [row["location_id"] for row in body["results"]] == (
        ["10", "20", "30", "40", "50"] if level == "h3_res8" else ["10", "20", "30", "40"]
    )
    assert body["results"][0] == {
        "location_id": "10",
        "block_geoid": "390490001101000",
        "h3_res8": CELL,
        "any_100_20": False,
        "wired_100_20": False,
        "terrestrial_100_20": False,
    }
    assert body["selection"] == {
        "level": level,
        "code": code,
        "state": None,
        "flag": "wired",
        "status": None,
    }
    assert [state["code"] for state in body["release"]["states"]] == ["39", "54"]
    assert body["threshold"] == {"download_mbps": 100, "upload_mbps": 20}
    assert body["boundary_vintage"] == (None if level == "h3_res8" else 2020)
    assert body["area_coverage"] == "observed"
    assert body["next"] is body["previous"] is None
    assert "count" not in body
    assert response["Cache-Control"] == "no-store"


@pytest.mark.parametrize(
    ("flag", "status", "expected"),
    [
        ("any", "served", ["20", "30", "40"]),
        ("any", "not_served", ["10"]),
        ("wired", "served", ["40"]),
        ("wired", "not_served", ["10", "20", "30"]),
        ("terrestrial", "served", ["30", "40"]),
        ("terrestrial", "not_served", ["10", "20"]),
    ],
)
def test_status_flags(locations: Release, flag: str, status: str, expected: list[str]) -> None:
    body = APIClient().get(URL, {**PARAMS, "flag": flag, "status": status}).json()
    assert [row["location_id"] for row in body["results"]] == expected
    default = APIClient().get(URL, {**PARAMS, "status": "served"}).json()
    assert [row["location_id"] for row in default["results"]] == ["40"]


def test_h3_state_filter_and_place_assignment(locations: Release, block: Block) -> None:
    client = APIClient()
    body = client.get(URL, {"level": "h3_res8", "code": CELL, "state": "54"}).json()
    assert [row["location_id"] for row in body["results"]] == ["50"]
    # A block outside every place must not enter the place's results by a prefix rule.
    outside = Block.objects.create(
        geoid="390490001101001",
        name="Outside",
        block_group=block.block_group,
        county_subdivision=block.county_subdivision,
        population_2020=0,
        housing_units_2020=0,
        urban_rural="R",
        **boundary_fields(),
    )
    add_status(locations, outside, 60, (True, True, True))
    body = client.get(URL, {"level": "place", "code": "3918000"}).json()
    assert [row["location_id"] for row in body["results"]] == ["10", "20", "30", "40"]
    assert len(client.get(URL, PARAMS).json()["results"]) == 5


@pytest.mark.parametrize("page_size", [1, 2, 3, 4, 1000])
def test_forward_backward_boundaries(locations: Release, page_size: int) -> None:
    client = APIClient()
    first = client.get(URL, {**PARAMS, "page_size": page_size}).json()
    assert first["previous"] is None
    pages = [first]
    while pages[-1]["next"]:
        pages.append(client.get(pages[-1]["next"]).json())
        assert len(pages) <= 4
    assert [row["location_id"] for page in pages for row in page["results"]] == [
        "10",
        "20",
        "30",
        "40",
    ]
    current = pages[-1]
    for expected in reversed(pages[:-1]):
        current = client.get(current["previous"]).json()
        assert current["results"] == expected["results"]
    assert current["previous"] is None


def test_cursor_pins_release_and_new_latest_does_not_switch(
    locations: Release, block: Block
) -> None:
    client = APIClient()
    old_period = Release.objects.create(
        filing_period="J25", as_of="2025-06-30", processed_on="2026-10-01"
    )
    add_status(old_period, block, 99, (True, True, True))
    first = client.get(URL, {**PARAMS, "page_size": 1}).json()
    assert first["release"]["as_of"] == "2025-12-31"
    explicit = client.get(
        URL, {**PARAMS, "as_of": "2025-06-30", "processed_on": "2026-10-01"}
    ).json()
    assert explicit["results"][0]["location_id"] == "99"
    newer = Release.objects.create(
        filing_period="J26", as_of="2026-06-30", processed_on="2026-10-02"
    )
    add_status(newer, block, 88, (True, True, True))
    assert client.get(first["next"]).json()["results"][0]["location_id"] == "20"
    query = parse_qs(urlsplit(first["next"]).query)
    del query["as_of"], query["processed_on"]
    pinned = client.get(URL + "?" + urlencode(query, doseq=True)).json()
    assert pinned["release"]["as_of"] == "2025-12-31"
    assert client.get(URL, PARAMS).json()["results"][0]["location_id"] == "88"


@pytest.mark.parametrize(
    "change",
    [
        {"code": "39001"},
        {"level": "place", "code": "3918000"},
        {"state": "39"},
        {"flag": "any"},
        {"status": "served"},
        {"page_size": "2"},
        {"as_of": "2025-06-30", "processed_on": "2026-10-01"},
    ],
)
def test_cursor_context_changes_rejected(locations: Release, change: dict[str, str]) -> None:
    client = APIClient()
    first = client.get(URL, {**PARAMS, "page_size": 1}).json()
    query = parse_qs(urlsplit(first["next"]).query)
    query.update({name: [value] for name, value in change.items()})
    response = client.get(URL + "?" + urlencode(query, doseq=True))
    assert response.status_code == 400
    assert problem(response)["errors"][0]["pointer"] == "/cursor"


@pytest.mark.parametrize("cursor", ["broken", " ", "x" * 2049])
def test_invalid_cursor(cursor: str, locations: Release) -> None:
    assert APIClient().get(URL, {**PARAMS, "cursor": cursor}).status_code == 400


def test_tampered_and_malformed_signed_cursors(locations: Release) -> None:
    client = APIClient()
    link = client.get(URL, {**PARAMS, "page_size": 1}).json()["next"]
    query = parse_qs(urlsplit(link).query)
    original = query["cursor"][0]
    query["cursor"] = [original[:-5] + "xxxxx"]
    assert client.get(URL + "?" + urlencode(query, doseq=True)).status_code == 400
    payload = signing.loads(original, salt=SALT)
    for name, value in [
        ("v", 2),
        ("position", True),
        ("position", 2**63),
        ("reverse", 1),
        ("as_of", None),
    ]:
        query["cursor"] = [signing.dumps({**payload, name: value}, salt=SALT)]
        assert client.get(URL + "?" + urlencode(query, doseq=True)).status_code == 400


@pytest.mark.parametrize(
    "query",
    [
        "",
        "level=county",
        "code=39049",
        "level=bad&code=39049",
        "level=county&code=abcde",
        "level=county&code=3904",
        "level=county&code=39049&state=54",
        "level=county&code=39049&state=3",
        "level=h3_res8&code=882A91AE3BFFFFF",
        "level=county&code=%2039049",
        "level=county&code=39049&status=bad",
        "level=county&code=39049&flag=bad",
        "level=county&code=39049&as_of=2025-12-31",
        "level=county&code=39049&processed_on=2026-09-29",
        "level=county&code=39049&as_of=2025-1-01&processed_on=2026-09-29",
        "level=county&code=39049&as_of=2025-02-30&processed_on=2026-09-29",
        "level=county&code=39049&page=1",
        "level=county&code=39049&page_size=0",
        "level=county&code=39049&page_size=1001",
        "level=county&code=39049&page_size=1.0",
        "level=county&code=39049&page_size=1e2",
        "level=county&code=39049&cursor=",
        "level=county&code=39049&code=39049",
        "level=county&code=39049&flga=wired",
    ],
)
def test_invalid_queries(query: str) -> None:
    response = APIClient().get(URL + "?" + query)
    assert response.status_code == 400
    assert problem(response)["code"] == "validation_error"


@pytest.mark.parametrize(
    "query",
    [
        {"level": "county", "code": "39999"},
        {"level": "h3_res8", "code": "882a91ae39fffff"},
        {**PARAMS, "state": "99", "level": "h3_res8", "code": CELL},
        {**PARAMS, "as_of": "2025-06-30", "processed_on": "2026-10-01"},
    ],
)
def test_unknown_resources(locations: Release, query: dict[str, str]) -> None:
    assert APIClient().get(URL, query).status_code == 404


def test_no_release(county: County) -> None:
    assert APIClient().get(URL, PARAMS).status_code == 404


def test_empty_area_filter_and_outside_coverage(
    locations: Release, state: State, block: Block
) -> None:
    County.objects.create(geoid="39001", name="Adams", state=state, **boundary_fields())
    empty = APIClient().get(URL, {"level": "county", "code": "39001"}).json()
    assert empty["results"] == []
    assert empty["area_coverage"] == "no_observations"
    assert empty["next"] is empty["previous"] is None
    ServedStatus.objects.filter(release=locations, block=block).update(wired_100_20=False)
    filtered = APIClient().get(URL, {**PARAMS, "status": "served"}).json()
    assert filtered["results"] == []
    assert filtered["area_coverage"] == "observed"
    ServedStatus.objects.filter(release=locations, block__geoid__startswith="54").delete()
    outside = APIClient().get(URL, {"level": "county", "code": "54009"}).json()
    assert outside["area_coverage"] == "outside_release_coverage"


def test_summary_and_location_state_scopes_agree(locations: Release, state: State) -> None:
    client = APIClient()
    County.objects.create(geoid="39001", name="Adams", state=state, **boundary_fields())
    query = {"level": "county", "code": "39001", "state": "39"}
    summary = client.get("/api/v1/served-unserved/rollups/", query)
    detail = client.get(URL, query)
    assert summary.status_code == detail.status_code == 200
    assert summary.json()["summary_coverage"] == detail.json()["area_coverage"] == "no_observations"
    # Missing derived rows do not prevent reading the original locations.
    query["code"] = "39049"
    assert client.get("/api/v1/served-unserved/rollups/", query).status_code == 503
    assert client.get(URL, query).json()["area_coverage"] == "observed"


def test_query_count_bounded_no_count_offset_or_n_plus_one(locations: Release) -> None:
    client = APIClient()
    counts = []
    for size in (1, 3):
        first = client.get(URL, {**PARAMS, "page_size": size}).json()
        with CaptureQueriesContext(connection) as queries:
            response = client.get(first["next"])
        assert response.status_code == 200
        sql = [query["sql"].upper() for query in queries]
        assert not any("COUNT(" in query or "OFFSET" in query for query in sql)
        assert any(f"LIMIT {size + 1}" in query and '"LOCATION_ID" >' in query for query in sql)
        counts.append(len(queries))
    assert counts[0] == counts[1]


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_public_writes_rejected(locations: Release, method: str) -> None:
    response = getattr(APIClient(), method)(URL, {}, format="json")
    assert response.status_code == 405
    assert problem(response)["code"] == "method_not_allowed"


def test_head_options_and_schema(locations: Release) -> None:
    client = APIClient()
    assert client.head(URL, PARAMS).status_code == 200
    assert client.options(URL).status_code == 200
    document = json.loads(BASELINE_PATH.read_text())
    operation = document["paths"][URL]["get"]
    assert not operation.get("security")
    assert {param["name"] for param in operation["parameters"]} == {
        "as_of",
        "processed_on",
        "level",
        "code",
        "state",
        "flag",
        "status",
        "page_size",
        "cursor",
    }
    cases: list[tuple[dict[str, Any], int, str]] = [
        (PARAMS, 200, "application/json"),
        ({**PARAMS, "page_size": 0}, 400, "application/problem+json"),
        ({**PARAMS, "code": "39999"}, 404, "application/problem+json"),
    ]
    for query, status, media_type in cases:
        response = client.get(URL, query)
        assert response.status_code == status
        schema = operation["responses"][str(status)]["content"][media_type]["schema"]
        OAS30Validator(document, format_checker=OAS30Validator.FORMAT_CHECKER).evolve(
            schema=schema
        ).validate(response.json())
