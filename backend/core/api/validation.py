"""Strict defaults for singleton query parameter validation."""

from collections.abc import Mapping
from typing import Any, cast

from django.http import QueryDict
from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail


class StrictQuerySerializer(serializers.Serializer[Any]):
    """Reject unknown names and repeated singleton parameters before field validation."""

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        if not isinstance(data, Mapping):
            return cast(dict[str, Any], super().to_internal_value(data))

        declared = {name for name, field in self.fields.items() if not field.read_only}
        errors: dict[str, list[ErrorDetail]] = {}
        for name in sorted(set(data.keys()) - declared):
            errors.setdefault(str(name), []).append(
                ErrorDetail("Unknown query parameter.", code="unknown_parameter")
            )

        if isinstance(data, QueryDict):
            for name in sorted(declared & set(data.keys())):
                if len(data.getlist(name)) > 1:
                    errors.setdefault(name, []).append(
                        ErrorDetail(
                            "This query parameter must occur only once.", code="repeated_parameter"
                        )
                    )
        if errors:
            raise serializers.ValidationError({name: errors[name] for name in sorted(errors)})
        if isinstance(data, QueryDict):
            data = {name: data.get(name) for name in data}
        return cast(dict[str, Any], super().to_internal_value(data))
