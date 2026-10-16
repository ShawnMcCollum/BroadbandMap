"""Generated schema and schema-baseline command behavior."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from django.core.management import CommandError, call_command
from django.test import override_settings
from django.urls import path
from drf_spectacular.drainage import GENERATOR_STATS, reset_generator_stats
from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.validation import validate_schema
from jsonschema import ValidationError  # type: ignore[import-untyped]
from openapi_schema_validator import OAS30Validator
from rest_framework.test import APIClient

from core.management.commands import check_api_schema
from core.tests.api import urls as test_urls
from core.tests.api.helpers import problem

pytestmark = pytest.mark.urls("core.tests.api.urls")


@pytest.fixture(autouse=True)
def reset_schema_warning_statistics() -> Iterator[None]:
    reset_generator_stats()
    yield
    reset_generator_stats()


def _validator(document: dict[str, Any], response_schema: dict[str, Any]) -> OAS30Validator:
    return OAS30Validator(
        document,
        format_checker=OAS30Validator.FORMAT_CHECKER,
    ).evolve(schema=response_schema)


def test_production_schema_matches_business_contract_and_is_public(api_client: APIClient) -> None:
    reset_generator_stats()
    call_command("check_api_schema")
    baseline = json.loads(check_api_schema.BASELINE_PATH.read_text(encoding="utf-8"))
    assert baseline["openapi"] == "3.0.3"
    assert baseline["info"]["title"] == "BroadbandMap API"
    assert set(baseline["paths"]) == {
        "/api/v1/releases/",
        "/api/v1/served-unserved/rollups/",
        "/api/v1/served-unserved/locations/",
        "/api/v1/geographies/county/",
    }
    assert not any("test_" in path for path in baseline["paths"])

    with override_settings(ROOT_URLCONF="config.urls"):
        response = api_client.get("/api/schema/")
        denied = api_client.post("/api/schema/", data={})
    assert response.status_code == 200
    assert response["Content-Type"].split(";", 1)[0] in {
        "application/json",
        "application/vnd.oai.openapi+json",
    }
    assert json.loads(response.content) == baseline
    assert denied.status_code == 405
    assert problem(denied)["code"] == "method_not_allowed"
    reset_generator_stats()


def test_test_route_schema_and_actual_contract_responses(api_client: APIClient) -> None:
    patterns = [
        path("api/v1/public/", test_urls.PublicRead.as_view(), name="schema-public"),
        path("api/v1/limit/", test_urls.LimitView.as_view(), name="schema-limit"),
        path("api/v1/operation/", test_urls.OperationView.as_view(), name="schema-operation"),
    ]
    reset_generator_stats()
    generator: Any = cast(Any, SchemaGenerator)
    document = cast(dict[str, Any], generator(patterns=patterns).get_schema(public=True))
    assert document is not None
    validate: Any = cast(Any, validate_schema)
    validate(document)
    assert not GENERATOR_STATS
    assert document["openapi"] == "3.0.3"
    assert set(document["paths"]) == {
        "/api/v1/public/",
        "/api/v1/limit/",
        "/api/v1/operation/",
    }
    public_operation = document["paths"]["/api/v1/public/"]["get"]
    assert public_operation["operationId"] == "test_public_read"
    assert public_operation.get("security", []) == []
    operation = document["paths"]["/api/v1/operation/"]
    assert operation["get"]["operationId"] == "test_operation_read"
    assert operation["post"]["operationId"] == "test_operation_write"
    assert operation["get"].get("security")
    limit_operation = document["paths"]["/api/v1/limit/"]["get"]
    assert any(
        parameter["name"] == "limit" and parameter["in"] == "query"
        for parameter in limit_operation["parameters"]
    )
    bad_content = limit_operation["responses"]["400"]["content"]
    assert set(bad_content) == {"application/problem+json"}

    public_response = api_client.get("/api/v1/public/")
    public_schema = public_operation["responses"]["200"]["content"]["application/json"]["schema"]
    _validator(document, public_schema).validate(json.loads(public_response.content))
    assert json.loads(public_response.content) == {"id": "00123", "count": 4, "enabled": True}
    with pytest.raises(ValidationError):
        _validator(document, public_schema).validate({"id": 123, "count": 4, "enabled": True})
    with pytest.raises(ValidationError):
        _validator(document, public_schema).validate({"id": "00123", "count": 4})

    valid_response = api_client.get("/api/v1/limit/?limit=2")
    valid_schema = limit_operation["responses"]["200"]["content"]["application/json"]["schema"]
    _validator(document, valid_schema).validate(json.loads(valid_response.content))
    assert valid_response.json() == {"limit": 2}

    invalid_response = api_client.get("/api/v1/limit/?limit=0")
    invalid_body = problem(invalid_response)
    error_schema = bad_content["application/problem+json"]["schema"]
    _validator(document, error_schema).validate(invalid_body)
    assert invalid_body["code"] == "validation_error"
    assert invalid_body["errors"][0]["pointer"] == "/limit"

    denied_response = api_client.get("/api/v1/operation/")
    denied_body = problem(denied_response)
    denied_schema = operation["get"]["responses"]["403"]["content"]["application/problem+json"][
        "schema"
    ]
    _validator(document, denied_schema).validate(denied_body)
    assert denied_response.status_code == 403
    assert denied_body["code"] == "not_authenticated"

    plain_error = api_client.get("/api/plain-error/bad_request/")
    plain_body = problem(plain_error)
    _validator(document, error_schema).validate(plain_body)
    assert plain_body["code"] == "bad_request"
    reset_generator_stats()


def _patch_generation(monkeypatch: pytest.MonkeyPatch, document: dict[str, Any]) -> None:
    def generate(command: str, **kwargs: Any) -> None:
        assert command == "spectacular"
        Path(kwargs["file"]).write_text(json.dumps(document), encoding="utf-8")

    monkeypatch.setattr(check_api_schema, "call_command", generate)


def test_schema_command_unchanged_drift_and_update_are_intentional(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = tmp_path / "openapi.json"
    baseline.write_text(json.dumps({"openapi": "3.0.3", "paths": {}}), encoding="utf-8")
    monkeypatch.setattr(check_api_schema, "BASELINE_PATH", baseline)
    generated: dict[str, Any] = {"paths": {}, "openapi": "3.0.3"}
    _patch_generation(monkeypatch, generated)
    call_command("check_api_schema")
    original = baseline.read_text(encoding="utf-8")

    _patch_generation(monkeypatch, {"openapi": "3.0.3", "paths": {"/new/": {}}})
    with pytest.raises(CommandError, match="schema differs"):
        call_command("check_api_schema")
    assert baseline.read_text(encoding="utf-8") == original

    call_command("check_api_schema", update=True)
    assert json.loads(baseline.read_text(encoding="utf-8")) == {
        "openapi": "3.0.3",
        "paths": {"/new/": {}},
    }


def test_schema_command_propagates_generation_failures_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = tmp_path / "openapi.json"
    baseline.write_text('{"paths": {}}', encoding="utf-8")
    monkeypatch.setattr(check_api_schema, "BASELINE_PATH", baseline)

    def fail(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("schema warnings present")

    monkeypatch.setattr(check_api_schema, "call_command", fail)
    with pytest.raises(CommandError, match="generation or validation failed"):
        call_command("check_api_schema", update=True)
    assert baseline.read_text(encoding="utf-8") == '{"paths": {}}'
