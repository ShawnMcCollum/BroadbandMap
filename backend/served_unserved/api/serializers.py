"""Summary selection and explicit count envelopes."""

import re
from typing import Any

from rest_framework import serializers

from bdc.api.serializers import ReleaseQuery, ReleaseSummary
from core.api.pagination import PageEnvelope
from served_unserved.models import AREA_KEYS, RollupLevel


class RollupQuery(ReleaseQuery):
    level = serializers.ChoiceField(choices=RollupLevel.choices)
    code = serializers.CharField(
        required=False,
        max_length=15,
        trim_whitespace=False,
        help_text="Optional GEOID or lowercase H3 cell matching the selected level's "
        "AREA_KEYS form.",
    )
    state = serializers.RegexField(
        r"^[0-9]{2}$",
        required=False,
        min_length=2,
        max_length=2,
        trim_whitespace=False,
        help_text="Optional state FIPS code. For H3, limits contributions rather than "
        "cell containment.",
    )
    flag = serializers.ChoiceField(choices=["any", "wired", "terrestrial"], default="wired")
    page_size = serializers.IntegerField(min_value=1, max_value=1000, default=100)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)
        code = attrs.get("code")
        if code is not None:
            key = AREA_KEYS[attrs["level"]]
            if not re.fullmatch(key.pattern, code):
                raise serializers.ValidationError({"code": f"Expected {key.form}."})
            if (
                attrs["level"] != RollupLevel.H3_RES8
                and "state" in attrs
                and not code.startswith(attrs["state"])
            ):
                raise serializers.ValidationError({"state": "State must match the census code."})
        return attrs


class SummarySelection(serializers.Serializer[Any]):
    level = serializers.ChoiceField(choices=RollupLevel.choices)
    code = serializers.CharField(allow_null=True)
    state = serializers.CharField(allow_null=True)
    flag = serializers.ChoiceField(choices=["any", "wired", "terrestrial"])


class SpeedThreshold(serializers.Serializer[Any]):
    download_mbps = serializers.IntegerField()
    upload_mbps = serializers.IntegerField()


class RollupResult(serializers.Serializer[Any]):
    code = serializers.CharField()
    locations = serializers.IntegerField(min_value=1)
    any_100_20 = serializers.IntegerField(min_value=0)
    wired_100_20 = serializers.IntegerField(min_value=0)
    terrestrial_100_20 = serializers.IntegerField(min_value=0)
    served = serializers.IntegerField(min_value=0)
    not_served = serializers.IntegerField(min_value=0)


class RollupPage(PageEnvelope):
    results = RollupResult(many=True)
    release = ReleaseSummary()
    selection = SummarySelection()
    threshold = SpeedThreshold()
    boundary_vintage = serializers.IntegerField(allow_null=True)
    summary_coverage = serializers.ChoiceField(
        choices=[
            "stored_rollups_only",
            "observed",
            "no_observations",
            "outside_release_coverage",
        ],
        help_text="Collections enumerate stored rows only. Use code to distinguish "
        "no observations, outside-release states, or unavailable rollups (503). "
        "Missing rows are never implied zeros.",
    )
