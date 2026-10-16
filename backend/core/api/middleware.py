"""Translate errors at the Django API boundary, including non-DRF failures."""

import json
import logging
import uuid
from collections.abc import Callable

from django.core.exceptions import BadRequest, PermissionDenied, SuspiciousOperation
from django.http import Http404, HttpRequest, HttpResponse

from core.api.problems import problem_payload

logger = logging.getLogger("core.api")


class ApiProblemBoundaryMiddleware:
    """Give API failures a safe Problem Details body and correlation identifier."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if not self._is_api_request(request):
            return self.get_response(request)
        identifier = uuid.uuid4().hex
        setattr(request, "api_request_id", identifier)  # noqa: B010 - Django request extension point.
        response = self.get_response(request)
        response["X-Request-ID"] = identifier
        if response.status_code >= 400:
            if response.get("Content-Type", "").split(";", 1)[0] != "application/problem+json":
                code = self._code_for_status(response.status_code)
                self._replace_response(request, response, code)
            if response.status_code >= 500 and not getattr(request, "api_failure_logged", False):
                logger.error(
                    "Unhandled API failure request_id=%s status=%s",
                    identifier,
                    response.status_code,
                )
                setattr(request, "api_failure_logged", True)  # noqa: B010 - request-local log marker.
        return response

    def process_exception(self, request: HttpRequest, exception: Exception) -> HttpResponse | None:
        if not self._is_api_request(request) or request.path_info == "/api/health/":
            return None
        if isinstance(exception, Http404):
            status, code = 404, "not_found"
        elif isinstance(exception, PermissionDenied):
            status, code = 403, "permission_denied"
        elif isinstance(exception, (BadRequest, SuspiciousOperation)):
            status, code = 400, "bad_request"
        else:
            status, code = 500, "internal_error"
            logger.exception(
                "Unhandled API exception request_id=%s",
                getattr(request, "api_request_id", ""),
            )
            setattr(request, "api_failure_logged", True)  # noqa: B010 - request-local log marker.
        response = HttpResponse(status=status)
        self._replace_response(request, response, code)
        response["X-Request-ID"] = getattr(request, "api_request_id", uuid.uuid4().hex)
        return response

    @staticmethod
    def _is_api_request(request: HttpRequest) -> bool:
        path = request.path_info
        return (path == "/api" or path.startswith("/api/")) and path != "/api/health/"

    @staticmethod
    def _code_for_status(status: int) -> str:
        return {
            400: "bad_request",
            403: "permission_denied",
            404: "not_found",
            405: "method_not_allowed",
            406: "not_acceptable",
            415: "unsupported_media_type",
            429: "throttled",
            503: "service_unavailable",
        }.get(status, "internal_error" if status >= 500 else "http_error")

    @staticmethod
    def _replace_response(request: HttpRequest, response: HttpResponse, code: str) -> None:
        headers = {key: value for key, value in response.items()}
        payload = problem_payload(response.status_code, code, request)
        response.content = json.dumps(payload, separators=(",", ":"))
        response["Content-Type"] = "application/problem+json"
        for header in ("Content-Length", "Content-Encoding", "ETag"):
            if header in response:
                del response[header]
        for name, value in headers.items():
            if name.lower() not in {"content-type", "content-length", "content-encoding", "etag"}:
                response[name] = value
