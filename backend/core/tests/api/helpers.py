"""Assertions shared by API boundary tests."""

import json
from collections.abc import Callable
from typing import Any, cast

from django.http import HttpRequest, HttpResponse

LOGIN_VALUE = "pass1234"


def problem(response: Any) -> dict[str, Any]:
    assert response["Content-Type"].split(";", 1)[0] == "application/problem+json"
    body = json.loads(response.content)
    assert body["status"] == response.status_code
    assert body["request_id"] == response["X-Request-ID"]
    assert len(body["request_id"]) == 32
    return cast(dict[str, Any], body)


class FailingTestMiddleware:
    """Raise inside Django's middleware stack to exercise the outer API boundary."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.path_info == "/api/v1/middleware-failure/":
            raise RuntimeError("middleware leaked secret SQL")
        return self.get_response(request)
