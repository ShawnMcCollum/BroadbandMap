"""Validate production OpenAPI declarations against representative HTTP payloads."""

import json
from pathlib import Path
from typing import Any

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from openapi_schema_validator import OAS30Validator
from rest_framework.test import APIClient

from core.management.commands.check_api_schema import BASELINE_PATH

pytestmark = pytest.mark.django_db


def _validate(document: dict[str, Any], path: str, method: str, response: Any) -> None:
    operation = document["paths"][path][method]
    content_type = response["Content-Type"].split(";", 1)[0]
    schema = operation["responses"][str(response.status_code)]["content"][content_type]["schema"]
    validator = OAS30Validator(document, format_checker=OAS30Validator.FORMAT_CHECKER).evolve(
        schema=schema
    )
    validator.validate(json.loads(response.content))


def test_actual_responses_match_schema_and_credentials_are_write_only(
    admin_user: User, monkeypatch: pytest.MonkeyPatch, key_file: Path
) -> None:
    call_command("check_api_schema")
    document = json.loads(BASELINE_PATH.read_text())
    assert set(document["paths"]) >= {
        "/api/v1/natural-language/",
        "/api/v1/natural-language/configuration/",
        "/api/v1/natural-language/query/",
    }
    config_path = "/api/v1/natural-language/configuration/"
    query_path = "/api/v1/natural-language/query/"
    status_path = "/api/v1/natural-language/"
    assert set(document["paths"][config_path]) == {"get", "patch"}
    assert set(document["paths"][query_path]) == {"post"}
    assert set(document["paths"][status_path]) == {"get"}
    assert document["paths"][config_path]["patch"].get("security")
    assert not document["paths"][query_path]["post"].get("security")
    assert not document["paths"][status_path]["get"].get("security")
    schema_ref = document["paths"][config_path]["patch"]["requestBody"]["content"][
        "application/json"
    ]["schema"]["$ref"]
    patch_schema = document["components"]["schemas"][schema_ref.rsplit("/", 1)[-1]]
    assert patch_schema["properties"]["api_key"].get("writeOnly") is True
    assert "api_key_ciphertext" not in str(document)
    response_ref = document["paths"][config_path]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["$ref"]
    response_schema = document["components"]["schemas"][response_ref.rsplit("/", 1)[-1]]
    assert "api_key" not in response_schema["properties"]

    client = APIClient()
    anonymous = client.get(config_path)
    _validate(document, config_path, "get", anonymous)
    assert anonymous.status_code == 403

    admin = APIClient()
    admin.force_login(admin_user)
    ok = admin.get(config_path)
    _validate(document, config_path, "get", ok)
    invalid = admin.patch(config_path, {"unexpected": 1}, format="json")
    _validate(document, config_path, "patch", invalid)
    wrong_method = admin.post(config_path, {}, format="json")
    _validate(document, config_path, "patch", wrong_method)
    unacceptable = admin.get(config_path, HTTP_ACCEPT="application/xml")
    _validate(document, config_path, "get", unacceptable)
    unsupported = client.post(query_path, data="question", content_type="text/plain")
    _validate(document, query_path, "post", unsupported)
    disabled = client.post(query_path, {"question": "hello"}, format="json")
    _validate(document, query_path, "post", disabled)
    assert disabled.status_code == 503
    disabled_status = client.get(status_path)
    _validate(document, status_path, "get", disabled_status)
    assert disabled_status.json()["enabled"] is False
    saved = admin.patch(
        config_path,
        {"provider": "vendor", "model_name": "model", "api_key": "secret", "enabled": True},
        format="json",
    )
    assert saved.status_code == 200
    _validate(document, config_path, "patch", saved)
    enabled_status = client.get(status_path)
    _validate(document, status_path, "get", enabled_status)
    assert enabled_status.json()["enabled"] is True
    answered = client.post(query_path, {"question": "hello"}, format="json")
    assert answered.status_code == 200
    _validate(document, query_path, "post", answered)
    malformed = client.post(query_path, data="{", content_type="application/json")
    assert malformed.status_code == 400
    _validate(document, query_path, "post", malformed)
    key_file.unlink()
    unavailable = client.post(query_path, {"question": "hello"}, format="json")
    assert unavailable.status_code == 503
    assert unavailable.json()["code"] == "ai_credentials_unavailable"
    _validate(document, query_path, "post", unavailable)
    failed_update = admin.patch(config_path, {"timeout_seconds": 50}, format="json")
    assert failed_update.status_code == 503
    _validate(document, config_path, "patch", failed_update)

    from natural_language.api import views

    monkeypatch.setattr(
        views,
        "get_configuration",
        lambda: (_ for _ in ()).throw(RuntimeError("secret path")),
    )
    failure = client.get("/api/v1/natural-language/")
    _validate(document, "/api/v1/natural-language/", "get", failure)
    assert "secret path" not in failure.content.decode()
