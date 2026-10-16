"""HTTP validation, session/CSRF behavior, and response secrecy."""

import os
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from core.tests.api.helpers import problem
from natural_language.configuration import update_configuration
from natural_language.models import AIConfiguration

pytestmark = pytest.mark.django_db


def test_configuration_round_trip_persists_without_returning_credential(
    configuration: APIClient,
) -> None:
    response = configuration.patch(
        "/api/v1/natural-language/configuration/",
        {"provider": "vendor", "model_name": "model", "api_key": "secret-value"},
        format="json",
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "vendor"
    assert payload["key_configured"] is True and payload["key_available"] is True
    assert "secret-value" not in response.content.decode()
    assert "api_key_ciphertext" not in payload
    assert response["Cache-Control"] == "no-store"
    configuration.logout()
    another = APIClient()
    another.force_login(User.objects.get(username="ai-admin"))
    assert another.get("/api/v1/natural-language/configuration/").json() == payload


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"surprise": 1},
        {"enabled": "true"},
        {"timeout_seconds": True},
        {"timeout_seconds": 1.5},
        {"timeout_seconds": "30"},
        {"api_key": None},
        {"api_key": "   "},
        {"provider": "Upper"},
        {"model_name": "x" * 201},
        {"timeout_seconds": 0},
        {"timeout_seconds": 121},
        {"max_output_tokens": 0},
        {"max_output_tokens": 8193},
        {"clear_api_key": True, "enabled": True},
        {"clear_api_key": True, "api_key": "replacement"},
        {"api_key": "x" * 4097},
        {"provider": 123},
        {"max_output_tokens": False},
        {"key_configured": True},
        {"api_key_ciphertext": "forged"},
    ],
)
def test_configuration_rejects_invalid_patch_without_partial_write(
    configuration: APIClient, config: AIConfiguration, payload: dict[str, object]
) -> None:
    response = configuration.patch(
        "/api/v1/natural-language/configuration/", payload, format="json"
    )
    assert response.status_code == 400
    assert problem(response)["code"] == "validation_error"
    config.refresh_from_db()
    assert config.provider == "" and config.api_key_ciphertext == ""


def test_explicit_clear_removes_key_and_disables(
    configuration: APIClient, admin_user: User
) -> None:
    update_configuration(
        {"provider": "vendor", "model_name": "x", "api_key": "key", "enabled": True}, admin_user
    )
    response = configuration.patch(
        "/api/v1/natural-language/configuration/", {"clear_api_key": True}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert response.json()["key_configured"] is False


def test_status_and_query_are_stub_only(configuration: APIClient, admin_user: User) -> None:
    update_configuration(
        {"provider": "vendor", "model_name": "x", "api_key": "key", "enabled": True}, admin_user
    )
    status = APIClient().get("/api/v1/natural-language/")
    assert status.json()["enabled"] is True and status.json()["is_stub"] is True
    query = APIClient().post(
        "/api/v1/natural-language/query/", {"question": "  Hello  "}, format="json"
    )
    assert query.status_code == 200
    assert query.json()["question"] == "Hello"
    assert query.json()["is_stub"] is True
    assert "No broadband data was queried" in query.json()["answer"]
    assert query["Cache-Control"] == "no-store"
    boundary = APIClient().post(
        "/api/v1/natural-language/query/", {"question": "x" * 2000}, format="json"
    )
    assert boundary.status_code == 200
    sql_like = APIClient().post(
        "/api/v1/natural-language/query/",
        {"question": "DROP TABLE locations; SELECT * FROM provider_keys"},
        format="json",
    )
    assert sql_like.status_code == 200
    assert sql_like.json()["question"].startswith("DROP TABLE")


@pytest.mark.parametrize("question", [None, 2, True, [], {}, "  ", "x" * 2001])
def test_query_rejects_invalid_question(
    api_client: APIClient, question: object, config: AIConfiguration
) -> None:
    response = api_client.post(
        "/api/v1/natural-language/query/", {"question": question}, format="json"
    )
    assert response.status_code == 400
    assert problem(response)["code"] == "validation_error"


def test_query_validates_before_disabled_gate_and_rejects_query_parameters(
    api_client: APIClient,
) -> None:
    bad = api_client.post(
        "/api/v1/natural-language/query/?unexpected=x", {"question": ""}, format="json"
    )
    assert bad.status_code == 400
    disabled = api_client.post(
        "/api/v1/natural-language/query/", {"question": "hello"}, format="json"
    )
    assert disabled.status_code == 503
    assert problem(disabled)["code"] == "natural_language_disabled"


def test_query_validation_is_independent_of_feature_state(
    api_client: APIClient, admin_user: User
) -> None:
    invalid_values: list[object] = [None, 2, True, [], {}, " ", "x" * 2001]
    for value in invalid_values:
        response = api_client.post(
            "/api/v1/natural-language/query/", {"question": value}, format="json"
        )
        assert response.status_code == 400
    update_configuration(
        {"provider": "vendor", "model_name": "model", "api_key": "key", "enabled": True},
        admin_user,
    )
    for value in invalid_values:
        response = api_client.post(
            "/api/v1/natural-language/query/", {"question": value}, format="json"
        )
        assert response.status_code == 400
    missing = api_client.post("/api/v1/natural-language/query/", {}, format="json")
    extra = api_client.post(
        "/api/v1/natural-language/query/", {"question": "hello", "extra": 1}, format="json"
    )
    assert missing.status_code == extra.status_code == 400


def test_patch_requires_session_and_csrf(configuration: APIClient, admin_user: User) -> None:
    csrf_client = APIClient(enforce_csrf_checks=True)
    csrf_client.force_login(admin_user)
    no_token = csrf_client.patch(
        "/api/v1/natural-language/configuration/", {"enabled": False}, format="json"
    )
    assert no_token.status_code == 403
    assert csrf_client.get("/api/v1/natural-language/configuration/").status_code == 200
    token = csrf_client.cookies["csrftoken"].value
    wrong_token = csrf_client.patch(
        "/api/v1/natural-language/configuration/",
        {"enabled": False},
        format="json",
        HTTP_X_CSRFTOKEN="0" * 64,
    )
    assert wrong_token.status_code == 403
    accepted = csrf_client.patch(
        "/api/v1/natural-language/configuration/",
        {"enabled": False},
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert accepted.status_code == 200


def test_empty_nonobject_and_wrong_query_body(
    api_client: APIClient, configuration: APIClient
) -> None:
    empty = configuration.patch(
        "/api/v1/natural-language/configuration/", data="{}", content_type="application/json"
    )
    assert empty.status_code == 400
    malformed = api_client.post(
        "/api/v1/natural-language/query/", data="{", content_type="application/json"
    )
    assert malformed.status_code == 400
    assert problem(malformed)["code"] == "parse_error"
    plain = api_client.post(
        "/api/v1/natural-language/query/", data="hello", content_type="text/plain"
    )
    assert plain.status_code == 415


@pytest.mark.parametrize("suffix", ["?unknown=x", "?question=x&question=x"])
def test_every_resource_rejects_query_parameters(configuration: APIClient, suffix: str) -> None:
    for path, method, data in (
        ("/api/v1/natural-language/", "get", {}),
        ("/api/v1/natural-language/configuration/", "patch", {"enabled": False}),
        ("/api/v1/natural-language/query/", "post", {"question": "Hello"}),
    ):
        response = getattr(configuration, method)(path + suffix, data=data, format="json")
        assert response.status_code == 400
        assert problem(response)["code"] == "validation_error"


@pytest.mark.parametrize("data", ["[]", "1", "null", '"text"'])
def test_nonobject_json_is_rejected_by_configuration_and_query(
    configuration: APIClient, data: str
) -> None:
    for path, method in (
        ("/api/v1/natural-language/configuration/", "patch"),
        ("/api/v1/natural-language/query/", "post"),
    ):
        response = getattr(configuration, method)(path, data=data, content_type="application/json")
        assert response.status_code == 400
        assert problem(response)["code"] == "validation_error"


@pytest.mark.parametrize("timeout,tokens", [(1, 1), (120, 8192)])
def test_configuration_accepts_exact_bounds_and_normalizes_key(
    configuration: APIClient, timeout: int, tokens: int
) -> None:
    response = configuration.patch(
        "/api/v1/natural-language/configuration/",
        {"timeout_seconds": timeout, "max_output_tokens": tokens, "api_key": "  saved-key  "},
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["timeout_seconds"] == timeout
    assert response.json()["max_output_tokens"] == tokens
    from natural_language.credentials import require_credential

    assert require_credential(AIConfiguration.objects.get(pk=1).api_key_ciphertext) == "saved-key"


def test_credential_failure_is_safe_and_admin_can_clear_it(
    configuration: APIClient, admin_user: User, key_file: Path
) -> None:
    update_configuration(
        {"provider": "vendor", "model_name": "model", "api_key": "sensitive", "enabled": True},
        admin_user,
    )
    key_file.unlink()
    status = APIClient().get("/api/v1/natural-language/")
    assert status.status_code == 200 and status.json()["enabled"] is False
    failure = APIClient().post(
        "/api/v1/natural-language/query/", {"question": "Hello"}, format="json"
    )
    assert failure.status_code == 503
    assert problem(failure)["code"] == "ai_credentials_unavailable"
    assert "sensitive" not in failure.content.decode()
    assert str(key_file) not in failure.content.decode()
    metadata = configuration.get("/api/v1/natural-language/configuration/").json()
    assert metadata["key_configured"] is True and metadata["key_available"] is False
    cleared = configuration.patch(
        "/api/v1/natural-language/configuration/", {"clear_api_key": True}, format="json"
    )
    assert cleared.status_code == 200 and cleared.json()["key_configured"] is False


def test_failed_key_file_write_returns_safe_error_and_preserves_settings(
    configuration: APIClient,
    config: AIConfiguration,
    key_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fail_replace(source: str, destination: Path) -> None:
        raise PermissionError("private-storage-path secret-token")

    monkeypatch.setattr(os, "replace", fail_replace)
    response = configuration.patch(
        "/api/v1/natural-language/configuration/",
        {"provider": "vendor", "api_key": "new-credential"},
        format="json",
    )
    assert response.status_code == 503
    assert problem(response)["code"] == "ai_credentials_unavailable"
    assert "private-storage-path" not in response.content.decode() + caplog.text
    assert "new-credential" not in response.content.decode() + caplog.text
    config.refresh_from_db()
    assert config.provider == "" and config.api_key_ciphertext == ""
    assert not key_file.exists()
    assert list(key_file.parent.glob(".ai-key-*")) == []
