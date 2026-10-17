"""API-only reads with bounded waits, strict decoding and complete collections."""

import re
from collections.abc import Iterator
from contextlib import suppress
from datetime import date
from time import monotonic
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from config import base_url
from summaries import FLAGS, CountySummaries, Flag, Release, State, SummaryRow

COMPONENTS = ("database", "redis", "worker")
RELEASES = "/api/v1/releases/"
COUNTIES = "/api/v1/geographies/county/"
ROLLUPS = "/api/v1/served-unserved/rollups/"
COLLECTION_SECONDS = 60


class ApiUnavailableError(Exception):
    """Safe resource failure, optionally with structured Problem Details."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        code: str | None = None,
        errors: tuple[tuple[str, str, str], ...] = (),
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.errors = errors
        self.request_id = request_id

    @property
    def explanation(self) -> str:
        lines = [str(self)]
        lines.extend(f"{pointer}: {message}" for pointer, _, message in self.errors)
        if self.request_id:
            lines.append(f"Request ID: {self.request_id}")
        return "\n".join(lines)


def client_for(api_base: str) -> httpx.Client:
    return httpx.Client(
        base_url=base_url(api_base, origin_only=True),
        timeout=httpx.Timeout(10.0, connect=5.0),
        follow_redirects=False,
        headers={"Accept": "application/json, application/geo+json, application/problem+json"},
    )


def invalid() -> ApiUnavailableError:
    return ApiUnavailableError(
        "The API returned unexpected or inconsistent data. Refresh to retry."
    )


def record(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise invalid()
    return value


def text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise invalid()
    return value


def count(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise invalid()
    return value


def iso_date(value: Any) -> str:
    parsed_value = text(value)
    try:
        if date.fromisoformat(parsed_value).isoformat() != parsed_value:
            raise invalid()
    except ValueError as error:
        raise invalid() from error
    return parsed_value


def decode_release(value: Any) -> Release:
    item = record(value)
    states = item.get("states")
    if not isinstance(states, list):
        raise invalid()
    decoded: list[State] = []
    for raw in states:
        state = record(raw)
        code = text(state.get("code"))
        if not re.fullmatch(r"[0-9]{2}", code) or any(s.code == code for s in decoded):
            raise invalid()
        decoded.append(State(code, text(state.get("name")), text(state.get("abbreviation"))))
    return Release(
        iso_date(item.get("as_of")),
        iso_date(item.get("processed_on")),
        text(item.get("filing_period")),
        tuple(decoded),
    )


def page_url(link: str, client: httpx.Client, endpoint: str) -> str:
    expected = urlsplit(str(client.base_url.join(endpoint)))
    try:
        if "\\" in link or any(ord(c) <= 32 or ord(c) == 127 for c in link):
            raise invalid()
        resolved = urljoin(expected.geturl(), link)
        parsed = urlsplit(resolved)
        if (
            parsed.scheme not in ("http", "https")
            or parsed.scheme != expected.scheme
            or parsed.hostname != expected.hostname
            or (
                parsed.port
                if parsed.port is not None
                else (443 if parsed.scheme == "https" else 80)
            )
            != (
                expected.port
                if expected.port is not None
                else (443 if expected.scheme == "https" else 80)
            )
            or parsed.path != endpoint
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or "#" in link
        ):
            raise invalid()
    except ValueError as error:
        raise invalid() from error
    return resolved


def get_json(client: httpx.Client, url: str, resource: str, *, health: bool = False) -> Any:
    try:
        response = client.get(url, follow_redirects=False)
    except httpx.HTTPError as error:
        raise ApiUnavailableError(f"{resource} could not be reached. Try refreshing.") from error
    media_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
    body: Any = None
    if media_type in ("application/json", "application/geo+json", "application/problem+json"):
        with suppress(ValueError):
            body = response.json()
    if response.status_code != 200 and not (health and response.status_code == 503):
        message = f"{resource} failed with HTTP {response.status_code}. Try refreshing."
        if not health and response.status_code == 503 and resource == "County summaries":
            message = (
                "County summaries are unavailable. Try refreshing; an application operator "
                "may need to rebuild them."
            )
        fields: list[tuple[str, str, str]] = []
        code = None
        request_id = response.headers.get("x-request-id")
        if isinstance(body, dict) and body.get("status") == response.status_code:
            code = body.get("code") if isinstance(body.get("code"), str) else None
            if isinstance(body.get("request_id"), str):
                request_id = body["request_id"]
            if isinstance(body.get("errors"), list):
                for field in body["errors"]:
                    if isinstance(field, dict) and all(
                        isinstance(field.get(key), str) for key in ("pointer", "code", "message")
                    ):
                        fields.append((field["pointer"], field["code"], field["message"]))
        raise ApiUnavailableError(
            message,
            status=response.status_code,
            code=code,
            errors=tuple(fields),
            request_id=request_id,
        )
    if body is None:
        raise ApiUnavailableError(f"{resource} returned an unexpected response. Try refreshing.")
    return body


def pages(
    client: httpx.Client,
    endpoint: str,
    params: dict[str, str],
    resource: str,
) -> Iterator[dict[str, Any]]:
    url = str(client.base_url.join(endpoint).copy_merge_params(params))
    visited: set[str] = set()
    deadline = monotonic() + COLLECTION_SECONDS
    expected_count: int | None = None
    while True:
        canonical = str(httpx.URL(url))
        if canonical in visited or monotonic() >= deadline:
            raise ApiUnavailableError(f"{resource} did not finish loading. Refresh to retry.")
        visited.add(canonical)
        page = record(get_json(client, url, resource))
        size = count(page.get("count"))
        if expected_count is not None and size != expected_count:
            raise invalid()
        expected_count = size
        for key in ("next", "previous"):
            if key not in page or (page[key] is not None and not isinstance(page[key], str)):
                raise invalid()
            if page[key] is not None:
                page_url(page[key], client, endpoint)
        yield page
        if page["next"] is None:
            return
        url = page_url(page["next"], client, endpoint)


def items(page: dict[str, Any], key: str) -> list[Any]:
    value = page.get(key)
    if not isinstance(value, list) or (page["next"] is not None and not value):
        raise invalid()
    return value


def fetch_releases(client: httpx.Client) -> tuple[Release, ...]:
    result: list[Release] = []
    expected = 0
    for page in pages(client, RELEASES, {"page_size": "100"}, "Data releases"):
        expected = page["count"]
        for raw in items(page, "results"):
            release = decode_release(raw)
            if result and release.key >= result[-1].key:
                raise invalid()
            result.append(release)
        if len(result) > expected:
            raise invalid()
    if len(result) != expected:
        raise invalid()
    return tuple(result)


def fetch_counties(client: httpx.Client) -> dict[str, str]:
    for size in (100, 50, 25, 12, 6, 3, 1):
        try:
            result: dict[str, str] = {}
            expected = 0
            for page in pages(
                client,
                COUNTIES,
                {"state": "39", "page_size": str(size)},
                "County names",
            ):
                if (
                    page.get("type") != "FeatureCollection"
                    or page.get("state") != "39"
                    or type(page.get("boundary_vintage")) is not int
                    or page["boundary_vintage"] != 2020
                ):
                    raise invalid()
                expected = page["count"]
                for raw in items(page, "features"):
                    feature = record(raw)
                    props = record(feature.get("properties"))
                    code = text(feature.get("id"))
                    if (
                        feature.get("type") != "Feature"
                        or not re.fullmatch(r"39[0-9]{3}", code)
                        or props.get("code") != code
                        or (result and code <= next(reversed(result)))
                    ):
                        raise invalid()
                    result[code] = text(props.get("name"))
                if len(result) > expected:
                    raise invalid()
            if len(result) != expected:
                raise invalid()
            return result
        except ApiUnavailableError as error:
            if error.status != 400 or not any(
                pointer == "/page_size" and code == "geometry_payload_too_large"
                for pointer, code, _ in error.errors
            ):
                raise
            if size == 1:
                raise ApiUnavailableError(
                    "A county boundary exceeds the response limit even at one feature per page. "
                    "Contact an application operator."
                ) from error
    raise invalid()


def fetch_summary(
    client: httpx.Client,
    release: Release,
    flag: Flag,
    *,
    code: str | None = None,
) -> tuple[CountySummaries, str]:
    params = {
        "level": "county",
        "state": "39",
        "flag": flag,
        "as_of": release.as_of,
        "processed_on": release.processed_on,
        "page_size": "100",
    }
    if code is not None:
        params["code"] = code
    result: list[SummaryRow] = []
    expected = 0
    coverage = ""
    for page in pages(client, ROLLUPS, params, "County summaries"):
        current = decode_release(page.get("release"))
        threshold = record(page.get("threshold"))
        if (
            current != release
            or page.get("selection")
            != {"level": "county", "state": "39", "flag": flag, "code": code}
            or threshold != {"download_mbps": 100, "upload_mbps": 20}
            or any(type(n) is not int for n in threshold.values())
            or type(page.get("boundary_vintage")) is not int
            or page["boundary_vintage"] != 2020
        ):
            raise invalid()
        expected = page["count"]
        coverage = text(page.get("summary_coverage"))
        if code is None and coverage != "stored_rollups_only":
            raise invalid()
        for raw in items(page, "results"):
            item = record(raw)
            row_code = text(item.get("code"))
            locations = count(item.get("locations"))
            served = count(item.get("served"))
            not_served = count(item.get("not_served"))
            flags = {f: count(item.get(f + "_100_20")) for f in FLAGS}
            if (
                not re.fullmatch(r"39[0-9]{3}", row_code)
                or locations == 0
                or served + not_served != locations
                or flags[flag] != served
                or any(n > locations for n in flags.values())
                or (result and row_code <= result[-1].code)
                or (code is not None and row_code != code)
            ):
                raise invalid()
            result.append(SummaryRow(row_code, locations, served, not_served))
        if len(result) > expected:
            raise invalid()
        if code is not None and (
            page["next"] is not None
            or page["previous"] is not None
            or not (
                (expected == 1 and coverage == "observed")
                or (expected == 0 and coverage in ("no_observations", "outside_release_coverage"))
            )
        ):
            raise invalid()
    if len(result) != expected:
        raise invalid()
    return CountySummaries(release, flag, tuple(result)), coverage


def fetch_health(client: httpx.Client) -> dict[str, bool]:
    body = record(get_json(client, "/api/health/", "Health check", health=True))
    if any(body.get(name) not in ("ok", "unreachable") for name in COMPONENTS):
        raise invalid()
    return {name: body[name] == "ok" for name in COMPONENTS}
