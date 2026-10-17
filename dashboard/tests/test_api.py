from collections.abc import Callable
from copy import deepcopy
from typing import Any

import httpx
import pytest

from api import (
    RELEASES,
    ApiUnavailableError,
    decode_release,
    fetch_counties,
    fetch_health,
    fetch_releases,
    fetch_summary,
    page_url,
)
from summaries import Release
from tests.conftest import (
    FixtureApi,
    county_page,
    envelope,
    feature,
    release_json,
    row,
    summary_page,
)


def client_for(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(base_url="http://api", transport=httpx.MockTransport(handler))


def test_all_components_up() -> None:
    body = {"status": "ok", "database": "ok", "redis": "ok", "worker": "ok"}
    client = client_for(lambda _: httpx.Response(200, json=body))

    assert fetch_health(client) == {"database": True, "redis": True, "worker": True}


def test_unreachable_component() -> None:
    body = {"status": "error", "database": "ok", "redis": "ok", "worker": "unreachable"}
    client = client_for(lambda _: httpx.Response(503, json=body))

    assert fetch_health(client) == {"database": True, "redis": True, "worker": False}


def test_unexpected_status() -> None:
    client = client_for(lambda _: httpx.Response(502))

    with pytest.raises(ApiUnavailableError, match="HTTP 502"):
        fetch_health(client)


def test_connection_error() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ApiUnavailableError):
        fetch_health(client_for(refuse))


@pytest.mark.parametrize(
    "link",
    [
        "http://api/api/v1/releases/?page=2&opaque=a%2Fb",
        "/api/v1/releases/?page=2&opaque=a%2Fb",
        "?page=2&opaque=a%2Fb",
        "http://API:80/api/v1/releases/?page=2&opaque=a%2Fb",
    ],
)
def test_allowed_page_links(link: str) -> None:
    with client_for(lambda _: httpx.Response(200)) as client:
        assert page_url(link, client, RELEASES).endswith("?page=2&opaque=a%2Fb")


@pytest.mark.parametrize(
    "link",
    [
        "https://api/api/v1/releases/?page=2",
        "http://evil/api/v1/releases/",
        "http://api:81/api/v1/releases/",
        "http://api:0/api/v1/releases/",
        "/api/v1/geographies/county/",
        "http://user:pass@api/api/v1/releases/",
        "?page=2#fragment",
        "?page=2#",
        "http://api:bad/api/v1/releases/",
        "javascript:alert(1)",
        "\\evil/path",
        "\n?page=2",
        "../locations/",
        "http://api/api/v1/releases/%2e%2e/",
    ],
)
def test_rejected_paging_never_fetches_destination(link: str) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=envelope([release_json()], count=2, next_link=link))

    with pytest.raises(ApiUnavailableError):
        fetch_releases(client_for(handler))
    assert len(requests) == 1


def sequence_client(responses: list[httpx.Response]) -> httpx.Client:
    pending = iter(responses)
    return client_for(lambda _: next(pending))


def test_multiple_release_versions_and_pages() -> None:
    pages = [
        envelope([release_json()], count=2, next_link="?page=2"),
        envelope([release_json("2026-09-28")], count=2),
    ]
    data = fetch_releases(sequence_client([httpx.Response(200, json=p) for p in pages]))
    assert [r.processed_on for r in data] == ["2026-09-29", "2026-09-28"]


def test_multiple_geometry_pages_drop_coordinates() -> None:
    pages = [
        county_page([feature("39001", "Adams")], count=2, next_link="?state=39&page=2"),
        county_page([feature("39003", "Allen")], count=2),
    ]
    assert fetch_counties(sequence_client([httpx.Response(200, json=p) for p in pages])) == {
        "39001": "Adams",
        "39003": "Allen",
    }


def test_multiple_summary_pages_are_pinned(fixture_api: FixtureApi, release: Release) -> None:
    fixture_api.summary_second_page = True
    data, coverage = fetch_summary(fixture_api.client(), release, "wired")
    assert len(data.rows) == 2
    assert coverage == "stored_rollups_only"
    for request in fixture_api.requests:
        assert request.url.params["as_of"] == release.as_of
        assert request.url.params["processed_on"] == release.processed_on
        assert request.url.params["flag"] == "wired"
    fixture_api.fail_second_page = True
    with pytest.raises(ApiUnavailableError):
        fetch_summary(fixture_api.client(), release, "wired")


@pytest.mark.parametrize(
    "broken",
    [
        "changed_count",
        "duplicate",
        "unordered",
        "empty_intermediate",
        "truncated",
        "overfull",
        "cycle",
    ],
)
def test_incomplete_release_collection_rejected(broken: str) -> None:
    first = envelope([release_json()], count=2, next_link="?page=2")
    second = envelope([release_json("2026-09-28")], count=2)
    if broken == "changed_count":
        second["count"] = 3
    elif broken == "duplicate":
        second["results"] = [release_json()]
    elif broken == "unordered":
        second["results"] = [release_json("2026-09-30")]
    elif broken == "empty_intermediate":
        first["results"] = []
    elif broken == "truncated":
        second["results"] = []
    elif broken == "overfull":
        first["count"] = 0
    elif broken == "cycle":
        first["next"] = "?page_size=100"
    with pytest.raises(ApiUnavailableError):
        fetch_releases(sequence_client([httpx.Response(200, json=p) for p in [first, second]]))


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="<html>secret</html>"),
        httpx.Response(200, content=b"{bad", headers={"content-type": "application/json"}),
        httpx.Response(200, json=[]),
        httpx.Response(200, json={}),
        httpx.Response(200, json={"count": True, "next": None, "previous": None, "results": []}),
        httpx.Response(302, headers={"location": "http://evil/"}),
        httpx.Response(500, text="private traceback"),
    ],
)
def test_malformed_network_boundary(response: httpx.Response) -> None:
    with pytest.raises(ApiUnavailableError) as failure:
        fetch_releases(client_for(lambda _: response))
    assert "secret" not in str(failure.value)
    assert "private traceback" not in str(failure.value)


@pytest.mark.parametrize(
    "mutation",
    [
        {"code": 39001},
        {"code": "54001"},
        {"locations": True},
        {"locations": 0},
        {"locations": -1},
        {"served": 2},
        {"not_served": 3},
        {"wired_100_20": 0},
        {"any_100_20": 2},
    ],
)
def test_invalid_summary_counts_or_ids(mutation: dict[str, Any], release: Release) -> None:
    body = summary_page(rows=[{**row("39001", 1), **mutation}])
    with pytest.raises(ApiUnavailableError):
        fetch_summary(client_for(lambda _: httpx.Response(200, json=body)), release, "wired")


@pytest.mark.parametrize(
    "key,value",
    [
        ("selection", {"level": "county", "state": "39", "code": None, "flag": "any"}),
        ("release", release_json("2026-09-28")),
        ("threshold", {"download_mbps": 25, "upload_mbps": 3}),
        ("boundary_vintage", 2021),
        ("summary_coverage", "observed"),
    ],
)
def test_mismatched_summary_context(key: str, value: Any, release: Release) -> None:
    first = summary_page(rows=[row("39001", 1)], count=2, next_link="?page=2")
    second = summary_page(rows=[row("39003", 9)], count=2)
    second[key] = value
    with pytest.raises(ApiUnavailableError):
        fetch_summary(
            sequence_client([httpx.Response(200, json=p) for p in [first, second]]),
            release,
            "wired",
        )


def test_problem_details_and_missing_rollups(release: Release) -> None:
    problem = {
        "status": 400,
        "code": "validation_error",
        "request_id": "request-123",
        "errors": [{"pointer": "/flag", "code": "invalid", "message": "Choose a flag."}],
    }
    with pytest.raises(ApiUnavailableError) as caught:
        fetch_summary(client_for(lambda _: httpx.Response(400, json=problem)), release, "wired")
    assert caught.value.status == 400
    assert caught.value.code == "validation_error"
    assert caught.value.explanation.endswith("/flag: Choose a flag.\nRequest ID: request-123")
    with pytest.raises(ApiUnavailableError, match="may need to rebuild"):
        fetch_summary(
            client_for(lambda _: httpx.Response(503, json={"status": 503})), release, "wired"
        )


def test_geometry_size_restart_discards_partial_data() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.params.get("page") == "2":
            return oversized()
        if request.url.params["page_size"] == "100":
            return httpx.Response(
                200,
                json=county_page(
                    [feature("39001", "Old attempt")],
                    count=2,
                    next_link="?page_size=100&page=2",
                ),
            )
        return httpx.Response(200, json=county_page([feature("39001", "Fresh attempt")]))

    assert fetch_counties(client_for(handler)) == {"39001": "Fresh attempt"}
    assert [r.url.params["page_size"] for r in requests] == ["100", "100", "50"]


def oversized() -> httpx.Response:
    return httpx.Response(
        400,
        json={
            "status": 400,
            "code": "validation_error",
            "errors": [
                {
                    "pointer": "/page_size",
                    "code": "geometry_payload_too_large",
                    "message": "Too large.",
                },
            ],
        },
    )


def test_geometry_size_recovery_is_finite() -> None:
    sizes: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sizes.append(request.url.params["page_size"])
        return oversized()

    with pytest.raises(ApiUnavailableError, match="one feature"):
        fetch_counties(client_for(handler))
    assert sizes == ["100", "50", "25", "12", "6", "3", "1"]


@pytest.mark.parametrize("coverage", ["no_observations", "outside_release_coverage"])
def test_missing_county_exact_diagnosis(coverage: str, release: Release) -> None:
    body = summary_page(code="39005", rows=[], coverage=coverage)
    data, returned = fetch_summary(
        client_for(lambda _: httpx.Response(200, json=body)), release, "wired", code="39005"
    )
    assert data.rows == ()
    assert returned == coverage


@pytest.mark.parametrize("body", ["html", [], {}, {"database": True}, None])
def test_malformed_health_is_safe(body: Any) -> None:
    with pytest.raises(ApiUnavailableError):
        fetch_health(client_for(lambda _: httpx.Response(200, json=body)))


def test_release_metadata_is_validated() -> None:
    for key, value in [
        ("as_of", "20251231"),
        ("processed_on", "2026-02-30"),
        ("states", [{"code": 39, "name": "Ohio", "abbreviation": "OH"}]),
    ]:
        broken = deepcopy(release_json())
        broken[key] = value
        with pytest.raises(ApiUnavailableError):
            decode_release(broken)


def test_deadline_between_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    times = iter([0, 0, 61])
    monkeypatch.setattr("api.monotonic", lambda: next(times))
    first = envelope([release_json()], count=2, next_link="?page=2")
    with pytest.raises(ApiUnavailableError, match="did not finish"):
        fetch_releases(client_for(lambda _: httpx.Response(200, json=first)))


def test_timeout_is_safe() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("secret hostname", request=request)

    with pytest.raises(ApiUnavailableError, match="Data releases could not be reached") as caught:
        fetch_releases(client_for(handler))
    assert "secret" not in str(caught.value)
