"""Problem Details and full Django boundary behavior."""

import json
import logging

import pytest
from django.conf import settings
from django.test import Client, override_settings
from rest_framework.test import APIClient

from core.tests.api.helpers import problem

pytestmark = pytest.mark.urls("core.tests.api.urls")


@pytest.mark.parametrize(
    ("kind", "status", "code"),
    [
        ("not_found", 404, "not_found"),
        ("permission", 403, "permission_denied"),
        ("bad_request", 400, "bad_request"),
        ("parse", 400, "parse_error"),
        ("not_authenticated", 403, "not_authenticated"),
        ("authentication_failed", 403, "authentication_failed"),
        ("throttle", 429, "throttled"),
        ("unavailable", 503, "service_unavailable"),
    ],
)
def test_expected_exception_mappings(
    api_client: APIClient, kind: str, status: int, code: str
) -> None:
    response = api_client.get(f"/api/v1/error/?kind={kind}")
    body = problem(response)
    assert response.status_code == status
    assert body["code"] == code
    if status == 429:
        assert response["Retry-After"] == "3"


def test_malformed_json_and_unsupported_media_type(api_client: APIClient) -> None:
    malformed = api_client.generic(
        "POST", "/api/v1/parse/", data="{bad", content_type="application/json"
    )
    assert problem(malformed)["code"] == "parse_error"
    unsupported = api_client.generic(
        "POST", "/api/v1/parse/", data="hello", content_type="text/plain"
    )
    assert problem(unsupported)["code"] == "unsupported_media_type"


def test_not_acceptable_has_problem_media_type(api_client: APIClient) -> None:
    response = api_client.get("/api/v1/public/", HTTP_ACCEPT="text/html")
    assert response.status_code == 406
    assert problem(response)["code"] == "not_acceptable"


def test_unknown_api_paths_and_root_are_problems(api_client: APIClient) -> None:
    for path in ("/api/v1/missing/", "/api/v2/missing/", "/api/"):
        response = api_client.get(path)
        assert response.status_code == 404
        assert problem(response)["code"] == "not_found"


@pytest.mark.parametrize(
    ("kind", "status", "code"),
    [
        ("not_found", 404, "not_found"),
        ("permission", 403, "permission_denied"),
        ("bad_request", 400, "bad_request"),
        ("suspicious", 400, "bad_request"),
    ],
)
def test_plain_django_exceptions_keep_their_http_meaning(
    api_client: APIClient, kind: str, status: int, code: str
) -> None:
    response = api_client.get(f"/api/plain-error/{kind}/")
    body = problem(response)
    assert response.status_code == status
    assert body["code"] == code


@pytest.mark.parametrize("debug", [True, False])
def test_unexpected_view_failure_is_sanitized_and_logged(
    api_client: APIClient, debug: bool, caplog: pytest.LogCaptureFixture
) -> None:
    api_client.raise_request_exception = False
    with override_settings(DEBUG=debug), caplog.at_level(logging.ERROR, logger="core.api"):
        response = api_client.get("/api/v1/error/?kind=unexpected")
    body = problem(response)
    assert response.status_code == 500
    assert body["code"] == "internal_error"
    assert body["detail"] == "An unexpected error occurred."
    assert "select *" not in response.content.decode()
    assert "C:\\private" not in response.content.decode()
    matching = [record for record in caplog.records if "request_id=" in record.getMessage()]
    assert len(matching) == 1
    assert body["request_id"] in matching[0].getMessage()


@pytest.mark.parametrize("debug", [True, False])
def test_rendering_and_middleware_failures_are_sanitized(
    api_client: APIClient, debug: bool
) -> None:
    api_client.raise_request_exception = False
    with override_settings(DEBUG=debug):
        rendered = api_client.get("/api/v1/render-failure/")
    assert problem(rendered)["code"] == "internal_error"
    assert "secret SQL" not in rendered.content.decode()

    middleware = [
        settings.MIDDLEWARE[0],
        "core.tests.api.helpers.FailingTestMiddleware",
        *settings.MIDDLEWARE[1:],
    ]
    with override_settings(MIDDLEWARE=middleware, DEBUG=debug):
        client = APIClient()
        client.raise_request_exception = False
        response = client.get("/api/v1/middleware-failure/")
    body = problem(response)
    assert response.status_code == 500
    assert "secret SQL" not in json.dumps(body)


def test_returned_nonproblem_error_is_replaced_without_losing_headers(
    api_client: APIClient,
) -> None:
    response = api_client.get("/api/plain-returned/")
    body = problem(response)
    assert body["code"] == "bad_request"
    assert "unsafe detail" not in response.content.decode()
    assert response["Allow"] == "GET"
    assert response["Retry-After"] == "3"
    assert response["WWW-Authenticate"] == "Session"
    assert response["Vary"] == "Cookie"
    assert response.cookies["sessionid"].value == "session-value"
    assert "Content-Length" not in response
    assert "Content-Encoding" not in response
    assert "ETag" not in response


def test_expected_failures_do_not_emit_shared_error_logs(
    api_client: APIClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("ERROR", logger="core.api"):
        api_client.get("/api/v1/limit/?limit=0")
        api_client.get("/api/v1/error/?kind=permission")
    assert not [record for record in caplog.records if record.name == "core.api"]


def test_head_problem_keeps_status_headers_and_empty_body(api_client: APIClient) -> None:
    response = api_client.head("/api/v1/missing/")
    assert response.status_code == 404
    assert response["Content-Type"].startswith("application/problem+json")
    assert response["X-Request-ID"]
    assert response.content == b""


def test_non_api_failure_keeps_django_behavior(client: Client) -> None:
    non_api = client.get("/not-api/")
    assert non_api.status_code == 404
    assert non_api["Content-Type"].startswith("text/html")


def test_health_503_legacy_response_is_not_wrapped(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("core.views.check_database", lambda: False)
    response = client.get("/api/health/")
    assert response.status_code == 503
    assert response["Content-Type"].startswith("application/json")
    assert response.json()["status"] == "error"
    assert "X-Request-ID" not in response


def test_response_request_ids_are_fresh_and_incoming_header_is_ignored(
    api_client: APIClient,
) -> None:
    first = api_client.get("/api/v1/public/", HTTP_X_REQUEST_ID="f" * 32)
    second = api_client.get("/api/v1/public/", HTTP_X_REQUEST_ID="f" * 32)
    assert first["X-Request-ID"] != "f" * 32
    assert second["X-Request-ID"] != "f" * 32
    assert first["X-Request-ID"] != second["X-Request-ID"]
