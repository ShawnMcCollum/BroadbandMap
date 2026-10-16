"""Strict singleton query parameter validation contracts."""

import pytest
from django.http import QueryDict
from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail
from rest_framework.test import APIClient

from core.api.validation import StrictQuerySerializer
from core.tests.api.helpers import problem
from core.tests.api.urls import LimitQuery, NestedQuery

pytestmark = pytest.mark.urls("core.tests.api.urls")


def test_limit_default_and_valid_value(api_client: APIClient) -> None:
    omitted = api_client.get("/api/v1/limit/")
    assert omitted.status_code == 200
    assert omitted.json() == {"limit": 7}
    provided = api_client.get("/api/v1/limit/?limit=2")
    assert provided.status_code == 200
    assert provided.json() == {"limit": 2}


@pytest.mark.parametrize("query", ["limit=", "limit=bad", "limit=0", "limit=11"])
def test_invalid_limit_is_validation_problem(api_client: APIClient, query: str) -> None:
    response = api_client.get(f"/api/v1/limit/?{query}")
    body = problem(response)
    assert response.status_code == 400
    assert body["code"] == "validation_error"
    assert body["errors"]
    assert all(error["pointer"] == "/limit" for error in body["errors"])


def test_unknown_and_repeated_names_have_stable_codes(api_client: APIClient) -> None:
    unknown = problem(api_client.get("/api/v1/limit/?flga=wired"))
    assert unknown["errors"] == [
        {"pointer": "/flga", "code": "unknown_parameter", "message": "Unknown query parameter."}
    ]
    for query in ("limit=1&limit=2", "limit=1&limit=1"):
        repeated = problem(api_client.get(f"/api/v1/limit/?{query}"))
        assert repeated["errors"] == [
            {
                "pointer": "/limit",
                "code": "repeated_parameter",
                "message": "This query parameter must occur only once.",
            }
        ]


def test_multiple_unknown_names_are_sorted(api_client: APIClient) -> None:
    body = problem(api_client.get("/api/v1/limit/?z=1&a=2"))
    assert [item["pointer"] for item in body["errors"]] == ["/a", "/z"]
    combined = problem(api_client.get("/api/v1/limit/?z=1&limit=1&limit=2"))
    assert [item["pointer"] for item in combined["errors"]] == ["/limit", "/z"]


def test_cross_field_and_nested_errors_keep_json_pointers(api_client: APIClient) -> None:
    paired = problem(api_client.get("/api/v1/pair/?start=2"))
    assert paired["errors"][0]["pointer"] == "/non_field_errors"
    nested = NestedQuery(data={"values": ["bad"]})
    assert nested.is_valid() is False
    from core.api.problems import flatten_errors

    assert flatten_errors(nested.errors)[0]["pointer"] == "/values/0"
    escaped = problem(api_client.get("/api/v1/slash/?a~%2Fb=bad"))
    assert escaped["errors"][0]["pointer"] == "/a~0~1b"
    multiple = problem(api_client.get("/api/v1/multiple/?value=1"))
    assert [item["pointer"] for item in multiple["errors"]] == ["/value", "/value"]


def test_root_level_error_uses_empty_pointer() -> None:
    from core.api.problems import flatten_errors

    assert flatten_errors(ErrorDetail("Invalid value.", code="invalid")) == [
        {"pointer": "", "code": "invalid", "message": "Invalid value."}
    ]


def test_plain_dictionary_validation_still_rejects_unknown_names() -> None:
    serializer = LimitQuery(data={"limit": "2", "typo": "x"})
    assert serializer.is_valid() is False
    assert serializer.errors["typo"][0].code == "unknown_parameter"
    serializer = LimitQuery(data={"limit": "2"})
    assert serializer.is_valid(raise_exception=True)
    assert serializer.validated_data["limit"] == 2


def test_plain_serializer_extension_can_be_isolated() -> None:
    class Pair(StrictQuerySerializer):
        left = serializers.IntegerField(required=False)
        right = serializers.IntegerField(required=False)

    serializer = Pair(data={"extra": "x"})
    assert serializer.is_valid() is False
    assert serializer.errors["extra"][0].code == "unknown_parameter"
    query = QueryDict("left=1&left=2")
    serializer = Pair(data=query)
    assert serializer.is_valid() is False
    assert serializer.errors["left"][0].code == "repeated_parameter"
