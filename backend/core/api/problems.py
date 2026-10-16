"""RFC 9457 Problem Details representations shared by API errors."""

from collections.abc import Mapping, Sequence
from http import HTTPStatus
from typing import Any

from django.http import HttpRequest, JsonResponse
from django.http.response import HttpResponseBase
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    ErrorDetail,
    MethodNotAllowed,
    NotAcceptable,
    NotAuthenticated,
    NotFound,
    ParseError,
    PermissionDenied,
    Throttled,
    UnsupportedMediaType,
    ValidationError,
)
from rest_framework.views import exception_handler as drf_exception_handler


class ServiceUnavailable(APIException):
    status_code = 503
    default_detail = "The service is temporarily unavailable."
    default_code = "service_unavailable"


ERROR_DETAILS: dict[str, tuple[int, str, str]] = {
    "validation_error": (400, "Bad Request", "Request validation failed."),
    "parse_error": (400, "Bad Request", "The request body could not be parsed."),
    "bad_request": (400, "Bad Request", "The request is invalid."),
    "not_authenticated": (403, "Forbidden", "Authentication is required."),
    "authentication_failed": (403, "Forbidden", "Authentication failed."),
    "permission_denied": (403, "Forbidden", "You do not have permission to perform this action."),
    "not_found": (404, "Not Found", "The requested resource was not found."),
    "method_not_allowed": (405, "Method Not Allowed", "This method is not allowed."),
    "not_acceptable": (406, "Not Acceptable", "The requested representation is not available."),
    "unsupported_media_type": (
        415,
        "Unsupported Media Type",
        "The request media type is not supported.",
    ),
    "throttled": (429, "Too Many Requests", "Request limit exceeded."),
    "internal_error": (500, "Internal Server Error", "An unexpected error occurred."),
    "service_unavailable": (503, "Service Unavailable", "The service is temporarily unavailable."),
}


def pointer_segment(value: object) -> str:
    return str(value).replace("~", "~0").replace("/", "~1")


def flatten_errors(value: Any, path: tuple[object, ...] = ()) -> list[dict[str, str]]:
    if isinstance(value, ErrorDetail):
        pointer = "/" + "/".join(pointer_segment(part) for part in path) if path else ""
        return [{"pointer": pointer, "code": str(value.code), "message": str(value)}]
    if isinstance(value, Mapping):
        results: list[dict[str, str]] = []
        for key, child in value.items():
            results.extend(flatten_errors(child, (*path, key)))
        return results
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        if value and all(isinstance(child, ErrorDetail) for child in value):
            messages: list[dict[str, str]] = []
            pointer = "/" + "/".join(pointer_segment(part) for part in path) if path else ""
            for child in value:
                messages.append(
                    {"pointer": pointer, "code": str(child.code), "message": str(child)}
                )
            return messages
        items: list[dict[str, str]] = []
        for index, child in enumerate(value):
            items.extend(flatten_errors(child, (*path, index)))
        return items
    return []


def request_id(request: HttpRequest) -> str:
    identifier = getattr(request, "api_request_id", None)
    return identifier if isinstance(identifier, str) else "0" * 32


def problem_payload(
    status: int, code: str, request: HttpRequest, *, errors: Any = None
) -> dict[str, Any]:
    status = status if 400 <= status <= 599 else 500
    if code not in ERROR_DETAILS:
        code = "http_error" if status < 500 else "internal_error"
    _, default_title, detail = ERROR_DETAILS.get(
        code, (status, "HTTP Error", "The request could not be completed.")
    )
    try:
        title = HTTPStatus(status).phrase
    except ValueError:
        title = default_title if code != "http_error" else "HTTP Error"
    payload: dict[str, Any] = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "detail": detail,
        "code": code,
        "request_id": request_id(request),
    }
    if errors is not None:
        payload["errors"] = flatten_errors(errors)
    return payload


def problem_response(
    status: int,
    code: str,
    request: HttpRequest,
    *,
    errors: Any = None,
    headers: HttpResponseBase | None = None,
) -> JsonResponse:
    payload = problem_payload(status, code, request, errors=errors)
    response = JsonResponse(
        payload, status=payload["status"], content_type="application/problem+json"
    )
    if headers:
        for name, value in headers.items():
            if name.lower() != "content-type":
                response[name] = value
    return response


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> JsonResponse | None:
    standard = drf_exception_handler(exc, context)
    if standard is None:
        return None
    request = context["request"]._request
    if isinstance(exc, ValidationError):
        return problem_response(
            400, "validation_error", request, errors=standard.data, headers=standard
        )
    codes: tuple[tuple[type[Exception], str], ...] = (
        (ParseError, "parse_error"),
        (NotAuthenticated, "not_authenticated"),
        (AuthenticationFailed, "authentication_failed"),
        (PermissionDenied, "permission_denied"),
        (NotFound, "not_found"),
        (MethodNotAllowed, "method_not_allowed"),
        (NotAcceptable, "not_acceptable"),
        (UnsupportedMediaType, "unsupported_media_type"),
        (Throttled, "throttled"),
        (ServiceUnavailable, "service_unavailable"),
    )
    for exception_type, code in codes:
        if isinstance(exc, exception_type):
            return problem_response(standard.status_code, code, request, headers=standard)
    fallback_code = {403: "permission_denied", 404: "not_found", 400: "bad_request"}.get(
        standard.status_code, "http_error"
    )
    return problem_response(standard.status_code, fallback_code, request, headers=standard)
