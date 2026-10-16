"""Validate actual business payloads against the generated production contract."""

import json
from typing import Any

import pytest
from django.core.management import call_command
from openapi_schema_validator import OAS30Validator
from rest_framework.test import APIClient

from core.management.commands.check_api_schema import BASELINE_PATH
from geography.models import County
from served_unserved.models import Rollup

pytestmark = pytest.mark.django_db(transaction=True)


def test_business_responses_validate_against_reviewed_schema(
    rollup: Rollup, county: County
) -> None:
    call_command("check_api_schema")
    document = json.loads(BASELINE_PATH.read_text())
    client = APIClient()
    cases: list[tuple[str, dict[str, Any], int, str]] = [
        ("/api/v1/releases/", {}, 200, "application/json"),
        ("/api/v1/served-unserved/rollups/", {"level": "county"}, 200, "application/json"),
        ("/api/v1/geographies/county/", {"state": "39"}, 200, "application/geo+json"),
        ("/api/v1/releases/", {"page_size": 0}, 400, "application/problem+json"),
        ("/api/v1/served-unserved/rollups/", {"level": "bad"}, 400, "application/problem+json"),
        ("/api/v1/geographies/county/", {"state": "99"}, 404, "application/problem+json"),
    ]
    for path, params, status, media_type in cases:
        operation = document["paths"][path]["get"]
        assert not operation.get("security")
        assert set(document["paths"][path]) == {"get"}
        response = client.get(path, params)
        assert response.status_code == status
        schema = operation["responses"][str(status)]["content"][media_type]["schema"]
        OAS30Validator(document, format_checker=OAS30Validator.FORMAT_CHECKER).evolve(
            schema=schema
        ).validate(response.json())
        assert response["Content-Type"].split(";")[0] == media_type
