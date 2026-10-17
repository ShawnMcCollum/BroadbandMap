"""Small API-shaped fixtures, served through the actual httpx request boundary."""

from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from api import COUNTIES, RELEASES, ROLLUPS, decode_release
from summaries import Release


def release_json(processed: str = "2026-09-29", *, ohio: bool = True) -> dict[str, Any]:
    return {
        "as_of": "2025-12-31",
        "processed_on": processed,
        "filing_period": "D25",
        "states": [{"code": "39", "name": "Ohio", "abbreviation": "OH"}]
        if ohio
        else [
            {"code": "54", "name": "West Virginia", "abbreviation": "WV"},
        ],
    }


def envelope(
    rows: list[Any], *, next_link: str | None = None, count: int | None = None, key: str = "results"
) -> dict[str, Any]:
    return {
        "count": len(rows) if count is None else count,
        "next": next_link,
        "previous": None,
        key: rows,
    }


def feature(code: str, name: str) -> dict[str, Any]:
    return {
        "type": "Feature",
        "id": code,
        "properties": {"code": code, "name": name},
        "geometry": {
            "type": "MultiPolygon",
            "coordinates": [
                [
                    [
                        [-84, 40],
                        [-83, 40],
                        [-83, 41],
                        [-84, 40],
                    ]
                ]
            ],
        },
    }


def county_page(rows: list[Any], **kwargs: Any) -> dict[str, Any]:
    return {
        **envelope(rows, key="features", **kwargs),
        "type": "FeatureCollection",
        "state": "39",
        "boundary_vintage": 2020,
    }


def summary_page(
    release: dict[str, Any] | None = None,
    flag: str = "wired",
    *,
    code: str | None = None,
    rows: list[dict[str, Any]] | None = None,
    coverage: str = "stored_rollups_only",
    **kwargs: Any,
) -> dict[str, Any]:
    if rows is None:
        rows = [row("39001", 1, flag), row("39003", 9, flag)]
    return {
        **envelope(rows, **kwargs),
        "release": release or release_json(),
        "selection": {"level": "county", "state": "39", "flag": flag, "code": code},
        "threshold": {"download_mbps": 100, "upload_mbps": 20},
        "boundary_vintage": 2020,
        "summary_coverage": coverage,
    }


def row(code: str, locations: int, flag: str = "wired", *, newer: bool = False) -> dict[str, Any]:
    flags = {"wired": 1 if not newer else 0, "any": locations, "terrestrial": 0}
    return {
        "code": code,
        "locations": locations,
        "served": flags[flag],
        "not_served": locations - flags[flag],
        **{key + "_100_20": value for key, value in flags.items()},
    }


@dataclass
class FixtureApi:
    releases: list[dict[str, Any]] = field(
        default_factory=lambda: [
            release_json(),
            release_json("2026-09-28"),
        ]
    )
    names: list[dict[str, Any]] = field(
        default_factory=lambda: [
            feature("39001", "Adams County"),
            feature("39003", "Allen County"),
            feature("39005", "Ashland County"),
        ]
    )
    requests: list[httpx.Request] = field(default_factory=list)
    failure: str | None = None
    summary_second_page: bool = False
    fail_second_page: bool = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if self.failure == "network":
            raise httpx.ConnectError("internal credentials must not leak", request=request)
        if path == RELEASES:
            return httpx.Response(200, json=envelope(self.releases))
        if path == COUNTIES:
            if self.failure == "names":
                return httpx.Response(502, text="<secret>internal response</secret>")
            return httpx.Response(200, json=county_page(self.names))
        if path == ROLLUPS:
            if self.failure == "summaries":
                return httpx.Response(503, json={"status": 503, "code": "service_unavailable"})
            params = request.url.params
            release = next(r for r in self.releases if r["processed_on"] == params["processed_on"])
            flag = params["flag"]
            code = params.get("code")
            if code:
                return httpx.Response(
                    200,
                    json=summary_page(
                        release,
                        flag,
                        code=code,
                        rows=[],
                        coverage="no_observations",
                    ),
                )
            rows = [
                row("39001", 1, flag, newer=release != self.releases[0]),
                row("39003", 9, flag, newer=release != self.releases[0]),
            ]
            kwargs: dict[str, Any] = {}
            if self.summary_second_page:
                kwargs["count"] = 2
                if params.get("page") == "2":
                    if self.fail_second_page:
                        return httpx.Response(502)
                    rows = rows[1:]
                else:
                    rows = rows[:1]
                    kwargs["next_link"] = str(request.url.copy_set_param("page", "2"))
            return httpx.Response(200, json=summary_page(release, flag, rows=rows, **kwargs))
        if path == "/api/health/":
            return httpx.Response(200, json={"database": "ok", "redis": "ok", "worker": "ok"})
        raise AssertionError(f"Unexpected endpoint: {request.url}")

    def client(self, _base: str = "http://api") -> httpx.Client:
        return httpx.Client(base_url="http://api", transport=httpx.MockTransport(self.handler))


@pytest.fixture
def fixture_api() -> FixtureApi:
    return FixtureApi()


@pytest.fixture
def release() -> Release:
    return decode_release(release_json())
