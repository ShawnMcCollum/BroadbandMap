"""Strict configuration and inert query request/response contracts."""

import re
from collections.abc import Mapping
from typing import Any, cast

from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail

from core.api.validation import StrictQuerySerializer


class EmptyQuery(StrictQuerySerializer):
    """Reject every query parameter on these fixed resources."""


class ConfigurationPatch(serializers.Serializer[Any]):
    enabled = serializers.BooleanField(required=False)
    provider = serializers.CharField(
        required=False, allow_blank=True, trim_whitespace=True, max_length=64
    )
    model_name = serializers.CharField(
        required=False, allow_blank=True, trim_whitespace=True, max_length=200
    )
    timeout_seconds = serializers.IntegerField(required=False, min_value=1, max_value=120)
    max_output_tokens = serializers.IntegerField(required=False, min_value=1, max_value=8192)
    api_key = serializers.CharField(
        required=False,
        write_only=True,
        trim_whitespace=True,
        min_length=1,
        max_length=4096,
        help_text="Replacement credential. Omit to preserve the saved key; never returned.",
    )
    clear_api_key = serializers.BooleanField(required=False)

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        if not isinstance(data, Mapping):
            raise serializers.ValidationError(
                {"non_field_errors": ["Expected a JSON object."]}, code="invalid"
            )
        if not data:
            raise serializers.ValidationError(
                {"non_field_errors": ["Supply at least one setting."]}, code="empty"
            )
        errors: dict[str, list[ErrorDetail]] = {}
        for key in sorted(set(data) - set(self.fields)):
            errors[str(key)] = [ErrorDetail("Unknown field.", code="unknown_field")]
        for name in ("enabled", "clear_api_key"):
            if name in data and type(data[name]) is not bool:
                errors[name] = [ErrorDetail("Expected a JSON boolean.", code="invalid")]
        for name in ("timeout_seconds", "max_output_tokens"):
            if name in data and type(data[name]) is not int:
                errors[name] = [ErrorDetail("Expected a JSON integer.", code="invalid")]
        for name in ("provider", "model_name", "api_key"):
            if name in data and not isinstance(data[name], str):
                errors[name] = [ErrorDetail("Expected a string.", code="invalid")]
        if isinstance(data.get("api_key"), str):
            key = data["api_key"].strip()
            if not key or len(key) > 4096:
                errors["api_key"] = [ErrorDetail("Enter 1 to 4096 characters.", code="invalid")]
        if errors:
            raise serializers.ValidationError(errors)
        result = cast(dict[str, Any], super().to_internal_value(data))
        if result.get("provider") and not re.fullmatch(
            r"[a-z][a-z0-9_.-]{0,63}", result["provider"]
        ):
            raise serializers.ValidationError(
                {"provider": [ErrorDetail("Use a lowercase provider identifier.", code="invalid")]}
            )
        if result.get("clear_api_key") and ("api_key" in result or result.get("enabled") is True):
            raise serializers.ValidationError(
                {
                    "clear_api_key": [
                        ErrorDetail(
                            "Cannot combine clearing with a key or enabling.", code="invalid"
                        )
                    ]
                }
            )
        return result


class QueryRequest(serializers.Serializer[Any]):
    question = serializers.CharField(min_length=1, max_length=2000, trim_whitespace=True)

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        if not isinstance(data, Mapping):
            raise serializers.ValidationError(
                {"non_field_errors": ["Expected a JSON object."]}, code="invalid"
            )
        if set(data) != {"question"}:
            errors = {
                str(key): [ErrorDetail("Unknown field.", code="unknown_field")]
                for key in sorted(set(data) - {"question"})
            }
            if not errors:
                errors = {"question": [ErrorDetail("This field is required.", code="required")]}
            raise serializers.ValidationError(errors)
        if not isinstance(data.get("question"), str):
            raise serializers.ValidationError(
                {"question": [ErrorDetail("Expected a string.", code="invalid")]}
            )
        return cast(dict[str, Any], super().to_internal_value(data))


class QueryResponse(serializers.Serializer[Any]):
    question = serializers.CharField()
    answer = serializers.CharField()
    is_stub = serializers.BooleanField()


class StatusResponse(serializers.Serializer[Any]):
    enabled = serializers.BooleanField()
    is_stub = serializers.BooleanField()
    message = serializers.CharField()


class ConfigurationResponse(serializers.Serializer[Any]):
    enabled = serializers.BooleanField()
    provider = serializers.CharField(allow_blank=True)
    model_name = serializers.CharField(allow_blank=True)
    timeout_seconds = serializers.IntegerField()
    max_output_tokens = serializers.IntegerField()
    key_configured = serializers.BooleanField()
    key_available = serializers.BooleanField()
    is_stub = serializers.BooleanField()
    provider_validated = serializers.BooleanField()
    updated_at = serializers.DateTimeField()
