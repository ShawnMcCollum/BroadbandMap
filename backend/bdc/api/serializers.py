"""Explicit release representations and shared date-pair input."""

import re
from datetime import date
from typing import Any

from rest_framework import serializers

from core.api.pagination import PageEnvelope, PageQuery


class ISODateField(serializers.DateField):
    """strptime also accepts unpadded dates; the public input contract does not."""

    def to_internal_value(self, value: Any) -> date:
        if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise serializers.ValidationError("Use YYYY-MM-DD.", code="invalid")
        return super().to_internal_value(value)


class ReleaseQuery(PageQuery):
    as_of = ISODateField(
        required=False,
        input_formats=["%Y-%m-%d"],
        help_text="Data period in YYYY-MM-DD form. Supply both dates or neither; "
        "omission selects latest.",
    )
    processed_on = ISODateField(
        required=False,
        input_formats=["%Y-%m-%d"],
        help_text="FCC processing date in YYYY-MM-DD form; requires as_of.",
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if ("as_of" in attrs) != ("processed_on" in attrs):
            raise serializers.ValidationError("Supply as_of and processed_on together.")
        return attrs


class StateSummary(serializers.Serializer[Any]):
    code = serializers.CharField()
    name = serializers.CharField()
    abbreviation = serializers.CharField()


class ReleaseSummary(serializers.Serializer[Any]):
    filing_period = serializers.CharField()
    as_of = serializers.DateField()
    processed_on = serializers.DateField()
    states = StateSummary(many=True)


class ReleasePage(PageEnvelope):
    results = ReleaseSummary(many=True)
