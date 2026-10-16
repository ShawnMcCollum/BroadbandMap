"""County GeoJSON contract, separate from availability observations."""

from typing import Any

from rest_framework import serializers

from core.api.pagination import PageEnvelope, PageQuery


class CountyQuery(PageQuery):
    state = serializers.RegexField(r"^[0-9]{2}$", min_length=2, max_length=2, trim_whitespace=False)


class CountyProperties(serializers.Serializer[Any]):
    code = serializers.CharField()
    name = serializers.CharField()


class MultiPolygonGeometry(serializers.Serializer[Any]):
    type = serializers.ChoiceField(choices=["MultiPolygon"])
    coordinates = serializers.ListField(
        child=serializers.ListField(
            child=serializers.ListField(
                child=serializers.ListField(
                    child=serializers.FloatField(), min_length=2, max_length=2
                ),
                min_length=4,
            ),
            min_length=1,
        ),
        min_length=1,
    )


class CountyFeature(serializers.Serializer[Any]):
    type = serializers.ChoiceField(choices=["Feature"])
    id = serializers.CharField()
    properties = CountyProperties()
    geometry = MultiPolygonGeometry()


class CountyCollection(PageEnvelope):
    type = serializers.ChoiceField(choices=["FeatureCollection"])
    features = CountyFeature(many=True)
    state = serializers.CharField()
    boundary_vintage = serializers.IntegerField()
