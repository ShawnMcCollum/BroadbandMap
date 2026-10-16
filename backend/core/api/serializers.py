"""Public schema components for shared API errors."""

from typing import Any

from rest_framework import serializers


class FieldError(serializers.Serializer[Any]):
    pointer = serializers.CharField(allow_blank=True)
    code = serializers.CharField()
    message = serializers.CharField()


class Problem(serializers.Serializer[Any]):
    type = serializers.ChoiceField(choices=("about:blank",))
    title = serializers.CharField()
    status = serializers.IntegerField(min_value=400, max_value=599)
    detail = serializers.CharField()
    code = serializers.ChoiceField(
        choices=(
            "parse_error",
            "bad_request",
            "not_authenticated",
            "authentication_failed",
            "permission_denied",
            "not_found",
            "method_not_allowed",
            "not_acceptable",
            "unsupported_media_type",
            "throttled",
            "internal_error",
            "service_unavailable",
            "http_error",
        )
    )
    request_id = serializers.RegexField(r"^[0-9a-f]{32}$")


class ValidationProblem(serializers.Serializer[Any]):
    type = serializers.ChoiceField(choices=("about:blank",))
    title = serializers.CharField()
    status = serializers.IntegerField(min_value=400, max_value=599)
    detail = serializers.CharField()
    code = serializers.ChoiceField(choices=("validation_error",))
    request_id = serializers.RegexField(r"^[0-9a-f]{32}$")
    errors = FieldError(many=True, allow_empty=False)  # type: ignore[assignment]


__all__ = ["FieldError", "Problem", "ValidationProblem"]
