"""Bounded page-number reads with explicit, reproducible query links."""

import re
from typing import Any
from urllib.parse import urlencode

from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.request import Request

from core.api.validation import StrictQuerySerializer


class IntegerQueryField(serializers.IntegerField):
    """Check integer notation before DRF coerces whole-valued decimal strings."""

    def to_internal_value(self, value: Any) -> int:
        if isinstance(value, str):
            if not re.fullmatch(r"[+-]?[0-9]+", value):
                self.fail("invalid")
        elif type(value) is not int:
            self.fail("invalid")
        return super().to_internal_value(value)


class PageQuery(StrictQuerySerializer):
    page = IntegerQueryField(min_value=1, default=1)
    page_size = IntegerQueryField(min_value=1, max_value=100, default=100)


def page_bounds(count: int, params: dict[str, Any]) -> tuple[int, int]:
    start = (params["page"] - 1) * params["page_size"]
    if start >= count and params["page"] != 1:
        raise NotFound()
    return start, start + params["page_size"]


def page_metadata(request: Request, count: int, params: dict[str, Any]) -> dict[str, Any]:
    start, end = page_bounds(count, params)

    def link(page: int) -> str:
        query = {key: value for key, value in params.items() if value is not None}
        query["page"] = page
        return request.build_absolute_uri(request.path + "?" + urlencode(query))

    return {
        "count": count,
        "next": link(params["page"] + 1) if end < count else None,
        "previous": link(params["page"] - 1) if start else None,
    }


class PageEnvelope(serializers.Serializer[Any]):
    count = serializers.IntegerField(min_value=0)
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
